from __future__ import annotations

import ctypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import zipfile


DEFAULT_NBA2K26_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\NBA 2K26"
)
_MOD_EXTRACT_LOCK = threading.Lock()


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    archive_id: str
    offset: int
    size: int

    @property
    def display_name(self) -> str:
        return Path(self.name).name


def load_font_manifest_entries(manifest_path: str | Path) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    with Path(manifest_path).open("r", encoding="utf-8", errors="replace") as manifest:
        for line in manifest:
            entry = _parse_manifest_line(line)
            if entry is not None and entry.name.lower().endswith("_font.iff"):
                entries.append(entry)
    return entries


def extract_manifest_iff(
    entry: ManifestEntry,
    game_root: str | Path,
    destination: str | Path,
) -> Path:
    root = Path(game_root)
    archive_path = root / entry.archive_id
    if not archive_path.is_file():
        raise FileNotFoundError(
            f"Game archive {entry.archive_id} was not found for {entry.name}."
        )

    with archive_path.open("rb") as archive:
        archive.seek(entry.offset)
        wrapped = archive.read(entry.size)
    if len(wrapped) != entry.size:
        raise RuntimeError(f"Could not read the complete archive entry {entry.name}.")

    if zipfile.is_zipfile(BytesIO(wrapped)):
        iff_data = wrapped
    elif len(wrapped) >= 20 and wrapped[12:16] == b"VCZ\x00":
        raw_size = struct.unpack_from("<I", wrapped, len(wrapped) - 4)[0]
        iff_data = _oodle_decompress(
            wrapped[16:],
            raw_size,
            root / "data" / "oodle" / "oo2core_9_win64.dll",
        )
    else:
        raise RuntimeError(f"{entry.name} is not a supported NBA 2K archive entry.")

    if not zipfile.is_zipfile(BytesIO(iff_data)):
        raise RuntimeError(f"Extracted data for {entry.name} is not a readable IFF.")

    output_path = Path(destination)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(iff_data)
    with zipfile.ZipFile(output_path) as archive:
        names = [name.lower() for name in archive.namelist()]
    if any(name.endswith(".txtr") for name in names) and not any(
        name.endswith(".dds") for name in names
    ):
        _expand_shared_textures_with_mod(entry.name, root, output_path)
    return output_path


def _parse_manifest_line(line: str) -> ManifestEntry | None:
    parts = line.rstrip("\r\n").rsplit(",", 3)
    if len(parts) != 4:
        return None
    name, archive_id, offset_text, size_text = parts
    try:
        offset = int(offset_text)
        size = int(size_text)
    except ValueError:
        return None
    if not name or not archive_id or offset < 0 or size < 1:
        return None
    return ManifestEntry(name, archive_id, offset, size)


def _oodle_decompress(compressed: bytes, raw_size: int, dll_path: Path) -> bytes:
    if not dll_path.is_file():
        raise FileNotFoundError(
            "NBA 2K26's Oodle library was not found. Verify the selected game folder."
        )
    if raw_size < 1:
        raise RuntimeError("The archive entry has an invalid decompressed size.")

    oodle = ctypes.CDLL(str(dll_path))
    decompress = oodle.OodleLZ_Decompress
    decompress.restype = ctypes.c_longlong
    source = ctypes.create_string_buffer(compressed)
    output = ctypes.create_string_buffer(raw_size)
    result = decompress(
        source,
        len(compressed),
        output,
        raw_size,
        1,
        1,
        0,
        None,
        0,
        None,
        None,
        None,
        0,
        3,
    )
    if result != raw_size:
        raise RuntimeError(
            f"Oodle decompression returned {result}; expected {raw_size} bytes."
        )
    return output.raw


def _expand_shared_textures_with_mod(
    archive_entry: str,
    game_root: Path,
    destination: Path,
) -> None:
    relative_entry = Path(archive_entry)
    if relative_entry.is_absolute() or ".." in relative_entry.parts:
        raise RuntimeError("The manifest entry has an invalid path.")

    mod_exe = game_root / "mod.exe"
    if not mod_exe.is_file():
        raise FileNotFoundError(
            "NBA 2K26 mod.exe was not found. Verify the selected game folder."
        )

    live_path = game_root / "mods" / relative_entry
    held_path = destination.with_name(f"{destination.name}.held_loose")
    creation_flags = (
        subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    )
    with _MOD_EXTRACT_LOCK:
        live_path.parent.mkdir(parents=True, exist_ok=True)
        held_path.unlink(missing_ok=True)
        had_loose = live_path.exists()
        if had_loose:
            try:
                shutil.move(live_path, held_path)
            except PermissionError as exc:
                raise RuntimeError(
                    f"{live_path.name} is locked. Close NBA 2K26 and try again."
                ) from exc
        try:
            result = None
            for _attempt in range(2):
                live_path.unlink(missing_ok=True)
                result = subprocess.run(
                    [str(mod_exe), archive_entry],
                    cwd=str(game_root),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=creation_flags,
                    check=False,
                )
                if result.returncode == 0 and _is_valid_zip(live_path):
                    break
            if result is None or result.returncode or not _is_valid_zip(live_path):
                output = result.stdout if result is not None else "mod.exe did not run."
                raise RuntimeError(
                    f"mod.exe could not expand {archive_entry}.\n\n{output}"
                )
            with zipfile.ZipFile(live_path) as expanded:
                names = [name.lower() for name in expanded.namelist()]
            if not any(name.endswith(".dds") for name in names):
                raise RuntimeError(
                    f"mod.exe did not expand the shared textures for {archive_entry}."
                )
            shutil.copy2(live_path, destination)
        finally:
            live_path.unlink(missing_ok=True)
            if had_loose and held_path.exists():
                shutil.move(held_path, live_path)


def _is_valid_zip(path: Path) -> bool:
    try:
        if not path.is_file() or not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as archive:
            return archive.testzip() is None
    except (OSError, ValueError, zipfile.BadZipFile):
        return False
