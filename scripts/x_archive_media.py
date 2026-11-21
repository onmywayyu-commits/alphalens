import re
from hashlib import file_digest
from pathlib import Path, PureWindowsPath

from PIL import Image

from .x_archive_models import Media

IMAGE_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


def image_names(value: str | None) -> list[str]:
    return [
        part.strip().strip('"')
        for part in re.split(r"[\r\n;；]+", value or "")
        if part.strip().strip('"')
    ]


def digest(path: Path) -> bytes:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").digest()


def inspect_image(reference: str, raw_dir: Path, record_id: str, row: int, position: int) -> Media:
    window_path = PureWindowsPath(reference)
    original_filename = window_path.name or "未识别文件名"
    base = {
        "media_id": f"{record_id}-m{position}",
        "original_filename": original_filename,
        "excel_row": row,
        "position": position,
    }
    expected = IMAGE_FORMATS.get(window_path.suffix.lower())
    if expected is None:
        return Media(**base, exists=False, availability="unsupported_extension")

    source = Path(reference)
    if window_path.drive.startswith("\\\\") or reference.startswith("//"):
        source = None
    elif not source.is_absolute():
        source = (
            raw_dir.joinpath(*window_path.parts)
            if not window_path.anchor and ".." not in window_path.parts
            else None
        )
        if source is not None and not source.resolve().is_relative_to(raw_dir):
            source = None

    present = staged_present = False
    try:
        media_dir = raw_dir / "media"
        staged = (media_dir / original_filename).resolve()
        archive_root = media_dir.resolve()
        source = source.resolve() if source is not None else None
        present = source is not None and source.is_file()
        staged_present = (
            archive_root.is_relative_to(raw_dir)
            and staged.is_relative_to(archive_root)
            and staged.is_file()
        )
        if present and source.is_relative_to(media_dir):
            candidate, availability = source, "available"
        elif present and staged_present:
            if digest(source) != digest(staged):
                return Media(**base, exists=True, availability="conflict")
            candidate, availability = staged, "available"
        elif present:
            candidate, availability = source, "outside_archive"
        elif staged_present:
            candidate, availability = staged, "filename_match"
        else:
            return Media(**base, exists=False, availability="missing")

        try:
            with Image.open(candidate) as image:
                if image.format != expected:
                    return Media(**base, exists=True, availability="invalid_file")
                image.verify()
        except PermissionError:
            return Media(**base, exists=True, availability="unreadable")
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
            return Media(**base, exists=True, availability="invalid_file")
    except (OSError, RuntimeError, ValueError):
        return Media(**base, exists=present or staged_present, availability="unreadable")

    local_path = candidate.relative_to(raw_dir).as_posix() if availability != "outside_archive" else None
    return Media(**base, exists=True, availability=availability, local_path=local_path)

