from abc import ABC, abstractmethod
from PIL import Image
from pdf2docx_ai.document.models import Region


class LayoutDetector(ABC):
    """A detector returns image-pixel boxes; caller transforms them to PDF points."""

    @abstractmethod
    def detect(self, image: Image.Image, page_number: int = 1) -> list[Region]:
        pass

    def shutdown(self):
        pass

