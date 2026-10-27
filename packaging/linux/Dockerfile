# syntax=docker/dockerfile:1.7
# Linux packages from one self-contained build: .deb, .rpm, Arch and a portable tarball.
#
#   docker build -f packaging/linux/Dockerfile --output type=local,dest=dist/linux .
#
# The app is frozen with its own Python and Qt on Ubuntu 22.04 (glibc 2.35), so the same build
# runs on Ubuntu 22.04+, Debian 12+, Fedora, openSUSE, Arch and their derivatives.

# ---- 1. Web UI ----------------------------------------------------------------------------
FROM node:22-bookworm-slim AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Vite writes the bundle to /src/rgcopy/web/dist
RUN npm run build

# ---- 2. The app with its own Python, dependencies and Qt web view (PyInstaller) ------------
FROM ubuntu:22.04 AS bundle
ARG DEBIAN_FRONTEND=noninteractive
# Python 3.12 with its shared library (PyInstaller needs it) from the deadsnakes PPA, plus
# binutils for PyInstaller and the libraries it resolves Qt against (the spec then leaves out
# the ones every desktop provides)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF23C5A6CF475977595C89F51BA6932366A755776" \
      | gpg --dearmor -o /usr/share/keyrings/deadsnakes.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/deadsnakes.gpg] http://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu jammy main" \
      > /etc/apt/sources.list.d/deadsnakes.list \
 && apt-get update && apt-get install -y --no-install-recommends python3.12 python3.12-dev python3.12-venv binutils \
      libasound2 libdbus-1-3 libegl1 libfontconfig1 libgbm1 libgl1 libglib2.0-0 libnss3 \
      libwayland-client0 libwayland-cursor0 libwayland-egl1 libxcb-cursor0 libxcb-icccm4 \
      libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
      libxcb-xinerama0 libxcb-xkb1 libxcomposite1 libxdamage1 libxkbcommon-x11-0 libxkbcommon0 \
      libxkbfile1 libxrandr2 libxshmfence1 libxtst6 \
 && rm -rf /var/lib/apt/lists/* \
 && python3.12 -m venv /venv
ENV PATH=/venv/bin:$PATH
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY rgcopy ./rgcopy
COPY --from=ui /src/rgcopy/web/dist ./rgcopy/web/dist
RUN pip install --no-cache-dir ".[desktop]" "pyinstaller>=6.10,<7"
COPY packaging/linux/rgcopy.spec packaging/linux/launcher.py ./packaging/linux/
RUN cd packaging/linux \
 && pyinstaller --noconfirm --clean --distpath /dist --workpath /tmp/pyinstaller rgcopy.spec \
 && /dist/rgcopy/rgcopy --version

# ---- 3. Packages ----------------------------------------------------------------------------
FROM golang:1.26-bookworm AS packages
RUN go install github.com/goreleaser/nfpm/v2/cmd/nfpm@v2.47.0
RUN apt-get update && apt-get install -y --no-install-recommends appstream desktop-file-utils librsvg2-bin \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /pkg
COPY packaging/linux/ ./
COPY LICENSE rgcopy/assets/rgcopy.svg ./
COPY --from=bundle /dist/rgcopy ./rgcopy
RUN ./package.sh /out

FROM scratch
COPY --from=packages /out/ /
