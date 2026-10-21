FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

WORKDIR /app

COPY services/sandbox /tmp/pkg-sandbox
COPY services/worker/pyproject.toml /app/pyproject.toml
COPY services/worker/src /app/src

RUN pip install --no-cache-dir /tmp/pkg-sandbox \
    && pip install --no-cache-dir .

RUN mkdir -p /uploads && chown 65534:65534 /uploads

EXPOSE 8001

USER nobody

CMD ["python", "-m", "legacylift_worker"]
