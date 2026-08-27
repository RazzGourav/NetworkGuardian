FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir flask flask-socketio eventlet requests

COPY . /app/

ENV FLASK_APP=backend.app
ENV FLASK_DEBUG=1
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "backend.app"]
