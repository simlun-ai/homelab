# syntax=docker/dockerfile:1
FROM ubuntu:26.04 AS base
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /project
RUN rm -f /etc/apt/apt.conf.d/docker-clean
RUN --mount=type=cache,id=homelab-ci-apt-packages,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=homelab-ci-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates git make python3 python3-venv

FROM base AS helper-tools
RUN --mount=type=cache,id=homelab-ci-apt-packages,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=homelab-ci-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev swig pkg-config libpcsclite-dev
COPY --link support/yubikey/Makefile support/yubikey/requirements.txt ./support/yubikey/
COPY --link tools/homelab-hsm/homelab_secrets/pyproject.toml ./tools/homelab-hsm/homelab_secrets/
COPY --link tools/homelab-hsm/homelab_secrets/src/ ./tools/homelab-hsm/homelab_secrets/src/
RUN --mount=type=cache,id=homelab-ci-helper-pip,target=/root/.cache/pip,sharing=locked \
    make -C support/yubikey tools

FROM helper-tools AS helpers
COPY --link scripts/ ./scripts/
COPY --link tests/ ./tests/
COPY --link secrets/manifest.json ./secrets/manifest.json
COPY --link tools/homelab-hsm/homelab_secrets/scripts/ ./tools/homelab-hsm/homelab_secrets/scripts/
COPY --link tools/homelab-hsm/homelab_secrets/tests/ ./tools/homelab-hsm/homelab_secrets/tests/
RUN --network=none test ! -e secrets/wrapped && \
    support/yubikey/.venv/bin/python -m pip check && \
    make -C support/yubikey test

FROM base AS ups-tools
COPY --link support/ups/Makefile support/ups/requirements.txt support/ups/check-tools.py support/ups/ansible.cfg ./support/ups/
RUN --mount=type=cache,id=homelab-ci-ups-pip,target=/root/.cache/pip,sharing=locked \
    make -C support/ups tools

FROM ups-tools AS ups
COPY --link support/ups/inventory.yaml ./support/ups/inventory.yaml
COPY --link support/ups/ansible/ ./support/ups/ansible/
RUN --network=none make -C support/ups check-tools inventory syntax

FROM base AS syntax
COPY --link scripts/ ./scripts/
COPY --link tests/ ./tests/
COPY --link support/ ./support/
COPY --link ci/check-syntax.py ./ci/check-syntax.py
RUN --network=none python3 -I -B ci/check-syntax.py

FROM base AS lint-tools
RUN --mount=type=cache,id=homelab-ci-ruff-pip,target=/root/.cache/pip,sharing=locked \
    python3 -m venv /ruff && /ruff/bin/python -m pip install ruff==0.17.2
ENV PATH="/ruff/bin:$PATH"

FROM lint-tools AS lint
COPY --link pyproject.toml ./
COPY --link scripts/ ./scripts/
COPY --link tests/ ./tests/
COPY --link support/ ./support/
COPY --link ci/check-syntax.py ./ci/check-syntax.py
RUN --network=none ruff check --no-cache scripts tests support ci && \
    ruff format --check --no-cache scripts tests support ci

# Match the component's pinned checker and JavaScript runtime.
FROM node:24.19.0-bookworm-slim AS pyright-node
RUN npm install --global pyright@1.1.414

FROM helper-tools AS typecheck
COPY --from=pyright-node /usr/local/bin/node /usr/local/bin/node
COPY --from=pyright-node /usr/local/lib/node_modules/pyright /opt/pyright
COPY --link pyproject.toml ./
COPY --link scripts/ ./scripts/
COPY --link tests/ ./tests/
COPY --link support/ ./support/
COPY --link ci/check-syntax.py ./ci/check-syntax.py
RUN --network=none node /opt/pyright/index.js --pythonpath support/yubikey/.venv/bin/python
