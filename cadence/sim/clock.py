"""The only source of time inside core/. Never call datetime.now() in core/.

RealClock backs the live demo. VirtualClock backs eval mode and lets a 30-day
recovery campaign run in seconds — advance it in ticks, default one tick per
simulated day.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Protocol, runtime_checkable

# Every simulated "day" ticks at this UTC hour (11:30 IST) — safely inside
# business hours, so quiet-hours (21:00-09:00 IST) never blocks every single
# action purely because the clock happens to land at midnight.
SIMULATED_TIME_OF_DAY = time(6, 0)


def at_simulated_time(d) -> datetime:
    return datetime.combine(d, SIMULATED_TIME_OF_DAY, tzinfo=timezone.utc)


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class RealClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class VirtualClock:
    def __init__(self, start: datetime, tick: timedelta = timedelta(days=1)):
        if start.tzinfo is None:
            raise ValueError("VirtualClock start must be timezone-aware (UTC)")
        self._current = start
        self._tick = tick

    def now(self) -> datetime:
        return self._current

    def advance(self, ticks: int = 1) -> datetime:
        if ticks < 0:
            raise ValueError("VirtualClock cannot move backwards")
        self._current = self._current + (self._tick * ticks)
        return self._current

    def set(self, when: datetime) -> None:
        if when.tzinfo is None:
            raise ValueError("VirtualClock.set requires a timezone-aware datetime")
        if when < self._current:
            raise ValueError("VirtualClock cannot move backwards")
        self._current = when
