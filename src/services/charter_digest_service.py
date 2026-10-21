"""G8: the weekly charter digest and the immediate charter notices. Reads and notifies; never writes a value.
G8：章程週報與即時章程通知。只讀與通知，從不寫任何參數值。

The digest replaces per-change approval (ADR-003 (2)): one Markdown report a week, plus a notice only for apply,
rollback, freeze, resume and degrade. Missing data is printed as 'unknown' with its reason, never defaulted.
Clock contract: every function takes ``now``; the only clock read is in src/workflow/charter_tasks.py.
週報取代逐筆核准；即時通知只限 apply／rollback／freeze／resume／degrade。缺資料印 unknown 並附原因。
所有函式收 now；時鐘只在 charter_tasks 讀取。
"""
import asyncio
import json
import logging
from pathlib import Path
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import sessionmaker

from src.config.mission import load_mission
from src.config.parameter_registry import Parameter, load_registry
from src.data.models import (CharterEvent, CharterState, ParameterChange, ParameterTrial, RotationPairObservation,
                             StrategyTrial, ThresholdBandObservation)
from src.services import enablement_checker
from src.services.marginal_band_evaluator import evaluate_key
from src.services.mission_watchdog_service import MissionWatchdogService
from src.services.notification_service import NotificationService
from src.services.param_policy import evidence_clock_start, get_param, seed_value
from src.services.parameter_engine import add_event, grid_neighbours, quarter_start
from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"
DIGEST_KIND = "digest"
REALTIME_KINDS = ("apply", "rollback", "freeze", "resume", "degrade", "enable", "drill")
RATE_WINDOW_DAYS = 30            # observed rate = decisions observed in this window / its length / 近 30 日觀察率
LOOSEN_QUARTER_QUOTA = 1         # same rule as parameter_engine.budget_gate quarter_quota_ok / 與 budget_gate 同規則
LAST_LOOSENINGS = 4              # the engine's degrade window / 引擎降級視窗
EVENT_WINDOW_DAYS = 7
DIGEST_TITLE = "📋 章程週報 / Charter weekly digest"
_TITLES = {
    "apply": "⚙️ 章程引擎套用參數變更 / Charter engine applied a change",
    "rollback": "↩️ 章程引擎回滾放寬 / Charter engine rolled back a loosening",
    "freeze": "🧊 章程引擎凍結 / Charter engine frozen",
    "resume": "▶️ 章程引擎恢復 / Charter engine resumed",
    "degrade": "🛑 章程引擎降級為僅收緊 / Charter engine degraded to tighten-only",
    "enable": "✅ 章程引擎自動啟用（dry_run → apply） / Charter engine enabled (dry_run to apply)",
    "drill": "🧪 章程停機演練結果 / Charter halt drill result",
}

Notify = Callable[[str, str], None]


def make_notifier(user_id: str) -> Notify:
    """Same send path as src/infrastructure/tasks.py run_mission_watchdog. Raises on failure; callers log it."""
    def notify(title: str, content: str) -> None:
        noti = NotificationService.create_with_settings(
            settings_service=SettingsService(user_id=user_id), user_id=user_id)
        asyncio.run(noti.notify_all(title, content, user_id=user_id, category="report"))
    return notify


def _fmt(value: Any, reason: Optional[str] = None) -> str:
    if value is None:
        return f"{UNKNOWN}（{reason}）" if reason else UNKNOWN
    return str(value)


def _challenger(p: Parameter, cur: Any) -> Tuple[Optional[float], Optional[str]]:
    """The loosening challenger the engine would test (the tightening one at the edge). / 引擎會測的挑戰值。"""
    try:
        loosen_c, tighten_c = grid_neighbours(p, cur)
    except ValueError as e:
        return None, f"off_grid: {e}"
    c = loosen_c if loosen_c is not None else tighten_c
    return c, (None if c is not None else "at_grid_edge")


