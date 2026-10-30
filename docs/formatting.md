# Formatting

Formatting is a development dependency; rendering does not require these tools.

| Files                       | Formatter                                                                           | Configuration      |
| --------------------------- | ----------------------------------------------------------------------------------- | ------------------ |
| Python                      | [Ruff](https://docs.astral.sh/ruff/formatter/)                                      | `pyproject.toml`   |
| C# and GLSL compute shaders | [clang-format](https://clang.llvm.org/docs/ClangFormatStyleOptions.html)            | `.clang-format`    |
| JSON, YAML, Markdown        | [Prettier](https://prettier.io/docs/)                                               | `.prettierrc.json` |
| TOML                        | [Prettier TOML plugin](https://github.com/un-ts/prettier/tree/master/packages/toml) | `.prettierrc.json` |

Install Python 3.11+ and Node.js 24, then restore the pinned tools:

```powershell
python -m pip install -r requirements-dev.txt
npm ci --ignore-scripts
```

Run from the repository root with the development environment active:

```powershell
python scripts/format_code.py
python scripts/format_code.py --check
```

The equivalent npm commands are `npm run format` and `npm run format:check`.
Check mode returns a failure if formatting changes are needed and does not edit
source files. CI runs this same check.

The runner uses the public-file inventory shared with source export. It never
passes working files, production archives, caches or dependencies to formatters.
Ruff and Prettier also explicitly exclude those folders for direct/editor use.

Code uses four-space indentation and a 100-character target line width. C# uses
Allman braces; GLSL uses clang-format's C++ syntax mode. JSON, YAML, Markdown and
TOML use two-space indentation. `.editorconfig` specifies UTF-8 and LF endings.
Embedded Markdown examples are left as written.

Python and clang-format versions are pinned in `requirements-dev.txt`. Node tools
are pinned in `package.json` and `package-lock.json`. The runner uses the Python
environment's packaged clang-format binary rather than an unrelated global tool.
