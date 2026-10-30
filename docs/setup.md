# MineTrek Cutaway Renderer setup

Use Windows x64 for rendering. Python 3.12 was used for local validation; Python
3.11+ is supported. `requirements-tested.txt` records installed dependency
versions, while `requirements.txt` allows compatible updates.

The C# compiler is normally at
`%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`.
Set `MINETREK_CUTAWAY_CSC` if it lives elsewhere. `build-engine` compiles the engines
into `work/generic-bin`; source stays under `src/minetrek_cutaway/engine`.

Set `MINETREK_CUTAWAY_WORK` before starting Python to use another working folder.
The default is the checkout's `work` folder, or `work` in the current directory
when using an installed package.
Relative project inputs are resolved against the project JSON's directory, not
the terminal's current directory. This includes external frame plans, texture
files and fonts. Moving projects requires preserving or updating their paths.

The GPU path requires OpenGL 4.3 and double precision shader support. Test it with
`python run.py demo --backend gpu --output work/gpu-check`. `doctor` reports the
compiler and dependencies but does not create an OpenGL context.

Stills do not require FFmpeg. Video export uses FFmpeg's `libx264` encoder and
does not require NVIDIA hardware. Put FFmpeg and FFprobe on PATH for video export
and inspection. CPU rendering uses cutout transparency; GPU glass is filtered.

The importer supports original gzip/Java-serialized Classic levels. It does not
execute serialized Java objects. Maximum input volume is 268,435,456 cells,
subject to available RAM, VRAM and driver 3D texture limits. Multiple sources
can be cached on the GPU during a render.

## Installed commands

The source checkout works through `python run.py`. To install its command into
your active Python environment:

```powershell
python -m pip install -e .
minetrek-cutaway --help
python -m minetrek_cutaway --help
```

The distribution/repository name is `minetrek-cutaway`; Python imports use
`minetrek_cutaway`. The previous `classic-cutaway` console command and
`CLASSIC_CUTAWAY_WORK` / `CLASSIC_CUTAWAY_CSC` environment variables remain accepted
as compatibility aliases. The `MINETREK_CUTAWAY_*` settings take precedence.
