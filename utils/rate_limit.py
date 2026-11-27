import threading
import time
from collections import deque
from typing import Dict, Optional

from utils.logger import get_logger


class RateLimitGuard:
    """按接口维护滑动窗口，发请求前主动等待，避免触发服务端 429。"""

    def __init__(
        self,
        limits: Dict[str, int],
        window_seconds: float = 60,
        buffer_seconds: float = 0.5,
        enabled: bool = True,
    ):
        self.limits = {key: int(value) for key, value in limits.items()}
        self.window_seconds = float(window_seconds)
        self.buffer_seconds = float(buffer_seconds)
        self.enabled = bool(enabled)
        self._events = {
            key: deque() for key, limit in self.limits.items() if limit > 0
        }
        self._lock = threading.Lock()
        self.logger = get_logger("rate_limit")

    def wait(self, key: Optional[str]) -> None:
        limit = self.limits.get(key or "", 0)
        if not self.enabled or limit <= 0 or self.window_seconds <= 0:
            return

        with self._lock:
            while True:
                now = time.monotonic()
                events = self._events[key]
                # 先移出窗口外的请求，再判断当前配额。
                while events and now - events[0] >= self.window_seconds:
                    events.popleft()

                if len(events) < limit:
                    events.append(now)
                    return

                # 等待最早一条记录过期，再加上缓冲时间。
                delay = self.window_seconds - (now - events[0]) + self.buffer_seconds
                self.logger.info(
                    "RATE_LIMIT_WAIT key=%s limit=%s/%ss wait=%.1fs",
                    key,
                    limit,
                    self.window_seconds,
                    delay,
                )
                time.sleep(max(delay, 0.01))


def build_rate_limit_guard(config: dict) -> RateLimitGuard:
    return RateLimitGuard(
        limits={
            "register": config.get("register_per_minute", 0),
            "login": config.get("login_per_minute", 0),
            "me": config.get("me_per_minute", 0),
        },
        window_seconds=config.get("window_seconds", 60),
        buffer_seconds=config.get("buffer_seconds", 0.5),
        enabled=config.get("enabled", True),
    )
