FROM registry.access.redhat.com/ubi9/python-312:9.6

ARG TARGETARCH=amd64
ARG KUBECTL_VERSION=v1.31.13

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/app-root/bin:$PATH"

USER 0
RUN microdnf install -y tar gzip curl \
    && microdnf clean all \
    && curl -fsSL -o /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && chmod 0755 /usr/local/bin/kubectl

WORKDIR /app

COPY services/sandbox /tmp/pkg-sandbox
COPY services/worker/pyproject.toml /app/pyproject.toml
COPY services/worker/src /app/src

RUN pip install --no-cache-dir /tmp/pkg-sandbox \
    && pip install --no-cache-dir . \
    && mkdir -p /uploads \
    && chown -R 1001:0 /app /uploads

USER 1001
EXPOSE 8001
CMD ["python", "-m", "legacylift_worker"]
