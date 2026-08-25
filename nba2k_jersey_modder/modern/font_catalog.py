from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import zipfile

from PIL import Image

from ..font_iff import extract_number_sheet_from_font_iff, inspect_font_number_texture
from ..game_manifest import ManifestEntry, extract_manifest_iff, load_font_manifest_entries


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEAM_NAMES = {
    "atl":"Atlanta Hawks", "bos":"Boston Celtics", "bkn":"Brooklyn Nets",
    "cha":"Charlotte Hornets", "chi":"Chicago Bulls", "cle":"Cleveland Cavaliers",
    "dal":"Dallas Mavericks", "den":"Denver Nuggets", "det":"Detroit Pistons",
    "gsw":"Golden State Warriors", "hou":"Houston Rockets", "ind":"Indiana Pacers",
    "lac":"LA Clippers", "lal":"Los Angeles Lakers", "mem":"Memphis Grizzlies",
    "mia":"Miami Heat", "mil":"Milwaukee Bucks", "min":"Minnesota Timberwolves",
    "nop":"New Orleans Pelicans", "nyk":"New York Knicks", "okc":"Oklahoma City Thunder",
    "orl":"Orlando Magic", "phi":"Philadelphia 76ers", "phx":"Phoenix Suns",
    "por":"Portland Trail Blazers", "sac":"Sacramento Kings", "sas":"San Antonio Spurs",
    "tor":"Toronto Raptors", "uta":"Utah Jazz", "was":"Washington Wizards",
    "sea":"Seattle SuperSonics", "njn":"New Jersey Nets", "van":"Vancouver Grizzlies",
    "chh":"Charlotte Hornets", "noh":"New Orleans Hornets", "sdc":"San Diego Clippers",
    "buf":"Buffalo Braves", "kck":"Kansas City Kings", "cin":"Cincinnati Royals",
    "syr":"Syracuse Nationals", "stl":"St. Louis Hawks", "bal":"Baltimore Bullets",
}


def describe_manifest_font(entry: ManifestEntry) -> tuple[str, str, str]:
    stem = Path(entry.name).stem.lower()
    match = re.search(r"_u\d+([a-z]{3})_(.+?)_font$", stem)
    if not match:
        return "Unknown team", stem.replace("_", " ").title(), ""
    code, uniform = match.groups()
    return TEAM_NAMES.get(code, code.upper()), uniform.replace("_", " ").title(), code.upper()


class FontCatalog:
    """Persistent NBA 2K manifest-font cache shared with the classic workspace."""

    def __init__(self, game_root: Path) -> None:
        self.game_root = Path(game_root)
        self.lock = threading.Lock()

    @property
    def manifest_path(self) -> Path:
        return self.game_root / "manifest"

    @property
    def preview_cache(self) -> Path:
        return PROJECT_ROOT / "cache" / "font_previews"

    @property
    def work_cache(self) -> Path:
        return Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "game_fonts"

    def entries(self) -> list[ManifestEntry]:
        if not self.manifest_path.is_file():
            raise FileNotFoundError("No manifest was found. Choose the NBA 2K26 game folder.")
        return load_font_manifest_entries(self.manifest_path)

    def cache_key(self, entry: ManifestEntry) -> str:
        identity = "|".join((
            str(self.game_root.resolve()).lower(), entry.name.lower(),
            entry.archive_id, str(entry.offset), str(entry.size),
        ))
        return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]

    def thumbnail_paths(self, entry: ManifestEntry) -> tuple[Path, Path]:
        stem = f"{Path(entry.name).stem}_{self.cache_key(entry)}"
        return self.preview_cache / f"{stem}.webp", self.preview_cache / f"{stem}.json"

    def working_iff_path(self, entry: ManifestEntry) -> Path:
        return self.work_cache / f"{Path(entry.name).stem}_{self.cache_key(entry)}.iff"

    def cached_count(self, entries: list[ManifestEntry]) -> int:
        return sum(1 for entry in entries if self.is_cached(entry))

    def is_cached(self, entry: ManifestEntry) -> bool:
        return all(path.is_file() for path in self.thumbnail_paths(entry))

    def cached_thumbnail(self, entry: ManifestEntry) -> tuple[Path, dict] | None:
        preview, metadata_path = self.thumbnail_paths(entry)
        if not preview.is_file() or not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not all(key in metadata for key in ("width", "height", "format")):
                raise ValueError("Incomplete metadata")
            with Image.open(preview) as opened:
                opened.verify()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            preview.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            return None
        return preview, metadata

    def ensure_thumbnail(self, entry: ManifestEntry) -> tuple[Path, str, bool]:
        with self.lock:
            cached = self.cached_thumbnail(entry)
            if cached is not None:
                preview, metadata = cached
                preview.touch(); self.thumbnail_paths(entry)[1].touch()
                return preview, self._label(entry, metadata, cached=True), True
            iff_path = self.ensure_working_iff(entry)
            sheet = extract_number_sheet_from_font_iff(iff_path)
            info = inspect_font_number_texture(iff_path)
            thumbnail = sheet.copy()
            thumbnail.thumbnail((1024, 256), Image.Resampling.LANCZOS)
            preview, metadata_path = self.thumbnail_paths(entry)
            preview.parent.mkdir(parents=True, exist_ok=True)
            thumbnail.save(preview, format="WEBP", quality=82, method=4)
            metadata = {"width": info.width, "height": info.height, "format": info.format_label}
            metadata_path.write_text(json.dumps(metadata, separators=(",", ":")), encoding="utf-8")
            return preview, self._label(entry, metadata, cached=False), False

    def ensure_working_iff(self, entry: ManifestEntry) -> Path:
        path = self.working_iff_path(entry)
        try:
            inspect_font_number_texture(path)
        except (OSError, ValueError, zipfile.BadZipFile):
            path.unlink(missing_ok=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            extract_manifest_iff(entry, self.game_root, path)
        return path

    @staticmethod
    def _label(entry: ManifestEntry, metadata: dict, *, cached: bool) -> str:
        suffix = " | cached" if cached else ""
        return f"{entry.display_name} | {metadata['width']} x {metadata['height']} | {metadata['format']}{suffix}"
