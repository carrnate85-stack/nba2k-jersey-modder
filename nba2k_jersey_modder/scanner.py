from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import struct
from typing import Iterable
import zipfile


PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{4,}")
NAMED_RESOURCE_RE = re.compile(
    rb"([A-Za-z0-9_./\\ -]+\.(?:dds|txtr|rdat))", re.IGNORECASE
)


@dataclass(frozen=True)
class StringHit:
    offset: int
    text: str


@dataclass(frozen=True)
class ResourceHit:
    kind: str
    offset: int
    name: str
    size: int | None = None
    source: str = "string"
    archive_path: str | None = None


@dataclass(frozen=True)
class TexturePair:
    key: str
    dds_hits: tuple[ResourceHit, ...] = field(default_factory=tuple)
    txtr_hits: tuple[ResourceHit, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        if self.dds_hits and self.txtr_hits:
            return "Matched"
        if self.dds_hits:
            return "Missing .txtr"
        return "Missing .dds"


@dataclass(frozen=True)
class IffScanResult:
    path: Path
    size: int
    strings: tuple[StringHit, ...]
    resources: tuple[ResourceHit, ...]
    texture_pairs: tuple[TexturePair, ...]


def scan_iff(path: str | Path) -> IffScanResult:
    file_path = Path(path)
    if zipfile.is_zipfile(file_path):
        return _scan_zip_iff(file_path)

    data = file_path.read_bytes()

    strings = tuple(_scan_printable_strings(data))
    named_resources = list(_scan_named_resource_references(data))
    dds_magic_resources = list(_scan_dds_magic(data))

    resources = _dedupe_resources(
        _merge_named_dds_with_embedded_headers(named_resources, dds_magic_resources)
    )
    pairs = _pair_textures(resources)

    return IffScanResult(
        path=file_path,
        size=len(data),
        strings=strings,
        resources=tuple(resources),
        texture_pairs=tuple(pairs),
    )


def _scan_zip_iff(file_path: Path) -> IffScanResult:
    resources: list[ResourceHit] = []
    strings: list[StringHit] = []

    with zipfile.ZipFile(file_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename.lower()).suffix
            if suffix in {".dds", ".txtr", ".rdat"}:
                resources.append(
                    ResourceHit(
                        kind=suffix.removeprefix(".").upper(),
                        offset=info.header_offset,
                        name=Path(info.filename.replace("\\", "/")).name,
                        size=info.file_size,
                        source="archive entry",
                        archive_path=info.filename,
                    )
                )
            strings.append(StringHit(offset=info.header_offset, text=info.filename))

    resources = _dedupe_resources(resources)
    return IffScanResult(
        path=file_path,
        size=file_path.stat().st_size,
        strings=tuple(strings),
        resources=tuple(resources),
        texture_pairs=tuple(_pair_textures(resources)),
    )


def _scan_printable_strings(data: bytes) -> Iterable[StringHit]:
    for match in PRINTABLE_RE.finditer(data):
        text = match.group(0).decode("ascii", errors="replace").strip()
        if text:
            yield StringHit(offset=match.start(), text=text)


def _scan_named_resource_references(data: bytes) -> Iterable[ResourceHit]:
    seen: set[tuple[int, str]] = set()
    for match in NAMED_RESOURCE_RE.finditer(data):
        raw_name = match.group(1).decode("ascii", errors="replace")
        name = _clean_embedded_name(raw_name)
        suffix = Path(name.lower()).suffix
        if suffix not in {".dds", ".txtr", ".rdat"}:
            continue
        item = (match.start(1), name.lower())
        if item in seen:
            continue
        seen.add(item)
        yield ResourceHit(
            kind=suffix.removeprefix(".").upper(),
            offset=match.start(1),
            name=name,
            source="filename reference",
        )


def _scan_dds_magic(data: bytes) -> Iterable[ResourceHit]:
    start = 0
    counter = 1
    while True:
        offset = data.find(b"DDS ", start)
        if offset == -1:
            return

        size = _estimate_dds_size(data, offset)
        yield ResourceHit(
            kind="DDS",
            offset=offset,
            name=f"embedded_dds_{counter:03d}.dds",
            size=size,
            source="DDS header",
        )
        counter += 1
        start = offset + 4


def _merge_named_dds_with_embedded_headers(
    named_resources: list[ResourceHit],
    dds_magic_resources: list[ResourceHit],
) -> list[ResourceHit]:
    named_dds = [resource for resource in named_resources if resource.kind == "DDS"]
    other_named = [resource for resource in named_resources if resource.kind != "DDS"]

    merged: list[ResourceHit] = [*other_named]
    used_header_offsets: set[int] = set()

    for named, header in zip(
        sorted(named_dds, key=lambda item: item.offset),
        sorted(dds_magic_resources, key=lambda item: item.offset),
    ):
        used_header_offsets.add(header.offset)
        merged.append(
            ResourceHit(
                kind="DDS",
                offset=header.offset,
                name=named.name,
                size=header.size,
                source="DDS header matched to filename",
                archive_path=named.archive_path,
            )
        )

    if len(named_dds) > len(dds_magic_resources):
        merged.extend(sorted(named_dds, key=lambda item: item.offset)[len(dds_magic_resources) :])

    merged.extend(
        resource
        for resource in dds_magic_resources
        if resource.offset not in used_header_offsets
    )
    return merged


def _estimate_dds_size(data: bytes, offset: int) -> int | None:
    if offset + 128 > len(data):
        return None
    try:
        header_size = struct.unpack_from("<I", data, offset + 4)[0]
        height = struct.unpack_from("<I", data, offset + 12)[0]
        width = struct.unpack_from("<I", data, offset + 16)[0]
        linear_size = struct.unpack_from("<I", data, offset + 20)[0]
        mip_count = struct.unpack_from("<I", data, offset + 28)[0]
    except struct.error:
        return None

    if header_size != 124 or width == 0 or height == 0:
        return None

    if linear_size:
        total = 128
        current = linear_size
        levels = max(1, min(mip_count or 1, 16))
        for _ in range(levels):
            total += max(1, current)
            current //= 4
        return min(total, len(data) - offset)

    # Uncompressed or unusual DDS: report the header as confirmed, not a guessed payload.
    return 128


def _pair_textures(resources: Iterable[ResourceHit]) -> list[TexturePair]:
    groups: dict[str, dict[str, list[ResourceHit]]] = {}
    for resource in resources:
        if resource.kind not in {"DDS", "TXTR"}:
            continue
        key = _texture_key(resource.name)
        bucket = groups.setdefault(key, {"DDS": [], "TXTR": []})
        bucket[resource.kind].append(resource)

    pairs: list[TexturePair] = []
    for key in sorted(groups):
        bucket = groups[key]
        pairs.append(
            TexturePair(
                key=key,
                dds_hits=tuple(_unique_texture_hits(bucket["DDS"])),
                txtr_hits=tuple(_unique_texture_hits(bucket["TXTR"])),
            )
        )
    return pairs


def _unique_texture_hits(resources: Iterable[ResourceHit]) -> list[ResourceHit]:
    unique: dict[str, ResourceHit] = {}
    for resource in sorted(resources, key=lambda item: item.offset):
        key = resource.name.replace("\\", "/").split("/")[-1].lower()
        unique.setdefault(key, resource)
    return list(unique.values())


def _texture_key(name: str) -> str:
    normalized = name.replace("\\", "/").split("/")[-1].lower()
    if normalized.endswith(".txtr"):
        return normalized[: -len(".txtr")]
    if normalized.endswith(".dds"):
        stem = normalized[: -len(".dds")]
        parts = stem.rsplit(".", 1)
        if len(parts) == 2 and _looks_like_hash(parts[1]):
            return parts[0]
        return stem
    return normalized


def _looks_like_hash(value: str) -> bool:
    return len(value) >= 8 and all(char in "0123456789abcdef" for char in value)


def _clean_embedded_name(name: str) -> str:
    cleaned = name.strip().replace("\x00", "")
    cleaned = cleaned.replace("\\", "/")
    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")
    return cleaned


def _dedupe_resources(resources: Iterable[ResourceHit]) -> list[ResourceHit]:
    seen: set[tuple[str, int, str, str | None]] = set()
    deduped: list[ResourceHit] = []
    for resource in sorted(resources, key=lambda item: (item.offset, item.kind, item.name)):
        key = (
            resource.kind,
            resource.offset,
            resource.name.lower(),
            resource.archive_path.lower() if resource.archive_path else None,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(resource)
    return deduped
