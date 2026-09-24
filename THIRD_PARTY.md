# 第三方来源与许可

- 本项目源码为独立实现，采用仓库中的 [MIT 许可证](LICENSE)。NCM 文件结构研究参考 [ncmdump-py](https://github.com/ww-rm/ncmdump-py)，其[源码许可证为 MIT](https://github.com/ww-rm/ncmdump-py/blob/main/LICENSE)；未复制或捆绑该项目代码。
- Python 运行依赖 [cryptography](https://github.com/pyca/cryptography)，其[许可标识为 Apache-2.0 OR BSD-3-Clause](https://github.com/pyca/cryptography/blob/main/pyproject.toml)。本仓库未捆绑其二进制文件。
- 可选转码工具 [FFmpeg](https://ffmpeg.org/) 由用户另行安装。本仓库不捆绑 FFmpeg；具体构建可能采用 LGPL 或 GPL 组件，详见 [FFmpeg 官方许可说明](https://ffmpeg.org/legal.html)。
- GUI 使用 Python 标准库 `tkinter` 和本机 Tcl/Tk。安装包未捆绑 Python 或 Tcl/Tk。
- 圆角卡片、按钮、输入框和其他现代 GUI 控件使用 [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)，采用 MIT 许可证。
- 文件拖拽使用 [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2)，其项目采用 MIT 许可证并包含跨平台 tkdnd 运行文件；详见其仓库中的许可证与第三方说明。

若将本项目再打包成包含 Python、FFmpeg 或其他依赖的安装包，发布者需要重新核对所捆绑组件的具体版本、构建选项、许可证与归属要求。
