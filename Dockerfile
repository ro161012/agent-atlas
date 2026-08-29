# Agent Atlas — containerized for Cloud Run (scales to zero between cron ticks)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web

EXPOSE 8080

# uvicorn workers: keep it modest — state lives in Firestore, not the process.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
