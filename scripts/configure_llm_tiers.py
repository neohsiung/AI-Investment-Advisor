#!/usr/bin/env python3
"""
Point the app's LLM tiers at the LiteLLM tier aliases. Idempotent, prints a diff.
把 app 的 LLM tier 指向 LiteLLM 的 tier alias；具冪等性並列出前後差異。

Run (scripts/ is not mounted into the containers, and the DB host only
resolves on the docker network, so pipe it in):
    docker exec -i advisor_prod_worker_1 python - < scripts/configure_llm_tiers.py
    docker exec -i advisor_prod_worker_1 python - --apply < scripts/configure_llm_tiers.py

Why / 為什麼
────────────
`llm_models.model_code` held raw vendor names like `google/gemini-3.6-flash`,
but the configured endpoint is a LiteLLM proxy that serves **tier aliases**
(`nano`, `fast`, `smart`, `advanced` and their `-fbN` variants) and nothing
else. Every call with a raw name came back:

    Invalid model name passed in model=google/gemini-3.6-flash

which exhausted the chain and made CompositorService fall back to
`_fallback_score()` — a deterministic hash of the ticker. Confidence scores
were noise. The DB was half-migrated already: `nano` and `advanced` used
aliases and worked; `fast` and `smart` still used raw names and did not.

Cost ordering lives in the LiteLLM config (free models first, paid as a
safety net); this script only makes the app address that config correctly.
The app-level fallbacks below duplicate LiteLLM's own router fallbacks on
purpose — a cheap second layer if the proxy's router itself misbehaves.

llm_models.model_code 原本存的是原始廠商名稱，但實際端點是只服務 tier alias 的
LiteLLM proxy，因此每次呼叫都回 "Invalid model name"，鏈路耗盡後 CompositorService
退回以 ticker 雜湊產生的假分數。成本排序由 LiteLLM 設定檔負責；本腳本只讓 app
正確地定址到那份設定。
"""
import argparse
import sys
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
except NameError:
    pass

PROVIDER_CODE = "openrouter"  # the LiteLLM proxy row in llm_providers

# alias -> (model id, display name). Mirrors litellm-config.yaml exactly.
ALIASES = {
    "nano":         ("m_tier_nano",         "Tier nano (LiteLLM routed)"),
    "nano-fb1":     ("m_tier_nano_fb1",     "Tier nano fallback 1"),
    "nano-fb2":     ("m_tier_nano_fb2",     "Tier nano fallback 2"),
    "nano-fb3":     ("m_tier_nano_fb3",     "Tier nano fallback 3"),
    "fast":         ("m_tier_fast",         "Tier fast (LiteLLM routed)"),
    "fast-fb1":     ("m_tier_fast_fb1",     "Tier fast fallback 1"),
    "fast-fb2":     ("m_tier_fast_fb2",     "Tier fast fallback 2"),
    "fast-fb3":     ("m_tier_fast_fb3",     "Tier fast fallback 3"),
    "smart":        ("m_tier_smart",        "Tier smart (LiteLLM routed)"),
    "smart-fb1":    ("m_tier_smart_fb1",    "Tier smart fallback 1"),
    "smart-fb2":    ("m_tier_smart_fb2",    "Tier smart fallback 2"),
    "smart-fb3":    ("m_tier_smart_fb3",    "Tier smart fallback 3"),
    "advanced":     ("m_tier_advanced",     "Tier advanced (LiteLLM routed)"),
    "advanced-fb1": ("m_tier_advanced_fb1", "Tier advanced fallback 1"),
    "advanced-fb2": ("m_tier_advanced_fb2", "Tier advanced fallback 2"),
    "advanced-fb3": ("m_tier_advanced_fb3", "Tier advanced fallback 3"),
}

TIERS = {
    "nano":     ("nano",     ["nano-fb1", "nano-fb2", "nano-fb3"]),
    "fast":     ("fast",     ["fast-fb1", "fast-fb2", "fast-fb3"]),
    "smart":    ("smart",    ["smart-fb1", "smart-fb2", "smart-fb3"]),
    "advanced": ("advanced", ["advanced-fb1", "advanced-fb2", "advanced-fb3"]),
}

