"""
Factor Orthogonalization & Multi-Collinearity Gate Service (Phase 32).
自研量化因子截面正交化、多重共線性檢定與特徵交互作用引擎。
=============================================================================
1. 候選策略正交性檢定 (Artifact Collinearity Gate):
   - 確保新產生的自研因子候選程式碼/收益序列與線上既有因子相關性低於門檻 (預設 0.65)。
2. 截面多因子動態正交化 (Cross-Sectional Dynamic Orthogonalization):
   - 對稱低丁正交化 (Löwdin Symmetric Orthogonalization)：在弗羅貝尼烏斯範數意義下以最小幾何形變
     消除 6 大核心因子（Momentum, Smart Money, Liquidity Premium, Quality, Value, Low Vol）
     之多重共線性，保留最大經濟學可解釋性。
   - 循序格拉姆-施密特正交化 (Gram-Schmidt Sequential Orthogonalization)：支援體制優先級基底正交化。
3. 多重共線性診斷 (Variance Inflation Factor, VIF):
   - 計算各因子之 VIF 分數與截面相關性矩陣，即時預警共線性極端曝險 (VIF >= 5.0)。
4. 非線性特徵交互作用 (Factor Interactions):
   - 捕捉動能主力協同 (Momentum x Smart Money)、品質價值協同 (Quality x Value) 等二階交互增益。
"""
from __future__ import annotations

import copy
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("FactorOrthogonalizationService")

DEFAULT_MAX_CORRELATION = 0.65
DEFAULT_MAX_VIF_THRESHOLD = 5.0

CORE_FACTOR_NAMES = [
    "momentum",
    "smart_money",
    "liquidity_premium",
    "quality",
    "value",
    "low_vol",
]

INTERACTION_PAIRS = [
    ("momentum", "smart_money", "mom_x_smart"),
    ("quality", "value", "qual_x_val"),
    ("low_vol", "quality", "lowvol_x_qual"),
    ("momentum", "liquidity_premium", "mom_x_liq"),
]


@dataclass
class FactorCollinearityReport:
    """Collinearity diagnostics across cross-sectional factors."""
    factor_names: List[str]
    correlation_matrix: Dict[str, Dict[str, float]]
    vif_scores: Dict[str, float]
    max_vif: float
    multicollinear_pairs: List[Tuple[str, str, float]]
    is_collinear_alert: bool
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factor_names": self.factor_names,
            "correlation_matrix": {
                k: {kk: round(vv, 4) for kk, vv in v.items()}
                for k, v in self.correlation_matrix.items()
            },
            "vif_scores": {k: round(v, 2) for k, v in self.vif_scores.items()},
            "max_vif": round(self.max_vif, 2),
            "multicollinear_pairs": [
                [p[0], p[1], round(p[2], 4)] for p in self.multicollinear_pairs
            ],
            "is_collinear_alert": self.is_collinear_alert,
            "summary": self.summary,
        }


@dataclass
class CrossSectionalOrthogonalizationResult:
    """Result of cross-sectional factor orthogonalization."""
    tickers: List[str]
    factor_names: List[str]
    method: str  # "lowdin" or "gram_schmidt"
    raw_scores: Dict[str, Dict[str, float]]  # ticker -> {factor: score}
    orthogonal_scores: Dict[str, Dict[str, float]]  # ticker -> {factor: score [0.0, 1.0]}
    interaction_scores: Dict[str, Dict[str, float]]  # ticker -> {interaction: score [0.0, 1.0]}
    pre_collinearity: FactorCollinearityReport
    post_collinearity: FactorCollinearityReport
    correlation_reduction_pct: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tickers": self.tickers,
            "factor_names": self.factor_names,
            "method": self.method,
            "raw_scores": {
                t: {k: round(v, 4) for k, v in s.items()}
                for t, s in self.raw_scores.items()
            },
            "orthogonal_scores": {
                t: {k: round(v, 4) for k, v in s.items()}
                for t, s in self.orthogonal_scores.items()
            },
            "interaction_scores": {
                t: {k: round(v, 4) for k, v in s.items()}
                for t, s in self.interaction_scores.items()
            },
            "pre_collinearity": self.pre_collinearity.to_dict(),
            "post_collinearity": self.post_collinearity.to_dict(),
            "correlation_reduction_pct": round(self.correlation_reduction_pct, 2),
            "timestamp": self.timestamp,
        }


