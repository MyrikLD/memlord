FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

# Copy lockfile first for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project
# Copy source code
COPY src/ src/
COPY LICENSE* README.md ./
RUN uv sync --no-dev --frozen

FROM python:3.12-slim AS runtime

ARG VERSION=0.0.0
LABEL org.opencontainers.image.version="${VERSION}"

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
