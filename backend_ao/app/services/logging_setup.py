"""Logs lisibles dans docker logs / terminal (API et worker)."""

import logging
import sys


class _FlushHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def configure_logging(level: int = logging.INFO) -> None:
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    handler = _FlushHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("arq").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
