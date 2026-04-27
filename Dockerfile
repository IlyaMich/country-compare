FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app \
    && useradd --system --gid app --home /app app

COPY pyproject.toml README.md ./
COPY country_compare ./country_compare
COPY config ./config
COPY data/examples ./data/examples

RUN python -m pip install --upgrade pip \
    && python -m pip install .

RUN mkdir -p /app/data/raw /app/data/processed /app/data/audit /app/data/exports \
    && chown -R app:app /app

USER app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["python", "-m", "streamlit", "run", "country_compare/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]