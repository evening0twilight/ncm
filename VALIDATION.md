# 本机验证记录（2026-09-23）

## 自动测试

在 macOS、Python 3.14.7、`cryptography` 46.0.7、系统 FFmpeg 环境中：

```text
python -m unittest discover -s tests -v
Ran 4 tests — OK
```

合成 NCM 内含测试时生成的短 FLAC/MP3 音频；恢复字节与输入原始音频逐字节相同。覆盖中文路径、跨数据块位置、错误格式提示、原始元数据/封面侧车、批量失败、重名与 FFmpeg 缺席状态。

## 真实本地样例

只读扫描 `/Users/a1-6/Music/网易云音乐` 找到两份 `.ncm`。转换产物放在仓库外 `/tmp`，未纳入 Git。转换命令执行后，成功 2、失败 0；两份输出均通过恢复时 SHA-256 回读以及 FFmpeg 完整解码。FFprobe 均识别为 FLAC、192000 Hz、双声道：

| 源文件 | 恢复字节数 | 时长（秒） | 输出 SHA-256 |
|---|---:|---:|---|
| `Matisse & Sadko,James French - Pull Me Through The Fire.ncm` | 143401581 | 216.569354 | `aa4c6b50ace0d3149e8aab676fb679fbb8a7cd0176d229e5068c4a005ac6c652` |
| `VALORANT,Grabbitz,Oli Sykes - If The Sun Burns Out Tonight (feat. Oli Sykes & Courtney LaPlante).ncm` | 155907260 | 226.403188 | `022a67e0473aaecfc9e273d130b1b236e8a0fdd24581ee27f5633c968ef018e2` |

源 `.ncm` 在验证前后 SHA-256 相同。外层 JSON 元数据和封面均成功导出为侧车文件。完整解码与哈希校验不能证明音源本身的真实质量，也不能代替目标设备的播放测试。

同目录另外只有 `Marcus Warner - Wings.flac.tmp` 等 3 个 0 字节临时文件，没有对应的可用 `.ncm` 样例。扫描 `/Users/a1-6/Music/Music` 仍返回 `Operation not permitted`，因此没有检验该目录内容或第三首歌曲。
