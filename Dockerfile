# syntax=docker/dockerfile:1.7

# ---- 1. Web UI -----------------------------------------------------------------
# The UI and the wheel are the same for every platform: build them natively, not under emulation
FROM --platform=$BUILDPLATFORM node:22-alpine AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Vite writes the bundle to /src/rgcopy/web/dist
RUN npm run build

# ---- 2. Python wheel with the UI embedded ----------------------------------------
FROM --platform=$BUILDPLATFORM python:3.12-slim AS wheel
WORKDIR /src
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md ./
COPY rgcopy ./rgcopy
COPY --from=ui /src/rgcopy/web/dist ./rgcopy/web/dist
RUN python -m build --wheel --outdir /wheels

# ---- 3. Runtime ------------------------------------------------------------------
FROM python:3.12-alpine
RUN apk add --no-cache rsync tini \
 && adduser -D -u 1000 rgcopy \
 && mkdir -p /media /config \
 && chmod 1777 /config
COPY --from=wheel /wheels/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

# /config is world-writable so the container can also run as the owner of the files (`user:`)
ENV PYTHONUNBUFFERED=1 \
    RGCOPY_HOST=0.0.0.0 \
    RGCOPY_PORT=8000 \
    RGCOPY_ROOTS=/media \
    RGCOPY_DATA_DIR=/config

USER rgcopy
VOLUME ["/config"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"]
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["rgcopy", "serve"]
