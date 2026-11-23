from abc import ABC, abstractmethod

from PIL import Image

from pdf2docx_ai.document.models import OCRResult


class OCRUnavailableError(RuntimeError):
    """The selected runtime or locally installed model is unavailable."""


class OCREngine(ABC):
    name = "abstract"

    @abstractmethod
    def initialize(self) -> None:
        """Prepare an already installed local engine, without downloading files."""

    @abstractmethod
    def recognize(self, image: Image.Image, region_type: str = "text", language: str = "it") -> OCRResult:
        """Read a crop without translating it; returned boxes are crop pixels."""

    @abstractmethod
    def health_check(self) -> dict:
        """Read availability without loading model weights."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release resources owned by this adapter."""

