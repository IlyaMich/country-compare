from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from zipfile import ZipFile, ZipInfo


class UnsafeArchiveError(RuntimeError):
    """Raised when an archive member cannot be extracted safely."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_zip_members(zip_file: ZipFile) -> list[ZipInfo]:
    """Return non-directory ZIP members after validating their names are safe."""

    members: list[ZipInfo] = []
    for member in zip_file.infolist():
        if member.is_dir():
            continue
        _validate_member_name(member.filename)
        members.append(member)
    return members


def extract_zip_member(
    zip_file: ZipFile, member: ZipInfo, destination: str | Path
) -> Path:
    """Extract one ZIP member to an explicit destination path.

    The member name is still validated even though the destination path is
    supplied by the caller. This prevents accidentally accepting malicious ZIPs
    while normalizing World Bank member names into project-specific filenames.
    """

    _validate_member_name(member.filename)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with zip_file.open(member, "r") as source, destination_path.open("wb") as target:
        shutil.copyfileobj(source, target)
    return destination_path


def _validate_member_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        raise UnsafeArchiveError(f"archive member has absolute path: {name!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeArchiveError(f"archive member has unsafe path: {name!r}")