def _latest_verdict(engine: Any, user_id: str, key: str) -> Dict[str, Any]:
    with sessionmaker(bind=engine)() as s:
        ev = (s.query(CharterEvent).filter(CharterEvent.user_id == user_id, CharterEvent.kind == "verdict",
                                           CharterEvent.key == key)
              .order_by(CharterEvent.id.desc()).first())
        if ev is None:
            return {"latest_verdict": UNKNOWN, "reasons": [], "verdict_reason": "no_verdict_row"}
        payload = ev.payload_json or {}
        return {"latest_verdict": payload.get("verdict", UNKNOWN), "reasons": list(payload.get("reasons", [])),
                "verdict_reason": None}


def _param_row(engine: Any, user_id: str, p: Parameter, now: datetime) -> Dict[str, Any]:
    got = get_param(p.key, engine=engine)
    row: Dict[str, Any] = {"key": p.key, "cls": p.cls, "policy": p.policy, "current": got.value,
                           "source": got.source, "fallback": got.fallback_reason, "seed": seed_value(p.key),
                           "untestable_reason": p.untestable_reason, "n_5d": None, "n_63d": None, "min_n": None,
                           "days_to_min_n": UNKNOWN, "days_reason": None, "unavailable_reason": None}
    row.update(_latest_verdict(engine, user_id, p.key))
    if p.policy != "adaptive" or got.value is None:
        row["days_reason"] = "not_adaptive" if p.policy != "adaptive" else got.fallback_reason or "no_value"
        return row
    cur = got.value
    row["min_n"] = p.evidence.min_n
    challenger, why = _challenger(p, cur)
    if challenger is None:
        row["days_reason"] = why
        return row
    since = evidence_clock_start(p.key, engine)
    series = evaluate_key(engine, user_id, p.key, cur, challenger, since)
    s5, s63 = series.get((5, 1.0)), series.get((63, 1.0))
    if s63 is None or s63.unavailable_reason:
        row["unavailable_reason"] = s63.unavailable_reason if s63 is not None else "no_series"
        row["days_reason"] = row["unavailable_reason"]
        return row
    row["n_5d"] = s5.n if s5 is not None and not s5.unavailable_reason else None
    row["n_63d"] = s63.n
    if s63.n >= p.evidence.min_n:
        row["days_to_min_n"], row["days_reason"] = 0, "reached"
        return row
    recent = evaluate_key(engine, user_id, p.key, cur, challenger, now - timedelta(days=RATE_WINDOW_DAYS))[(63, 1.0)]
    rate = recent.n / RATE_WINDOW_DAYS
    if rate <= 0:
        row["days_reason"] = "no_settlement_rate"
        return row
    row["days_to_min_n"] = math.ceil((p.evidence.min_n - s63.n) / rate)
    return row


def _state(engine: Any) -> Dict[str, Any]:
    with sessionmaker(bind=engine)() as s:
        st = s.query(CharterState).filter(CharterState.id == 1).first()
        if st is None:
            return {"missing": True}
        return {"mode": st.mode, "since": st.since.date().isoformat() if st.since else UNKNOWN,
                "reason": st.reason, "human_stop": bool(st.human_stop)}


def _quota(engine: Any, now: datetime) -> Dict[str, Any]:
    q0 = quarter_start(now)
    cap = load_mission().budgets.max_hypothesis_trials_per_quarter
    with sessionmaker(bind=engine)() as s:
        trials = (s.query(ParameterTrial).filter(ParameterTrial.registered_at >= q0).count()
                  + s.query(StrategyTrial).filter(StrategyTrial.first_eval_at >= q0).count())
        loosen = (s.query(ParameterChange).filter(ParameterChange.direction == "loosen",
                                                  ParameterChange.applied_at.isnot(None),
                                                  ParameterChange.applied_at >= q0).count())
    return {"trials_used": trials, "trials_cap": cap, "loosen_used": loosen, "loosen_quota": LOOSEN_QUARTER_QUOTA}


def _engine_stats(engine: Any) -> Dict[str, Any]:
    with sessionmaker(bind=engine)() as s:
        base = s.query(ParameterChange).filter(ParameterChange.direction == "loosen",
                                               ParameterChange.applied_at.isnot(None))
        last = base.order_by(ParameterChange.applied_at.desc(), ParameterChange.id.desc()).limit(LAST_LOOSENINGS).all()
        return {"applied_loosenings": base.count(), "last_count": len(last),
                "rollbacks_in_last": sum(r.rolled_back_at is not None for r in last)}


