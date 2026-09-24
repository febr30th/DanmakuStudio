# DanmakuStudio

[中文](README.md) | [English](README.en.md)

A graphical tool for burning danmaku/LRC subtitles into one or more video segments. It combines livestream recordings with danmaku XML or LRC files and permanently renders the comments as translucent, rounded bubbles on the video.

## Features

- **Graphical media arrangement** - Select one or more videos and produce one finished video
- **Automatic subtitle matching** - Find XML/LRC files with matching names in the same directory; XML takes priority when both formats are present
- **XML/LRC support** - XML supports regular comments and gift messages; LRC supports timestamped text and attempts to recognize usernames in common export formats
- **Two-zone layout** - Gift messages and text comments use independent layouts and do not interfere with each other
- **Space-driven layout** - Comments stack upward from the bottom with collision detection to minimize overlap
- **Damped animation** - Comment and gift movement uses smooth interpolated transitions
- **Emoji and gift images** - Load Emoji and gift PNG images from `assets/` on demand
- **Font fallback** - Chain multiple font families and automatically try system fallback fonts for unsupported characters
- **FFmpeg encoding** - Automatically detect GPU, QSV, and CPU encoding paths; automatic mode falls back to the CPU when hardware encoding is unavailable

## Requirements

### Running from source

- Python >= 3.13
- FFmpeg and ffprobe available on the command line
- Dependencies: `lxml`, `PySide6`, `loguru`, `tqdm`, and `pyyaml`

### Running the EXE

The packaged `DanmakuStudio.exe` does not require a separate Python installation, but it does require:

- Windows
- The complete `dist\DanmakuStudio\` folder; do not copy only the executable
- `ffmpeg.exe` and `ffprobe.exe` discoverable by the application

Adding FFmpeg's `bin` directory to the system `Path` is recommended. Verify the installation with:

```powershell
ffmpeg -version
ffprobe -version
```

NVIDIA GPU encoding also requires a working graphics driver and an FFmpeg build that supports `h264_nvenc`:

```powershell
ffmpeg -hide_banner -encoders | findstr nvenc
```

Automatic mode falls back to CPU encoding when hardware encoding is unavailable. If GPU or QSV is selected manually, the application reports an error when the required hardware or FFmpeg support is missing.

## Format limitations

The current version primarily targets common SDR, 8-bit, constant-frame-rate video. It generates danmaku frames at one detected frame rate and outputs H.264 8-bit video (`yuv420p` for CPU/NVENC and `nv12` for QSV).

With VFR (variable-frame-rate) video, danmaku timing may drift slightly during long encodes. HDR, 10-bit, or wide-color-gamut input may lose HDR, high-bit-depth, or color metadata, which can change the perceived brightness and colors.

For the most consistent results, convert the source to SDR 8-bit CFR video before processing.

## Installation

### One-command setup on Windows (recommended)

```bash
git clone https://github.com/febr30th/DanmakuStudio.git
cd DanmakuStudio
```

Run the following in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Install uv 0.12.17+ first (for example, `python -m pip install uv==0.12.17`). The script first looks for a user-installed Python 3.13+ from python.org, then creates or synchronizes `.venv` with the runtime, test, and build dependencies pinned in `uv.lock`. Before finishing, it also verifies that PySide6/Qt can be imported successfully. To use a specific Python executable, add `-Python "C:\path\to\python.exe"`.

FFmpeg and ffprobe are external runtime dependencies and are not downloaded into the repository. The setup script displays a warning if they are not available on `Path`.

After setup, run the tests or GUI with one command each:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_gui.ps1
```

`test.ps1` and `run_gui.ps1` invoke `setup.ps1` by default to synchronize the environment. Each run writes test temporary files to its own ignored `.pytest-tmp-*/` directory inside the repository, so tests neither depend on the system temporary directory nor get blocked by stale files from an interrupted run.

### Manual installation

Install all locked dependencies, then install the project with the locked build backend:

```powershell
uv sync --locked --all-groups --no-install-project
uv sync --locked --all-groups --no-build-isolation
```

Setup, tests, GUI startup, and packaging use this same lockfile. `test.ps1` synchronizes by default; `-NoSetup` and the build script's `-SkipInstall` validate the environment and fail on dependency drift or an outdated lockfile. Exact synchronization removes unlisted packages, so use a dedicated project environment.

To update dependencies, explicitly run `uv lock --upgrade-package PACKAGE`, commit the relevant `pyproject.toml` and `uv.lock` changes, then retest and rebuild. Normal installation does not upgrade dependencies automatically.

## Quick start

### Graphical interface

