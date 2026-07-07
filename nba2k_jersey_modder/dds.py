from __future__ import annotations

from pathlib import Path
import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PillowImage


DDS_MAGIC = b"DDS "
DXT1_FOURCC = b"DXT1"


def save_bc1_dds(
    source: str | Path | PillowImage,
    output_path: str | Path,
    *,
    generate_mipmaps: bool = True,
) -> None:
    from PIL import Image

    if isinstance(source, str | Path):
        opened = Image.open(source)
        try:
            image = opened.convert("RGBA")
        finally:
            opened.close()
    else:
        image = source.convert("RGBA")

    if image.width < 1 or image.height < 1:
        raise ValueError("DDS export needs an image with a real width and height.")

    mipmaps = _mipmap_chain(image) if generate_mipmaps else [image]
    payload = b"".join(_encode_bc1_blocks(mipmap) for mipmap in mipmaps)
    header = _dds_header(image.width, image.height, len(mipmaps))
    Path(output_path).write_bytes(DDS_MAGIC + header + payload)


def _mipmap_chain(image: PillowImage) -> list[PillowImage]:
    from PIL import Image

    mipmaps = [image]
    current = image
    while current.width > 1 or current.height > 1:
        next_size = (max(1, current.width // 2), max(1, current.height // 2))
        current = current.resize(next_size, Image.Resampling.LANCZOS)
        mipmaps.append(current)
    return mipmaps


def _dds_header(width: int, height: int, mipmap_count: int) -> bytes:
    ddsd_caps = 0x1
    ddsd_height = 0x2
    ddsd_width = 0x4
    ddsd_pixelformat = 0x1000
    ddsd_mipmapcount = 0x20000
    ddsd_linearsize = 0x80000
    ddpf_fourcc = 0x4
    ddscaps_complex = 0x8
    ddscaps_texture = 0x1000
    ddscaps_mipmap = 0x400000

    flags = ddsd_caps | ddsd_height | ddsd_width | ddsd_pixelformat | ddsd_linearsize
    caps = ddscaps_texture
    if mipmap_count > 1:
        flags |= ddsd_mipmapcount
        caps |= ddscaps_complex | ddscaps_mipmap

    linear_size = ((width + 3) // 4) * ((height + 3) // 4) * 8
    header = struct.pack(
        "<7I11I2I4s5I5I",
        124,
        flags,
        height,
        width,
        linear_size,
        0,
        mipmap_count,
        *([0] * 11),
        32,
        ddpf_fourcc,
        DXT1_FOURCC,
        0,
        0,
        0,
        0,
        0,
        caps,
        0,
        0,
        0,
        0,
    )
    if len(header) != 124:
        raise AssertionError("DDS header must be 124 bytes.")
    return header


def _encode_bc1_blocks(image: PillowImage) -> bytes:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    encoded = bytearray()
    for y in range(0, rgba.height, 4):
        for x in range(0, rgba.width, 4):
            block = []
            for by in range(4):
                py = min(y + by, rgba.height - 1)
                for bx in range(4):
                    px = min(x + bx, rgba.width - 1)
                    block.append(pixels[px, py])
            encoded.extend(_encode_bc1_block(block))
    return bytes(encoded)


def _encode_bc1_block(block: list[tuple[int, int, int, int]]) -> bytes:
    first_pixel = block[0]
    if all(pixel == first_pixel for pixel in block):
        color = first_pixel[:3]
        code = _rgb_to_565(color)
        color0, color1 = (code, code)
        transparent_index = 3 if first_pixel[3] < 128 else 0
        indices = 0
        if transparent_index:
            for index in range(16):
                indices |= transparent_index << (index * 2)
        return struct.pack("<HHI", color0, color1, indices)

    has_alpha = any(pixel[3] < 128 for pixel in block)
    colors = [pixel[:3] for pixel in block if pixel[3] >= 128]
    if not colors:
        color_a = (0, 0, 0)
        color_b = (0, 0, 0)
    else:
        color_a, color_b = _endpoint_colors(colors)

    code_a = _rgb_to_565(color_a)
    code_b = _rgb_to_565(color_b)
    if has_alpha:
        color0, color1 = (code_a, code_b) if code_a <= code_b else (code_b, code_a)
    else:
        color0, color1 = (code_a, code_b) if code_a >= code_b else (code_b, code_a)

    palette = _bc1_palette(color0, color1)
    indices = 0
    usable_palette_length = 3 if color0 <= color1 else 4
    for index, pixel in enumerate(block):
        if has_alpha and pixel[3] < 128:
            palette_index = 3
        else:
            palette_index = _closest_palette_index(pixel[:3], palette, usable_palette_length)
        indices |= palette_index << (index * 2)

    return struct.pack("<HHI", color0, color1, indices)


def _endpoint_colors(colors: list[tuple[int, int, int]]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if len(colors) == 1:
        return colors[0], colors[0]
    red_range = max(color[0] for color in colors) - min(color[0] for color in colors)
    green_range = max(color[1] for color in colors) - min(color[1] for color in colors)
    blue_range = max(color[2] for color in colors) - min(color[2] for color in colors)
    axis = max(range(3), key=(red_range, green_range, blue_range).__getitem__)
    return (
        min(colors, key=lambda color: color[axis]),
        max(colors, key=lambda color: color[axis]),
    )


def _rgb_to_565(color: tuple[int, int, int]) -> int:
    r, g, b = color
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def _rgb_from_565(value: int) -> tuple[int, int, int]:
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return (
        (r << 3) | (r >> 2),
        (g << 2) | (g >> 4),
        (b << 3) | (b >> 2),
    )


def _bc1_palette(color0: int, color1: int) -> list[tuple[int, int, int]]:
    rgb0 = _rgb_from_565(color0)
    rgb1 = _rgb_from_565(color1)
    if color0 > color1:
        return [
            rgb0,
            rgb1,
            tuple((2 * a + b) // 3 for a, b in zip(rgb0, rgb1)),
            tuple((a + 2 * b) // 3 for a, b in zip(rgb0, rgb1)),
        ]
    return [
        rgb0,
        rgb1,
        tuple((a + b) // 2 for a, b in zip(rgb0, rgb1)),
        (0, 0, 0),
    ]


def _closest_palette_index(
    color: tuple[int, int, int],
    palette: list[tuple[int, int, int]],
    usable_palette_length: int,
) -> int:
    best_index = 0
    best_distance = None
    for index in range(usable_palette_length):
        distance = _color_distance(color, palette[index])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def _color_distance(color_a: tuple[int, int, int], color_b: tuple[int, int, int]) -> int:
    return sum((a - b) * (a - b) for a, b in zip(color_a, color_b))
