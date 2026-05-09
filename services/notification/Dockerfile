FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm

WORKDIR /workspace

ENV PIP_ROOT_USER_ACTION=ignore
ENV PYTHONUNBUFFERED=1

# We add /workspace to PYTHONPATH so that internal absolute imports like `src.*` keep working
# if we mount the entire project, or we copy the specific service code.
ENV PYTHONPATH=/workspace

# Install system dependencies
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

# Copy service code & core packages
COPY ./services/notification /workspace/services/notification
COPY ./src /workspace/src

# Create data directories
RUN mkdir -p /workspace/data /workspace/logs && \
    chown -R appuser:appgroup /workspace /home/appuser

USER appuser

# Exposed API port for Notification Service
EXPOSE 8001

CMD ["uvicorn", "services.notification.src.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
