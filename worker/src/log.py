import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the worker logger."""
    logger = logging.getLogger("bsnexus.worker")
    if logger.handlers:
        return logger

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


log = setup_logging()
