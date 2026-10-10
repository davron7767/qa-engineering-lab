# QA Commerce application image.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

RUN useradd --create-home --uid 10001 appuser

# Dependencies first so code changes do not invalidate the dependency layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]

# Applies migrations, seeds deterministic data (if SEED_ON_STARTUP=true), then serves.
CMD ["python", "-m", "app.serve", "--host", "0.0.0.0", "--port", "8000"]
