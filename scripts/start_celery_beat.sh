#!/bin/bash
# Celery Beat 啟動腳本
# 用於啟動 Celery Beat scheduler 以執行排程任務
#
# Usage:
#   ./scripts/start_celery_beat.sh              # 前台啟動
#   ./scripts/start_celery_beat.sh --daemon     # 後台 daemon 啟動
#
# 排程任務列表 (定義於 src/infrastructure/celery_app.py):
#   - generate_market_intelligence  (08:30 EST)
#   - trigger_portfolio_rebalance   (12:00, 17:00 EST)
#   - sentinel_tick                 (每分鐘)
#   - sync_broker_positions         (每5分鐘)
#   - distill_memories              (01:00 EST)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# 啟用虛擬環境（如果存在）
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 確認 Redis 連線
echo "Checking Redis connectivity..."
python3 -c "from celery_app import app; conn = app.connection().connect(); print('Redis OK'); conn.disconnect()" 2>/dev/null || \
    echo "Warning: Redis connection check failed. Ensure REDIS_URL is set."

# 啟動 Celery Beat
BEAT_ARGS="-A src.infrastructure.celery_app beat --loglevel=info"

if [ "$1" == "--daemon" ]; then
    echo "Starting Celery Beat in daemon mode..."
    celery $BEAT_ARGS --detach
    echo "Celery Beat started (PID: $!)"
else
    echo "Starting Celery Beat (foreground)..."
    exec celery $BEAT_ARGS
fi