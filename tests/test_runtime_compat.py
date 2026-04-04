import importlib


def test_runtime_compat_restores_click_parameter_source(monkeypatch):
    click_core = importlib.import_module("click.core")
    had_original = hasattr(click_core, "ParameterSource")
    original = getattr(click_core, "ParameterSource", None)

    if had_original:
        monkeypatch.delattr(click_core, "ParameterSource")

    runtime_compat = importlib.import_module("runtime_compat")
    runtime_compat.ensure_click_parameter_source()

    assert hasattr(click_core, "ParameterSource")
    parameter_source = click_core.ParameterSource
    assert parameter_source.COMMANDLINE == "COMMANDLINE"
    assert parameter_source.DEFAULT == "DEFAULT"
    assert parameter_source.DEFAULT_MAP == "DEFAULT_MAP"
    assert parameter_source.ENVIRONMENT == "ENVIRONMENT"
    assert parameter_source.PROMPT == "PROMPT"

    if had_original:
        monkeypatch.setattr(click_core, "ParameterSource", original, raising=False)
