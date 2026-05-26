"""
ai-service/app/core/logging_config.py

Structured JSON logging for the AI service.
Replaces basicConfig with a JSON formatter so logs can be parsed by
Loki, ELK, or any log aggregator.

Usage:
    # In main.py and kafka_worker.py, replace:
    logging.basicConfig(level=..., format=...)
    # With:
    from app.core.logging_config import configure_logging
    configure_logging()

Every log record will include:
    timestamp, level, logger, message, service, version
    + any extra fields passed as kwargs to logger calls.

Example structured log record:
{
  "timestamp": "2025-01-01T00:00:00.000Z",
  "level": "INFO",
  "logger": "kafka_worker",
  "message": "Processing AI command GENERATE_QUIZ for job abc-123",
  "service": "ai-service",
  "version": "2.2.0",
  "job_id": "abc-123",
  "command_type": "GENERATE_QUIZ"
}
"""
from __future__ import annotations

import logging
import os
import sys

from app.core.config import get_settings

settings = get_settings()


def configure_logging() -> None:
    """
    Configure structured JSON logging for the application.
    Falls back to plain-text format if pythonjsonlogger is not installed
    (e.g. during local development without the package).
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    try:
        from pythonjsonlogger import jsonlogger

        class _BDCJsonFormatter(jsonlogger.JsonFormatter):
            def add_fields(self, log_record, record, message_dict):
                super().add_fields(log_record, record, message_dict)
                log_record["timestamp"] = self.formatTime(record, self.datefmt)
                log_record["level"]     = record.levelname
                log_record["logger"]    = record.name
                log_record["service"]   = "ai-service"
                log_record["version"]   = "2.2.0"
                # Remove redundant fields added by the base class
                log_record.pop("asctime",  None)
                log_record.pop("levelname", None)
                log_record.pop("name",      None)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_BDCJsonFormatter(
            fmt="%(timestamp)s %(level)s %(logger)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S.%fZ",
        ))

    except ImportError:
        # Fallback: human-readable format for local dev
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))

    root = logging.getLogger()
    root.setLevel(log_level)
    # Remove any handlers added by basicConfig calls elsewhere
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy in ("asyncio", "aiokafka.consumer.fetcher", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Filter out /health endpoint logs from uvicorn access logs
    class EndpointFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "/health" not in record.getMessage()

    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

    logging.getLogger(__name__).info(
        "Logging configured",
        extra={"log_level": settings.log_level, "json_logging": True},
    )
