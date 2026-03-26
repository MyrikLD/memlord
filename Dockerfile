# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Copy lockfile first for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project
# Download ONNX model files
COPY scripts/ scripts/
RUN pip install --no-cache-dir huggingface_hub && python scripts/download_model.py
# Copy source code
COPY src/ src/
COPY LICENSE* .
RUN uv sync --no-dev --frozen

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
# libgomp1 is required by onnxruntime
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY migrations/ migrations/
COPY alembic.ini alembic.ini
COPY scripts/ scripts/
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["memlord"]
