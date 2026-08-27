# NetworkGuardian — Monitoring Agent Container
#
# Runs the monitoring agent that polls network links for health metrics
# (latency, packet loss, jitter) and stores them in SQLite database.
#
# Based on Python 3.10 slim for lightweight operation.

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for ping and monitoring
RUN apt-get update && apt-get install -y --no-install-recommends \
        iputils-ping \
        net-tools \
        iproute2 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python testing dependencies and ML packages for detection engine
RUN pip install --no-cache-dir pytest scikit-learn joblib

# Create application directories
WORKDIR /app
RUN mkdir -p /app/logs /app/monitoring /app/detection

# Copy monitoring agent code (requirements are minimal - just standard Python)
COPY monitoring/ /app/monitoring/
COPY detection/ /app/detection/
COPY tests/ /app/tests/

# Create volume mount points
VOLUME ["/app/monitoring/metrics.db", "/app/logs"]

# Run the monitoring agent
CMD ["python", "/app/monitoring/agent.py"]