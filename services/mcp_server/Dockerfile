FROM python:3.11-slim-bookworm

WORKDIR /workspace

ENV PIP_ROOT_USER_ACTION=ignore
ENV PYTHONUNBUFFERED=1
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

# Copy service code & core packages
COPY ./services/mcp_server /workspace/services/mcp_server
COPY ./src /workspace/src

RUN mkdir -p /workspace/data /workspace/logs && \
    chown -R appuser:appgroup /workspace /home/appuser

USER appuser

EXPOSE 8000

CMD ["uvicorn", "services.mcp_server.src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
