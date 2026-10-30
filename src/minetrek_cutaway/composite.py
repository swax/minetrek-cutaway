"""Generic caption layers and frame dissolves, declared as JSON drawing data."""

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .paths import relative_path


@lru_cache(maxsize=256)
def font(path, size):
    return (
        ImageFont.load_default(size=size) if path == "default" else ImageFont.truetype(path, size)
    )


def draw_operations(image, operations, base):
    draw = ImageDraw.Draw(image)
    for op in operations:
        kind = op["type"]
        if kind == "rectangle":
            draw.rectangle(op["bounds"], fill=tuple(op["fill"]))
        elif kind == "text":
            font_path = (
                "default" if op["font"] == "default" else str(relative_path(base, op["font"]))
            )
            options = dict(font=font(font_path, op["size"]), fill=tuple(op["fill"]))
            for key in ["anchor", "stroke_width", "align", "spacing"]:
                if key in op:
                    options[key] = op[key]
            if "stroke_fill" in op:
                options["stroke_fill"] = tuple(op["stroke_fill"])
            draw.text(tuple(op["position"]), op["text"], **options)
        else:
            raise ValueError(f"Unknown drawing operation: {kind}")


def compose(model, overlay, base, background):
    image = Image.alpha_composite(
        Image.new("RGBA", model.size, tuple(background) + (255,)), model
    ).convert("RGB")
    for stage in overlay.get("stages", []):
        if stage["mode"] == "over":
            layer = Image.new("RGBA", image.size)
            draw_operations(layer, stage.get("draw", []), base)
            image = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
        elif stage["mode"] == "draw":
            draw_operations(image, stage.get("draw", []), base)
        else:
            raise ValueError("Overlay stage mode must be over or draw.")
    return image


def finish(parts, blend=0, fade=0):
    if len(parts) == 1:
        image = parts[0]
    elif len(parts) == 2:
        image = Image.blend(parts[0], parts[1], blend)
    else:
        raise ValueError("A frame must contain one or two complete views.")
    return Image.blend(image, Image.new("RGB", image.size, (0, 0, 0)), fade) if fade else image
