class EvaluationService:
    """
    Service for calculating agent performance scores based on signal accuracy.
    評估服務：根據訊號準確度計算 Agent 績效得分。
    """

    # Default flat-market threshold (configurable via constructor or settings).
    # 預設平盤閾值（可透過建構子或設定調整）。
    DEFAULT_FLAT_THRESHOLD = 0.005

    def __init__(self, flat_threshold: float = None, settings_service=None):
        """
        Initialize the evaluation service.
        初始化評估服務。

        Args:
            flat_threshold: Market movement threshold below which is considered "flat".
                            低於此值的市場波動視為「平盤」。
                            Defaults to dynamic setting or DEFAULT_FLAT_THRESHOLD if not provided.
            settings_service: Service to fetch dynamic settings.
        """
        self.settings_service = settings_service
        self._flat_threshold = flat_threshold

    @property
    def flat_threshold(self) -> float:
        """Dynamic threshold. (動態閾值)"""
        # 1. Constructor override
        if self._flat_threshold is not None:
            return self._flat_threshold
        
        # 2. Settings lookup (Dynamic)
        if self.settings_service:
            # v4.1.7: Use dynamic setting with a safe fallback
            return float(self.settings_service.get_setting("flat_market_threshold", self.DEFAULT_FLAT_THRESHOLD))
            
        # 3. Final default
        return self.DEFAULT_FLAT_THRESHOLD

    def calculate_score(self, signal: str, price_start: float, price_end: float) -> float:
        """
        Calculate a score based on the signal and actual price movement.
        根據訊號與實際價格變動計算得分。
        
        Range: -1.0 (Wrong) to 1.0 (Correct).
        範圍：-1.0（錯誤）到 1.0（正確）。
        """
        signal = signal.upper().strip()
        delta_pct = (price_end - price_start) / price_start if price_start != 0 else 0
        
        threshold = self.flat_threshold

        if signal == 'BUY':
            if delta_pct > threshold:
                return 1.0  # Explicitly Good
            elif delta_pct < -threshold:
                return -1.0 # Explicitly Bad
            else:
                return 0.0  # Neutral
        
        elif signal == 'SELL':
            if delta_pct < -threshold:
                return 1.0  # Saved loss or profited from short
            elif delta_pct > threshold:
                return -1.0 # Missed opportunity or loss on short
            else:
                return 0.0

        elif signal == 'HOLD':
            # Hold is good if market is flat/choppy or slightly down
            # Hold is bad if market moved significantly in either direction (missed opp)
            if abs(delta_pct) < threshold:
                return 1.0
            else:
                return -0.5 # Missed opportunity, but not as bad as wrong direction trade

        return 0.0
