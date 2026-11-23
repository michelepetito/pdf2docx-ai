"""Deterministic policy: local Xiaomi, MiniCPM, Apple Vision, then Tesseract."""
from .base import OCRUnavailableError
from .minicpm import MiniCPMOCR10Engine
from .tesseract import TesseractEngine
from .vision import AppleVisionEngine
from .xiaomi import XiaomiOCR0Engine

PRIORITY = ("xiaomi", "minicpm", "vision", "tesseract")
ENGINE_TYPES = {"xiaomi": XiaomiOCR0Engine, "minicpm": MiniCPMOCR10Engine,
                "vision": AppleVisionEngine, "tesseract": TesseractEngine}


def create_engine(name, settings):
    try:
        return ENGINE_TYPES[name](settings)
    except KeyError as exc:
        raise ValueError(f"Unknown OCR engine: {name}") from exc


def select_engine(settings):
    if settings.engine != "auto":
        if settings.engine == "compare":
            raise ValueError("Compare requires separate runs for Xiaomi and MiniCPM")
        return create_engine(settings.engine, settings)
    errors = []
    for name in PRIORITY:
        engine = create_engine(name, settings)
        health = engine.health_check()
        if health.get("available"):
            return engine
        errors.append(f"{name}: {health.get('reason', 'unavailable')}")
        engine.shutdown()
    raise OCRUnavailableError("No local OCR engine available. " + "; ".join(errors))


def engine_health(settings):
    results = {}
    for name in PRIORITY:
        engine = create_engine(name, settings)
        try:
            results[name] = engine.health_check()
        finally:
            engine.shutdown()
    return results

