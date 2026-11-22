"""Automated tests. Run from the repo root:

    uv run python -m unittest discover -s backend/tests -t backend

They need no network and no database. The Postgres tests skip unless TEST_DATABASE_URL is set;
see `test_link_postgres.py`.
"""

import os

# Importing src.database builds an engine from DATABASE_URL. An environment variable beats
# .env.local, so this makes it impossible for a test to reach the development database.
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@127.0.0.1:1/never_connect_test"
