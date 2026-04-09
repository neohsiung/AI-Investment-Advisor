FROM python:3.11-slim-bookworm

WORKDIR /workspace

ENV PIP_ROOT_USER_ACTION=ignore
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system appgroup && \
    adduser --system --group --home /home/appuser appuser

ENV HOME=/home/appuser

# Copy dependency files
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -r pyproject.toml

# Copy service and core
COPY ./services/scheduler /workspace/services/scheduler
COPY ./src /workspace/src

RUN mkdir -p /workspace/data /workspace/logs && \
    chown -R appuser:appgroup /workspace /home/appuser

USER appuser

# Removed hardcoded USER_ID=system to support multi-tenant isolation
CMD ["python", "services/scheduler/src/app.py", "--mode", "scheduler"]
