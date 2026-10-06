from typing import Protocol


class SourceError(Exception):
    """A sanitised error safe to display; never include upstream bodies or secrets."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ReadOnlySource(Protocol):
    async def check_access(self, commit: str = '') -> dict: ...
    async def begin_snapshot(self) -> dict: ...
    async def list_files(self, cursor: int = 0) -> dict: ...
    async def read_file(self, path: str) -> dict: ...
