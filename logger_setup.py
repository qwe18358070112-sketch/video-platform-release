from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from common import LoggingConfig


def setup_logger(logging_config: LoggingConfig, base_dir: Path) -> logging.Logger:
    raw_log_dir = Path(logging_config.log_dir)
    log_dir = raw_log_dir if raw_log_dir.is_absolute() else (base_dir / raw_log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("video_auto_poll")
    logger.setLevel(getattr(logging, logging_config.level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_dir / "video_auto_poll.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if logging_config.keep_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