On Windows, the repository script is recommended:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_gui.ps1
```

After installing the dependencies or activating the virtual environment, you can also run the module directly:

```bash
python -m danmakustudio.gui
```

After installing the project, the GUI entry point is also available:

```bash
danmakustudio-gui
```

Running `danmakustudio` without arguments also opens the graphical interface:

```bash
danmakustudio
```

Click **Select videos** to open the material editor directly. Both lists are empty the first time; later openings retain the currently selected videos, danmaku files, and output path. The editor manages videos on the left and danmaku files on the right; each list supports adding, removing, and reordering. Adding another video also discovers and adds its matching danmaku file.

Supported video extensions:

```text
.mp4 .flv .mkv .avi .mov .ts .webm
```

Supported output containers are `.mp4`, `.flv`, `.mkv`, `.avi`, and `.mov`. Output audio is encoded as AAC at 192 kbps to prevent failures caused by an input audio codec that is incompatible with the selected output container.

Supported subtitle extensions:

```text
.xml .lrc
```

For example:

```text
video.mp4
video.xml
video.lrc
```

When matching XML and LRC files both exist, the application uses the XML file.

Multiple selected videos are merged directly into one output. The interface does not expose a separate timeline-mode selector. One danmaku file starts at `00:00` on the complete output timeline. Multiple selected danmaku files are automatically organized and all included in the final output; differing list sizes do not block the next step.

Videos and danmaku files may come from different folders. The next step remains disabled only while either list is empty. Before processing, ffprobe verifies segment resolution and audio/video stream parameters; incompatible segments are rejected. Different reported frame rates do not block the task: the first segment's reported frame rate is used to generate the danmaku layer, whose coverage is calculated from the total segment duration. Videos are not resized, frame-rate-normalized, or pre-transcoded. Long VFR videos or large frame-rate differences may still cause slight danmaku timing drift.

During processing, **Cancel task** asks for confirmation, stops FFmpeg, discards the unfinished output, and deletes temporary video and concat-list files. The selected materials remain available for another attempt.

### Command line

```bash
danmakustudio source/video.mp4 source/danmaku.xml
danmakustudio source/video.mp4 source/subtitles.lrc
```

Specify the encoding mode and output path:

```bash
danmakustudio source/video.mp4 source/danmaku.xml --encode gpu -o output.mp4 -f
```

Use a custom configuration file:

```bash
danmakustudio source/video.mp4 source/danmaku.xml -c danmakustudio.yaml
```

## Configuration

Edit `danmakustudio.yaml` to customize the application's behavior.

Configuration precedence:

```text
Configuration file specified on the command line > danmakustudio.yaml in the current directory > danmakustudio.yaml in the user directory > built-in defaults
```

If an explicitly specified configuration file does not exist or has an invalid structure, the application reports an error instead of falling back to another configuration file.

When running from source, the application reads `danmakustudio.yaml` from the current working directory. When running the EXE, the graphical interface first looks for `danmakustudio.yaml` beside the executable, allowing users to edit it directly.

In the tables below, “Repository value” refers to the current repository's `danmakustudio.yaml`. If that file or a particular field is removed, the corresponding field falls back to its “Built-in default.”

### Layout style (`style`)

| Parameter | Repository value | Built-in default | Description |
| --- | ---: | ---: | --- |
| `danmaku_x` | 10 | 30 | Starting X coordinate for comments (pixels) |
| `layer_width_extra` | 100 | 100 | Extra render-layer width (pixels) |
| `bubble_padding_x` | 14 | 14 | Horizontal bubble padding (pixels) |
| `bubble_padding_y` | 5 | 5 | Vertical bubble padding (pixels) |
| `bubble_row_gap` | 5 | 5 | Line spacing inside multiline bubbles (pixels) |
| `bubble_vertical_gap` | 4 | 4 | Vertical spacing between comment bubbles (pixels) |
| `bubble_multiline_radius` | 10.0 | 14.0 | Corner radius for multiline bubbles (pixels) |
| `gift_spacing` | 6 | 6 | Spacing between gift icons (pixels) |
| `emoji_spacing` | 4 | 4 | Emoji spacing (pixels) |
| `font_size` | 18 | 25 | Font size (pt) |
| `fade_out_zone` | 20.0 | 30.0 | Height of the text-comment fade-out zone (pixels) |

### Layout ratios (`ratio`)

| Parameter | Repository value | Built-in default | Description |
| --- | ---: | ---: | --- |
| `max_text_rows` | 8 | 4 | Maximum visible rows of text comments |
| `max_gift_rows` | 2 | 2 | Maximum visible rows of gift messages |
| `text_width_ratio` | 0.8 | 0.8 | Maximum text-comment width ratio |
| `bottom_margin` | 12 | 22 | Bottom margin (pixels) |

### Animation (`animation`)

| Parameter | Repository value | Built-in default | Description |
| --- | ---: | ---: | --- |
| `text_damping_factor` | 0.1 | 0.25 | Text-comment movement damping factor (0–1; larger values move faster) |
| `gift_damping_factor` | 0.1 | 0.25 | Gift-message movement damping factor (0–1; larger values move faster) |
| `text_spawn_interval` | 0.5 | 0.5 | Text-comment spawn interval (seconds) |
| `text_spawn_batch_size` | 3 | 3 | Number of text comments spawned per batch |
| `gift_spawn_interval` | 0.5 | 0.5 | Gift-message spawn interval (seconds) |
| `gift_spawn_batch_size` | 2 | 2 | Number of gift messages spawned per batch |
| `gift_dwell_time` | 5.0 | 5.0 | Gift dwell time (seconds); `null` means gifts never expire due to dwell time |
| `min_gift_price` | 0.0 | 1.0 | Minimum gift-price filter (CNY) |

### Encoding (`encode`)

The encoding parameters in the current `danmakustudio.yaml` are commented out, so the built-in defaults are used.

| Parameter | Built-in default | Description |
| --- | ---: | --- |
| `gpu_preset` | `"p5"` | NVIDIA NVENC preset (p1–p7; larger values are slower and higher quality) |
| `gpu_cq` | 15 | NVIDIA NVENC QP quality (0–51; lower values give better quality and larger files) |
| `qsv_preset` | `"slow"` | Intel QSV preset (slower presets usually provide better quality) |
| `qsv_quality` | 18 | Intel QSV quality (0–51; lower values give better quality and larger files) |
| `cpu_preset` | `"medium"` | libx264 preset (slower presets improve compression efficiency) |
| `cpu_crf` | 18 | libx264 CRF quality (0–51; lower values give better quality and larger files) |
| `cpu_min_reserve_threads` | 2 | Number of CPU threads reserved during encoding |

### System (`system`)

The system parameters in the current `danmakustudio.yaml` are commented out, so the built-in defaults are used.

| Parameter | Built-in default | Description |
| --- | ---: | --- |
| `pipe_buffer_size` | 10000000 | Pipe buffer size (bytes) |
| `ffmpeg_timeout` | 10 | FFmpeg/ffprobe detection and metadata-read timeout (seconds) |
| `stderr_thread_timeout` | 5 | Error-log thread timeout (seconds) |
| `video_alignment` | 2 | Align video dimensions to even values to prevent 1080 from being enlarged to 1088 |

## Packaging

The repository root includes a one-command packaging script. In a clean clone, it creates a separate `.venv-build`, installs runtime, test, and build dependencies from the same lockfile, runs the full test suite in that environment, and only then packages the application using `DanmakuStudio.spec`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

After packaging, the script launches the generated EXE to check Qt DLLs, the native platform plugin, main-window creation, and the event loop. A failed startup check fails the build command. DLL search paths are isolated during packaging to avoid collecting conflicting libraries from tools such as Anaconda or Poppler.

To verify the packaging dependencies and entry point without generating the EXE:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1 -CheckOnly
```