def _monthly_signals(engine: Any, now: datetime) -> Dict[str, Any]:
    month_start = date(now.year, now.month, 1)
    with sessionmaker(bind=engine)() as s:
        th = (s.query(ThresholdBandObservation).filter(ThresholdBandObservation.in_band.is_(True),
                                                       ThresholdBandObservation.obs_date >= month_start).count())
        rot = s.query(RotationPairObservation).filter(RotationPairObservation.obs_date >= month_start).count()
    return {"month": month_start.strftime("%Y-%m"), "threshold_band": th, "rotation_pair": rot}


def _recent_events(engine: Any, now: datetime) -> List[Dict[str, Any]]:
    with sessionmaker(bind=engine)() as s:
        rows = (s.query(CharterEvent).filter(CharterEvent.kind.in_(REALTIME_KINDS),
                                             CharterEvent.created_at >= now - timedelta(days=EVENT_WINDOW_DAYS))
                .order_by(CharterEvent.created_at, CharterEvent.id).all())
        return [{"kind": r.kind, "key": r.key, "at": r.created_at.isoformat() if r.created_at else UNKNOWN}
                for r in rows]



BACKUP_STATUS_PATH = Path(__file__).resolve().parents[2] / "config" / ".backup_status.json"
BACKUP_STALE_DAYS = 2
CRITERION_LABELS = {"adr": "ADR-003 已合併", "dry_run_90d": "dry_run 滿 90 天", "zero_effect_sim": "零效應誤放寬率 ≤ α",
                    "drill": "停機演練通過", "8_digests": "連續 8 週週報", "no_freeze_30d": "近 30 天無 K 違規凍結"}


def _backup_status(now: datetime, path: Optional[Path] = None) -> Dict[str, Any]:
    """Last nightly backup as recorded by scripts/backup_db.sh in config/.backup_status.json (the worker mounts ./config
    but not ./backups). Missing or unreadable is reported as such, never as fine. / 讀不到就如實回報，不當成正常。"""
    p = path or BACKUP_STATUS_PATH
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(str(st["at"]).replace("Z", "+00:00"))
        age_days = (now - at).total_seconds() / 86400.0
        return {"ok": bool(st["ok"]), "file": st.get("file") or "", "mb": round(float(st.get("bytes", 0)) / 1e6, 1),
                "at": str(st["at"]), "age_days": round(age_days, 1), "reason": st.get("reason") or "",
                "stale": age_days > BACKUP_STALE_DAYS}
    except Exception as e:
        logger.warning("charter digest: backup status unreadable (%s): %s", p, e)
        return {"error": f"{type(e).__name__}: {e}"}


def _readable_missing(m: Dict[str, Any]) -> str:
    """One missing enablement criterion in plain Traditional Chinese. / 單一未滿足啟用條件的中文說明。"""
    name = CRITERION_LABELS.get(m["criterion"], m["criterion"])
    v = m.get("value") or {}
    status = "無法量測" if m.get("status") == "not_measurable" else "未滿足"
    if m["criterion"] == "dry_run_90d":
        detail = f"已 {v.get('days')} 天／需 {v.get('required_days')} 天" if v.get("days") is not None else "尚無判決紀錄"
        if v.get("keys_without_verdict"):
            detail += f"；尚無判決的參數：{', '.join(v['keys_without_verdict'])}"
    elif m["criterion"] == "8_digests":
        detail = f"已連續 {v.get('consecutive_weeks')} 週／需 {v.get('required')} 週"
    elif m["criterion"] == "drill":
        detail = f"演練 {v.get('drills')} 次、通過 {v.get('passed')} 次（需操作者呼叫 POST /charter/drill）"
    elif m["criterion"] == "no_freeze_30d":
        detail = f"近 {v.get('lookback_days')} 天內有 {v.get('freezes')} 次凍結"
    elif m["criterion"] == "zero_effect_sim":
        detail = f"誤放寬率 {v.get('rate')}／α {v.get('alpha')}"
    elif m["criterion"] == "adr":
        detail = "mission.yaml 找不到 ADR-003"
    else:
        detail = str(v)
    return f"- {status}：{name}（{detail}）"


