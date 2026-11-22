FROM python:3.13.18-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72

COPY clusters/trust/containers/talos-kms/requirements.txt /tmp/kms-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: -r /tmp/kms-requirements.txt

WORKDIR /app
COPY scripts/homelab/__init__.py scripts/homelab/talos_kms_wire.py scripts/homelab/transit_kms.py scripts/homelab/transit_kms_service.py ./homelab/
USER 10001:10001
ENTRYPOINT ["python", "-B", "-m", "homelab.transit_kms_service"]
