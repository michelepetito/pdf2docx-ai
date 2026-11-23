"""Optional PP-DocLayoutV3 PaddleX adapter, requiring existing local weights."""
from __future__ import annotations
import importlib.util
import os
import re
from pathlib import Path
import numpy as np
from PIL import Image
from pdf2docx_ai.document.models import BBox, Region
from .base import LayoutDetector

_LABELS = {"doc_title": "title", "document_title": "title", "paragraph_title": "title",
           "table": "table", "image": "image", "figure": "image", "chart": "image",
           "display_formula": "formula", "formula": "formula", "inline_formula": "formula",
           "header": "header", "header_image": "image", "footer": "footer", "number": "footer",
           "footer_image": "image", "figure_title": "caption", "table_title": "caption"}


class PPDocLayoutDetector(LayoutDetector):
    name = "ppdoclayoutv3"

    def __init__(self, model_dir: Path | str | None = None, threshold: float = .3, device: str = "cpu"):
        self.model_dir = Path(model_dir).resolve() if model_dir else None
        self.threshold = threshold
        if device != "cpu":
            raise ValueError("This adapter currently verifies only the Paddle CPU API contract")
        self.device = device
        self.model = None

    def health_check(self):
        missing = [name for name in ("paddle", "paddlex") if importlib.util.find_spec(name) is None]
        weights = bool(self.model_dir and (self.model_dir / "inference.pdiparams").is_file()
                       and (self.model_dir / "inference.yml").is_file())
        return {"available": not missing and weights, "engine": self.name,
                "reason": None if not missing and weights else
                f"Requires local PP-DocLayoutV3 inference directory and paddle/paddlex; missing {missing}",
                "inference_verified": False}

    def initialize(self):
        if self.model is not None:
            return
        if not self.health_check()["available"]:
            raise RuntimeError(self.health_check()["reason"])
        config = (self.model_dir / "inference.yml").read_text(encoding="utf-8")
        names = re.findall(r"(?m)^\s*model_name\s*:\s*['\"]?([^\s'\"#]+)", config)
        if not names or any(name != "PP-DocLayoutV3" for name in names):
            raise ValueError("Local layout configuration must identify PP-DocLayoutV3")
        # Upstream reads this process-local flag at import. It avoids the
        # optional network reachability check; all model files are local.
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["HF_HUB_OFFLINE"] = "1"
        from paddlex import create_model
        # Providing a validated local directory prevents first-use model pulls.
        self.model = create_model(model_name="PP-DocLayoutV3", model_dir=str(self.model_dir),
                                  device=self.device, threshold=self.threshold)

    def detect(self, image: Image.Image, page_number: int = 1) -> list[Region]:
        self.initialize()
        bgr = np.ascontiguousarray(np.asarray(image.convert("RGB"))[:, :, ::-1])
        results = list(self.model.predict(bgr, batch_size=1))
        if not results:
            return []
        result = results[0]
        boxes = result.get("boxes", [])
        if not boxes and isinstance(result.get("res"), dict):
            boxes = result["res"].get("boxes", [])
        regions = []
        for index, box in enumerate(boxes):
            label = str(box["label"])
            x0, y0, x1, y1 = (float(x) for x in box["coordinate"])
            x0, x1 = max(0, x0), min(image.width, x1)
            y0, y1 = max(0, y0), min(image.height, y1)
            if x1 <= x0 or y1 <= y0:
                continue
            regions.append(Region(page_number=page_number, kind=_LABELS.get(label, "text"),
                                  bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), source="ocr",
                                  confidence=float(box["score"]), reading_order=index,
                                  metadata={"layout_detector": self.name, "label": label,
                                            "coordinate_space": "pixels",
                                            "polygon": np.asarray(box.get("polygon_points", [])).tolist()}))
        return regions

    def shutdown(self):
        self.model = None

