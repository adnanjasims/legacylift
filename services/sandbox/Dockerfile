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

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --no-cache-dir .

EXPOSE 8002

USER nobody

CMD ["python", "-m", "legacylift_sandbox"]
