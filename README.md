# NCM 本地音频恢复

把本机 `.ncm` 文件中包裹的原始 **FLAC 或 MP3 字节**恢复出来。恢复过程不重新编码，源文件保持不变。若 NCM 内部是 MP3，得到的仍是有损 MP3；把它改名或转换成 FLAC 也不能补回已损失的音质。输出格式由解密后的音频文件头决定，不信任 NCM 元数据里的 `format` 字段。

本工具只处理你有权使用的本地文件，不提供下载或在线服务。不会绕过帐号验证或获取平台内容。

## 安装

需要 Python 3.10+。推荐同时安装 FFmpeg，以便对恢复的整首音频做完整解码校验。

```sh
cd /Users/a1-6/projects/person/ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

在 macOS 上如果没有 FFmpeg，可以 `brew install ffmpeg`。没有 FFmpeg 也能恢复和逐字节回读校验，但报告会标为 `byte_verified_only`，不能视作完整音频解码通过。

## 使用

```sh
# 单文件：默认输出到源文件旁的 recovered 目录
.venv/bin/ncm-restore '/path/歌曲.ncm'

# 批量目录（递归），统一输出目录，并保存成功/失败 JSON 报告
.venv/bin/ncm-restore -r '/path/网易云音乐' -o '/path/转换结果' --report '/path/ncm-report.json'

# 查看所有选项
.venv/bin/ncm-restore --help
```

支持中文路径、多个文件/目录。重名输出会自动编号，如 `歌曲 (2).flac`；已有文件和报告绝不覆盖。目录扫描默认仅当前层，`-r` 才搜索子目录。每个失败会显示原因，批量执行继续处理其他文件；有失败时进程退出码为 1。报告文件不存在时才会新建。

音频原始字节保持不变。NCM 外层的 JSON 元数据和封面分别保存为 `歌曲.ncm-metadata.json` 和 `歌曲.cover.jpg/png/bin`，不会为写标签而重编码或修改恢复出的音频。若原始音频本身已有标签，它们自然保留。外层元数据若损坏，音频仍尝试恢复，并给出提示。

## 校验与限制

- 恢复时计算 SHA-256，再从临时文件回读计算一次；两次必须相同。
- 若安装 FFmpeg，输出发布前运行完整解码，失败则不留下音频文件。`byte_verified_and_full_decode` 表示两关均通过。完整解码通过不等于证明录音来源或音质等级。
- NCM 头中的 5 字节保留区并没有可靠的公开校验语义，本工具不把它声称为源文件 CRC。若源 NCM 本身被截断而仍能解码，无法保证原始发布文件完整。
- 只识别 FLAC/MP3。其他变体会失败并报告，不会猜扩展名。没有“转换成其他设备格式”的重新编码功能；如设备不支持恢复出的原格式，需要另外用可信音频工具转码，转成 MP3/AAC 会有损。
- 源文件是只读打开；输出与附属文件采用新文件名，不删除源文件。建议先少量试用，核对设备能播放后再批量处理。

## 开发验证与来源

```sh
.venv/bin/python -m unittest discover -s tests -v
```

测试运行时用 FFmpeg 生成短正弦波 FLAC/MP3，再封装成合成 NCM；比较恢复音频与原始夹具的全部字节，并覆盖中文路径、封面、元数据、批量失败报告、重名与截断文件。仓库不存放任何商业音频或转换产物。

本机真实样例验证记录见 [VALIDATION.md](VALIDATION.md)。

格式研究参考了 [ncmdump-py](https://github.com/ww-rm/ncmdump-py)（[MIT 许可证](https://github.com/ww-rm/ncmdump-py/blob/main/LICENSE)）与 [pyNCMDUMP](https://github.com/allenfrostline/pyNCMDUMP)（仓库显示 MIT 许可证）。本项目按已公开的文件结构独立实现，没有复制这些项目的源代码。音频完整解码校验使用本机 FFmpeg，详见 [FFmpeg 文档](https://ffmpeg.org/ffmpeg.html)。
