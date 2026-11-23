from pathlib import Path
from pydantic import BaseModel, Field
from typing import Literal


class Settings(BaseModel):
    engine: Literal["auto", "xiaomi", "minicpm", "tesseract", "vision", "compare"] = "auto"
    mode: Literal["editable", "visual"] = "editable"
    language: Literal["it", "en", "it+en"] = "it"
    dpi: int = Field(default=180, ge=72, le=400)
    max_file_mb: int = Field(default=100, ge=1, le=2000)
    max_pages: int = Field(default=500, ge=1, le=10000)
    max_pixels: int = Field(default=30_000_000, ge=1_000_000)
    ocr_timeout: float = Field(default=180, gt=0)
    workers: int = Field(default=1, ge=1, le=8)
    layout: Literal["geometric", "ppdoclayout"] = "geometric"
    layout_model_dir: Path | None = None
    xiaomi_url: str = "http://127.0.0.1:11434/v1"
    xiaomi_model: str = "longwayxu/xiaomi-ocr-0:bf16"
    minicpm_url: str = "http://127.0.0.1:18499/v1"
    minicpm_model: str = "minicpm-ocr"
    resume: bool = True
    overwrite: bool = False
    validate_visual: bool = False
    validate_editability: bool = False
    validation_ssim_target: float = Field(default=.990,ge=0,le=1)
    validation_cer_target: float = Field(default=.001,ge=0,le=1)
    validation_median_geometry_mm: float = Field(default=1.,ge=0)
    validation_p95_geometry_mm: float = Field(default=2.,ge=0)
    searchable_pdf: bool = False
    second_pass: bool = False
    second_engine: Literal["xiaomi", "minicpm", "tesseract", "vision"] | None = None
    ground_truth: Path | None = None
    renderer: str | None = None
    optimize_layout: bool = True
    max_layout_iterations: int = Field(default=3,ge=0,le=12)
    layout_max_adjustment_pt: float = Field(default=24,ge=0,le=72)
    layout_tolerance_pt: float = Field(default=.15,ge=.01,le=10)
    layout_min_improvement: float = Field(default=.001,ge=0,le=1)
    layout_optimization_timeout: float = Field(default=60,ge=1,le=600)
