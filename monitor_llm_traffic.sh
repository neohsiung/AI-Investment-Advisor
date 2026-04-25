#!/bin/bash
# Monitor real LLM traffic in production containers

echo "🚀 PAD Real-Time LLM Traffic Monitor"
echo "========================================"
echo ""
echo "Monitoring containers:"
echo "  • advisor_prod_api (MCP Server)"
echo "  • advisor_prod_db (PostgreSQL)"
echo "  • advisor_prod_cache (Redis)"
echo ""
echo "Real-time logs (press Ctrl+C to stop):"
echo "========================================"
echo ""

# Start monitoring with color
docker logs advisor_prod_api -f 2>&1 | grep --color=always \
  -E "model|router|inference|llm|token|cost|error|WARNING|ERROR" &

DOCKER_PID=$!

# Also monitor Redis commands
echo "" 
echo "Redis Command Monitor (every 5 seconds):"
while true; do
  echo "[$(date '+%H:%M:%S')] Redis connections:"
  docker exec advisor_prod_cache redis-cli INFO stats 2>/dev/null | \
    grep -E "total_connections|total_commands|instantaneous"
  sleep 5
done &

REDIS_PID=$!

# Cleanup on exit
trap "kill $DOCKER_PID $REDIS_PID 2>/dev/null" EXIT

wait
