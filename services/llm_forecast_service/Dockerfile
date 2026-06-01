FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY services/llm_forecast_service/pyproject.toml /app/pyproject.toml
COPY services/llm_forecast_service/src /app/src

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install . \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; port=os.environ.get('PORT','8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3).read()" || exit 1

CMD ["sh", "-c", "python -m uvicorn llm_forecast_service.main:app --host 0.0.0.0 --port ${PORT:-8080}"]