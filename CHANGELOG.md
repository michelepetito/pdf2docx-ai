# Changelog

## 0.3.1

- English and Italian installation/usage guides for macOS, Linux and Windows.
- Project-local Python bootstrap and shared dependency constraints.
- Standard Windows LibreOffice/Tesseract discovery and explicit UTF-8 OCR output.
- Portable isolated Ollama launcher; process checks avoid Windows `os.kill(pid, 0)`.
- Complex corpus generation detects the installed renderer instead of a workstation path.
- Cross-platform CI and Linux LibreOffice/Tesseract integration checks.
- Linux fontconfig recognizes the explicitly supported Liberation/Carlito metric
  aliases while continuing to reject unrelated fallback families.

The layout strategy and experimental quality targets are unchanged.
Historical 0.3.0 reports remain preserved with their original dates/hashes.

## 0.3.0

Four-dimensional validation, exact CER/WER, geometry in pt/mm, immutable assessment
history, regression detection and real edit probes on copies. The original full
macOS verification passed 174 tests, including real Vision and MiniCPM.