def _enablement(engine: Any, now: datetime) -> Dict[str, Any]:
    """ADR-003 (6) status: the criteria still missing before dry_run switches to apply. A failure is kept as an error."""
    try:
        ok, missing = enablement_checker.check(engine, now)
        return {"ok": ok, "missing": missing}
    except Exception as e:
        logger.warning("charter digest: enablement check unavailable: %s", e)
        return {"error": str(e)}


def build_digest(engine: Any, user_id: str, now: datetime, watchdog: Optional[Callable[[date], Dict]] = None
                 ) -> Dict[str, Any]:
    """Structured digest. ``watchdog(today)`` defaults to MissionWatchdogService.evaluate; a failure is kept as
    {'error': ...} and printed, never hidden. / 結構化週報；看門狗失敗保留為 error 並印出。"""
    today = now.date()
    if watchdog is None:
        def watchdog(d: date) -> Dict[str, Any]:
            return MissionWatchdogService(user_id=user_id, engine=engine).evaluate(today=d)
    try:
        res = watchdog(today)
        k_status = {"overall": res["overall"], "criteria": res["criteria"]}
    except Exception as e:
        logger.warning("charter digest: watchdog unavailable: %s", e)
        k_status = {"error": str(e)}
    return {
        "as_of": now.isoformat(),
        "monthly_signals": _monthly_signals(engine, now),
        "charter_state": _state(engine),
        "params": [_param_row(engine, user_id, p, now) for p in load_registry().parameters],
        "quota": _quota(engine, now),
        "watchdog": k_status,
        "engine": _engine_stats(engine),
        "enablement": _enablement(engine, now),
        "backup": _backup_status(now),
        "events_7d": _recent_events(engine, now),
    }


