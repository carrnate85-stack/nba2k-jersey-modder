from __future__ import annotations

MAX_NUMBER_OUTLINE_THICKNESS = 20

def _recolor_font_image(
    image,
    dark_color: tuple[int, int, int] | None,
    light_color: tuple[int, int, int] | None,
    *,
    edge_protection: float = 0.75,
    outline_thickness: int = 0,
):
    rgba = image.convert("RGBA")
    if dark_color is None and light_color is None:
        return rgba
    edge_protection = _clamp(edge_protection, 0.0, 1.0)
    outline_thickness = max(
        0,
        min(MAX_NUMBER_OUTLINE_THICKNESS, int(outline_thickness)),
    )
    rgba_data = getattr(rgba, "get_flattened_data", rgba.getdata)
    pixels = list(rgba_data())
    distances = _font_alpha_edge_distances(rgba)
    fill_mixes = _font_fill_region_mixes(pixels, distances, edge_protection)
    if fill_mixes is None:
        return rgba
    if outline_thickness:
        fill_mixes = _thicken_font_outline_mixes(
            pixels,
            fill_mixes,
            rgba.width,
            rgba.height,
            outline_thickness,
        )

    recolored = []
    for index, (red, green, blue, alpha) in enumerate(pixels):
        if alpha == 0:
            recolored.append((red, green, blue, alpha))
            continue
        mix = fill_mixes[index]
        original = (red, green, blue)
        outline = dark_color if dark_color is not None else original
        fill = light_color if light_color is not None else original
        recolored.append((*_blend_rgb(outline, fill, mix), alpha))
    rgba.putdata(recolored)
    return rgba


def _thicken_font_outline_mixes(
    pixels: list[tuple[int, int, int, int]],
    fill_mixes: list[float],
    width: int,
    height: int,
    amount: int,
) -> list[float]:
    mixes = list(fill_mixes)
    outline = {
        index
        for index, (_red, _green, _blue, alpha) in enumerate(pixels)
        if alpha > 0 and mixes[index] <= 0.52
    }
    visible = {index for index, pixel in enumerate(pixels) if pixel[3] > 0}
    for _step in range(amount):
        next_outline = set(outline)
        for index in outline:
            x = index % width
            y = index // width
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if neighbor in visible and mixes[neighbor] > 0.52:
                        next_outline.add(neighbor)
        if len(next_outline) == len(outline):
            break
        outline = next_outline
    for index in outline:
        mixes[index] = 0.0
    return mixes


def _font_fill_region_mixes(
    pixels: list[tuple[int, int, int, int]],
    distances: list[float],
    edge_protection: float,
) -> list[float] | None:
    visible_indices = [
        index
        for index, (_red, _green, _blue, alpha) in enumerate(pixels)
        if alpha > 0
    ]
    if not visible_indices:
        return None

    visible_distances = [distances[index] for index in visible_indices]
    distance_mixes = _font_distance_fill_mixes(
        visible_indices,
        distances,
        edge_protection,
        len(pixels),
    )
    centers = _font_outline_fill_color_centers(pixels, distances, visible_indices)
    if centers is None:
        return distance_mixes

    outline_center, fill_center = centers
    separation = _rgb_distance(outline_center, fill_center)
    color_weight = _clamp((separation - 16.0) / 72.0, 0.0, 1.0)
    if color_weight <= 0:
        return distance_mixes

    max_distance = max(visible_distances) if visible_distances else 1.0
    mixes = [0.0] * len(pixels)
    edge_gate_weight = 0.42 * edge_protection
    for index in visible_indices:
        red, green, blue, _alpha = pixels[index]
        color = (red, green, blue)
        outline_distance = _rgb_distance(color, outline_center)
        fill_distance = _rgb_distance(color, fill_center)
        color_mix = outline_distance / max(1.0, outline_distance + fill_distance)
        color_mix = _smoothstep(_clamp(color_mix, 0.0, 1.0))
        distance_mix = distance_mixes[index]
        if max_distance > 1:
            interior_ratio = _clamp(distances[index] / max_distance, 0.0, 1.0)
            edge_gate = _smoothstep(interior_ratio)
            color_mix *= (1.0 - edge_gate_weight) + edge_gate_weight * edge_gate
        mixes[index] = (
            color_mix * color_weight
            + distance_mix * (1.0 - color_weight)
        )
    return mixes


def _font_distance_fill_mixes(
    visible_indices: list[int],
    distances: list[float],
    edge_protection: float,
    pixel_count: int,
) -> list[float]:
    edge_threshold = 0.75 + (edge_protection * 2.75)
    edge_softness = max(0.65, 2.2 - (edge_protection * 1.25))
    mixes = [0.0] * pixel_count
    for index in visible_indices:
        mixes[index] = _smoothstep(
            _clamp((distances[index] - edge_threshold) / edge_softness, 0.0, 1.0)
        )
    return mixes


