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

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy service and core
COPY ./services/dashboard /workspace/services/dashboard
COPY ./src /workspace/src

RUN mkdir -p /workspace/data /workspace/logs /home/appuser/.streamlit && \
    chown -R appuser:appgroup /workspace /home/appuser

USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "services/dashboard/src/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
