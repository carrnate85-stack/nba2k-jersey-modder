from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path


@dataclass(frozen=True)
class TrimStrip:
    name: str
    bbox: tuple[int, int, int, int]
    output_path: Path


@dataclass(frozen=True)
class _Component:
    bbox: tuple[int, int, int, int]
    area: int


def create_trim_strips_from_mockup(
    image_path: Path,
    output_dir: Path,
    *,
    strip_size: tuple[int, int] = (1024, 64),
) -> list[TrimStrip]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Trim Creator requires Pillow.") from exc

    image = Image.open(image_path).convert("RGBA")
    components = _detect_trim_components(image)
    assignments = _assign_trim_components(components, image.size)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[TrimStrip] = []
    for name, component in assignments.items():
        strip = _component_to_strip(image, name, component.bbox, strip_size)
        output_path = output_dir / f"{name}.png"
        strip.save(output_path)
        results.append(TrimStrip(name=name, bbox=component.bbox, output_path=output_path))
    return results


def create_trim_strip_from_line(
    image_path: Path,
    output_path: Path,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    strip_size: tuple[int, int] = (1024, 64),
    sample_width: int = 3,
    crop_top: int = 0,
    crop_bottom: int = 0,
) -> Path:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Trim Creator requires Pillow.") from exc

    image = Image.open(image_path).convert("RGBA")
    expanded_start, expanded_end, expanded_size, trim_top, trim_bottom = (
        _line_sample_settings_for_crop(start, end, strip_size, crop_top, crop_bottom)
    )
    sampled = _sample_line_to_strip(
        image,
        expanded_start,
        expanded_end,
        expanded_size,
        sample_width,
    )
    strip = _redraw_clean_trim_strip(sampled)
    strip = _crop_strip_vertical(strip, trim_top, trim_bottom)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(output_path)
    return output_path


def correct_trim_strip(
    input_path: Path,
    output_path: Path,
    *,
    max_gap: int = 3,
) -> Path:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Trim Creator requires Pillow.") from exc

    image = Image.open(input_path).convert("RGBA")
    corrected = _redraw_corrected_trim_strip(image, max_gap=max_gap)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    corrected.save(output_path)
    return output_path


def _line_sample_settings_for_crop(
    start: tuple[int, int],
    end: tuple[int, int],
    strip_size: tuple[int, int],
    crop_top: int,
    crop_bottom: int,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], int, int]:
    crop_top = int(crop_top)
    crop_bottom = int(crop_bottom)
    top_extra = max(0, -crop_top)
    bottom_extra = max(0, -crop_bottom)
    trim_top = max(0, crop_top)
    trim_bottom = max(0, crop_bottom)
    if top_extra == 0 and bottom_extra == 0:
        return start, end, strip_size, trim_top, trim_bottom

    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length = max(1.0, math.hypot(dx, dy))
    unit_x = dx / length
    unit_y = dy / length
    expanded_start = (
        round(x1 - unit_x * top_extra),
        round(y1 - unit_y * top_extra),
    )
    expanded_end = (
        round(x2 + unit_x * bottom_extra),
        round(y2 + unit_y * bottom_extra),
    )
    expanded_size = (
        strip_size[0],
        max(1, strip_size[1] + top_extra + bottom_extra),
    )
    return expanded_start, expanded_end, expanded_size, trim_top, trim_bottom


def _crop_strip_vertical(strip, crop_top: int, crop_bottom: int):
    crop_top = max(0, int(crop_top))
    crop_bottom = max(0, int(crop_bottom))
    max_crop = max(0, strip.height - 1)
    if crop_top + crop_bottom > max_crop:
        overflow = crop_top + crop_bottom - max_crop
        crop_bottom = max(0, crop_bottom - overflow)
        if crop_top + crop_bottom > max_crop:
            crop_top = max(0, max_crop - crop_bottom)
    top = min(strip.height - 1, crop_top)
    bottom = max(top + 1, strip.height - crop_bottom)
    return strip.crop((0, top, strip.width, bottom))


