# Local screening runner — Podman or Docker.
# Build: podman build -t candidate-eval .
#        docker build -t candidate-eval .

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install .

COPY config ./config
COPY schemas ./schemas
COPY templates ./templates
COPY fixtures ./fixtures
COPY scripts ./scripts

RUN chmod +x /app/scripts/container_entrypoint.sh \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/mail /data/output \
    && chown -R appuser:appuser ${APP_HOME} /data

USER appuser

VOLUME ["/data/mail", "/data/output"]

ENTRYPOINT ["/app/scripts/container_entrypoint.sh"]
CMD ["smoke"]
