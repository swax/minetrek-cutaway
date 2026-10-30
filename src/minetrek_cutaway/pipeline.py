"""Execute a project using only its JSON data and the reusable renderer."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image

from .build import build
from .composite import compose, finish
from .paths import PACKAGE, relative_path


def shader(project):
    path = PACKAGE / "engine/shaders/voxel.comp"
    lighting = project.renderer.get("lighting", "studio")
    if lighting == "studio":
        return path
    version, body = path.read_text().split("\n", 1)
    style = {"flat": 1, "dramatic": 2}[lighting]
    code = f"{version}\n#define LIGHTING_STYLE {style}\n{body}"
    target = project.cache / ("lighting-" + lighting + ".comp")
    target.write_text(code, encoding="utf-8")
    return target


def encoder(project, path, indices, log):
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError("FFmpeg is required for video export.")
    if indices != list(range(indices[0], indices[-1] + 1)):
        raise ValueError("Video export requires a contiguous frame range.")
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{project.width}x{project.height}",
        "-r",
        str(project.fps),
        "-i",
        "pipe:0",
    ]
    audio = project.spec.get("audio")
    if audio:
        start = indices[0] / project.fps
        command += [
            "-ss",
            str(start + audio.get("offset", 0)),
            "-i",
            str(relative_path(project.base, audio["path"])),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
        filters = []
        if "volume" in audio:
            filters.append("volume=" + str(audio["volume"]))
        if "fade_out" in audio:
            a, b = audio["fade_out"]
            filters += [
                f"asetpts=PTS+{start}/TB",
                f"afade=t=out:st={a}:d={b - a}",
                "asetpts=PTS-STARTPTS",
            ]
        if filters:
            command += ["-af", ",".join(filters)]
    else:
        command += ["-an"]
    command += [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-t",
        str(len(indices) / project.fps),
        "-movflags",
        "+faststart",
        str(path),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)


def render(project, indices, output, video=False):
    if not indices or any(type(i) != int or not 0 <= i < len(project.frames) for i in indices):
        raise ValueError("Frame selection is outside the project timeline.")
    output = Path(output).resolve()
    if video and (project.width % 2 or project.height % 2):
        raise ValueError("H.264 video requires even image dimensions.")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    scratch = project.cache / "render"
    scratch.mkdir(parents=True, exist_ok=True)
    jobs = []
    references = []
    for index in indices:
        frame = project.frames[index]
        for n, part in enumerate(frame["parts"]):
            jobs.append(project.job(part, scratch / f"frame-{index:06d}-{n}.rgba"))
            references.append((index, n, part, frame))
    jobs_path = scratch / "jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    binary = build(project.backend)[project.backend]
    if video:
        output.parent.mkdir(parents=True, exist_ok=True)
    else:
        output.mkdir(parents=True)
    command = [str(binary), "render", jobs[0]["Volume"], str(jobs_path)]
    if project.backend == "gpu":
        command.append(str(shader(project)))
    report = dict(
        project=str(project.path),
        frames=[],
        resolution=[project.width, project.height],
        fps=project.fps,
    )
    report_path = (
        output.with_suffix(".verification.json") if video else output / "verification.json"
    )
    enc = proc = None
    pending = {}
    models = {}
    try:
        with (
            (scratch / "renderer.log").open("w") as engine_log,
            (scratch / "encoder.log").open("w") as encode_log,
        ):
            if video:
                enc = encoder(project, output, indices, encode_log)
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=engine_log, text=True)
            for line in proc.stdout:
                sequence = int(line.strip())
                job = jobs[sequence]
                index, n, part, frame = references[sequence]
                raw = Path(job["Output"])
                pixels = raw.read_bytes()
                raw.unlink()
                model = Image.frombytes("RGBA", (project.width, project.height), pixels)
                models.setdefault(index, []).append(hashlib.sha256(pixels).hexdigest())
                image = compose(
                    model, project.overlay(part.get("overlay")), project.base, project.background
                )
                pending.setdefault(index, []).append(image)
                if n + 1 != len(frame["parts"]):
                    continue
                image = finish(pending.pop(index), frame.get("blend", 0), frame.get("fade", 0))
                pixels = image.tobytes()
                if enc:
                    enc.stdin.write(pixels)
                else:
                    image.save(output / f"frame-{index:06d}.png", compress_level=3)
                report["frames"].append(
                    dict(
                        index=index,
                        rgb_sha256=hashlib.sha256(pixels).hexdigest(),
                        model_sha256=models.pop(index),
                    )
                )
                if len(report["frames"]) == 1 or len(report["frames"]) % 24 == 0:
                    print(f"Rendered {len(report['frames'])}/{len(indices)} frames", flush=True)
            if proc.wait():
                raise RuntimeError(f"Renderer failed; see {scratch / 'renderer.log'}")
            if enc:
                enc.stdin.close()
                if enc.wait():
                    raise RuntimeError(f"FFmpeg failed; see {scratch / 'encoder.log'}")
        if len(report["frames"]) != len(indices) or pending:
            raise RuntimeError("Incomplete renderer output.")
    finally:
        for process in [proc, enc]:
            if process and process.poll() is None:
                process.terminate()
                process.wait()
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