After packaging, the executable is located at:

```text
dist\DanmakuStudio\DanmakuStudio.exe
```

Keep the entire `dist\DanmakuStudio\` folder when distributing the application. The program still depends on FFmpeg and ffprobe being installed on the system.

Do not run `build\DanmakuStudio\DanmakuStudio.exe`; it is an intermediate PyInstaller artifact. The final executable is `dist\DanmakuStudio\DanmakuStudio.exe`.

The dependency lock does not pin the system Python, FFmpeg, GPU drivers, or operating system; record these versions for each release.

## Processing pipeline

```text
Subtitle parsing -> Asset loading -> Video metadata -> Danmaku layout -> Frame-by-frame rendering -> FFmpeg composition
```

1. Parse XML/LRC subtitles; XML parsing extracts `<d>` and `<gift>` elements, while LRC parsing extracts timestamped text
2. Load Emoji and gift-image assets and load fonts on demand
3. Use ffprobe to obtain the video's width, height, frame rate, and total frame count
4. Pre-create danmaku objects and calculate layout parameters
5. Build the FFmpeg encoding command and automatically detect GPU, QSV, or CPU encoding paths
6. Render the danmaku bubble layer frame by frame and pipe it to FFmpeg to produce the output video

## Project structure

```text
DanmakuStudio/
├── src/danmakustudio/        # Core package
│   ├── cli.py                # CLI entry point
│   ├── gui.py                # Graphical interface entry point
│   ├── batch.py              # Single-output task and subtitle matching
│   ├── config/               # Configuration modules
│   ├── core/                 # Processing-pipeline orchestration
│   ├── encode/               # FFmpeg process management
│   ├── input/                # XML/LRC subtitle parsing
│   ├── layout/               # Layout calculation and active-comment state
│   ├── render/               # Bubble rendering and image-asset loading
│   └── utils/                # Utilities and input/output validation
├── tests/                    # Tests
├── DanmakuStudio.spec        # PyInstaller packaging configuration
├── setup.ps1                 # One-command runtime/development setup
├── test.ps1                  # One-command test runner
├── run_gui.ps1               # One-command GUI launcher
├── build_exe.ps1             # One-command packaging and pre-build checks
├── scripts/_common.ps1       # Shared PowerShell helpers
├── danmakustudio.yaml        # Default configuration file
├── pyproject.toml
├── uv.lock
├── LICENSE
├── README.md
└── README.en.md
```

The optional `assets/` directory is normally used for Emoji, gift images, or font files. A clean clone of the current repository does not include specific media assets.

## License

This project is released under GPLv3. See `LICENSE` in the repository root for details. Because this project is based on GPLv3-licensed code, distributions of modified versions must also retain the GPLv3 license and copyright/license notices and make the corresponding source code available.

## Acknowledgments

This project is based on [cerulean26/DanmakuPro](https://github.com/cerulean26/DanmakuPro). Thanks to the original project for providing the foundation for danmaku video rendering.
