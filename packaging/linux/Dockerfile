# syntax=docker/dockerfile:1.7
# Linux packages from one self-contained build: .deb, .rpm, Arch, AppImage and a portable tarball,
# for the platform the build runs on (linux/amd64 or linux/arm64).
#
#   docker build -f packaging/linux/Dockerfile --output type=local,dest=dist/linux .
#   docker build --platform linux/arm64 -f packaging/linux/Dockerfile --output type=local,dest=dist/linux .
#
# The app is frozen with its own Python (python-build-standalone, glibc 2.17+) and the Qt wheels
# from PyPI, so the oldest glibc it needs is the one of the Qt wheels: 2.34 on x86_64 (RHEL 9,
# Ubuntu 22.04, Debian 12, openSUSE Leap 16 and newer) and 2.39 on aarch64. package.sh measures it
# and writes it into the package dependencies.

ARG UV_VERSION=0.9.5
ARG PYTHON_VERSION=3.12
ARG NFPM_VERSION=v2.47.0

# ---- 1. Web UI (the same on every platform) ----------------------------------------------
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Vite writes the bundle to /src/rgcopy/web/dist
RUN npm run build

# ---- 2. The app with its own Python, dependencies and Qt web view (PyInstaller) ------------
# PyInstaller imports Qt while it builds, so the build system needs at least the glibc of the Qt
# wheels; everything it picks up from the system is either left to the system (rgcopy.spec) or
# older than that floor
FROM ubuntu:22.04 AS bundle-amd64
FROM ubuntu:24.04 AS bundle-arm64
FROM bundle-${TARGETARCH} AS bundle
ARG UV_VERSION PYTHON_VERSION
ARG DEBIAN_FRONTEND=noninteractive
# binutils for PyInstaller, and the libraries it resolves Qt against (24.04 renamed some for the
# 64-bit time_t transition: libasound2t64, libglib2.0-0t64). The aarch64 Qt wheels also link to
# libwebp, opus, snappy, lcms2, minizip and libSM/libICE from the system: PyInstaller bundles them.
RUN t64() { if apt-cache show "$1t64" >/dev/null 2>&1; then echo "$1t64"; else echo "$1"; fi; } \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates curl binutils \
      "$(t64 libasound2)" libdbus-1-3 libegl1 libfontconfig1 libgbm1 libgl1 "$(t64 libglib2.0-0)" libnss3 \
      libwayland-client0 libwayland-cursor0 libwayland-egl1 libxcb-cursor0 libxcb-icccm4 \
      libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
      libxcb-xinerama0 libxcb-xkb1 libxcomposite1 libxdamage1 libxkbcommon-x11-0 libxkbcommon0 \
      libxkbfile1 libxrandr2 libxshmfence1 libxtst6 \
      libice6 libsm6 liblcms2-2 "$(t64 libminizip1)" libopus0 libsnappy1v5 libwebp7 libwebpdemux2 libwebpmux3 \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-$(uname -m)-unknown-linux-gnu.tar.gz" \
      | tar -xz --strip-components=1 -C /usr/local/bin
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1 PATH=/venv/bin:$PATH
RUN uv venv --python "$PYTHON_VERSION" --managed-python /venv
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY rgcopy ./rgcopy
COPY --from=ui /src/rgcopy/web/dist ./rgcopy/web/dist
RUN uv pip install --python /venv/bin/python ".[desktop]" "pyinstaller>=6.10,<7"
COPY packaging/linux/rgcopy.spec packaging/linux/launcher.py ./packaging/linux/
RUN cd packaging/linux \
 && pyinstaller --noconfirm --clean --distpath /dist --workpath /tmp/pyinstaller rgcopy.spec \
 && /dist/rgcopy/rgcopy --version

# ---- 3. Packages ----------------------------------------------------------------------------
FROM golang:1.26-bookworm AS nfpm
ARG NFPM_VERSION
RUN CGO_ENABLED=0 go install "github.com/goreleaser/nfpm/v2/cmd/nfpm@${NFPM_VERSION}"

FROM ubuntu:24.04 AS packages
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends appstream binutils ca-certificates curl \
      desktop-file-utils file librsvg2-bin squashfs-tools xz-utils zstd \
 && rm -rf /var/lib/apt/lists/*
COPY --from=nfpm /go/bin/nfpm /usr/local/bin/nfpm
WORKDIR /pkg
COPY packaging/linux/ ./
COPY LICENSE rgcopy/assets/rgcopy.svg ./
COPY --from=bundle /dist/rgcopy ./rgcopy
RUN ./package.sh /out

FROM scratch
COPY --from=packages /out/ /