def render_digest(d: Dict[str, Any]) -> str:
    """Traditional Chinese Markdown. Pure. First line is the monthly in-band count. / 繁中 Markdown，首行為本月在帶訊號。"""
    ms = d["monthly_signals"]
    lines = [f"本月在帶訊號：門檻 {ms['threshold_band']} 筆、rotation {ms['rotation_pair']} 筆（{ms['month']}）",
             f"產生時間：{d['as_of']}", "", "## 章程狀態"]
    st = d["charter_state"]
    if st.get("missing"):
        lines.append(f"- charter_state：{UNKNOWN}（無狀態列；引擎只記錄、不寫值）")
    else:
        lines.append(f"- 模式：{st['mode']}（自 {st['since']}；原因 {st['reason']}）；人工停止：{st['human_stop']}")
    lines += ["", "## 參數（adaptive）",
              "| 參數 | 類別 | 目前值 | seed | n 5d | n 63d | min_n | 預估達 min_n 天數 | 最近判決 | 理由 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    fixed = []
    for r in d["params"]:
        if r["policy"] != "adaptive":
            fixed.append(f"- {r['key']}（{r['cls']} 類，policy {r['policy']}）：不可試驗：{r['untestable_reason'] or UNKNOWN}")
            continue
        days = r["days_to_min_n"] if r["days_to_min_n"] == UNKNOWN else str(r["days_to_min_n"])
        if r["days_to_min_n"] == UNKNOWN and r["days_reason"]:
            days = f"{UNKNOWN}（{r['days_reason']}）"
        reasons = ", ".join(r["reasons"]) or (r["verdict_reason"] or "")
        lines.append(f"| {r['key']} | {r['cls']} | {_fmt(r['current'], r['fallback'])} | {_fmt(r['seed'])} | "
                     f"{_fmt(r['n_5d'], r['unavailable_reason'])} | {_fmt(r['n_63d'], r['unavailable_reason'])} | "
                     f"{_fmt(r['min_n'])} | {days} | {r['latest_verdict']} | {reasons} |")
    if fixed:
        lines += ["", "## 不可試驗參數"] + fixed
    q = d["quota"]
    lines += ["", "## 額度",
              f"- 本季試驗：{q['trials_used']} / {q['trials_cap']}",
              f"- 本季已套用放寬：{q['loosen_used']} / {q['loosen_quota']}"]
    wd = d["watchdog"]
    lines += ["", "## K 狀態（看門狗）"]
    if "error" in wd:
        lines.append(f"- 看門狗不可用：{wd['error']}")
    else:
        lines.append(f"- 總結：{wd['overall']}")
        for c in wd["criteria"]:
            lines.append(f"- {c['id']} {c['name']}：{c['status']}（值 {_fmt(c['value'])} / 門檻 {c['threshold']} "
                         f"{c['unit']}）{c['note']}".rstrip())
    e = d["engine"]
    lines += ["", "## 引擎",
              f"- 已套用放寬 {e['applied_loosenings']} 次；最近 {e['last_count']} 次中回滾 {e['rollbacks_in_last']} 次"]
    en = d["enablement"]
    lines += ["", "## 啟用條件（ADR-003 (6)）"]
    if "error" in en:
        lines.append(f"- 啟用檢查不可用：{en['error']}")
    elif en["ok"]:
        lines.append("- 六項條件皆成立（dry_run 時下次檢查會自動切到 apply）")
    else:
        lines += [_readable_missing(m) for m in en["missing"]]
    bk = d.get("backup")
    lines += ["", "## 夜間備份"]
    if bk is None or "error" in bk:
        lines.append(f"- {UNKNOWN}：找不到備份狀態檔（{(bk or {}).get('error', '未提供')}）；夜間備份可能沒有執行")
    elif not bk["ok"]:
        lines.append(f"- 失敗：{bk['reason']}（{bk['at']}）")
    else:
        lines.append(f"- 最近一次成功：{bk['file']}（{bk['mb']} MB，{bk['age_days']} 天前）" + ("；**已超過 2 天沒有新備份**" if bk["stale"] else ""))
    lines += ["", "## 近 7 日事件"]
    lines += [f"- {ev['at']} {ev['kind']} {ev['key'] or ''}".rstrip() for ev in d["events_7d"]] or ["- 無"]
    return "\n".join(lines) + "\n"


def _week_start(now: datetime) -> datetime:
    monday = now.date() - timedelta(days=now.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)


def write_weekly_digest(engine: Any, user_id: str, now: datetime, notify: Optional[Notify] = None,
                        watchdog: Optional[Callable[[date], Dict]] = None) -> Dict[str, Any]:
    """One digest row per ISO week. A notify failure is logged at WARNING and recorded in payload 'error'; the row
    is still written. / 每個 ISO 週一筆；通知失敗記 WARNING 並寫入 payload error，仍寫列。"""
    with sessionmaker(bind=engine)() as s:
        done = (s.query(CharterEvent).filter(CharterEvent.user_id == user_id, CharterEvent.kind == DIGEST_KIND,
                                             CharterEvent.created_at >= _week_start(now)).count())
    if done:
        return {"written": False, "reason": "already_written_this_week", "error": None}
    d = build_digest(engine, user_id, now, watchdog=watchdog)
    text = render_digest(d)
    error = None
    try:
        (notify or make_notifier(user_id))(DIGEST_TITLE, text)
    except Exception as e:
        error = str(e)
        logger.warning("charter weekly digest: notify failed: %s", e)
    payload: Dict[str, Any] = {"digest": d, "text": text}
    if error is not None:
        payload["error"] = error
    with sessionmaker(bind=engine)() as s:
        add_event(s, user_id, DIGEST_KIND, None, payload, now)
        s.commit()
    return {"written": True, "reason": None, "error": error}


def notify_event(engine: Any, user_id: str, kind: str, key: Optional[str], payload: Dict[str, Any], now: datetime,
                 notify: Optional[Notify] = None) -> None:
    """Write the charter_events row, then notify. Only the five realtime kinds qualify. / 寫事件列後通知；只接受五種。"""
    if kind not in REALTIME_KINDS:
        raise ValueError(f"not a realtime charter kind: {kind}")
    with sessionmaker(bind=engine)() as s:
        add_event(s, user_id, kind, key, payload, now)
        s.commit()
    body = "\n".join([f"key: {key}"] + [f"{k}: {v}" for k, v in payload.items()])
    try:
        (notify or make_notifier(user_id))(_TITLES[kind], body)
    except Exception as e:
        logger.warning("charter realtime notice %s failed: %s", kind, e)
