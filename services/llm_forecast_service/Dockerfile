FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY services/llm_forecast_service/pyproject.toml /app/pyproject.toml
COPY services/llm_forecast_service/README.md /app/README.md
COPY services/llm_forecast_service/src /app/src

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install . \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn llm_forecast_service.main:app --host 0.0.0.0 --port ${PORT:-8080}"]