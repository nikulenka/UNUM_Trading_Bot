import sys
from logging.config import dictConfig


def setup_logging(log_level: str = "INFO") -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "default",
                }
            },
            "root": {
                "level": log_level.upper(),
                "handlers": ["console"],
            },
            "loggers": {
                "uvicorn": {
                    "level": log_level.upper(),
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": log_level.upper(),
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": log_level.upper(),
                    "handlers": ["console"],
                    "propagate": False,
                },
            },
        }
    )