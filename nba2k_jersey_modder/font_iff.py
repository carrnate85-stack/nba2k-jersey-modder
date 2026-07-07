from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import shutil
from pathlib import Path
import struct
import subprocess
import tempfile
from typing import TYPE_CHECKING
import zipfile

from .dds import save_bc1_dds

if TYPE_CHECKING:
    from PIL.Image import Image as PillowImage


@dataclass(frozen=True)
class FontNumberTextureInfo:
    source_path: Path
    entry_name: str
    width: int
    height: int
    cell_width: int
    mip_count: int
    dds_format: str
    dxgi_format: int | None = None

    @property
    def format_label(self) -> str:
        if self.dds_format == "DX10" and self.dxgi_format == 98:
            return "BC7"
        if self.dds_format == "DX10" and self.dxgi_format == 99:
            return "BC7 sRGB"
        if self.dds_format == "DXT1":
            return "BC1"
        return self.dds_format


def extract_number_sheet_from_font_iff(path: str | Path) -> "PillowImage":
    from PIL import Image

    info = inspect_font_number_texture(path)

    with zipfile.ZipFile(info.source_path) as archive:
        data = archive.read(info.entry_name)

    with Image.open(BytesIO(data)) as opened:
        return opened.convert("RGBA").copy()


def inspect_font_number_texture(path: str | Path) -> FontNumberTextureInfo:
    file_path = Path(path)
    if not zipfile.is_zipfile(file_path):
        raise ValueError("This font IFF is not in the readable archive format.")

    with zipfile.ZipFile(file_path) as archive:
        entry_name = _find_number_color_entry(archive.namelist())
        if entry_name is None:
            raise ValueError("Could not find font_number_color DDS inside this IFF.")
        data = archive.read(entry_name)

    if len(data) < 128 or not data.startswith(b"DDS "):
        raise ValueError(f"{entry_name} is not a readable DDS texture.")

    height = struct.unpack_from("<I", data, 12)[0]
    width = struct.unpack_from("<I", data, 16)[0]
    mip_count = struct.unpack_from("<I", data, 28)[0]
    fourcc = data[84:88]
    dxgi_format = None
    if fourcc == b"DX10":
        if len(data) < 148:
            raise ValueError(f"{entry_name} has an incomplete DX10 DDS header.")
        dxgi_format = struct.unpack_from("<I", data, 128)[0]
        dds_format = "DX10"
    elif fourcc == b"DXT1":
        dds_format = "DXT1"
    else:
        dds_format = fourcc.decode("ascii", errors="replace").strip("\0") or "RGBA"

    if width % 10 != 0:
        raise ValueError(f"Number texture width {width} is not divisible into ten digits.")

    return FontNumberTextureInfo(
        source_path=file_path,
        entry_name=entry_name,
        width=width,
        height=height,
        cell_width=width // 10,
        mip_count=max(1, mip_count),
        dds_format=dds_format,
        dxgi_format=dxgi_format,
    )


def split_number_sheet_digits(sheet: "PillowImage", digit_count: int = 10) -> list["PillowImage"]:
    if digit_count < 1:
        raise ValueError("Digit count must be at least 1.")
    if sheet.width % digit_count != 0:
        raise ValueError(
            f"Number sheet width {sheet.width} is not divisible by {digit_count}."
        )
    cell_width = sheet.width // digit_count
    return [
        sheet.crop((index * cell_width, 0, (index + 1) * cell_width, sheet.height))
        for index in range(digit_count)
    ]


def build_font_number_sheet(
    digit_paths: dict[str, Path],
    size: tuple[int, int],
) -> "PillowImage":
    from PIL import Image

    width, height = size
    if width <= 0 or height <= 0 or width % 10 != 0:
        raise ValueError("Font number sheet needs a positive width divisible by 10.")

    cell_width = width // 10
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for index in range(10):
        path = digit_paths.get(str(index))
        if path is None or not path.exists():
            continue
        with Image.open(path) as opened:
            digit = opened.convert("RGBA")
        if digit.size != (cell_width, height):
            digit = _fit_digit_to_cell(digit, (cell_width, height))
        sheet.alpha_composite(digit, (index * cell_width, 0))
    return sheet


