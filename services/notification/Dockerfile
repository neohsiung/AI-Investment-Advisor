FROM python:3.11-slim-bookworm

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

# Copy requirements
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY ./services/notification /workspace/services/notification

# Create data directories
RUN mkdir -p /workspace/data /workspace/logs && \
    chown -R appuser:appgroup /workspace /home/appuser

USER appuser

# Exposed API port for Notification Service
EXPOSE 8001

CMD ["uvicorn", "services.notification.src.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
