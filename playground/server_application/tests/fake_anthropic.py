"""A scripted stand-in for Anthropic, shared by the chat tests. No test calls a real model.

The use_fake fixture in conftest.py installs one of these. Keeping the class here and the fixture
there means a test module can import the helpers without redefining the fixture.
"""

from types import SimpleNamespace
from typing import Any

URL = "/api/v1/sandbox/chat/suggest"


def tool_use(name: str, arguments: dict[str, Any], use_id: str = "toolu_1") -> SimpleNamespace:
    """A tool_use content block, shaped like the SDK's."""
    return SimpleNamespace(type="tool_use", id=use_id, name=name, input=arguments)


def reply(*blocks: SimpleNamespace) -> SimpleNamespace:
    """One Messages API response."""
    return SimpleNamespace(content=list(blocks))


def text(value: str) -> SimpleNamespace:
    """A text content block."""
    return SimpleNamespace(type="text", text=value)


class FakeAnthropic:
    """Returns scripted responses in order and records every request."""

    def __init__(self, *responses: SimpleNamespace):
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.messages = self

    async def create(self, **request: Any) -> SimpleNamespace:
        """Record the request and return the next scripted response."""
        self.requests.append(request)
        return self.responses.pop(0)
