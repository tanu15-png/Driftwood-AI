"""Shared test setup."""

import os

# Settings fail fast on a missing OPENAI_API_KEY (the ingest scripts need
# it), but unit tests never call OpenAI. A placeholder keeps the fast suite
# runnable on machines whose backend/.env predates the key; a real value in
# .env or the shell takes precedence.
os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-unit-tests")
