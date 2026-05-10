#!/bin/bash
# Ollama 启动脚本（本地直接启动）

echo "🚀 启动 Ollama 本地服务..."

# 检查 Ollama 是否已运行
if pgrep -x "ollama" > /dev/null; then
    echo "✅ Ollama 已在运行"
    exit 0
fi

# 尝试用 brew 启动
if command -v ollama &> /dev/null; then
    echo "📍 找到 Ollama CLI，启动服务..."
    ollama serve &
    sleep 5
    echo "✅ Ollama 服务启动完成（PID: $!）"
    exit 0
fi

# 如果没有 CLI，尝试从 Docker 启动（使用 host network）
echo "📍 尝试从 Docker 启动..."

docker run -d \
  --name ollama_service \
  --network host \
  --restart always \
  -v ~/.ollama:/root/.ollama \
  ollama/ollama:latest \
  ollama serve 2>&1 | tail -5

sleep 5
echo "✅ Ollama 容器启动完成"
