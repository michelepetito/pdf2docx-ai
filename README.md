# PDF2DOCX AI Fidelity

**English** · [Italiano](README.it.md)

Local PDF → editable Word converter with a web interface, command line, optional OCR and measured quality. **Version 0.3.1.** No cloud account or GPU is needed for native PDFs or Tesseract OCR. The current web interface labels are Italian.

Word output uses native paragraphs, sections, columns, tabs, real tables and independent images. Visual similarity, text accuracy, geometry and editability remain separate: SSIM 0.99 does not certify 99% fidelity.

## Requirements

| Component | Purpose |
| --- | --- |
| Git + 64-bit Python **3.12** | Required; Python 3.11–3.13 is accepted |
| LibreOffice | Recommended: layout optimization, DOCX rendering and visual/edit validation |
| Tesseract + `ita`/`eng` data | Cross-platform scan OCR; unnecessary for native PDFs |
| Apple Vision / Ollama + MiniCPM | Optional alternative OCR backends |

Use Python for your architecture. Common native targets: **macOS Intel/Apple Silicon, Linux x86_64/ARM64, Windows x64**. Windows ARM64 users can use x64 Python/runtime under emulation or ARM64 Linux in WSL2, subject to dependency availability. Arbitrary 32-bit systems and every GPU are not guaranteed; check [PyMuPDF wheel support](https://pymupdf.readthedocs.io/en/latest/installation.html).

## 1. Install prerequisites once

### macOS

With [Homebrew](https://brew.sh/) already available:

```bash
brew install git python@3.12 tesseract tesseract-lang
brew install --cask libreoffice
```

Without Homebrew, install [Python](https://www.python.org/downloads/), [Git](https://git-scm.com/downloads), [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) and [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html) separately. Choose Intel or Apple Silicon builds matching your Mac. Codex and its runtime are not required.

### Linux — Ubuntu 24.04 / Debian family

```bash
sudo apt update
sudo apt install -y git python3 python3-venv libreoffice-writer tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng fontconfig fonts-liberation
python3 --version
```

Ubuntu 24.04 supplies Python 3.12. On other distributions install equivalent packages and verify Python is 3.11–3.13. Install the source document's fonts where licensing permits.

### Windows — PowerShell

Install [Git](https://git-scm.com/download/win), [Python 3.12](https://www.python.org/downloads/windows/), [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) and a [Tesseract installer linked by upstream](https://tesseract-ocr.github.io/tessdoc/Installation.html#windows). Include Italian and English OCR data, then reopen PowerShell.

Standard `Program Files` installations of LibreOffice and Tesseract are detected automatically. For custom locations, add their executable folders to your user `PATH`. `doctor --json` checks detected binaries and OCR languages.

## 2. Clone and install

**macOS / Linux:**

```bash
git clone https://github.com/michelepetito/pdf2docx-ai.git
cd pdf2docx-ai
python3.12 scripts/bootstrap.py
source .venv/bin/activate
```

On Ubuntu 24.04, `python3 scripts/bootstrap.py` also works. If needed, Homebrew Python is at `"$(brew --prefix python@3.12)/bin/python3.12"`.

**Windows:**

```powershell
git clone https://github.com/michelepetito/pdf2docx-ai.git
cd pdf2docx-ai
py -3.12 scripts/bootstrap.py
.\.venv\Scripts\Activate.ps1
```

If activation is blocked, use `.\.venv\Scripts\python.exe -m pdf2docx_ai ...` instead of `pdf2docx-ai ...`; no execution-policy change is needed. On macOS/Linux the equivalent is `.venv/bin/python -m pdf2docx_ai ...`.

Bootstrap creates only `.venv`, installs the project with [shared application versions](constraints.txt), and runs `pip check`. It does not install system programs, fetch OCR weights or start services. Add `--dev` for test dependencies or `--venv .venv-other` for another environment.

Manual installation in an activated Python environment:

```bash
python -m pip install --upgrade pip
python -m pip install -c constraints.txt -e ".[test]"
python -m pip check
```

Native wheels are selected for the host platform. [requirements-lock-macos-arm64.txt](requirements-lock-macos-arm64.txt) is the full historical Mac freeze, not a universal lock. Record your full resolved environment with `python -m pip freeze > requirements-local.txt`.

## 3. Use the web interface

```bash
pdf2docx-ai doctor --json
pdf2docx-ai serve
```

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)**. Upload a PDF, choose language/engine, keep **editable** mode, convert, then download Word and the quality report. In advanced options, **“Verifica una modifica al Word”** tests an ordinary edit on a copy.

For scans, Tesseract is the simplest common backend. `auto` checks Xiaomi → MiniCPM → Vision → Tesseract. Unavailable optional engines do not prevent native-PDF conversion; an explicitly selected unavailable engine fails with a diagnostic.

Stop with **Ctrl+C**; **download results first**, because web session files are deleted on shutdown. Another port: `pdf2docx-ai serve --port 8766`. The server binds only to loopback and uses local frontend assets.

## 4. Examples — Bash and PowerShell

```bash
# Native PDF: no OCR model needed
pdf2docx-ai convert input.pdf --output output.docx
# Italian scan: CPU OCR, searchable PDF and visual check
pdf2docx-ai convert scan.pdf --engine tesseract --language it --output scan.docx --searchable-pdf --validate-visual
# Both languages
pdf2docx-ai convert bilingual.pdf --engine tesseract --language it+en --output bilingual.docx
# Real edit probe, always on a COPY
pdf2docx-ai convert input.pdf --output checked.docx --validate-editability
# Validate an existing Word file
pdf2docx-ai validate input.pdf output.docx --output validation.html --edit-probe
# OCR accuracy against a complete, independent reference
pdf2docx-ai validate scan.pdf scan.docx --ground-truth reference.txt --output ocr-validation.html
# Compare an earlier assessment of the SAME source PDF
pdf2docx-ai validate input.pdf output.docx --previous validation.json --output comparison.html
# Faster conversion
pdf2docx-ai convert input.pdf --output quick.docx --no-optimize-layout
```

Existing output names require `--overwrite`, which archives the previous quality report. `--renderer "path/to/soffice"` overrides the renderer for `convert`/`validate`; the web app uses automatic detection. More: `pdf2docx-ai --help` and `pdf2docx-ai convert --help`.

**Ready-made examples:**

```bash
python tests/fixtures/generate.py tests/fixtures/generated
pdf2docx-ai convert tests/fixtures/generated/native.pdf --output examples/output/demo-native.docx
pdf2docx-ai convert tests/fixtures/generated/scan_it.pdf --engine tesseract --language it --output examples/output/demo-scan.docx --ground-truth tests/fixtures/generated/scan_it.txt --validate-visual
```

## 5. Outputs and quality

| File | Contents |
| --- | --- |
| `output.docx` | Editable Word document |
| `output.quality.html` / `.json` | Measurements, warnings, comparisons, overlays and differences when rendering is available |
| `output.model.json` | Layout, coordinates and OCR provenance |
| `output.searchable.pdf` | Only with `--searchable-pdf`: original appearance plus OCR text layer |
| `output.work/` | Resume cache/previews; can contain document copies |

Four separate dimensions: **SSIM per page/global/foreground**, **exact CER/WER, values and reading order**, **IoU/geometry in pt/mm for eight categories**, and **Word structure/edit probe**. Initial targets—SSIM≥0.990, CER≤0.1%, median geometry≤1 mm, P95≤2 mm—are experimental. Missing references or renderers produce explicit unavailable measurements. `visual` mode intentionally creates noneditable page images in `.visual.docx`.

## 6. Optional MiniCPM-OCR 1.0 — macOS, Linux, Windows

Install [Ollama](https://ollama.com/download) and put `ollama` in `PATH`. The matched main/projector/DSpark setup requires **Ollama≥0.40.12**, per [OpenBMB's official guide](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/ollama_deploy.md). Download: **about 2.04 GB**; allow at least **6 GB free disk** for weights/import, plus runtime needs. GPU acceleration depends on the runtime and drivers; CPU inference can be slow.

In the activated environment, from the repository root:

```bash
python scripts/setup_minicpm.py
# Explicit download, pinned revisions + SHA-256 verification
python scripts/setup_minicpm.py --download-models
# Terminal A: keep open
python scripts/serve_minicpm.py
```

In **terminal B**, activate the same environment:

```bash
python scripts/setup_minicpm.py --register
pdf2docx-ai doctor --json
pdf2docx-ai convert tests/fixtures/generated/scan_it.pdf --engine minicpm --language it --output examples/output/demo-minicpm.docx --ground-truth tests/fixtures/generated/scan_it.txt --validate-visual
pdf2docx-ai serve
```

Generate the section 4 fixtures first. Endpoint: `http://127.0.0.1:18499`, alias `minicpm-ocr`, weights/store in ignored `models/`. Ctrl+C in terminal A stops only its server. Occupied ports are refused and other instances remain unchanged. The older `.command` launchers are macOS-only.

For an existing configured instance: `pdf2docx-ai serve --minicpm-url http://127.0.0.1:11434/v1 --minicpm-model minicpm-ocr`. Changing the URL does not install a model. Only numeric loopback addresses are allowed. [Historical setup evidence](docs/setup-minicpm.md).

Apple Vision: macOS + Xcode Command Line Tools, then `--engine vision`. Xiaomi and PP-DocLayoutV3 are optional adapters; original real inference was not verified. [Backend details](docs/ocr-backends.md).

## 7. Tests and reproducibility

```bash
python -m pip install -c constraints.txt -e ".[test]"
python -m pytest -m "not real_ocr and not complex and not renderer" -q
# With LibreOffice installed:
python -m pytest -m "not real_ocr and not complex" -q
```

The current 0.3.1 local verification passed **179 tests**: [verification](docs/portability-local-verification.json), [full JUnit](docs/portability-full-tests.xml), [cross-platform CI evidence](docs/portability-ci-verification.json).

[CI](https://github.com/michelepetito/pdf2docx-ai/actions) covers Linux x64/ARM64, macOS Intel/ARM64 and Windows x64, with a Linux rendering/OCR smoke test. Check the actual run results for verified combinations; it does not download VLM weights. The historical 0.3.0 macOS run passed **174 tests** with real Vision/MiniCPM and complex documents: [JUnit](docs/validation-test-results.xml), [verification](docs/validation-verification.json).

Generate and test a complex European CV on your machine:

```bash
python scripts/generate_complex_corpus.py
pdf2docx-ai convert tests/fixtures/complex/generated/europass_fictitious.reference.pdf --output examples/output/europass-geometric.docx --validate-editability
```

Fonts/renderers can change pagination. Historical `evaluate_reconstruction.py` and `evaluate_validation.py` require frozen conversions in ignored `examples/output/`: the multi-gigabyte output archive is not in Git. Generate new conversions as above. Historical HTML summaries embed previews; some individual-report links and absolute paths refer to the original workstation, and are not setup prerequisites.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Python missing / 3.14+ | Install/select Python 3.12 and reopen the terminal |
| No compatible wheel | Check 64-bit Python/architecture and upstream wheel availability; Windows ARM can try x64 emulation/WSL2 |
| Command not found | Activate `.venv` or use its Python with `-m pdf2docx_ai` |
| LibreOffice unavailable | Install it; use a standard folder, `PATH`, or CLI `--renderer` |
| OCR language missing | Install `ita`/`eng`; inspect `doctor --json` and `tesseract --list-langs` |
| MiniCPM connection refused | Start its server, register weights, then recheck engine availability |
| Different layout on another PC | Match fonts/renderer and inspect all four dimensions |

## Limits and license

Complex publications, rotated text, missing fonts and fixed-page decorations still have fidelity/editing limits. The CV edit probe detects two rule/title intersections despite intact text and objects. Microsoft Word was not the historical renderer. See [limits](docs/limitations.md), [methodology](docs/validation-methodology.md), [comparative report](docs/validation-final-report.md) and [architecture](docs/architecture.md).

Source: [src/](src/), [tests/](tests/), [scripts/](scripts/); historical snapshots in `examples/`. Git excludes environments, model binaries, caches, generated outputs and distributions. Setup scripts and the model manifest are included. Installation downloads packages/explicitly requested models; document conversion itself is local.

**AGPL-3.0-or-later**: [LICENSE](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md). Public PLOS/Eurostat fixtures have separate CC BY 4.0 [attribution](tests/fixtures/complex/public/manifest.json); CV data/portrait are synthetic. Model licenses remain separate.
