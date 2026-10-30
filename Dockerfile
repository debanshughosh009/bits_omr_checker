# OMR Checker web app: designer uploads layouts, professor scores scans.
# Build and run:  docker compose up -d --build   ->  http://localhost:8000
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    OMR_DATA_DIR=/data \
    PORT=8000

WORKDIR /app

# Headless OpenCV: same cv2 module as opencv-contrib-python, without GUI libraries
COPY scans_to_csv/requirements.txt scans_to_csv/requirements.txt
COPY webapp/requirements.txt webapp/requirements.txt
RUN pip install --no-cache-dir \
        -r scans_to_csv/requirements.txt \
        -r webapp/requirements.txt \
        opencv-contrib-python-headless

COPY scans_to_csv scans_to_csv
COPY scoring scoring
COPY webapp webapp

RUN useradd --create-home omr && mkdir -p /data && chown omr /data
USER omr
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

CMD ["python", "webapp/app.py"]
