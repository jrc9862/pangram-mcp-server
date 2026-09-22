"""Logging setup. Logs go to stderr so they never corrupt the stdio transport."""

import logging
import sys

_NOISY_LOGGERS = ("asyncio", "httpx", "httpcore", "mcp", "sse_starlette", "uvicorn")


def configure_logging(level: str = "WARNING") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    if level != "DEBUG":
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)
