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
RUN uv venv /opt/venv && \
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