def write_number_sheet_to_font_iff(
    source_iff: str | Path,
    output_iff: str | Path,
    sheet: "PillowImage",
    *,
    texconv_path: str | Path | None = None,
) -> None:
    info = inspect_font_number_texture(source_iff)
    if sheet.size != (info.width, info.height):
        raise ValueError(
            f"Number sheet must be {info.width} x {info.height} for this font IFF."
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        dds_path = tmp_path / "font_number_color.dds"
        _save_sheet_as_matching_dds(sheet, dds_path, info, texconv_path=texconv_path)
        _replace_archive_entry(info.source_path, Path(output_iff), info.entry_name, dds_path.read_bytes())


def find_texconv() -> Path | None:
    found = shutil.which("texconv")
    if found:
        return Path(found)
    candidates = [
        Path.cwd() / "tools" / "texconv.exe",
        Path.cwd() / "texconv.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _save_sheet_as_matching_dds(
    sheet: "PillowImage",
    output_path: Path,
    info: FontNumberTextureInfo,
    *,
    texconv_path: str | Path | None,
) -> None:
    if info.dds_format == "DXT1":
        texconv = Path(texconv_path) if texconv_path else find_texconv()
        if texconv is not None and texconv.exists():
            try:
                _save_with_texconv(
                    sheet,
                    output_path,
                    texconv,
                    "BC1_UNORM",
                    "BC1 DDS conversion",
                    extra_args=("-dx9",),
                )
                return
            except RuntimeError:
                pass
        save_bc1_dds(sheet, output_path)
        return

    if info.dds_format == "DX10" and info.dxgi_format in {98, 99}:
        texconv = Path(texconv_path) if texconv_path else find_texconv()
        if texconv is None or not texconv.exists():
            raise RuntimeError(
                "This font uses BC7 DDS. Put texconv.exe in the app folder or "
                "in a tools folder, then try Save Back again."
            )
        format_name = "BC7_UNORM_SRGB" if info.dxgi_format == 99 else "BC7_UNORM"
        _save_with_texconv(sheet, output_path, texconv, format_name, "BC7 DDS conversion")
        return

    raise RuntimeError(f"Font DDS format {info.format_label} is not supported for write-back yet.")


def _save_with_texconv(
    sheet: "PillowImage",
    output_path: Path,
    texconv: Path,
    format_name: str,
    error_label: str,
    *,
    extra_args: tuple[str, ...] = (),
) -> None:
    source_png = output_path.with_suffix(".png")
    sheet.save(source_png)
    command = [
        str(texconv),
        "-nologo",
        "-y",
        "-f",
        format_name,
        "-m",
        "0",
        *extra_args,
        "-o",
        str(output_path.parent),
        str(source_png),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    converted = output_path.parent / f"{source_png.stem}.DDS"
    if result.returncode != 0 or not converted.exists():
        details = (result.stderr or result.stdout or "texconv did not create a DDS.").strip()
        raise RuntimeError(f"{error_label} failed.\n\n{details}")
    converted.replace(output_path)


def _replace_archive_entry(
    source_iff: Path,
    output_iff: Path,
    entry_name: str,
    replacement_data: bytes,
) -> None:
    output_iff.parent.mkdir(parents=True, exist_ok=True)
    same_path = source_iff.resolve() == output_iff.resolve()
    target_path = output_iff
    temp_output: Path | None = None
    if same_path:
        handle = tempfile.NamedTemporaryFile(
            prefix=f"{output_iff.stem}_",
            suffix=output_iff.suffix,
            dir=output_iff.parent,
            delete=False,
        )
        temp_output = Path(handle.name)
        handle.close()
        target_path = temp_output

    with zipfile.ZipFile(source_iff, "r") as source:
        with zipfile.ZipFile(target_path, "w") as target:
            for info in source.infolist():
                if info.filename == entry_name:
                    new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    new_info.compress_type = info.compress_type
                    new_info.comment = info.comment
                    new_info.extra = info.extra
                    new_info.internal_attr = info.internal_attr
                    new_info.external_attr = info.external_attr
                    target.writestr(new_info, replacement_data)
                else:
                    target.writestr(info, source.read(info.filename))
    if temp_output is not None:
        temp_output.replace(output_iff)


def _fit_digit_to_cell(digit: "PillowImage", size: tuple[int, int]) -> "PillowImage":
    from PIL import Image

    cell_width, cell_height = size
    fitted = Image.new("RGBA", size, (0, 0, 0, 0))
    working = digit.copy()
    working.thumbnail(size, Image.Resampling.LANCZOS)
    x = (cell_width - working.width) // 2
    y = (cell_height - working.height) // 2
    fitted.alpha_composite(working, (x, y))
    return fitted


def _find_number_color_entry(names: list[str]) -> str | None:
    dds_names = [name for name in names if name.lower().endswith(".dds")]
    for name in dds_names:
        base_name = Path(name.replace("\\", "/")).name.lower()
        if base_name.startswith("font_number_color."):
            return name
    for name in dds_names:
        base_name = Path(name.replace("\\", "/")).name.lower()
        if "font_number_color" in base_name:
            return name
    return None
