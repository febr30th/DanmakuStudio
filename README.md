# DanmakuStudio

图形化弹幕/LRC 批量压制工具。它可以将直播录像与弹幕 XML/LRC 合成，以半透明圆角气泡形式将弹幕永久烧录到视频中。

## 特性

- **图形化批量处理** - 可多选视频或文件夹，自动递归查找文件夹内视频
- **自动匹配字幕** - 自动寻找同目录下同名 XML/LRC 字幕；XML 和 LRC 同时存在时优先选择 XML
- **XML/LRC 支持** - XML 支持普通弹幕与礼物弹幕；LRC 支持时间轴文本，并尽量识别常见导出格式中的用户名
- **双区布局** - 礼物区和文本弹幕区独立布局，互不干扰
- **空间驱动布局** - 弹幕从底部向上堆叠，含碰撞检测，尽量避免互相遮挡
- **阻尼动画** - 弹幕/礼物位移带平滑插值过渡
- **Emoji/礼物图片加载** - 可按需从 `assets/` 加载 Emoji 和礼物 PNG 图片
- **字体回退** - 多字体族链式匹配，未覆盖字符自动尝试系统字体回退
- **FFmpeg 编码** - 支持自动检测 GPU / QSV / CPU 编码路径；自动模式下无可用硬件编码时回退到 CPU

## 环境要求

### 源码运行

- Python >= 3.13
- FFmpeg / ffprobe 可在命令行中直接运行
- 依赖包：`lxml` `PySide6` `loguru` `tqdm` `pyyaml`

### EXE 运行

打包后的 `DanmakuStudio.exe` 不需要用户额外安装 Python，但需要：

