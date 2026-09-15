"""The existing model boundary used by the concrete SessionDriver."""
from typing import Protocol


class ModelAdapter(Protocol):
    identity: dict

    def count_tokens(self, messages: list[dict]) -> int: ...

    def generate(self, messages: list[dict], max_new_tokens: int, seed: int) -> dict: ...
