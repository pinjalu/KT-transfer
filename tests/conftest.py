"""The regression suite must never use the live embedding model from .env."""
import pytest


@pytest.fixture(autouse=True)
def isolated_embeddings(monkeypatch):
    # Set this in Python: Windows PowerShell removes empty environment variables,
    # which otherwise lets load_dotenv enable the user's live Ollama model.
    # Embedding-specific tests opt in with their own mocked model and vectors.
    monkeypatch.setenv('PKA_EMBED_MODEL', '')


@pytest.fixture(autouse=True)
def isolated_activity_log(monkeypatch, tmp_path):
    # Standalone service tests have no HTTP workspace context. Keep their
    # operational events out of the user's real activity file.
    from pka import monitoring
    original = monitoring.path
    def target(index_path=None):
        if index_path is None and monitoring._context.get() is None:
            return tmp_path/'logs'/'activity.jsonl'
        return original(index_path)
    monkeypatch.setattr(monitoring, 'path', target)
