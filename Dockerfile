FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PIP_ROOT_USER_ACTION=ignore
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user with a proper home directory
RUN addgroup --system appgroup && \
    adduser --system --group --home /home/appuser appuser

# Set HOME environment variable for Streamlit
ENV HOME=/home/appuser

# Copy requirements first to leverage cache
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create data/logs directory and set permissions
RUN mkdir -p data logs && \
    mkdir -p /home/appuser/.streamlit && \
    chown -R appuser:appgroup /app /home/appuser

# Switch to non-root user
USER appuser

# Default command
CMD ["python", "src/cli.py", "--mode", "scheduler"]
