from pathlib import Path
from tempfile import TemporaryFile


def writable_directory(path: Path) -> bool:
    """Probe the nearest existing parent without creating persistent directories."""
    candidate = path.resolve()
    while not candidate.exists():
        candidate = candidate.parent
    try:
        with TemporaryFile(dir=candidate):
            return True
    except OSError:
        return False
