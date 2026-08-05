#!/bin/bash
# Launches Matama against a separate, throwaway test database
# (matama_test.db) instead of the real one — safe to click around,
# add/delete anything, break things. Never touches matama.db.
set -e
cd "$(dirname "$0")"

export MATAMA_DB_PATH="$(pwd)/matama_test.db"

.venv/bin/python scripts/seed_test_db.py
.venv/bin/python src/main.py
