# Service de publication UDR (Railway). ffprobe sert à valider les masters.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY udr_publish ./udr_publish
COPY schema ./schema
COPY scripts ./scripts
COPY service ./service

# Journal et verrous : monter un volume Railway sur /data (sinon l'idempotence
# repose seulement sur la vérification external_id côté Post For Me).
ENV PUBLISH_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

# Un seul processus (verrous fichiers), plusieurs fils ; uploads longs tolérés.
CMD gunicorn service.wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 900