def _font_outline_fill_color_centers(
    pixels: list[tuple[int, int, int, int]],
    distances: list[float],
    visible_indices: list[int],
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if len(visible_indices) < 2:
        return None
    distance_values = sorted(distances[index] for index in visible_indices)
    edge_cutoff = _percentile(distance_values, 0.28)
    fill_cutoff = _percentile(distance_values, 0.72)
    edge_indices = [
        index for index in visible_indices if distances[index] <= edge_cutoff
    ] or visible_indices
    fill_indices = [
        index for index in visible_indices if distances[index] >= fill_cutoff
    ] or visible_indices
    centers = [
        _average_rgb(pixels, edge_indices),
        _average_rgb(pixels, fill_indices),
    ]
    if _rgb_distance(centers[0], centers[1]) < 8:
        return None

    assignments: dict[int, list[int]] = {0: [], 1: []}
    for _iteration in range(8):
        assignments = {0: [], 1: []}
        for index in visible_indices:
            red, green, blue, _alpha = pixels[index]
            color = (red, green, blue)
            group = (
                0
                if _rgb_distance(color, centers[0]) <= _rgb_distance(color, centers[1])
                else 1
            )
            assignments[group].append(index)
        if not assignments[0] or not assignments[1]:
            return None
        next_centers = [
            _average_rgb(pixels, assignments[0]),
            _average_rgb(pixels, assignments[1]),
        ]
        if all(_rgb_distance(centers[index], next_centers[index]) < 0.5 for index in (0, 1)):
            centers = next_centers
            break
        centers = next_centers

    mean_distances = [
        sum(distances[index] for index in assignments[group]) / len(assignments[group])
        for group in (0, 1)
    ]
    if abs(mean_distances[0] - mean_distances[1]) < 0.35:
        return None
    fill_group = 0 if mean_distances[0] > mean_distances[1] else 1
    outline_group = 1 - fill_group
    return centers[outline_group], centers[fill_group]


def _average_rgb(
    pixels: list[tuple[int, int, int, int]],
    indices: list[int],
) -> tuple[float, float, float]:
    if not indices:
        return (0.0, 0.0, 0.0)
    red = sum(pixels[index][0] for index in indices) / len(indices)
    green = sum(pixels[index][1] for index in indices) / len(indices)
    blue = sum(pixels[index][2] for index in indices) / len(indices)
    return red, green, blue


def _rgb_distance(
    first: tuple[float, float, float] | tuple[int, int, int],
    second: tuple[float, float, float] | tuple[int, int, int],
) -> float:
    return (
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    ) ** 0.5


def _blend_rgb(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    mix: float,
) -> tuple[int, int, int]:
    return (
        round(start[0] * (1 - mix) + end[0] * mix),
        round(start[1] * (1 - mix) + end[1] * mix),
        round(start[2] * (1 - mix) + end[2] * mix),
    )


def _font_alpha_edge_distances(image) -> list[float]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    alpha_channel = rgba.getchannel("A")
    alpha_data = getattr(alpha_channel, "get_flattened_data", alpha_channel.getdata)
    alpha_values = list(alpha_data())
    large = width + height + 2
    distances = [large if alpha > 0 else 0 for alpha in alpha_values]

    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            if distances[index] == 0:
                continue
            if x == 0 or y == 0:
                distances[index] = min(distances[index], 1)
            if x > 0:
                distances[index] = min(distances[index], distances[index - 1] + 1)
            if y > 0:
                distances[index] = min(distances[index], distances[index - width] + 1)

    for y in range(height - 1, -1, -1):
        row = y * width
        for x in range(width - 1, -1, -1):
            index = row + x
            if distances[index] == 0:
                continue
            if x == width - 1 or y == height - 1:
                distances[index] = min(distances[index], 1)
            if x + 1 < width:
                distances[index] = min(distances[index], distances[index + 1] + 1)
            if y + 1 < height:
                distances[index] = min(distances[index], distances[index + width] + 1)

    return [float(distance) for distance in distances]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _smoothstep(value: float) -> float:
    return value * value * (3 - (2 * value))


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ratio = _clamp(ratio, 0.0, 1.0)
    position = ratio * (len(values) - 1)
    lower_index = int(position)
    upper_index = min(len(values) - 1, lower_index + 1)
    mix = position - lower_index
    return values[lower_index] * (1.0 - mix) + values[upper_index] * mix

