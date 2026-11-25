"""A per-client cap on chat questions, because a keyword click is one click from a model call.

Fixed windows held in this process. One Vercel instance has its own counters, so the cap is per
instance, not per deployment. That is enough to stop a stuck client or a demo running away with
the budget, and it is not a defence against someone deliberately spreading requests around.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import Request

# A person reading a page asks a few questions a minute. These leave room for that and for a
# couple of people sharing a screen, and still cap a loop.
PER_MINUTE = 10
PER_HOUR = 100

MINUTE = 60.0
HOUR = 3600.0


@dataclass
class Limiter:
    """Question times per client, newest last, trimmed to the hour on every check."""

    asked: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, client: str, now: float | None = None) -> int | None:
        """Seconds to wait when the client is over a cap, or None when the question may go ahead.

        Records the question when it is allowed, so a refused question does not count against the
        caller twice.
        """
        now = time.monotonic() if now is None else now
        times = self.asked[client]
        while times and now - times[0] >= HOUR:
            times.popleft()

        in_minute = sum(1 for at in times if now - at < MINUTE)
        if in_minute >= PER_MINUTE:
            oldest_in_minute = next(at for at in times if now - at < MINUTE)
            return _seconds_until(oldest_in_minute + MINUTE, now)
        if len(times) >= PER_HOUR:
            return _seconds_until(times[0] + HOUR, now)

        times.append(now)
        return None

    def forget(self, client: str | None = None) -> None:
        """Drop one client's history, or everyone's. For tests."""
        if client is None:
            self.asked.clear()
        else:
            self.asked.pop(client, None)


def _seconds_until(deadline: float, now: float) -> int:
    """Whole seconds until a window frees up, at least 1 so Retry-After is never 0."""
    return max(1, int(deadline - now + 0.999))


limiter = Limiter()


def client_key(request: Request) -> str:
    """Who to count against: the first forwarded address when behind a proxy, else the socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
