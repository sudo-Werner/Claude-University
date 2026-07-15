import os
from pathlib import Path


def write_text_atomic(path, text):
    """Write via a same-directory temp file + os.replace, so a crash mid-write can
    never leave a truncated file at the destination — the old content survives."""
    path = Path(path)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
