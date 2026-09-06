FROM node:24-bookworm-slim AS javascript
FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/data \
    ANYTUBE_DATA=/data

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates iptables util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 anytube \
    && useradd --uid 10001 --gid anytube --no-create-home anytube \
    && groupadd --gid 10002 egress && useradd --uid 10002 --gid egress --no-create-home egress \
    && mkdir -p /data/downloads && chown -R anytube:anytube /data
COPY --chown=anytube:anytube app ./app
USER anytube
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
