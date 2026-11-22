ARG PYTHON_IMAGE=python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
FROM --platform=$BUILDPLATFORM ${PYTHON_IMAGE} AS wheels
ARG TARGETARCH

COPY clusters/trust/containers/talos-kms/requirements.txt /tmp/kms-requirements.txt
# Select target wheels without executing the target architecture during the build.
RUN case "$TARGETARCH" in \
      amd64) wheel_arch=x86_64 ;; \
      arm64) wheel_arch=aarch64 ;; \
      *) echo "Unsupported KMS image architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac && python -m pip install --no-cache-dir --no-compile --only-binary=:all: \
      --platform "manylinux2014_$wheel_arch" --implementation cp \
      --python-version 3.13 --abi cp313 --target /opt/kms-deps \
      -r /tmp/kms-requirements.txt

FROM ${PYTHON_IMAGE}
COPY --from=wheels /opt/kms-deps /opt/kms-deps
ENV PYTHONPATH=/opt/kms-deps

WORKDIR /app
COPY scripts/homelab/__init__.py scripts/homelab/talos_kms_wire.py scripts/homelab/transit_kms.py scripts/homelab/transit_kms_service.py ./homelab/
USER 10001:10001
ENTRYPOINT ["python", "-B", "-m", "homelab.transit_kms_service"]
