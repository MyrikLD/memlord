#!/bin/sh
set -e

alembic upgrade head

if [ "${REEMBED}" = "true" ] || [ "${REEMBED}" = "True" ] || [ "${REEMBED}" = "1" ]; then
    echo "REEMBED=true: re-embedding all memories..."
    python scripts/reembed.py
fi

exec "$@"