# The free NIM models the config now leads with are reasoning models: measured
# 75s (smart / GLM-5.2) and 89s (advanced / GLM-5.2) at max_tokens=2048 on this
# host. build_config_chain defaults timeout_seconds to 120.0, which covers
# them, but pinning it per candidate keeps a future default change from
# silently timing the free models out and falling through to the paid ones.
# 免費的 NIM 首選皆為推理模型，實測 smart 75 秒、advanced 89 秒。預設 120 秒足夠，
# 但在此明確指定，避免日後預設值變動導致免費模型逾時、默默落到付費模型。
PER_CANDIDATE_CONFIG = {"timeout_seconds": 120.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--user-id", default=None)
    args = ap.parse_args()

    from sqlalchemy import text
    from src.data.database import get_db_engine
    import json
    import uuid

    engine = get_db_engine()
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN (use --apply to write)'}\n")

    with engine.begin() as conn:
        uid = args.user_id
        if not uid:
            row = conn.execute(text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).fetchone()
            if not row:
                print("no users", file=sys.stderr)
                return 1
            uid = str(row[0])
        print(f"user_id: {uid}")

        prov = conn.execute(
            text("SELECT id FROM llm_providers WHERE user_id=:u AND provider_code=:c"),
            {"u": uid, "c": PROVIDER_CODE},
        ).fetchone()
        if not prov:
            print(f"no provider {PROVIDER_CODE!r} for user", file=sys.stderr)
            return 1
        provider_id = str(prov[0])
        print(f"provider: {PROVIDER_CODE} ({provider_id})\n")

        # ── 1. Upsert one model row per LiteLLM alias ──
        print("models:")
        for alias, (mid, display) in ALIASES.items():
            existing = conn.execute(
                text("SELECT id FROM llm_models WHERE provider_id=:p AND model_code=:c"),
                {"p": provider_id, "c": alias},
            ).fetchone()
            if existing:
                print(f"  = {alias:14} already present as {existing[0]}")
                ALIASES[alias] = (str(existing[0]), display)
                continue
            print(f"  + {alias:14} -> {mid}")
            if args.apply:
                conn.execute(text("""
                    INSERT INTO llm_models
                      (id, provider_id, model_code, display_name,
                       capability_tool_calling, capability_vision, capability_json_mode,
                       capability_streaming, capability_embeddings,
                       source, enabled, notes)
                    VALUES (:id, :p, :c, :d, false, false, true, true, false,
                            'manual', true, :n)
                    ON CONFLICT (provider_id, model_code) DO NOTHING
                """), {
                    "id": mid, "p": provider_id, "c": alias, "d": display,
                    "n": "LiteLLM tier alias; backing model and cost order live in litellm-config.yaml",
                })

        # ── 2. Repoint tier bindings ──
        print("\ntier bindings:")
        for tier, (primary_alias, fb_aliases) in TIERS.items():
            primary_id = ALIASES[primary_alias][0]
            fb_ids = [ALIASES[a][0] for a in fb_aliases]

            cur = conn.execute(
                text("SELECT id, primary_model_id, fallback_model_ids FROM llm_tier_bindings "
                     "WHERE user_id=:u AND tier=:t"),
                {"u": uid, "t": tier},
            ).fetchone()

            if cur:
                old_primary = conn.execute(
                    text("SELECT model_code FROM llm_models WHERE id=:i"), {"i": cur[1]}
                ).fetchone()
                old_code = old_primary[0] if old_primary else "<missing>"
                same = str(cur[1]) == primary_id and list(cur[2] or []) == fb_ids
                mark = "=" if same else ">"
                print(f"  {mark} {tier:9} primary {old_code!r} -> {primary_alias!r}")
                print(f"      fallbacks -> {fb_aliases}")
                if args.apply and not same:
                    conn.execute(text("""
                        UPDATE llm_tier_bindings
                           SET primary_model_id=:p, fallback_model_ids=CAST(:f AS jsonb),
                               per_candidate_config=CAST(:pc AS jsonb), updated_at=NOW()
                         WHERE id=:i
                    """), {"p": primary_id, "f": json.dumps(fb_ids),
                           "pc": json.dumps(PER_CANDIDATE_CONFIG), "i": cur[0]})
            else:
                print(f"  + {tier:9} creating binding -> {primary_alias!r} {fb_aliases}")
                if args.apply:
                    conn.execute(text("""
                        INSERT INTO llm_tier_bindings
                          (id, user_id, tier, primary_model_id, fallback_model_ids,
                           per_candidate_config, budget_aware)
                        VALUES (:i, :u, :t, :p, CAST(:f AS jsonb), CAST(:pc AS jsonb), true)
                    """), {"i": f"tb_{tier}_{uuid.uuid4().hex[:6]}", "u": uid, "t": tier,
                           "p": primary_id, "f": json.dumps(fb_ids),
                           "pc": json.dumps(PER_CANDIDATE_CONFIG)})

        # ── 3. Disable stale raw-vendor-name models ──
        # Disabled rather than deleted: llm_agent_overrides and historical
        # llm_usage_logs may reference them, and a FK is a worse outage than
        # a disabled row.
        # 停用而非刪除：agent override 與歷史用量紀錄可能引用它們，違反外鍵造成的
        # 故障比留下停用列更糟。
        print("\nstale raw-name models (disable):")
        stale = conn.execute(text("""
            SELECT id, model_code FROM llm_models
             WHERE provider_id=:p AND enabled=true AND model_code LIKE '%/%'
             ORDER BY model_code
        """), {"p": provider_id}).fetchall()
        for mid, code in stale:
            print(f"  - {code}")
            if args.apply:
                conn.execute(
                    text("UPDATE llm_models SET enabled=false, updated_at=NOW() WHERE id=:i"),
                    {"i": mid},
                )
        if not stale:
            print("  (none)")

        if not args.apply:
            print("\nDry run — nothing written. Re-run with --apply.")
            return 0

    print("\nApplied. Verifying:")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT t.tier, m.model_code, t.fallback_model_ids
              FROM llm_tier_bindings t JOIN llm_models m ON m.id=t.primary_model_id
             WHERE t.user_id=:u ORDER BY t.tier
        """), {"u": uid}).fetchall()
        for tier, code, fbs in rows:
            names = [
                conn.execute(text("SELECT model_code FROM llm_models WHERE id=:i"), {"i": f}).scalar()
                for f in (fbs or [])
            ]
            print(f"  {tier:9} {code:10} -> {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