def _sample_line_to_strip(
    image,
    start: tuple[int, int],
    end: tuple[int, int],
    strip_size: tuple[int, int],
    sample_width: int,
):
    from PIL import Image

    strip_width, strip_height = strip_size
    sampled = Image.new("RGBA", strip_size, (0, 0, 0, 0))
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length = max(1.0, math.hypot(dx, dy))
    normal_x = -dy / length
    normal_y = dx / length
    radius = max(0, sample_width // 2)

    for output_y in range(strip_height):
        amount = output_y / max(1, strip_height - 1)
        source_x = x1 + dx * amount
        source_y = y1 + dy * amount
        color = _average_sampled_color(image, source_x, source_y, normal_x, normal_y, radius)
        for output_x in range(strip_width):
            sampled.putpixel((output_x, output_y), color)
    return sampled


def _average_sampled_color(
    image,
    x: float,
    y: float,
    normal_x: float,
    normal_y: float,
    radius: int,
) -> tuple[int, int, int, int]:
    colors: list[tuple[int, int, int, int]] = []
    for offset in range(-radius, radius + 1):
        sx = round(x + normal_x * offset)
        sy = round(y + normal_y * offset)
        if 0 <= sx < image.width and 0 <= sy < image.height:
            colors.append(image.getpixel((sx, sy)))
    if not colors:
        return (0, 0, 0, 0)
    buckets: dict[tuple[int, int, int, int], list[tuple[int, int, int, int]]] = {}
    for color in colors:
        bucket = (color[0] // 16, color[1] // 16, color[2] // 16, color[3] // 16)
        buckets.setdefault(bucket, []).append(color)
    colors = max(buckets.values(), key=len)
    return tuple(round(sum(color[index] for color in colors) / len(colors)) for index in range(4))


def _detect_trim_components(image) -> list[_Component]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    background = _corner_background_color(rgb)
    mask = bytearray(width * height)

    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            saturation = max(red, green, blue) - min(red, green, blue)
            brightness = (red + green + blue) // 3
            background_distance = _color_distance((red, green, blue), background)
            is_candidate = (
                background_distance > 48
                and (
                    saturation > 45
                    or brightness < 70
                    or brightness > 225
                )
            )
            if is_candidate:
                mask[y * width + x] = 1

    return _connected_components(mask, width, height)


def _corner_background_color(image) -> tuple[int, int, int]:
    width, height = image.size
    samples = [
        image.getpixel((0, 0)),
        image.getpixel((width - 1, 0)),
        image.getpixel((0, height - 1)),
        image.getpixel((width - 1, height - 1)),
    ]
    return tuple(round(sum(sample[index] for sample in samples) / len(samples)) for index in range(3))


def _color_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> int:
    return sum(abs(first[index] - second[index]) for index in range(3))


def _connected_components(mask: bytearray, width: int, height: int) -> list[_Component]:
    visited = bytearray(len(mask))
    components: list[_Component] = []

    for start_y in range(height):
        for start_x in range(width):
            start_index = start_y * width + start_x
            if visited[start_index] or not mask[start_index]:
                continue
            queue: deque[tuple[int, int]] = deque([(start_x, start_y)])
            visited[start_index] = 1
            min_x = max_x = start_x
            min_y = max_y = start_y
            area = 0

            while queue:
                x, y = queue.popleft()
                area += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    index = ny * width + nx
                    if visited[index] or not mask[index]:
                        continue
                    visited[index] = 1
                    queue.append((nx, ny))

            bbox = (min_x, min_y, max_x + 1, max_y + 1)
            box_width = bbox[2] - bbox[0]
            box_height = bbox[3] - bbox[1]
            if area >= 60 and box_width >= 4 and box_height >= 4:
                components.append(_Component(bbox=bbox, area=area))

    return sorted(components, key=lambda component: component.area, reverse=True)


def _assign_trim_components(
    components: list[_Component],
    image_size: tuple[int, int],
) -> dict[str, _Component]:
    width, height = image_size
    usable = [
        component
        for component in components
        if component.bbox[1] < height * 0.72
    ]

    collar_candidates = [
        component
        for component in usable
        if _component_center(component)[1] < height * 0.45
        and (component.bbox[2] - component.bbox[0]) >= (component.bbox[3] - component.bbox[1])
    ]
    left_candidates = [
        component
        for component in usable
        if _component_center(component)[0] < width * 0.48
    ]
    right_candidates = [
        component
        for component in usable
        if _component_center(component)[0] > width * 0.52
    ]

    assigned: dict[str, _Component] = {}
    if collar_candidates:
        assigned["collar_trim"] = min(
            collar_candidates,
            key=lambda component: (
                abs(_component_center(component)[0] - width / 2),
                component.bbox[1],
            ),
        )
    if left_candidates:
        assigned["left_arm_hole_trim"] = min(
            left_candidates,
            key=lambda component: (
                abs(_component_center(component)[0] - width * 0.25),
                component.bbox[1],
            ),
        )
    if right_candidates:
        assigned["right_arm_hole_trim"] = min(
            right_candidates,
            key=lambda component: (
                abs(_component_center(component)[0] - width * 0.75),
                component.bbox[1],
            ),
        )
    return assigned


def _component_center(component: _Component) -> tuple[float, float]:
    left, top, right, bottom = component.bbox
    return (left + right) / 2, (top + bottom) / 2


def _component_to_strip(
    image,
    name: str,
    bbox: tuple[int, int, int, int],
    strip_size: tuple[int, int],
):
    from PIL import Image

    crop = image.crop(bbox).convert("RGBA")
    if crop.width <= 0 or crop.height <= 0:
        return Image.new("RGBA", strip_size, (0, 0, 0, 0))

    mask = _trim_mask_for_crop(crop)
    if name == "collar_trim":
        curved = _unwrap_circular_trim_to_strip(crop, mask, strip_size)
        if curved is not None:
            return _redraw_clean_trim_strip(curved)

    if crop.height > crop.width:
        crop = crop.rotate(90, expand=True)
        mask = _trim_mask_for_crop(crop)

    strip = _straighten_crop_to_strip(crop, mask, strip_size)
    return _redraw_clean_trim_strip(strip)


def _trim_mask_for_crop(crop) -> bytearray:
    width, height = crop.size
    rgb = crop.convert("RGB")
    pixels = rgb.load()
    background = _corner_background_color(rgb)
    mask = bytearray(width * height)
    hits = 0

    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = crop.getpixel((x, y))
            if alpha == 0:
                continue
            saturation = max(red, green, blue) - min(red, green, blue)
            brightness = (red + green + blue) // 3
            background_distance = _color_distance((red, green, blue), background)
            if background_distance > 32 and (
                saturation > 24
                or brightness < 90
                or brightness > 215
                or background_distance > 90
            ):
                mask[y * width + x] = 1
                hits += 1

    if hits < width * height * 0.18:
        for y in range(height):
            for x in range(width):
                if crop.getpixel((x, y))[3] > 0:
                    mask[y * width + x] = 1
    return mask


def _straighten_crop_to_strip(crop, mask: bytearray, strip_size: tuple[int, int]):
    from PIL import Image

    strip_width, strip_height = strip_size
    strip = Image.new("RGBA", strip_size, (0, 0, 0, 0))
    columns = [_column_trim_bounds(mask, crop.width, crop.height, x) for x in range(crop.width)]

    last_bounds = (0, crop.height - 1)
    for output_x in range(strip_width):
        source_x = round(output_x * (crop.width - 1) / max(1, strip_width - 1))
        bounds = _nearest_column_bounds(columns, source_x, last_bounds)
        last_bounds = bounds
        top, bottom = bounds
        for output_y in range(strip_height):
            source_y = round(top + output_y * (bottom - top) / max(1, strip_height - 1))
            strip.putpixel((output_x, output_y), crop.getpixel((source_x, source_y)))
    return strip


def _unwrap_circular_trim_to_strip(crop, mask: bytearray, strip_size: tuple[int, int]):
    points = _mask_points(mask, crop.width, crop.height)
    if len(points) < 24:
        return None

    circle = _fit_circle(points)
    if circle is None:
        return None

    cx, cy, radius = circle
    if radius < 4:
        return None

    angle_range = _continuous_angle_range(points, cx, cy)
    if angle_range is None:
        return None
    start_angle, end_angle = angle_range
    if end_angle - start_angle < 0.45:
        return None

    bins = _radial_bounds_by_angle(points, cx, cy, start_angle, end_angle, strip_size[0])
    if sum(1 for bounds in bins if bounds is not None) < max(8, strip_size[0] // 8):
        return None

    return _sample_arc_strip(crop, bins, cx, cy, start_angle, end_angle, strip_size)


def _mask_points(mask: bytearray, width: int, height: int) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for y in range(height):
        row = y * width
        for x in range(width):
            if mask[row + x]:
                points.append((x, y))
    return points


def _column_centerline_points(
    mask: bytearray,
    width: int,
    height: int,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for x in range(width):
        bounds = _column_trim_bounds(mask, width, height, x)
        if bounds is None:
            continue
        top, bottom = bounds
        points.append((float(x), (top + bottom) / 2))
    return points


def _fit_circle(points: list[tuple[float, float]] | list[tuple[int, int]]):
    count = len(points)
    if count < 3:
        return None

    sum_x = sum(point[0] for point in points)
    sum_y = sum(point[1] for point in points)
    sum_xx = sum(point[0] * point[0] for point in points)
    sum_yy = sum(point[1] * point[1] for point in points)
    sum_xy = sum(point[0] * point[1] for point in points)
    sum_z = sum(point[0] * point[0] + point[1] * point[1] for point in points)
    sum_xz = sum(point[0] * (point[0] * point[0] + point[1] * point[1]) for point in points)
    sum_yz = sum(point[1] * (point[0] * point[0] + point[1] * point[1]) for point in points)

    solution = _solve_3x3(
        [
            [sum_xx, sum_xy, sum_x],
            [sum_xy, sum_yy, sum_y],
            [sum_x, sum_y, float(count)],
        ],
        [-sum_xz, -sum_yz, -sum_z],
    )
    if solution is None:
        return None
    a, b, c = solution
    cx = -a / 2
    cy = -b / 2
    radius_squared = cx * cx + cy * cy - c
    if radius_squared <= 0:
        return None
    return cx, cy, math.sqrt(radius_squared)


def _solve_3x3(matrix: list[list[float]], values: list[float]) -> tuple[float, float, float] | None:
    rows = [matrix[index][:] + [values[index]] for index in range(3)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-6:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        pivot_value = rows[column][column]
        for item in range(column, 4):
            rows[column][item] /= pivot_value
        for row in range(3):
            if row == column:
                continue
            factor = rows[row][column]
            for item in range(column, 4):
                rows[row][item] -= factor * rows[column][item]
    return rows[0][3], rows[1][3], rows[2][3]


def _continuous_angle_range(
    points: list[tuple[int, int]],
    cx: float,
    cy: float,
) -> tuple[float, float] | None:
    angles = sorted((math.atan2(y - cy, x - cx) + math.tau) % math.tau for x, y in points)
    if len(angles) < 2:
        return None

    largest_gap = -1.0
    gap_index = 0
    for index, angle in enumerate(angles):
        next_angle = angles[(index + 1) % len(angles)]
        if index == len(angles) - 1:
            next_angle += math.tau
        gap = next_angle - angle
        if gap > largest_gap:
            largest_gap = gap
            gap_index = index

    start = angles[(gap_index + 1) % len(angles)]
    end = angles[gap_index]
    if end < start:
        end += math.tau
    return start, end


def _radial_bounds_by_angle(
    points: list[tuple[int, int]],
    cx: float,
    cy: float,
    start_angle: float,
    end_angle: float,
    bin_count: int,
) -> list[tuple[float, float] | None]:
    bins: list[tuple[float, float] | None] = [None] * bin_count
    angle_span = max(1e-6, end_angle - start_angle)
    for x, y in points:
        angle = (math.atan2(y - cy, x - cx) + math.tau) % math.tau
        while angle < start_angle:
            angle += math.tau
        while angle > end_angle:
            angle -= math.tau
        if angle < start_angle or angle > end_angle:
            continue
        index = min(bin_count - 1, max(0, round((angle - start_angle) / angle_span * (bin_count - 1))))
        radius = math.hypot(x - cx, y - cy)
        bounds = bins[index]
        if bounds is None:
            bins[index] = (radius, radius)
        else:
            bins[index] = (min(bounds[0], radius), max(bounds[1], radius))
    return bins


def _sample_arc_strip(
    crop,
    bins: list[tuple[float, float] | None],
    cx: float,
    cy: float,
    start_angle: float,
    end_angle: float,
    strip_size: tuple[int, int],
):
    from PIL import Image

    strip_width, strip_height = strip_size
    strip = Image.new("RGBA", strip_size, (0, 0, 0, 0))
    fallback = next((bounds for bounds in bins if bounds is not None), (0.0, 1.0))
    last_bounds = fallback
    for output_x in range(strip_width):
        angle = start_angle + output_x * (end_angle - start_angle) / max(1, strip_width - 1)
        bounds = _nearest_radial_bounds(bins, output_x, last_bounds)
        last_bounds = bounds
        inner_radius, outer_radius = bounds
        if outer_radius < inner_radius:
            inner_radius, outer_radius = outer_radius, inner_radius
        for output_y in range(strip_height):
            radius = inner_radius + output_y * (outer_radius - inner_radius) / max(1, strip_height - 1)
            source_x = round(cx + math.cos(angle) * radius)
            source_y = round(cy + math.sin(angle) * radius)
            if 0 <= source_x < crop.width and 0 <= source_y < crop.height:
                strip.putpixel((output_x, output_y), crop.getpixel((source_x, source_y)))
    return strip


def _redraw_clean_trim_strip(sampled):
    from PIL import Image, ImageDraw

    width, height = sampled.size
    rows = [_row_trim_color(sampled, y) for y in range(height)]
    bands = _trim_color_bands(rows, height)
    clean = Image.new("RGBA", sampled.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(clean)
    for top, bottom, color in bands:
        if color is None:
            continue
        draw.rectangle((0, top, width, bottom - 1), fill=(*color, 255))
    return clean


def _redraw_corrected_trim_strip(sampled, *, max_gap: int = 3):
    from PIL import Image, ImageDraw

    width, height = sampled.size
    rows = [_row_trim_color(sampled, y) for y in range(height)]
    rows = _fill_short_trim_gaps(rows, max_gap=max_gap)
    bands = _trim_color_bands(rows, height)
    clean = Image.new("RGBA", sampled.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(clean)
    for top, bottom, color in bands:
        if color is None:
            continue
        draw.rectangle((0, top, width, bottom - 1), fill=(*color, 255))
    return clean


def _fill_short_trim_gaps(
    rows: list[tuple[int, int, int] | None],
    *,
    max_gap: int,
) -> list[tuple[int, int, int] | None]:
    filled = list(rows)
    colored_indexes = [index for index, color in enumerate(rows) if color is not None]
    if not colored_indexes:
        return filled
    first = colored_indexes[0]
    last = colored_indexes[-1]
    index = first
    while index <= last:
        if filled[index] is not None:
            index += 1
            continue
        gap_start = index
        while index <= last and filled[index] is None:
            index += 1
        gap_end = index
        gap_size = gap_end - gap_start
        before = filled[gap_start - 1] if gap_start > 0 else None
        after = filled[gap_end] if gap_end < len(filled) else None
        if gap_size <= max_gap and before is not None and after is not None:
            fill_color = _average_band_color([before, after], before)
            for gap_index in range(gap_start, gap_end):
                filled[gap_index] = fill_color
    return filled


def _row_trim_color(sampled, y: int) -> tuple[int, int, int] | None:
    pixels = sampled.load()
    buckets: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    for x in range(sampled.width):
        red, green, blue, alpha = pixels[x, y]
        if alpha < 16:
            continue
        bucket = (red // 16, green // 16, blue // 16)
        buckets.setdefault(bucket, []).append((red, green, blue))
    color_count = sum(len(colors) for colors in buckets.values())
    if color_count < max(2, sampled.width // 10):
        return None
    colors = max(buckets.values(), key=len)
    return tuple(round(sum(color[index] for color in colors) / len(colors)) for index in range(3))


def _trim_color_bands(
    rows: list[tuple[int, int, int] | None],
    height: int,
) -> list[tuple[int, int, tuple[int, int, int] | None]]:
    raw_bands: list[tuple[int, int, tuple[int, int, int] | None]] = []
    start = 0
    current = rows[0] if rows else None
    for y, color in enumerate(rows[1:], start=1):
        if _same_trim_band(current, color):
            continue
        raw_bands.append((start, y, current))
        start = y
        current = color
    raw_bands.append((start, height, current))

    merged: list[tuple[int, int, tuple[int, int, int] | None]] = []
    for top, bottom, color in raw_bands:
        if bottom - top < 2 and merged:
            previous_top, _previous_bottom, previous_color = merged[-1]
            merged[-1] = (previous_top, bottom, previous_color)
            continue
        if merged and _same_trim_band(merged[-1][2], color):
            previous_top, _previous_bottom, previous_color = merged[-1]
            merged[-1] = (previous_top, bottom, previous_color)
        else:
            merged.append((top, bottom, color))
    return [
        (top, bottom, _average_band_color(rows[top:bottom], color))
        for top, bottom, color in merged
    ]


def _same_trim_band(
    first: tuple[int, int, int] | None,
    second: tuple[int, int, int] | None,
) -> bool:
    if first is None or second is None:
        return first is second
    return _color_distance(first, second) <= 54


def _average_band_color(
    colors: list[tuple[int, int, int] | None],
    fallback: tuple[int, int, int] | None,
) -> tuple[int, int, int] | None:
    usable = [color for color in colors if color is not None]
    if not usable:
        return fallback
    return tuple(round(sum(color[index] for color in usable) / len(usable)) for index in range(3))


def _nearest_radial_bounds(
    bins: list[tuple[float, float] | None],
    index: int,
    fallback: tuple[float, float],
) -> tuple[float, float]:
    if bins[index] is not None:
        return bins[index]
    for radius in range(1, len(bins)):
        left = index - radius
        right = index + radius
        if left >= 0 and bins[left] is not None:
            return bins[left]
        if right < len(bins) and bins[right] is not None:
            return bins[right]
    return fallback


def _column_trim_bounds(
    mask: bytearray,
    width: int,
    height: int,
    x: int,
) -> tuple[int, int] | None:
    rows = [y for y in range(height) if mask[y * width + x]]
    if not rows:
        return None
    return min(rows), max(rows)


def _nearest_column_bounds(
    columns: list[tuple[int, int] | None],
    source_x: int,
    fallback: tuple[int, int],
) -> tuple[int, int]:
    if columns[source_x] is not None:
        return columns[source_x]
    for radius in range(1, len(columns)):
        left = source_x - radius
        right = source_x + radius
        if left >= 0 and columns[left] is not None:
            return columns[left]
        if right < len(columns) and columns[right] is not None:
            return columns[right]
    return fallback
