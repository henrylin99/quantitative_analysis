"""Runtime compatibility helpers for local startup scripts."""


def ensure_click_parameter_source():
    """Backfill click.core.ParameterSource for older Click releases."""
    try:
        import click.core as click_core
    except Exception:
        return

    if hasattr(click_core, "ParameterSource"):
        return

    class ParameterSource:  # pragma: no cover - exercised via attribute checks
        COMMANDLINE = "COMMANDLINE"
        DEFAULT = "DEFAULT"
        DEFAULT_MAP = "DEFAULT_MAP"
        ENVIRONMENT = "ENVIRONMENT"
        PROMPT = "PROMPT"

    click_core.ParameterSource = ParameterSource
