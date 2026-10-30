"""Load and compile declarative JSON projects into generic render jobs."""

import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import uuid

import numpy as np

from .paths import WORK, relative_path
from .textures import prepare as prepare_texture
from .volumes import Sources, bounds


def read_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8-sig"),
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"Non-finite JSON number: {v}")),
    )


def number(value, name, lo=None, hi=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if lo is not None and value < lo or hi is not None and value > hi:
        raise ValueError(f"{name} is outside its allowed range.")
    return value


def tween(value, amount):
    return (
        value[0] + (value[1] - value[0]) * amount
        if isinstance(value, list) and len(value) == 2
        else value
    )


def auto_camera(size, clip, width, height, camera):
    w, h, l = size
    box = clip.get("bounds", [0, w, 0, h, 0, l])
    x0, x1, y0, y1, z0, z1 = box
    y1 = min(y1, clip.get("height", h))
    center = camera.get("center", [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    a, e = math.radians(camera.get("azimuth", -55)), math.radians(camera.get("elevation", 40))
    corners = np.array(list(itertools.product((x0, x1), (y0, y1), (z0, z1))))
    right = np.array([-math.cos(a), 0, math.sin(a)])
    up = np.array([math.sin(a) * math.sin(e), math.cos(e), math.cos(a) * math.sin(e)])
    scale = min(
        width * 0.88 / max(1, np.ptp(corners @ right)), height * 0.88 / max(1, np.ptp(corners @ up))
    )
    return dict(
        center=center,
        azimuth=camera.get("azimuth", -55),
        elevation=camera.get("elevation", 40),
        scale=camera.get("scale", float(scale)),
    )


class Project:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.base = self.path.parent
        self.spec = read_json(self.path)
        allowed = {
            "version",
            "output",
            "renderer",
            "sources",
            "shots",
            "frames",
            "frames_file",
            "overlays",
            "overlays_file",
            "audio",
        }
        if set(self.spec) - allowed:
            raise ValueError(f"Unknown project settings: {set(self.spec) - allowed}")
        if self.spec.get("version") != 1:
            raise ValueError("Project version must be 1.")
        output = self.spec.get("output", {})
        if set(output) - {"width", "height", "fps", "background"}:
            raise ValueError("Unknown output setting.")
        self.width = output.get("width", 1280)
        self.height = output.get("height", 720)
        self.fps = output.get("fps", 24)
        if any(type(v) != int or v < 1 for v in [self.width, self.height, self.fps]):
            raise ValueError("Output dimensions and fps must be positive integers.")
        if self.width * self.height > 33_554_432 or self.fps > 120:
            raise ValueError("Output exceeds 32 megapixels or 120 fps.")
        self.background = output.get("background", [9, 17, 28])
        if len(self.background) != 3 or any(
            type(v) != int or not 0 <= v <= 255 for v in self.background
        ):
            raise ValueError("Background must contain three bytes.")
        self.renderer = self.spec.get("renderer", {})
        allowed_renderer = {
            "backend",
            "lighting",
            "ray_offset",
            "shadow_distance",
            "ray_steps",
            "shadow_steps",
        }
        if set(self.renderer) - allowed_renderer:
            raise ValueError(f"Unknown renderer settings: {set(self.renderer) - allowed_renderer}")
        self.backend = self.renderer.get("backend", "gpu")
        if self.backend not in {"cpu", "gpu"}:
            raise ValueError("Renderer backend must be cpu or gpu.")
        if self.renderer.get("lighting", "studio") not in {"studio", "flat", "dramatic"}:
            raise ValueError("Lighting must be studio, flat or dramatic.")
        if self.backend == "cpu" and self.renderer.get("lighting", "studio") != "studio":
            raise ValueError("CPU rendering currently supports studio lighting only.")
        definitions = self.spec.get("sources", {})
        if not definitions or any(
            not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in definitions
        ):
            raise ValueError("Sources need safe nonempty identifiers.")
        identity = hashlib.sha256(
            str(self.path).encode() + json.dumps(self.spec, sort_keys=True).encode()
        ).hexdigest()[:16]
        self.cache = WORK / "generic-cache" / identity / uuid.uuid4().hex[:12]
        self.sources = Sources(definitions, self.base, self.cache / "volumes")
        self.overlays = self.spec.get("overlays", {})
        if "overlays_file" in self.spec:
            self.overlays = read_json(relative_path(self.base, self.spec["overlays_file"]))
        self.frames = self.spec.get("frames")
        choices = sum(key in self.spec for key in ["frames", "frames_file", "shots"])
        if choices != 1:
            raise ValueError("Choose exactly one of frames, frames_file or shots.")
        if "frames_file" in self.spec:
            self.frames = read_json(relative_path(self.base, self.spec["frames_file"]))
        if "shots" in self.spec:
            self.frames = self.compile_shots(self.spec["shots"])
        if not isinstance(self.frames, list) or not self.frames:
            raise ValueError("A project must contain frames.")
        self.textures = {}
        self.checked_overlays = set()
        self.validate_audio()

    def validate_audio(self):
        audio = self.spec.get("audio")
        if not audio:
            return
        if set(audio) - {"path", "offset", "volume", "fade_out"}:
            raise ValueError("Unknown audio setting.")
        if not relative_path(self.base, audio["path"]).is_file():
            raise FileNotFoundError(audio["path"])
        number(audio.get("offset", 0), "Audio offset", 0)
        number(audio.get("volume", 1), "Audio volume", 0)
        if "fade_out" in audio:
            a, b = audio["fade_out"]
            number(a, "Audio fade start", 0)
            number(b, "Audio fade end", a + 1e-8)

    def compile_shots(self, shots):
        output = []
        counts = []
        for shot in shots:
            if set(shot) - {
                "source",
                "duration",
                "camera",
                "clip",
                "textures",
                "overlay",
                "full_cube_slabs",
                "transition",
                "ease",
            }:
                raise ValueError("Unknown shot setting.")
            if shot.get("ease", "smooth") not in {"smooth", "linear"}:
                raise ValueError("Shot ease must be smooth or linear.")
            duration = number(shot["duration"], "Shot duration", 1 / self.fps)
            count = round(duration * self.fps)
            if abs(count / self.fps - duration) > 1e-7:
                raise ValueError("Shot durations must align with the output frame rate.")
            counts.append(count)

        def view(shot, i, count):
            u = i / max(1, count - 1)
            amount = u * u * (3 - 2 * u) if shot.get("ease", "smooth") == "smooth" else u
            camera = dict(shot.get("camera", {}))
            clip = dict(shot.get("clip", {}))
            for key in ["azimuth", "elevation", "scale"]:
                if key in camera:
                    camera[key] = tween(camera[key], amount)
            if "center_end" in camera:
                camera["center"] = [
                    a + (b - a) * amount for a, b in zip(camera["center"], camera.pop("center_end"))
                ]
            for key in ["height", "closed_height", "sweep_x"]:
                if key in clip:
                    clip[key] = tween(clip[key], amount)
            return dict(
                source=shot["source"],
                camera=camera,
                clip=clip,
                **{
                    key: shot[key]
                    for key in ["overlay", "textures", "full_cube_slabs"]
                    if key in shot
                },
            )

        for index, (shot, count) in enumerate(zip(shots, counts)):
            fade = number(shot.get("transition", 0), "Transition duration", 0, count / self.fps)
            fade_frames = round(fade * self.fps)
            for i in range(count):
                parts = [view(shot, i, count)]
                blend = 0
                if fade_frames and index + 1 < len(shots) and i >= count - fade_frames:
                    u = (i - count + fade_frames) / fade_frames
                    blend = u * u * (3 - 2 * u)
                    parts.append(view(shots[index + 1], 0, counts[index + 1]))
                output.append(dict(parts=parts, blend=blend))
        return output

    def overlay(self, value):
        overlay = self.overlays[value] if isinstance(value, str) else value or {}
        key = json.dumps(overlay, sort_keys=True)
        if key not in self.checked_overlays:
            for stage in overlay.get("stages", []):
                if stage.get("mode") not in {"over", "draw"}:
                    raise ValueError("Overlay mode must be over or draw.")
                for op in stage.get("draw", []):
                    if op.get("type") not in {"text", "rectangle"}:
                        raise ValueError("Unsupported overlay drawing operation.")
                    if (
                        op["type"] == "text"
                        and op["font"] != "default"
                        and not relative_path(self.base, op["font"]).is_file()
                    ):
                        raise FileNotFoundError(op["font"])
            self.checked_overlays.add(key)
        return overlay

    def job(self, part, output):
        if set(part) - {"source", "camera", "clip", "textures", "overlay", "full_cube_slabs"}:
            raise ValueError("Unknown frame-part setting.")
        if "full_cube_slabs" in part and type(part["full_cube_slabs"]) != bool:
            raise ValueError("full_cube_slabs must be a boolean.")
        source = self.sources.prepare(part["source"])
        w, h, l = source["size"]
        clip = part.get("clip", {})
        if set(clip) - {
            "bounds",
            "height",
            "closed_height",
            "sweep_x",
            "floor",
            "mode",
            "context_alpha",
            "focus_bounds",
            "closed_focus_bounds",
        }:
            raise ValueError("Unknown clip setting.")
        if set(part.get("camera", {})) - {"center", "scale", "azimuth", "elevation"}:
            raise ValueError("Unknown camera setting.")
        box = clip.get("bounds", [0, w, 0, h, 0, l])
        bounds(box, [w, h, l])
        x0, x1, y0, y1, z0, z1 = box
        camera = auto_camera(source["size"], clip, self.width, self.height, part.get("camera", {}))
        center = camera["center"]
        if len(center) != 3:
            raise ValueError("Camera center must contain X,Y,Z.")
        center = [number(v, "Camera center") for v in center]
        scale = number(camera["scale"], "Camera scale", 0.000001)
        elevation = number(camera["elevation"], "Elevation", 0, 90)
        azimuth = number(camera["azimuth"], "Azimuth")
        mode = clip.get("mode", "remaining")
        if mode not in {"remaining", "slice", "ghost"}:
            raise ValueError("Clip mode must be remaining, slice or ghost.")
        focus = clip.get("focus_bounds", [x0, x1, z0, z1])
        closed_focus = clip.get("closed_focus_bounds", focus)
        if len(focus) != 4 or len(closed_focus) != 4:
            raise ValueError("Focus bounds require xmin,xmax,zmin,zmax.")
        cut = number(clip.get("height", h), "Cut height", 0)
        closed = number(clip.get("closed_height", cut), "Closed cut height", 0)
        floor = number(clip.get("floor", y0), "Focus floor", 0)
        job = dict(
            Name="frame",
            Output=str(output),
            Volume=str(source["path"]),
            Mode=mode,
            Width=self.width,
            Height=self.height,
            CenterX=center[0],
            CenterY=center[1],
            CenterZ=center[2],
            Scale=scale,
            Azimuth=azimuth,
            Elevation=elevation,
            XMin=x0,
            XMax=x1,
            YMin=y0,
            YMax=y1,
            ZMin=z0,
            ZMax=z1,
            CutOpen=cut,
            CutClosed=closed,
            FocusFloor=floor,
            SweepX=number(clip.get("sweep_x", -1000), "Sweep position"),
            ContextAlpha=number(clip.get("context_alpha", 1), "Context opacity", 0, 1),
            FullCubeSlabs=bool(part.get("full_cube_slabs", False)),
            MarkedBlocks=source["marked"],
            RayOffset=number(
                self.renderer.get("ray_offset", max(1500, 2 * math.sqrt(w * w + h * h + l * l))),
                "Ray offset",
                1,
            ),
            ShadowDistance=number(
                self.renderer.get("shadow_distance", max(1100, math.sqrt(w * w + h * h + l * l))),
                "Shadow distance",
                1,
            ),
            RaySteps=self.renderer.get("ray_steps", max(2000, 2 * (w + h + l))),
            ShadowSteps=self.renderer.get("shadow_steps", max(1800, 2 * (w + h + l))),
        )
        for name, value in [("RaySteps", job["RaySteps"]), ("ShadowSteps", job["ShadowSteps"])]:
            if type(value) != int or not 1 <= value <= 100_000:
                raise ValueError(f"{name} must be an integer from 1 to 100000.")
        for prefix, values in [("", focus), ("Closed", closed_focus)]:
            for key, value in zip(["FocusXMin", "FocusXMax", "FocusZMin", "FocusZMax"], values):
                job[prefix + key] = number(value, "Focus bound")
        if part.get("textures"):
            key = part["textures"]
            if key not in self.textures:
                self.textures[key] = prepare_texture(
                    relative_path(self.base, key),
                    self.cache
                    / ("texture-" + hashlib.sha256(key.encode()).hexdigest()[:12] + ".mttex"),
                )
            job["Terrain"] = str(self.textures[key])
        self.overlay(part.get("overlay"))
        return job

    def validate(self):
        parts = 0
        for index, frame in enumerate(self.frames):
            if set(frame) - {"parts", "blend", "fade"}:
                raise ValueError(f"Unknown setting in frame {index}.")
            views = frame.get("parts", [])
            if not 1 <= len(views) <= 2:
                raise ValueError(f"Frame {index} needs one or two parts.")
            number(frame.get("blend", 0), "Frame blend", 0, 1)
            number(frame.get("fade", 0), "Frame fade", 0, 1)
            for view in views:
                self.job(view, self.cache / "unused.rgba")
                parts += 1
        return dict(
            frames=len(self.frames),
            parts=parts,
            sources=len(self.sources.prepared),
            duration_seconds=len(self.frames) / self.fps,
            resolution=[self.width, self.height],
            fps=self.fps,
            backend=self.backend,
        )
