FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/services/data_update_service/src:/app/src

WORKDIR /app

RUN python -m pip install --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY data ./data
COPY services/data_update_service ./services/data_update_service

RUN python -m pip install -e . \
    && python -m pip install -e "services/data_update_service[kafka]"

CMD ["python", "-m", "data_update_service.worker.consumer"]
