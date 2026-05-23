# Read-only operator API (apps/api) for cloud web service.
# Build from monorepo root:
#   docker build -f apps/api/Dockerfile -t origenlab-api .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/apps/api/.venv

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv

COPY apps/email-pipeline/pyproject.toml apps/email-pipeline/uv.lock apps/email-pipeline/README.md apps/email-pipeline/
COPY apps/email-pipeline/src apps/email-pipeline/src

COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md apps/api/
COPY apps/api/src apps/api/src

WORKDIR /app/apps/api
RUN uv sync --frozen --no-dev

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "origenlab_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
