"""Structured logging setup — consistent format, module name, level from settings."""
from __future__ import annotations

import logging
import sys

from utils.config import get_settings

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        settings = get_settings()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(settings.log_level.upper())
        _configured = True
    return logging.getLogger(name)
