# NCM 本地音频转换

把自己有权使用的本地 `.ncm` 文件恢复成普通音频。默认模式直接取出内部 FLAC/MP3 字节，**不重新编码**。也可明确选择设备需要的目标格式。工具在本机运行，不下载歌曲、不连接云端，不修改或删除源文件。

> “无损目标格式”只说明目标编码方式。若 NCM 内部原本是有损 MP3，转成 FLAC/WAV/ALAC 不会补回音质。若内部是 FLAC，默认原样恢复最能保留原始文件。

## 安装

需要 Python 3.10+。转码功能和完整音频解码校验需要 FFmpeg（含 FFprobe）；GUI 需要 Tk。macOS Homebrew Python 3.14 可用：

```sh
brew install ffmpeg python-tk@3.14
cd /path/to/ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

使用其他 Python 版本时，请安装与其版本匹配的 Tk 包；Linux 通常是 `python3-tk`。用 `.venv/bin/python -m tkinter` 可检查 GUI 依赖。

## 桌面界面

```sh
.venv/bin/ncm-restore-gui
```

点“添加文件…”或“添加文件夹…”选择输入；可搜索子目录、指定输出目录和目标格式。界面显示批量进度、每个文件的输出路径或失败原因。选择器支持中文路径。GUI 使用后台线程处理音频，窗口保持可操作。

## 命令行

```sh
# 默认原样恢复，输出到源文件旁的 recovered 文件夹
.venv/bin/ncm-restore '/path/歌曲.ncm'

# 批量转为 ALAC/M4A；报告是新文件，不覆盖已有报告
.venv/bin/ncm-restore -r '/path/NCM目录' --to alac -o '/path/输出目录' --report '/path/ncm-report.json'

# 查看支持的目标格式
.venv/bin/ncm-restore --help
```

支持多个文件/目录；`-r` 才递归扫描。已有输出自动编号为 `歌曲 (2).flac` 等。单个文件失败后继续处理其余文件，退出码 1 表示有失败，`--report` 记录逐项结果和提示。

## 格式与质量

| `--to` | 输出 | 编码质量 | 默认设置 | 外层封面 |
|---|---|---|---|---|
| `original`（默认） | 内部 FLAC 或 MP3 | 原始字节不变 | 不重新编码 | 侧车；原始音频自带标签不变 |
| `wav` | WAV / PCM | 无损编码 | 保留采样率、声道和已知位深 | 侧车 |
| `flac` | FLAC | 无损编码 | 保留采样率、声道和已知位深 | 尝试嵌入，始终保留侧车 |
| `alac` | ALAC / M4A | 无损编码 | 保留采样率、声道和已知位深 | 尝试嵌入，始终保留侧车 |
| `mp3` | MP3 | 有损编码 | 320 kb/s；最高 48 kHz | 尝试嵌入，始终保留侧车 |
| `aac` | AAC / M4A | 有损编码 | 256 kb/s；最高 96 kHz | 尝试嵌入，始终保留侧车 |
| `opus` | Opus / OGG | 有损编码 | 192 kb/s VBR；48 kHz | 侧车 |

有损格式需要调整采样率时，结果和 JSON 报告会写明源值与目标值。声道数保持不变；编码器不支持时会报错，不静默混成双声道。`original` 输出完全不写入新标签。转码时将 NCM 外层标题、艺术家、专辑写入容器可用标签，同时保留完整 JSON 和封面侧车；若输出无法核实这些标签或封面嵌入，结果会给出提示。侧车文件名为 `歌曲.ncm-metadata.json` 与 `歌曲.cover.jpg/png/bin`。

## 校验与失败处理

- 默认恢复计算输出 SHA-256，回读比对，并在 FFmpeg 可用时对整首音频完整解码。若未安装 FFmpeg，结果标为 `byte_verified_only`，不能声称整首解码通过。
- 转码输出发布前完整解码并检查 codec、采样率、声道；FLAC 来源到无损目标另比较转换前后 32 位 PCM SHA-256。失败时删除临时产物。报告有输出 SHA-256。
- 输出先写临时文件，验证成功后用不覆盖已有文件的方式发布。音频和侧车的冲突都会另取文件名。源文件只读打开。
- 当前识别 NCM 内部 FLAC/MP3。NCM 头部的保留字段没有可靠的公开校验语义；即使完成解码，也不能证明源文件来自高品质母带。目标设备的实际播放仍需用户验证。

## 开发、隐私和许可

```sh
.venv/bin/python -m unittest discover -s tests -v
```

测试只在运行时生成短合成音频和 NCM 夹具；仓库不包含受版权保护的歌曲或转换产物。本机真实样例的只读验证见 [VALIDATION.md](VALIDATION.md)。代码采用 [MIT 许可证](LICENSE)，第三方归属与许可证见 [THIRD_PARTY.md](THIRD_PARTY.md)。

转换运行时不请求网络，不上传音频、封面、元数据或路径。安装 Python 包和 FFmpeg 本身可能需要联网。请遵守你所在地区的法律及所使用音频的许可条款。
