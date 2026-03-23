FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    ORIGENLAB_DATA_ROOT=/data/origenlab-email

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sqlite3 \
        gcc \
        g++ \
        make \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv

# Copy minimal metadata needed to build/install project
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --group ui --frozen

COPY src ./src
COPY scripts ./scripts
COPY apps ./apps
COPY docs ./docs

RUN useradd -m -u 10001 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').read()"

CMD ["uv", "run", "streamlit", "run", "apps/business_mart_app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]

