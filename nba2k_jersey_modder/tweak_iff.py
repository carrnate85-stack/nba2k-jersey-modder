from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import zipfile


FRONT_NUMBER_HASHES = {
    "x": "55dd42ba8de1fd61",
    "width": "0cb25ac726bcafc3",
    "y": "c8c7aa8b6ee672ef",
    "height": "a2c0ce41bba647f2",
}

TWEAK_ENTRY_NAME = "unitweak.FxTweakables"
_RECORD_TYPES = {72, 76, 89, 136, 140, 144, 152, 153, 160}
_RECORD_SIZES = (36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80)
_VALUE_INDEX = 3


@dataclass(frozen=True)
class TweakScalar:
    key: str
    hash_id: str
    record_type: int
    record_offset: int
    value_offset: int
    value: float
    minimum: float
    maximum: float


@dataclass(frozen=True)
class FrontNumberTweak:
    source_path: Path
    entry_name: str | None
    data_size: int
    x: TweakScalar
    y: TweakScalar
    width: TweakScalar
    height: TweakScalar


def inspect_front_number_tweak(path: str | Path) -> FrontNumberTweak:
    source_path = Path(path)
    entry_name, data = _read_tweak_data(source_path)
    scalars = _find_front_number_scalars(data)
    return FrontNumberTweak(
        source_path=source_path,
        entry_name=entry_name,
        data_size=len(data),
        x=scalars["x"],
        y=scalars["y"],
        width=scalars["width"],
        height=scalars["height"],
    )


def write_front_number_tweak(
    source_path: str | Path,
    output_path: str | Path,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    source = Path(source_path)
    output = Path(output_path)
    entry_name, data = _read_tweak_data(source)
    patched = bytearray(data)
    scalars = _find_front_number_scalars(data)
    for key, value in (("x", x), ("y", y), ("width", width), ("height", height)):
        scalar = scalars[key]
        if value < scalar.minimum or value > scalar.maximum:
            raise ValueError(
                f"{key} value {value:g} is outside {scalar.minimum:g} to {scalar.maximum:g}."
            )
        struct.pack_into("<f", patched, scalar.value_offset, float(value))
    _write_tweak_data(source, output, entry_name, bytes(patched))


def _read_tweak_data(path: Path) -> tuple[str | None, bytes]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if TWEAK_ENTRY_NAME in names:
                return TWEAK_ENTRY_NAME, archive.read(TWEAK_ENTRY_NAME)
            if len(names) == 1:
                return names[0], archive.read(names[0])
            tweak_names = [name for name in names if name.lower().endswith("fxtweakables")]
            if tweak_names:
                return tweak_names[0], archive.read(tweak_names[0])
        raise ValueError("No tweak data entry was found in this IFF.")
    return None, path.read_bytes()


def _write_tweak_data(
    source_path: Path,
    output_path: Path,
    entry_name: str | None,
    tweak_data: bytes,
) -> None:
    if entry_name is None:
        output_path.write_bytes(tweak_data)
        return

    with zipfile.ZipFile(source_path, "r") as source:
        with zipfile.ZipFile(output_path, "w") as target:
            for info in source.infolist():
                data = tweak_data if info.filename == entry_name else source.read(info.filename)
                new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.comment = info.comment
                new_info.extra = info.extra
                new_info.internal_attr = info.internal_attr
                new_info.external_attr = info.external_attr
                target.writestr(new_info, data)


def _find_front_number_scalars(data: bytes) -> dict[str, TweakScalar]:
    records = _parse_records(data)
    found: dict[str, TweakScalar] = {}
    for record_offset, record_type, hash_id, _record_size, values in records:
        for key, expected_hash in FRONT_NUMBER_HASHES.items():
            if hash_id != expected_hash:
                continue
            if len(values) <= 5:
                raise ValueError(f"Front number {key} record is incomplete.")
            found[key] = TweakScalar(
                key=key,
                hash_id=hash_id,
                record_type=record_type,
                record_offset=record_offset,
                value_offset=record_offset + 12 + (_VALUE_INDEX * 4),
                value=values[_VALUE_INDEX],
                minimum=values[4],
                maximum=values[5],
            )
    missing = [key for key in FRONT_NUMBER_HASHES if key not in found]
    if missing:
        raise ValueError(
            "Could not find front number tweak controls: " + ", ".join(missing)
        )
    return found


def _parse_records(data: bytes) -> list[tuple[int, int, str, int, list[float]]]:
    start = _find_record_start(data)
    if start is None:
        raise ValueError("This file does not look like a supported tweak file.")

    records: list[tuple[int, int, str, int, list[float]]] = []
    offset = start
    while offset + 12 <= len(data):
        record_type = struct.unpack_from("<I", data, offset)[0]
        if record_type not in _RECORD_TYPES:
            break
        next_offset = _next_record_offset(data, offset)
        if next_offset is None:
            break
        hash_id = data[offset + 4 : offset + 12].hex()
        values = [
            struct.unpack_from("<f", data, value_offset)[0]
            for value_offset in range(offset + 12, next_offset, 4)
            if value_offset + 4 <= len(data)
        ]
        records.append((offset, record_type, hash_id, next_offset - offset, values))
        if next_offset == len(data):
            break
        offset = next_offset
    return records


def _find_record_start(data: bytes) -> int | None:
    for offset in range(0, min(256, len(data) - 4), 4):
        if struct.unpack_from("<I", data, offset)[0] in _RECORD_TYPES:
            return offset
    return None


def _next_record_offset(data: bytes, offset: int) -> int | None:
    for size in _RECORD_SIZES:
        next_offset = offset + size
        if next_offset == len(data):
            return next_offset
        if next_offset + 4 <= len(data):
            next_type = struct.unpack_from("<I", data, next_offset)[0]
            if next_type in _RECORD_TYPES:
                return next_offset
    return None
