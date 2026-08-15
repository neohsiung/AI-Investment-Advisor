# Builder Stage
FROM public.ecr.aws/docker/library/python:3.10-slim-bookworm as builder

RUN pip install uv
WORKDIR /workspace

# Install exact build deps required for underlying C-extensions
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Create venv and install dependencies into it at /opt/venv
#
# torch is installed first, from PyTorch's CPU index. `timesfm[torch]` in
# pyproject.toml otherwise resolves to a CUDA build — measured in the image
# running on 2026-08-14: torch 2.13.0+cu130 on aarch64, dragging in 2.9GB of
# `nvidia/*` CUDA libraries next to 897MB of torch, for a timesfm package that
# is itself 308KB. No container in this stack has an NVIDIA GPU, so those
# 2.9GB can never execute. They filled the 63GB Docker VM disk and blocked
# every rebuild.
#
# Two steps rather than one resolve: the PyTorch index also mirrors unrelated
# packages (requests, etc.) at older versions, and uv's default index strategy
# takes the first index that carries a name — pointing the whole install at it
# fails to resolve. Installing torch alone from that index, then everything
# else from PyPI, leaves torch satisfied at `2.13.0+cpu` (`==2.13.0` matches a
# local version) so the second resolve adds no nvidia wheels. Verified by
# dry-run before this change: 0 nvidia packages, torch stays +cpu.
#
# 先從 PyTorch CPU index 安裝 torch：pyproject 的 timesfm[torch] 預設會解析到
# CUDA 版本（實測為 torch 2.13.0+cu130），連帶 2.9GB 的 nvidia CUDA 函式庫，
# 而本堆疊沒有任何容器有 NVIDIA GPU——那 2.9GB 永遠不會被執行，卻塞爆了
# 63GB 的 Docker VM 磁碟並讓每次重建失敗。分兩步是因為該 index 也鏡像了
# requests 等套件的舊版本，整包指過去會解析失敗。
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv --no-cache \
        --index-url https://download.pytorch.org/whl/cpu torch==2.13.0+cpu && \
    uv pip install --python /opt/venv --no-cache -r pyproject.toml

# Runner Stage
FROM public.ecr.aws/docker/library/python:3.10-slim-bookworm
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /workspace

# Install runtime dependencies (e.g., ffmpeg for pydub/ffmpy)
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

RUN addgroup --system appgroup && \
    adduser --system --group --home /home/appuser appuser

ENV HOME=/home/appuser

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY ./services/mcp_server /workspace/services/mcp_server
COPY ./src /workspace/src
COPY ./prompts /workspace/prompts
COPY ./config /workspace/config
COPY ./workspace /workspace/workspace
COPY ./alembic.ini /workspace/alembic.ini
COPY ./alembic /workspace/alembic
COPY ./scripts /workspace/scripts

USER root
RUN mkdir -p /workspace/data /workspace/logs && \
    chown -R appuser:appgroup /workspace /home/appuser
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn services.mcp_server.src.app.main:app --host 0.0.0.0 --port 8000"]
