from dataclasses import dataclass, field
from typing import Any


@dataclass
class Request:
    messages: list[dict]
    schema: dict
    sources: list[dict]
    max_output_tokens: int = 2000
    context_window: int = 8192
    temperature: float = 0
    has_history: bool = False


@dataclass
class Reply:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    reported: dict = field(default_factory=dict)


class ProviderError(Exception):
    def __init__(self, code, *, status=None, retry_after=None, reported=None):
        # Only controlled codes; never retain provider bodies, prompts or credentials.
        self.code, self.status = code, status
        self.retry_after, self.reported = retry_after, reported or {}
        super().__init__(code)


class Generated(dict):
    """Metadata is outside schema data, preserving existing strict validators."""
    def __init__(self, value: dict[str, Any], generation: dict):
        super().__init__(value)
        self.generation = generation


def metadata(value):
    return getattr(value, 'generation', None)
