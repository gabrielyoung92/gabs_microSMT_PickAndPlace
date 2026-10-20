"""Read identical CAM member bytes from a ZIP or an extracted directory."""
from pathlib import Path
import zipfile


def read_source_files(source):
    source = Path(source)
    if source.is_dir():
        return {p.relative_to(source).as_posix(): p.read_bytes()
                for p in sorted(source.rglob('*')) if p.is_file()}
    with zipfile.ZipFile(source) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()
                if not info.is_dir()}