- Windows 系统
- 保留整个 `dist\DanmakuStudio\` 文件夹，不要只复制单个 exe
- `ffmpeg.exe` 和 `ffprobe.exe` 可被程序找到

推荐把 FFmpeg 的 `bin` 目录加入系统环境变量 `Path`。可以用下面命令验证：

```powershell
ffmpeg -version
ffprobe -version
```

如果要使用 NVIDIA GPU 编码，还需要显卡驱动正常，并且 FFmpeg 支持 `h264_nvenc`：

```powershell
ffmpeg -hide_banner -encoders | findstr nvenc
```

如果没有可用硬件编码，自动模式会回退到 CPU 编码；手动选择 GPU 或 QSV 时，硬件/FFmpeg 不支持会报错。

## 格式限制说明

当前版本主要面向常见 SDR 8-bit 恒定帧率视频。程序会按检测到的单一帧率生成弹幕帧，并输出 H.264 8-bit 视频（CPU/NVENC 为 `yuv420p`，QSV 为 `nv12`）。

对于 VFR（可变帧率）视频，长时间压制可能出现弹幕时间轻微偏移。对于 HDR、10-bit 或宽色域视频，输出可能丢失 HDR、高位深或色彩元数据，画面亮度与色彩观感可能发生变化。

如需尽量稳定的结果，建议先将素材转为 SDR 8-bit CFR 视频后再压制。

## 安装

```bash
git clone https://github.com/febr30th/DanmakuStudio.git
cd DanmakuStudio
```

使用 pip 安装：

```bash
python -m pip install -e .
```

如果已经安装 `uv`，也可以使用：

```bash
uv sync
```

## 快速开始

### 图形界面

```bash
danmakustudio-gui
```

也可以无参数运行 `danmakustudio` 打开图形界面：

```bash
danmakustudio
```

在图形界面中可以选择视频文件或文件夹。选择文件夹时会递归查找其中支持的视频文件，并自动匹配同目录下的同名字幕文件。

支持的视频扩展名：

```text
.mp4 .flv .mkv .avi .mov .ts .webm
```

支持的字幕扩展名：

```text
.xml .lrc
```

例如：

```text
视频.mp4
视频.xml
视频.lrc
```

如果同名 XML 和 LRC 同时存在，程序会优先选择 XML。

### 命令行

```bash
danmakustudio source/视频.mp4 source/弹幕.xml
danmakustudio source/视频.mp4 source/字幕.lrc
```

指定编码模式和输出路径：

```bash
danmakustudio source/视频.mp4 source/弹幕.xml --encode gpu -o output.mp4 -f
```

使用自定义配置文件：

```bash
danmakustudio source/视频.mp4 source/弹幕.xml -c danmakustudio.yaml
```

## 配置

通过 `danmakustudio.yaml` 调整行为。

配置优先级：

```text
命令行指定的配置文件 > 当前目录 danmakustudio.yaml > 用户目录 danmakustudio.yaml > 内置默认值
```

如果显式指定的配置文件不存在或结构不合法，程序会直接报错，不会继续回退到其它配置文件。

源码运行时，程序会读取当前工作目录下的 `danmakustudio.yaml`；EXE 运行时，图形界面会优先使用 exe 同目录下的 `danmakustudio.yaml`，用户可以直接编辑。

下表中，“随项目配置值”来自当前仓库中的 `danmakustudio.yaml`；删除该文件或删除某个字段后，对应字段会回退到“内置默认值”。

### 布局样式 (style)

| 参数                        | 随项目配置值 | 内置默认值 | 说明              |
| ------------------------- | ------ | ----- | --------------- |
| `danmaku_x`               | 10     | 30    | 弹幕起始 X 坐标（像素）   |
| `layer_width_extra`       | 100    | 100   | 渲染层额外宽度（像素）     |
| `bubble_padding_x`        | 14     | 14    | 气泡水平内边距（像素）     |
| `bubble_padding_y`        | 5      | 5     | 气泡垂直内边距（像素）     |
| `bubble_row_gap`          | 5      | 5     | 气泡内多行文本的行间距（像素） |
| `bubble_vertical_gap`     | 4      | 4     | 弹幕气泡之间的垂直间距（像素） |
| `bubble_multiline_radius` | 10.0   | 14.0  | 多行气泡圆角半径（像素）    |
| `gift_spacing`            | 6      | 6     | 礼物图标间距（像素）      |
| `emoji_spacing`           | 4      | 4     | Emoji 间距（像素）    |
| `font_size`               | 18     | 25    | 字体大小（pt）        |
| `fade_out_zone`           | 20.0   | 30.0  | 文本弹幕淡出区域高度（像素）  |

### 布局比例 (ratio)

| 参数                 | 随项目配置值 | 内置默认值 | 说明         |
| ------------------ | ------ | ----- | ---------- |
| `max_text_rows`    | 8      | 4     | 文本弹幕最多显示行数 |
| `max_gift_rows`    | 2      | 2     | 礼物弹幕最多显示行数 |
| `text_width_ratio` | 0.8    | 0.8   | 文本弹幕最大宽度比例 |
| `bottom_margin`    | 12     | 22    | 底部边距（像素）   |

### 动画参数 (animation)

| 参数                      | 随项目配置值 | 内置默认值 | 说明                           |
| ----------------------- | ------ | ----- | ---------------------------- |
| `text_damping_factor`   | 0.1    | 0.25  | 文本弹幕移动阻尼系数（0~1，越大越快）         |
| `gift_damping_factor`   | 0.1    | 0.25  | 礼物弹幕移动阻尼系数（0~1，越大越快）         |
| `text_spawn_interval`   | 0.5    | 0.5   | 文本弹幕发射间隔（秒）                  |
| `text_spawn_batch_size` | 3      | 3     | 文本弹幕每次发射数量                   |
| `gift_spawn_interval`   | 0.5    | 0.5   | 礼物弹幕发射间隔（秒）                  |
| `gift_spawn_batch_size` | 2      | 2     | 礼物弹幕每次发射数量                   |
| `gift_dwell_time`       | 5.0    | 5.0   | 礼物停留时间（秒），`null` 表示永不因停留时间过期 |
| `min_gift_price`        | 0.0    | 1.0   | 最低礼物价格过滤（元）                  |

### 编码参数 (encode)

当前 `danmakustudio.yaml` 中的编码参数处于注释状态，因此使用内置默认值。

| 参数                        | 内置默认值    | 说明                                 |
| ------------------------- | -------- | ---------------------------------- |
| `gpu_preset`              | "p5"     | NVIDIA NVENC 预设（p1~p7，越大越慢、质量越好）   |
| `gpu_cq`                  | 15       | NVIDIA NVENC QP 质量（0~51，越小越好、文件越大） |
| `qsv_preset`              | "slow"   | Intel QSV 预设（越慢通常质量越好）             |
| `qsv_quality`             | 18       | Intel QSV 质量（0~51，越小越好、文件越大）       |
| `cpu_preset`              | "medium" | libx264 预设（越慢压缩效率越好）               |
| `cpu_crf`                 | 18       | libx264 CRF 质量（0~51，越小越好、文件越大）     |
| `cpu_min_reserve_threads` | 2        | CPU 编码保留线程数                        |

### 系统参数 (system)

当前 `danmakustudio.yaml` 中的系统参数处于注释状态，因此使用内置默认值。

| 参数                      | 内置默认值    | 说明                          |
| ----------------------- | -------- | --------------------------- |
| `pipe_buffer_size`      | 10000000 | 管道缓冲区大小（字节）                 |
| `pipe_queue_size`       | 16       | 异步写入队列大小                    |
| `ffmpeg_timeout`        | 10       | FFmpeg 启动超时（秒）              |
| `stderr_thread_timeout` | 5        | 错误日志线程超时（秒）                 |
| `video_alignment`       | 2        | 视频尺寸对齐到偶数，避免 1080 被放大到 1088 |
| `max_queue_frames`      | 64       | 异步写入队列最大帧数                  |

## 打包

项目提供了一键打包脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

打包完成后，可执行文件位于：

```text
dist\DanmakuStudio\DanmakuStudio.exe
```

发布时请保留整个 `dist\DanmakuStudio\` 文件夹。程序仍依赖系统中的 FFmpeg / ffprobe。

## 处理流程

```text
字幕解析 -> 资源加载 -> 视频信息获取 -> 弹幕布局计算 -> 逐帧渲染 -> FFmpeg 合成
```

1. 解析 XML/LRC 字幕；XML 会提取 `<d>` 和 `<gift>` 标签，LRC 会解析时间轴文本
2. 加载 Emoji 和礼物图片资源，按需加载字体
3. 通过 ffprobe 获取视频宽高、帧率、总帧数
4. 预创建弹幕对象，计算布局参数
5. 构建 FFmpeg 编码命令，自动检测 GPU / QSV / CPU 编码路径
6. 逐帧渲染弹幕气泡图层，通过管道送入 FFmpeg，输出压制视频

## 项目结构

```text
DanmakuStudio/
├── src/danmakustudio/        # 核心包
│   ├── cli.py                # CLI 入口
│   ├── gui.py                # 图形界面入口
│   ├── batch.py              # 批量文件发现与字幕匹配
│   ├── config/               # 配置模块
│   ├── core/                 # 压制流程编排
│   ├── encode/               # FFmpeg 进程管理
│   ├── input/                # XML/LRC 字幕解析
│   ├── layout/               # 布局计算、活跃弹幕状态
│   ├── render/               # 气泡渲染、图片资源加载
│   └── utils/                # 工具函数与输入输出校验
├── tests/                    # 测试
├── DanmakuStudio.spec        # PyInstaller 打包配置
├── build_exe.ps1             # 一键打包脚本
├── danmakustudio.yaml        # 默认配置文件
├── pyproject.toml
├── uv.lock
├── LICENSE
└── README.md
```

`assets/` 目录为可选资源目录，通常用于存放 Emoji、礼物图片或字体文件；当前干净仓库不包含具体素材资源。

## 许可证

本项目沿用 GPLv3 发布，详见仓库根目录的 `LICENSE` 文件。由于本项目基于 GPLv3 代码修改，分发修改版时也应保留 GPLv3、保留版权与许可声明，并公开对应源代码。



## 致谢

本项目基于 [cerulean26/DanmakuPro](https://github.com/cerulean26/DanmakuPro) 修改。感谢原项目提供的弹幕压制基础实现。
