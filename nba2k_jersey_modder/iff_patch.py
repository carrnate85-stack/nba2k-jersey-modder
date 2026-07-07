from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile

from .scanner import ResourceHit


@dataclass(frozen=True)
class Replacement:
    resource: ResourceHit
    file_path: Path


def apply_replacements(
    source_iff: Path,
    output_iff: Path,
    replacements: list[Replacement],
) -> None:
    if zipfile.is_zipfile(source_iff) and any(
        replacement.resource.archive_path for replacement in replacements
    ):
        _apply_zip_replacements(source_iff, output_iff, replacements)
        return

    data = bytearray(source_iff.read_bytes())

    for replacement in replacements:
        resource = replacement.resource
        if not can_replace_resource(resource):
            raise ValueError(f"{resource.name} does not have a replaceable embedded range.")

        new_data = replacement.file_path.read_bytes()
        if resource.kind == "DDS" and not new_data.startswith(b"DDS "):
            raise ValueError(f"{replacement.file_path.name} is not a DDS file.")

        assert resource.size is not None
        if len(new_data) > resource.size:
            raise ValueError(
                f"{replacement.file_path.name} is {len(new_data)} bytes, but "
                f"{resource.name} only has {resource.size} bytes available."
            )

        start = resource.offset
        end = start + resource.size
        data[start:end] = new_data.ljust(resource.size, b"\0")

    output_iff.write_bytes(data)


def can_replace_embedded_resource(resource: ResourceHit) -> bool:
    return (
        resource.kind == "DDS"
        and resource.source.startswith("DDS header")
        and resource.size is not None
        and resource.size > 0
    )


def can_replace_resource(resource: ResourceHit) -> bool:
    return (
        resource.kind == "DDS"
        and (resource.archive_path is not None or can_replace_embedded_resource(resource))
    )


def _apply_zip_replacements(
    source_iff: Path,
    output_iff: Path,
    replacements: list[Replacement],
) -> None:
    replacement_by_path = {
        replacement.resource.archive_path: replacement
        for replacement in replacements
        if replacement.resource.archive_path
    }

    with zipfile.ZipFile(source_iff, "r") as source:
        with zipfile.ZipFile(output_iff, "w") as target:
            for info in source.infolist():
                replacement = replacement_by_path.get(info.filename)
                if replacement is None:
                    target.writestr(info, source.read(info.filename))
                    continue

                new_data = replacement.file_path.read_bytes()
                if replacement.resource.kind == "DDS" and not new_data.startswith(b"DDS "):
                    raise ValueError(f"{replacement.file_path.name} is not a DDS file.")

                new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.comment = info.comment
                new_info.extra = info.extra
                new_info.internal_attr = info.internal_attr
                new_info.external_attr = info.external_attr
                target.writestr(new_info, new_data)
