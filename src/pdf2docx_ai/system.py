"""Find optional native programs without changing the user's environment."""
from pathlib import Path
import os
import platform
import shutil


def find_program(name: str, explicit: str | None = None) -> str | None:
    if explicit:
        return shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
    found = shutil.which(name)
    if found:
        return found
    if platform.system() == 'Windows':
        relative = {'soffice': ('LibreOffice/program/soffice.com', 'LibreOffice/program/soffice.exe'),
                    'tesseract': ('Tesseract-OCR/tesseract.exe',)}.get(name, ())
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            parent = os.environ.get(variable)
            if not parent:
                continue
            for suffix in relative:
                candidate = Path(parent) / suffix
                if candidate.is_file():
                    return str(candidate)
    if name == 'soffice':
        candidate = Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')
        if candidate.is_file():
            return str(candidate)
    return None
