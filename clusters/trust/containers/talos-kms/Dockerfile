FROM python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

COPY clusters/trust/containers/talos-kms/requirements.txt /tmp/kms-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: -r /tmp/kms-requirements.txt

WORKDIR /app
COPY scripts/homelab/__init__.py scripts/homelab/talos_kms_wire.py scripts/homelab/transit_kms.py scripts/homelab/transit_kms_service.py ./homelab/
USER 10001:10001
ENTRYPOINT ["python", "-B", "-m", "homelab.transit_kms_service"]
