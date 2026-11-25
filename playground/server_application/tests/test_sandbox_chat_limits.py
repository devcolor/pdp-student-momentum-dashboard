"""The chat's rate limit and its own on/off flag.

The limiter is checked both directly, where the clock can be moved, and through the endpoint,
where the 429 and its Retry-After header are what a client sees.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.sandbox.chat import rate_limit
from app.sandbox.chat.rate_limit import HOUR, MINUTE, PER_HOUR, PER_MINUTE, Limiter
from tests.fake_anthropic import URL, reply, text

QUESTION = "What is retention?"


# The limiter on its own, with the clock in hand


def test_questions_up_to_the_minute_cap_are_allowed() -> None:
    limiter = Limiter()

    waits = [limiter.check("a", now=100.0) for _ in range(PER_MINUTE)]

    assert waits == [None] * PER_MINUTE


def test_one_over_the_minute_cap_says_how_long_to_wait() -> None:
    limiter = Limiter()
    for _ in range(PER_MINUTE):
        limiter.check("a", now=100.0)

    assert limiter.check("a", now=100.0) == int(MINUTE)


def test_the_minute_window_frees_up() -> None:
    limiter = Limiter()
    for _ in range(PER_MINUTE):
        limiter.check("a", now=100.0)

    assert limiter.check("a", now=100.0 + MINUTE) is None


def test_a_refused_question_is_not_counted() -> None:
    """Otherwise a client that keeps asking would push its own window further out."""
    limiter = Limiter()
    for _ in range(PER_MINUTE):
        limiter.check("a", now=100.0)
    for _ in range(5):
        limiter.check("a", now=100.0)

    assert limiter.check("a", now=100.0 + MINUTE) is None


def test_clients_are_counted_apart() -> None:
    limiter = Limiter()
    for _ in range(PER_MINUTE):
        limiter.check("a", now=100.0)

    assert limiter.check("b", now=100.0) is None


def test_the_hour_cap_holds_when_the_minutes_are_spread_out() -> None:
    limiter = Limiter()
    # Two a minute never trips the minute cap, and all of them stay inside the hour window.
    spacing = MINUTE / 2
    for step in range(PER_HOUR):
        assert limiter.check("a", now=100.0 + step * spacing) is None

    wait = limiter.check("a", now=100.0 + PER_HOUR * spacing)

    assert wait is not None and wait <= int(HOUR)


def test_a_wait_is_never_zero_seconds() -> None:
    """Retry-After: 0 would invite an immediate retry that is still refused."""
    limiter = Limiter()
    for _ in range(PER_MINUTE):
        limiter.check("a", now=100.0)

    assert limiter.check("a", now=100.0 + MINUTE - 0.0001) == 1


# Through the endpoint


def test_too_many_questions_returns_429_with_retry_after(client: TestClient, use_fake) -> None:
    use_fake(*[reply(text("Retention is 58.7%."))] * (PER_MINUTE + 1))

    for _ in range(PER_MINUTE):
        assert client.post(URL, json={"prompt": QUESTION}).status_code == 200

    refused = client.post(URL, json={"prompt": QUESTION})

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1
    assert "Try again in" in refused.json()["error"]["message"]


def test_a_question_with_no_key_does_not_use_up_the_allowance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 503 comes first, so a misconfigured server does not also look rate limited."""
    # Without this the configured development key is used and the question reaches a real model.
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    for _ in range(PER_MINUTE + 2):
        assert client.post(URL, json={"prompt": QUESTION}).status_code == 503

    assert rate_limit.limiter.check("testclient") is None


def test_an_invalid_body_does_not_use_up_the_allowance(client: TestClient, use_fake) -> None:
    use_fake(reply(text("unused")))

    for _ in range(PER_MINUTE + 2):
        assert client.post(URL, json={"prompt": ""}).status_code == 422

    assert rate_limit.limiter.check("testclient") is None


# Which client the count is kept against


def test_a_forwarded_address_is_counted_before_the_socket(client: TestClient, use_fake) -> None:
    use_fake(*[reply(text("Retention is 58.7%."))] * 2)

    client.post(URL, json={"prompt": QUESTION}, headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})

    # Counted against the first forwarded address, not the test client's socket.
    assert rate_limit.limiter.check("1.2.3.4") is None
    assert len(rate_limit.limiter.asked["1.2.3.4"]) == 2


# The flag


def sandbox_paths() -> set[str]:
    """The sandbox paths a client would see, with the flag as it stands now."""
    from fastapi import FastAPI

    from app.sandbox import router as sandbox

    app = FastAPI()
    app.include_router(sandbox.build_sandbox_router())
    return set(app.openapi()["paths"])


def test_the_chat_is_absent_when_its_flag_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """The router is built at import, so this checks the flag the builder reads."""
    monkeypatch.setattr(settings, "SANDBOX_CHAT_ENABLED", False)

    paths = sandbox_paths()

    assert not any("/chat/" in path for path in paths)
    assert any("/executive-view/" in path for path in paths)


def test_the_chat_is_present_when_its_flag_is_on() -> None:
    assert "/sandbox/chat/suggest" in sandbox_paths()
