class EvaluationService:
    @staticmethod
    def calculate_score(signal: str, price_start: float, price_end: float) -> float:
        """
        Calculate score based on signal and actual price movement.
        Range: -1.0 (Wrong) to 1.0 (Correct)
        """
        signal = signal.upper().strip()
        delta_pct = (price_end - price_start) / price_start if price_start != 0 else 0
        
        # Threshold for "flat" market (e.g. < 0.5% move is considered flat)
        threshold = 0.005

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
            # Hold is good if market is flat/choppy or slightly down?
            # Hold is bad if market moved significantly in either direction (missed opp)
            if abs(delta_pct) < threshold:
                return 1.0
            else:
                return -0.5 # Missed opportunity, but not as bad as wrong direction trade

        return 0.0