class FactorOrthogonalizationService:
    """
    Checks cross-sectional and time-series orthogonality of factor candidates,
    and dynamically orthogonalizes live cross-sectional factor matrices.
    檢定因子候選者與在線因子之相關性，並提供截面因子矩陣動態正交化。
    """

    _REDIS_LATEST_KEY_PREFIX = "factor_ortho:latest"
    _MEMORY_LATEST_REPORT: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        max_correlation: float = DEFAULT_MAX_CORRELATION,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
    ) -> None:
        self.max_correlation = max_correlation
        try:
            self.user_id = resolve_user_id(user_id) if user_id else "default"
        except Exception:
            self.user_id = user_id or "default"
        self.settings_service = settings_service

    def _get_setting_bool(self, key: str, default: bool = True) -> bool:
        if not self.settings_service:
            return default
        try:
            if hasattr(self.settings_service, "get_setting"):
                val = self.settings_service.get_setting(key, default)
            elif hasattr(self.settings_service, "get"):
                val = self.settings_service.get(self.user_id, key, default)
            else:
                val = default
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes")
        except Exception:
            return default

    def _get_setting_str(self, key: str, default: str) -> str:
        if not self.settings_service:
            return default
        try:
            if hasattr(self.settings_service, "get_setting"):
                val = self.settings_service.get_setting(key, default)
            elif hasattr(self.settings_service, "get"):
                val = self.settings_service.get(self.user_id, key, default)
            else:
                val = default
            return str(val) if val is not None else default
        except Exception:
            return default

    def _get_setting_float(self, key: str, default: float) -> float:
        if not self.settings_service:
            return default
        try:
            if hasattr(self.settings_service, "get_setting"):
                val = self.settings_service.get_setting(key, default)
            elif hasattr(self.settings_service, "get"):
                val = self.settings_service.get(self.user_id, key, default)
            else:
                val = default
            return float(val) if val is not None else default
        except Exception:
            return default

    @property
    def is_orthogonalization_enabled(self) -> bool:
        return self._get_setting_bool("enable_factor_orthogonalization", True)

    @property
    def is_interaction_enabled(self) -> bool:
        return self._get_setting_bool("enable_factor_interaction_terms", True)

    @property
    def default_method(self) -> str:
        return self._get_setting_str("factor_orthogonalization_method", "lowdin")

    @property
    def max_vif_threshold(self) -> float:
        return self._get_setting_float("factor_max_vif_threshold", DEFAULT_MAX_VIF_THRESHOLD)

    # =========================================================================
    # Part 1: Artifact & Candidate Orthogonality Gate (Preserved for compatibility)
    # =========================================================================

    @staticmethod
    def _extract_returns_series(record: Any) -> Dict[str, float]:
        """
        Extract date -> daily return map from an artifact record.
        Prioritizes shadow_tracking_log, then backtest_metrics.
        """
        returns_map: Dict[str, float] = {}

        # 1. Shadow tracking log
        shadow_log = getattr(record, "shadow_tracking_log", None) or []
        for entry in shadow_log:
            dt = entry.get("date") or entry.get("timestamp")
            if dt and "daily_pnl_pct" in entry:
                try:
                    returns_map[str(dt)[:10]] = float(entry["daily_pnl_pct"])
                except (ValueError, TypeError):
                    continue

        if returns_map:
            return returns_map

        # 2. Backtest returns if available
        metrics = getattr(record, "backtest_metrics", None) or {}
        daily_returns = metrics.get("daily_returns") or metrics.get("returns")
        if isinstance(daily_returns, dict):
            for dt, val in daily_returns.items():
                try:
                    returns_map[str(dt)[:10]] = float(val)
                except (ValueError, TypeError):
                    continue
        elif isinstance(daily_returns, list):
            for i, val in enumerate(daily_returns):
                try:
                    returns_map[f"idx_{i}"] = float(val)
                except (ValueError, TypeError):
                    continue

        return returns_map

    @staticmethod
    def compute_pearson_correlation(x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient between two series."""
        n = len(x)
        if n < 3:
            return 0.0

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if den_x == 0 or den_y == 0:
            return 0.0

        return num / (den_x * den_y)

    @staticmethod
    def compute_spearman_correlation(x: List[float], y: List[float]) -> float:
        """Calculate Spearman rank correlation coefficient between two series."""
        n = len(x)
        if n < 3:
            return 0.0

        def _get_ranks(seq: List[float]) -> List[float]:
            sorted_indices = sorted(range(len(seq)), key=lambda i: seq[i])
            ranks = [0.0] * len(seq)
            for rank, idx in enumerate(sorted_indices):
                ranks[idx] = float(rank + 1)
            return ranks

        rank_x = _get_ranks(x)
        rank_y = _get_ranks(y)
        return FactorOrthogonalizationService.compute_pearson_correlation(rank_x, rank_y)

    @staticmethod
    def compute_code_token_similarity(code_a: str, code_b: str) -> float:
        """Compute token-level Jaccard similarity between two source codes."""
        if not code_a or not code_b:
            return 0.0
        tokens_a = set(code_a.replace("\n", " ").split())
        tokens_b = set(code_b.replace("\n", " ").split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        return len(intersection) / len(union) if union else 0.0

    def calculate_correlation(
        self, candidate: Any, active_factor: Any
    ) -> Tuple[float, str]:
        """
        Calculate maximum correlation between candidate and an active factor.
        Returns: (correlation_score, method_used)
        """
        cand_returns = self._extract_returns_series(candidate)
        active_returns = self._extract_returns_series(active_factor)

        # Find matching timestamps
        overlap_dates = sorted(set(cand_returns.keys()) & set(active_returns.keys()))
        if len(overlap_dates) >= 3:
            x = [cand_returns[d] for d in overlap_dates]
            y = [active_returns[d] for d in overlap_dates]
            pearson = abs(self.compute_pearson_correlation(x, y))
            spearman = abs(self.compute_spearman_correlation(x, y))
            corr = max(pearson, spearman)
            return corr, f"return_series({len(overlap_dates)}_points)"

        # Fallback to code token similarity if returns are insufficient
        cand_code = getattr(candidate, "source_code", "")
        active_code = getattr(active_factor, "source_code", "")
        sim = self.compute_code_token_similarity(cand_code, active_code)
        return sim, "code_token_jaccard"

    def check_orthogonality(
        self,
        candidate: Any,
        active_factors: List[Any],
        max_correlation: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Verify if candidate is orthogonal to all existing active factors.
        檢定候選因子與既有在線因子是否滿足正交條件。
        """
        threshold = max_correlation if max_correlation is not None else self.max_correlation
        cand_name = getattr(candidate, "name", getattr(candidate, "id", "Unknown"))

        if not active_factors:
            return {
                "orthogonal": True,
                "max_correlation": 0.0,
                "correlated_with": None,
                "reason": "Passed: No active factors to compare against",
                "details": [],
            }

        max_corr = 0.0
        conflicting_factor = None
        details = []

        for active in active_factors:
            active_id = getattr(active, "id", "")
            cand_id = getattr(candidate, "id", "")
            if active_id and cand_id and active_id == cand_id:
                continue

            active_name = getattr(active, "name", active_id)
            corr, method = self.calculate_correlation(candidate, active)
            details.append({
                "factor_name": active_name,
                "correlation": round(corr, 4),
                "method": method,
            })

            if corr > max_corr:
                max_corr = corr
                conflicting_factor = active_name

        if max_corr > threshold:
            msg = (
                f"Factor collinearity check failed: Correlation with '{conflicting_factor}' "
                f"is {max_corr:.2f}, exceeding max threshold {threshold:.2f}."
            )
            logger.warning(f"Orthogonality gate blocked '{cand_name}': {msg}")
            return {
                "orthogonal": False,
                "max_correlation": max_corr,
                "correlated_with": conflicting_factor,
                "reason": msg,
                "details": details,
            }

        return {
            "orthogonal": True,
            "max_correlation": max_corr,
            "correlated_with": conflicting_factor if max_corr > 0.0 else None,
            "reason": f"Passed: Max correlation {max_corr:.2f} is within limit {threshold:.2f}",
            "details": details,
        }

    # =========================================================================
    # Part 2: Cross-Sectional Factor Orthogonalization & Interaction Engine
    # =========================================================================

    @staticmethod
    def compute_cross_sectional_collinearity(
        tickers: List[str],
        matrix: np.ndarray,
        factor_names: List[str],
        max_vif_threshold: float = DEFAULT_MAX_VIF_THRESHOLD,
    ) -> FactorCollinearityReport:
        """
        計算截面因子共線性指標：包括相關係數矩陣、VIF 與高度共線性因子對。
        """
        n, k = matrix.shape
        if n < 3 or k < 2:
            return FactorCollinearityReport(
                factor_names=factor_names,
                correlation_matrix={fn: {f2: 1.0 if fn == f2 else 0.0 for f2 in factor_names} for fn in factor_names},
                vif_scores={fn: 1.0 for fn in factor_names},
                max_vif=1.0,
                multicollinear_pairs=[],
                is_collinear_alert=False,
                summary="標的樣本數不足 (N < 3)，不計算共線性矩陣",
            )

        # 1. 欄位標準化 (Z-Score)
        means = np.mean(matrix, axis=0)
        stds = np.std(matrix, axis=0, ddof=1)
        stds_safe = np.where(stds < 1e-8, 1.0, stds)
        z = (matrix - means) / stds_safe

        # 2. 相關係數矩陣 R
        r_mat = np.dot(z.T, z) / float(max(1, n - 1))
        # 修正對角線為 1.0，並限制在 [-1, 1]
        for i in range(k):
            r_mat[i, i] = 1.0
        r_mat = np.clip(r_mat, -1.0, 1.0)

        corr_dict: Dict[str, Dict[str, float]] = {}
        for i, fn1 in enumerate(factor_names):
            corr_dict[fn1] = {}
            for j, fn2 in enumerate(factor_names):
                corr_dict[fn1][fn2] = float(r_mat[i, j])

        # 3. 找出高共線性對 (|r| >= 0.60)
        multicollinear_pairs: List[Tuple[str, str, float]] = []
        for i in range(k):
            for j in range(i + 1, k):
                val = float(r_mat[i, j])
                if abs(val) >= 0.60:
                    multicollinear_pairs.append((factor_names[i], factor_names[j], val))

        # 4. 計算方差膨脹因子 (VIF)
        # VIF_j = (R + epsilon * I)^{-1}_{jj}
        ridge = 1e-4 * np.eye(k)
        try:
            inv_r = np.linalg.inv(r_mat + ridge)
            vif_array = np.diag(inv_r)
        except Exception:
            # 奇異矩陣退化處理
            inv_r = np.linalg.pinv(r_mat + ridge)
            vif_array = np.diag(inv_r)

        vif_scores: Dict[str, float] = {}
        for idx, fn in enumerate(factor_names):
            score = float(max(1.0, vif_array[idx]))
            vif_scores[fn] = score

        max_vif = max(vif_scores.values()) if vif_scores else 1.0
        is_alert = max_vif >= max_vif_threshold

        if is_alert:
            collinear_names = [fn for fn, s in vif_scores.items() if s >= max_vif_threshold]
            summary = f"⚠️ 偵測到顯著多重共線性：Max VIF={max_vif:.1f}，高共線性因子: {', '.join(collinear_names)}"
        else:
            summary = f"✅ 因子多重共線性健全：Max VIF={max_vif:.1f} (門檻 < {max_vif_threshold:.1f})"

        return FactorCollinearityReport(
            factor_names=factor_names,
            correlation_matrix=corr_dict,
            vif_scores=vif_scores,
            max_vif=max_vif,
            multicollinear_pairs=multicollinear_pairs,
            is_collinear_alert=is_alert,
            summary=summary,
        )

    @classmethod
    def orthogonalize_lowdin(cls, matrix: np.ndarray) -> np.ndarray:
        """
        對稱低丁正交化 (Löwdin Symmetric Orthogonalization):
        Z = X * (X^T * X)^{-1/2}
        在弗羅貝尼烏斯範數 (Frobenius norm) 下具有最小形變性質：
        min ||Z - X||_F，使正交化後的因子最大限度保留原始因子的經濟學意義。
        """
        n, k = matrix.shape
        if n < 3 or k < 2:
            return matrix.copy()

        # 標準化欄向量
        means = np.mean(matrix, axis=0)
        stds = np.std(matrix, axis=0, ddof=1)
        stds_safe = np.where(stds < 1e-8, 1.0, stds)
        x = (matrix - means) / stds_safe

        # 計算協方差矩陣 M = X^T * X
        m = np.dot(x.T, x) / float(max(1, n - 1))

        # 特徵值分解 (Eigendecomposition for symmetric matrix)
        eigvals, eigvecs = np.linalg.eigh(m)
        # 數值穩定性：截斷極小或負特徵值
        eigvals_clipped = np.maximum(eigvals, 1e-7)

        # M^{-1/2} = V * diag(1 / sqrt(lambda)) * V^T
        inv_sqrt_d = np.diag(1.0 / np.sqrt(eigvals_clipped))
        m_inv_sqrt = np.dot(np.dot(eigvecs, inv_sqrt_d), eigvecs.T)

        # 正交矩陣 Z
        z = np.dot(x, m_inv_sqrt)
        return z

    @classmethod
    def orthogonalize_gram_schmidt(
        cls,
        matrix: np.ndarray,
        priority_order_indices: Optional[List[int]] = None,
    ) -> np.ndarray:
        """
        循序格拉姆-施密特正交化 (Gram-Schmidt Sequential Orthogonalization):
        依基底優先順序逐次剔除共線性投影分量。
        """
        n, k = matrix.shape
        if n < 3 or k < 2:
            return matrix.copy()

        means = np.mean(matrix, axis=0)
        stds = np.std(matrix, axis=0, ddof=1)
        stds_safe = np.where(stds < 1e-8, 1.0, stds)
        x = (matrix - means) / stds_safe

        order = priority_order_indices or list(range(k))
        ordered_x = x[:, order]

        q = np.zeros_like(ordered_x)
        for i in range(k):
            v = ordered_x[:, i].copy()
            for j in range(i):
                # 剔除投影分量 proj_{q_j}(v) = <v, q_j> / <q_j, q_j> * q_j
                denom = np.dot(q[:, j], q[:, j])
                if denom > 1e-10:
                    proj = (np.dot(v, q[:, j]) / denom) * q[:, j]
                    v -= proj
            # 歸一化
            norm_v = np.linalg.norm(v)
            if norm_v > 1e-8:
                q[:, i] = v / norm_v * math.sqrt(n - 1)
            else:
                q[:, i] = v

        # 還原回原本欄位順序
        result = np.zeros_like(matrix)
        for idx, orig_col in enumerate(order):
            result[:, orig_col] = q[:, idx]
        return result

    @classmethod
    def calculate_interaction_terms(
        cls,
        raw_scores: Dict[str, Dict[str, float]],
    ) -> Dict[str, Dict[str, float]]:
        """
        計算非線性特徵交互作用項 (Cross-Factor Interaction Terms)。
        """
        if not raw_scores:
            return {}

        tickers = list(raw_scores.keys())
        n = len(tickers)
        if n == 0:
            return {}

        results: Dict[str, Dict[str, float]] = {t: {} for t in tickers}

        for f1, f2, inter_name in INTERACTION_PAIRS:
            raw_interactions = []
            for t in tickers:
                scores = raw_scores[t]
                v1 = float(scores.get(f1, 0.50))
                v2 = float(scores.get(f2, 0.50))
                raw_interactions.append(v1 * v2)

            if n >= 3:
                # 截面百分位排名歸一化至 [0.0, 1.0]
                ranks = np.argsort(np.argsort(raw_interactions))
                norm_scores = ranks / float(max(1, n - 1))
                for idx, t in enumerate(tickers):
                    results[t][inter_name] = round(float(norm_scores[idx]), 4)
            else:
                for idx, t in enumerate(tickers):
                    results[t][inter_name] = round(float(raw_interactions[idx]), 4)

        return results

    def orthogonalize_cross_section(
        self,
        candidate_data: Dict[str, Dict[str, Any]],
        factor_names: Optional[List[str]] = None,
        method: Optional[str] = None,
        priority_order: Optional[List[str]] = None,
        enable_interactions: Optional[bool] = None,
    ) -> CrossSectionalOrthogonalizationResult:
        """
        對截面候選標的池執行多因子動態正交化與特徵交互作用運算。
        """
        factors = factor_names or CORE_FACTOR_NAMES
        ortho_method = (method or self.default_method).lower()
        use_interactions = (
            enable_interactions if enable_interactions is not None else self.is_interaction_enabled
        )
        tickers = list(candidate_data.keys())
        now_ts = datetime.now(timezone.utc).isoformat()

        # 1. 抽取原始分數矩陣
        raw_scores_dict: Dict[str, Dict[str, float]] = {}
        raw_matrix_list: List[List[float]] = []

        for t in tickers:
            data = candidate_data[t]
            t_scores: Dict[str, float] = {}
            row: List[float] = []
            for fn in factors:
                val = data.get(f"{fn}_score")
                if val is None:
                    val = data.get(fn, 0.50)
                try:
                    val_f = float(val)
                except (ValueError, TypeError):
                    val_f = 0.50
                t_scores[fn] = val_f
                row.append(val_f)
            raw_scores_dict[t] = t_scores
            raw_matrix_list.append(row)

        n = len(tickers)
        k = len(factors)

        # 標的數少於 3 個時優雅退化，原樣返回
        if n < 3:
            empty_rep = self.compute_cross_sectional_collinearity(tickers, np.zeros((n, k)), factors)
            result = CrossSectionalOrthogonalizationResult(
                tickers=tickers,
                factor_names=factors,
                method=ortho_method,
                raw_scores=raw_scores_dict,
                orthogonal_scores=copy.deepcopy(raw_scores_dict),
                interaction_scores={},
                pre_collinearity=empty_rep,
                post_collinearity=empty_rep,
                correlation_reduction_pct=0.0,
                timestamp=now_ts,
            )
            self._save_report_to_redis(result)
            return result

        raw_np = np.array(raw_matrix_list, dtype=float)

        # 2. 正交化前共線性診斷
        pre_collinearity = self.compute_cross_sectional_collinearity(
            tickers, raw_np, factors, max_vif_threshold=self.max_vif_threshold
        )

        # 3. 執行正交化演算法
        if ortho_method == "gram_schmidt":
            order_indices = [factors.index(p) for p in (priority_order or factors) if p in factors]
            ortho_z = self.orthogonalize_gram_schmidt(raw_np, order_indices)
        else:
            # 預設為 lowdin
            ortho_z = self.orthogonalize_lowdin(raw_np)

        # 4. 正交化後分數映射回截面百分位 [0.0, 1.0]
        ortho_scores_dict: Dict[str, Dict[str, float]] = {t: {} for t in tickers}
        ortho_matrix_list: List[List[float]] = []

        for col_idx, fn in enumerate(factors):
            col_vals = ortho_z[:, col_idx]
            # argsort argsort 百分位排名
            ranks = np.argsort(np.argsort(col_vals))
            norm_col = ranks / float(max(1, n - 1))
            for row_idx, t in enumerate(tickers):
                ortho_scores_dict[t][fn] = round(float(norm_col[row_idx]), 4)

        for t in tickers:
            ortho_matrix_list.append([ortho_scores_dict[t][fn] for fn in factors])
        ortho_np = np.array(ortho_matrix_list, dtype=float)

        # 5. 正交化後共線性診斷
        post_collinearity = self.compute_cross_sectional_collinearity(
            tickers, ortho_np, factors, max_vif_threshold=self.max_vif_threshold
        )

        # 6. 計算相關性消除百分比
        pre_corrs = []
        for i in range(k):
            for j in range(i + 1, k):
                pre_corrs.append(abs(pre_collinearity.correlation_matrix[factors[i]][factors[j]]))
        post_corrs = []
        for i in range(k):
            for j in range(i + 1, k):
                post_corrs.append(abs(post_collinearity.correlation_matrix[factors[i]][factors[j]]))

        mean_pre = float(np.mean(pre_corrs)) if pre_corrs else 0.0
        mean_post = float(np.mean(post_corrs)) if post_corrs else 0.0
        reduction_pct = (
            max(0.0, (mean_pre - mean_post) / max(1e-4, mean_pre) * 100.0) if mean_pre > 1e-4 else 0.0
        )

        # 7. 非線性交互作用項計算
        interaction_scores = self.calculate_interaction_terms(raw_scores_dict) if use_interactions else {}

        result = CrossSectionalOrthogonalizationResult(
            tickers=tickers,
            factor_names=factors,
            method=ortho_method,
            raw_scores=raw_scores_dict,
            orthogonal_scores=ortho_scores_dict,
            interaction_scores=interaction_scores,
            pre_collinearity=pre_collinearity,
            post_collinearity=post_collinearity,
            correlation_reduction_pct=reduction_pct,
            timestamp=now_ts,
        )

        # 8. 持久化至 Redis 與內存快取
        self._save_report_to_redis(result)
        return result

    def _save_report_to_redis(self, report: CrossSectionalOrthogonalizationResult) -> None:
        """持久化正交化診斷結果至 Redis 與記憶體快取"""
        rep_dict = report.to_dict()
        self._MEMORY_LATEST_REPORT[self.user_id] = rep_dict
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                r.set(f"{self._REDIS_LATEST_KEY_PREFIX}:{self.user_id}", json.dumps(rep_dict), ex=604800)  # 7 天有效
        except Exception as e:
            logger.debug(f"Non-blocking Redis write for orthogonalization report: {e}")

    def load_latest_report(self) -> Optional[Dict[str, Any]]:
        """讀取最新截面正交化報告"""
        if self.user_id in self._MEMORY_LATEST_REPORT:
            return self._MEMORY_LATEST_REPORT[self.user_id]
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                raw = r.get(f"{self._REDIS_LATEST_KEY_PREFIX}:{self.user_id}")
                if raw:
                    data = json.loads(raw)
                    self._MEMORY_LATEST_REPORT[self.user_id] = data
                    return data
        except Exception as e:
            logger.debug(f"Non-blocking Redis read for orthogonalization report: {e}")
        return None
