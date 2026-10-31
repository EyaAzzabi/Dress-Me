# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# torch's 196MB CPU wheel reliably stalls mid-download from inside the Docker build
# (reproduced with plain network, --network=host, and increased pip timeouts/retries
# — the host's own network fetches the same URL at a steady ~110KB/s, so this is
# specific to the build's network path, not the file or the connection in general).
# Workaround: pre-fetch it on the host with curl (resumable, tolerates stalls) via
# `curl -L -C - --retry 50 ... -o backend/wheels/torch-....whl <url>`, then
# --find-links here makes pip use that local file instead of fetching it itself.
# --extra-index-url still pulls the CPU build (not pip's default GPU/CUDA one, which
# drags in ~1GB+ of unused nvidia_cudnn/nvidia_cublas/etc.) for anything not already
# satisfied locally.
COPY wheels ./wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --find-links ./wheels \
    -r requirements.txt

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

EXPOSE 8000
# Migrations run on every container start, not as a separate manual step — safe to
# repeat (alembic no-ops once the DB is already at head). Needs the `postgres`
# service reachable at startup, which depends_on in docker-compose.yml guarantees
# the container ordering for, though not that Postgres has finished its own init.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
