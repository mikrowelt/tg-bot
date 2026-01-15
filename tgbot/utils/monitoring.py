"""Unified monitoring setup for Grafana Cloud (Prometheus + Loki)."""

import os

from .logger import setup_logger, configure_loki
from .metrics import configure_metrics, push_metrics

log = setup_logger("tg-bot.monitoring")


def init_monitoring(
    environment: str | None = None,
    profile_name: str | None = None,
) -> dict:
    """
    Initialize Grafana Cloud monitoring (metrics + logs).

    Reads configuration from environment variables:
        - GRAFANA_CLOUD_USER: Your Grafana Cloud instance ID
        - GRAFANA_CLOUD_API_KEY: Your Grafana Cloud API key
        - PROMETHEUS_PUSH_GATEWAY: Prometheus remote write URL
        - LOKI_URL: Loki push API URL
        - ENVIRONMENT: Environment name (default: development)

    Args:
        environment: Override ENVIRONMENT env var
        profile_name: Profile name to add to labels

    Returns:
        Dict with status of each component
    """
    env = environment or os.getenv("ENVIRONMENT", "development")

    status = {
        "metrics": False,
        "logs": False,
        "environment": env,
    }

    # Build additional labels
    labels = {"env": env}
    if profile_name:
        labels["profile"] = profile_name

    # Configure Prometheus metrics
    prometheus_url = os.getenv("PROMETHEUS_PUSH_GATEWAY")
    if prometheus_url:
        configure_metrics(
            push_gateway_url=prometheus_url,
            job_name=f"tg-bot-{env}",
        )
        status["metrics"] = True
        log.info(f"Prometheus metrics enabled: {prometheus_url}")
    else:
        log.debug("PROMETHEUS_PUSH_GATEWAY not set, metrics disabled")

    # Configure Loki logs
    loki_url = os.getenv("LOKI_URL")
    if loki_url:
        success = configure_loki(
            loki_url=loki_url,
            additional_labels=labels,
        )
        status["logs"] = success
        if success:
            log.info(f"Loki logging enabled: {loki_url}")
    else:
        log.debug("LOKI_URL not set, Loki logging disabled")

    if status["metrics"] or status["logs"]:
        log.info(f"Monitoring initialized for environment: {env}")
    else:
        log.info("No monitoring configured (set PROMETHEUS_PUSH_GATEWAY and/or LOKI_URL)")

    return status


def shutdown_monitoring():
    """
    Flush and shutdown monitoring.
    Call this before process exit to ensure all metrics/logs are sent.
    """
    log.debug("Shutting down monitoring...")
    push_metrics()
    log.debug("Monitoring shutdown complete")
