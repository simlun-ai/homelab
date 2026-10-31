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
ENV HSM_VENV=/opt/homelab-hsm
COPY --link support/hsm/Makefile ./support/hsm/
COPY --link tools/homelab-hsm/homelab_secrets/ ./tools/homelab-hsm/homelab_secrets/
RUN --network=none make -C support/hsm tools

FROM helper-tools AS helpers
COPY --link scripts/ ./scripts/
COPY --link tests/ ./tests/
COPY --link secrets/manifest.json ./secrets/manifest.json
COPY --link tools/homelab-hsm/homelab_secrets/scripts/ ./tools/homelab-hsm/homelab_secrets/scripts/
COPY --link tools/homelab-hsm/homelab_secrets/tests/ ./tools/homelab-hsm/homelab_secrets/tests/
RUN --network=none test ! -e secrets/wrapped && \
    /opt/homelab-hsm/bin/python -m pip check && \
    make -C support/hsm test

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
RUN --network=none node /opt/pyright/index.js --pythonpath /opt/homelab-hsm/bin/python

FROM base AS ansible-lint-tools
COPY --link support/ups/requirements.txt ./support/ups/requirements.txt
COPY --link ci/ansible-lint-requirements.txt ./ci/ansible-lint-requirements.txt
RUN --mount=type=cache,id=homelab-ci-ansible-lint-pip,target=/root/.cache/pip,sharing=locked \
    python3 -m venv /ansible-lint && \
    /ansible-lint/bin/python -m pip install \
      -r support/ups/requirements.txt -r ci/ansible-lint-requirements.txt && \
    /ansible-lint/bin/python -m pip check
ENV PATH="/ansible-lint/bin:$PATH"

FROM ansible-lint-tools AS ansible-lint
COPY --link support/ups/ansible.cfg support/ups/inventory.yaml support/ups/.ansible-lint ./support/ups/
COPY --link support/ups/ansible/ ./support/ups/ansible/
ENV ANSIBLE_CONFIG="/project/support/ups/ansible.cfg" \
    ANSIBLE_LOCAL_TEMP="/project/support/ups/.ansible/tmp"
RUN --network=none cd support/ups && ansible-lint --offline ansible inventory.yaml
