FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

FROM base AS test
COPY requirements-dev.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-dev.lock
COPY app ./app
COPY tests ./tests
COPY pyproject.toml ./
RUN ruff check app tests && pytest -q

FROM base AS production
RUN groupadd --gid 10001 netrevive && useradd --uid 10001 --gid netrevive --no-create-home netrevive \
    && mkdir -m 0700 /data && chown netrevive:netrevive /data
COPY app ./app
RUN chmod -R a+rX /app/app
USER 10001:10001
ENV DATABASE_PATH=/data/netrevive.db
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers", "--limit-concurrency", "64", "--timeout-keep-alive", "5", "--h11-max-incomplete-event-size", "16384"]
