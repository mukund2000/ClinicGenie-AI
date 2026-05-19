import json
import logging
import os
import time
from collections import defaultdict
from functools import wraps
from threading import Lock
from typing import Any, Callable, Optional


LOG_LEVEL = os.getenv("CLINICGENIE_LOG_LEVEL", "INFO").upper()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STANDARD_LOG_RECORD_KEYS:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


_STANDARD_LOG_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setFormatter(JsonFormatter())
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)


configure_logging()


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._durations_ms: dict[str, list[float]] = defaultdict(list)
        self.started_at = time.time()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def observe_duration(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self._durations_ms[name].append(duration_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = {
                name: _summarize_durations(values)
                for name, values in self._durations_ms.items()
            }
            return {
                "uptime_seconds": round(time.time() - self.started_at, 3),
                "counters": dict(self._counters),
                "durations_ms": durations,
            }


def _summarize_durations(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0}

    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


metrics = MetricsRegistry()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def observe_operation(
    *,
    layer: str,
    operation: Optional[str] = None,
    logger_name: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        operation_name = operation or func.__name__
        logger = get_logger(logger_name or layer)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started_at = time.perf_counter()
            metric_prefix = f"{layer}.{operation_name}"
            metrics.increment(f"{metric_prefix}.started")
            logger.info(
                "operation_started",
                extra={"layer": layer, "operation": operation_name},
            )
            try:
                result = func(*args, **kwargs)
            except Exception:
                duration_ms = (time.perf_counter() - started_at) * 1000
                metrics.increment(f"{metric_prefix}.failed")
                metrics.observe_duration(f"{metric_prefix}.duration_ms", duration_ms)
                logger.exception(
                    "operation_failed",
                    extra={
                        "layer": layer,
                        "operation": operation_name,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
                raise

            duration_ms = (time.perf_counter() - started_at) * 1000
            metrics.increment(f"{metric_prefix}.succeeded")
            metrics.observe_duration(f"{metric_prefix}.duration_ms", duration_ms)
            logger.info(
                "operation_succeeded",
                extra={
                    "layer": layer,
                    "operation": operation_name,
                    "duration_ms": round(duration_ms, 3),
                    "result_count": _result_count(result),
                },
            )
            return result

        return wrapper

    return decorator


def _result_count(result: Any) -> Optional[int]:
    if isinstance(result, (list, tuple, set, dict)):
        return len(result)
    return None
