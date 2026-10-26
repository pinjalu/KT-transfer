"""The regression suite must never use the live embedding model from .env."""
import pytest


@pytest.fixture(autouse=True)
def isolated_embeddings(monkeypatch):
    # Set this in Python: Windows PowerShell removes empty environment variables,
    # which otherwise lets load_dotenv enable the user's live Ollama model.
    # Embedding-specific tests opt in with their own mocked model and vectors.
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
