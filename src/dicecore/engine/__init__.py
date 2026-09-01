"""Engines, and the one function that picks one from the settings."""

from __future__ import annotations

from ..config import Settings
from .base import Engine, EngineError
from .classic import ClassicEngine

#: What the UI offers.
MODES = (
    ("auto", "Automatic — the trained model if there is one, otherwise classic"),
    ("classic", "Classic image processing — pips only, no training needed"),
    ("model", "Trained model — reads numerals too"),
    ("remote", "Another DiceCore node does the reading"),
)


def build_engine(settings: Settings) -> Engine:
    """
    Build the configured engine.

    `auto` falls back; the explicit modes do not. Asking for `model` and silently getting
    `classic` would mean numerals stop being read with no visible reason — the UI has to be
    able to say *why* a mode is unavailable, and it can only do that if this raises.
    """
    mode = settings.engine.mode
    if mode == "remote":
        from .remote import RemoteEngine

        return RemoteEngine(settings.engine.remote_url, settings.engine.remote_timeout_s,
                            settings.capture.jpeg_quality)
    if mode == "model":
        from .model import ModelEngine

        return ModelEngine(settings)
    if mode == "classic":
        return ClassicEngine(settings)
    if mode == "auto":
        from .model import ModelEngine, find_model

        if find_model(settings) is not None:
            try:
                return ModelEngine(settings)
            except EngineError:
                pass  # no onnxruntime here, or a broken bundle — classic still works
        return ClassicEngine(settings)
    raise EngineError(f"Unknown engine mode {mode!r}. One of: "
                      + ", ".join(name for name, _ in MODES))


__all__ = ["Engine", "EngineError", "ClassicEngine", "MODES", "build_engine"]
