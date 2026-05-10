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

# Runner Stage (Zero build dependencies)
FROM public.ecr.aws/docker/library/python:3.10-slim-bookworm
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace
ENV PATH="/opt/venv/bin:$PATH"

RUN addgroup --system appgroup && \
    adduser --system --group --home /home/appuser appuser

ENV HOME=/home/appuser

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY ./services/dashboard /workspace/services/dashboard
COPY ./src /workspace/src

USER root
RUN mkdir -p /workspace/data /workspace/logs /home/appuser/.streamlit && \
    chown -R appuser:appgroup /workspace /home/appuser
USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "services/dashboard/src/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
