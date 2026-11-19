FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends libseccomp2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY bots.py geometry.py protocol.py runner.py worker.py /app/backend/training/
USER 65532:65532
ENTRYPOINT ["python", "-B", "-m", "backend.training.runner"]
