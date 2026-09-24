# NCM Restore Local · NCM 本地音频转换

> A private, local NCM converter for NetEase Cloud Music files. Restore the original FLAC/MP3 audio without re-encoding, or convert `.ncm` to WAV, FLAC, ALAC/M4A, MP3, AAC/M4A, and Opus with a desktop GUI or CLI.

> 网易云音乐 NCM 本地转换工具：默认无重新编码地恢复原始 FLAC/MP3，也可批量将 NCM 转为 WAV、FLAC、ALAC、MP3、AAC 和 Opus。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GUI + CLI](https://img.shields.io/badge/Interface-GUI%20%2B%20CLI-blue)](#features)
[![Local processing](https://img.shields.io/badge/Privacy-Local%20processing-brightgreen)](#privacy-and-scope)

**Languages:** [简体中文](#zh-cn) · [English](#english) · [日本語](#日本語) · [한국어](#한국어)

NCM Restore Local is an open-source **NCM converter**, **NCM to MP3 converter**, and **NCM to FLAC converter** for local files you are authorized to use. Audio, artwork, metadata, and file paths stay on your computer during conversion.

> [!IMPORTANT]
> “Lossless output” describes the target codec. If the audio inside an NCM file is already lossy MP3, converting it to FLAC, WAV, or ALAC cannot recreate discarded audio information. For an internal FLAC source, **Original restore** preserves the exact audio bytes and is the preferred mode.

---

<a id="zh-cn"></a>

## 简体中文

### 项目介绍

NCM Restore Local 是一个开源的网易云音乐 `.ncm` 音频恢复与格式转换工具。默认模式直接解密并取出 NCM 内部原有的 FLAC 或 MP3 字节，不进行二次编码。需要兼容特定设备时，也可以通过 FFmpeg 转换成常见音频格式。

项目提供桌面界面和命令行，适合单曲处理、整个音乐文件夹批量转换，以及需要 JSON 结果报告的自动化场景。

<a id="features"></a>

### 功能

- 原样恢复 NCM 内部的 FLAC/MP3，不重新编码。
- 转换为 WAV、FLAC、ALAC/M4A、MP3、AAC/M4A 或 Opus。
- 现代桌面 GUI：圆角卡片布局、拖入或选择文件/文件夹、格式选择、进度与逐项结果。
- 命令行批量转换，支持中文、日文、韩文及其他 Unicode 路径。
- 尽量写入标题、艺术家、专辑和封面，同时保留完整元数据与封面侧车。
- SHA-256 回读校验、FFmpeg 整首解码检查，以及无损转换的 PCM 一致性检查。
- 不覆盖已有文件、不删除源文件；单个文件失败不会中止整个批次。
- 完全在本机处理，转换过程不上传音频或元数据。

### 快速开始

需要 Python 3.10+。转码和完整解码校验需要 FFmpeg（包含 FFprobe），桌面界面需要 Tk。

macOS（Homebrew Python 3.14）：

```sh
brew install ffmpeg python-tk@3.14
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Ubuntu / Debian：

```sh
sudo apt install ffmpeg python3-tk python3-venv
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Windows（常见安装方式，尚未纳入本项目的实机验证）：

```powershell
winget install Gyan.FFmpeg
git clone https://github.com/evening0twilight/ncm.git
cd ncm
py -m venv .venv
.venv\Scripts\python -m pip install -e .
```

### 怎么使用

启动桌面界面：

```sh
.venv/bin/ncm-restore-gui
```

Windows 使用：

```powershell
.venv\Scripts\ncm-restore-gui.exe
```

在界面中依次：

1. 把 NCM 文件或文件夹拖入蓝色区域，也可以点击该区域选择文件。
2. 选择输出目录；留空时会在源文件旁创建 `recovered` 文件夹。
3. 选择“原样恢复”或需要的目标格式。
4. 点击“开始转换”，在结果列表查看输出路径或失败原因。

命令行示例：

```sh
# 单个文件：原样恢复，不重新编码
.venv/bin/ncm-restore '/path/歌曲.ncm'

# 整个文件夹递归转换为 ALAC/M4A
.venv/bin/ncm-restore -r '/path/NCM音乐' --to alac -o '/path/转换结果'

# 批量转换为 MP3，并保存 JSON 报告
.venv/bin/ncm-restore -r '/path/NCM音乐' --to mp3 -o '/path/MP3' --report '/path/report.json'

# 查看完整参数
.venv/bin/ncm-restore --help
```

### 支持的输出格式

| `--to` | 输出 | 质量与默认设置 | 封面 |
|---|---|---|---|
| `original` | 内部 FLAC 或 MP3 | 原始字节不变；默认且推荐 | 侧车 |
| `wav` | WAV / PCM | 无损；保留采样率、声道和已知位深 | 侧车 |
| `flac` | FLAC | 无损；保留采样率、声道和已知位深 | 尝试嵌入并保留侧车 |
| `alac` | ALAC / M4A | 无损；保留采样率、声道和已知位深 | 尝试嵌入并保留侧车 |
| `mp3` | MP3 | 有损；320 kb/s，最高 48 kHz | 尝试嵌入并保留侧车 |
| `aac` | AAC / M4A | 有损；256 kb/s，最高 96 kHz | 尝试嵌入并保留侧车 |
| `opus` | Opus | 有损；192 kb/s VBR，48 kHz | 侧车 |

转换结果会报告实际 codec、采样率、声道、位深、SHA-256、标签和封面状态。已有输出会自动编号，例如 `歌曲 (2).flac`。

### 验证范围

当前版本通过 11 项自动测试。四份真实 NCM 样例已在 macOS 上原样恢复为 FLAC，源文件哈希保持不变，恢复结果通过 FFmpeg 整首解码；WAV、FLAC 和 ALAC 的无损转换通过 PCM 哈希一致性检查。详细证据见 [VALIDATION.md](VALIDATION.md)。

桌面界面可以启动，核心选择与批量逻辑有自动测试；尚未完成自动化鼠标交互验收。Windows、Linux 和具体播放设备也尚未做实机兼容性保证。

---

<a id="english"></a>

## English

### About

NCM Restore Local is an open-source converter for local NetEase Cloud Music `.ncm` files. Its default mode decrypts and restores the embedded FLAC or MP3 bytes without re-encoding. When a player requires another format, the tool can transcode the restored audio through FFmpeg.

Use the desktop GUI for everyday conversion or the CLI for recursive folders, automation, and JSON reports.

### Features

- Restore the original embedded FLAC/MP3 audio without re-encoding.
- Convert NCM to WAV, FLAC, ALAC/M4A, MP3, AAC/M4A, or Opus.
- Modern desktop GUI with rounded cards, drag-and-drop, format selection, progress, and per-file results.
- Batch CLI with Unicode paths and machine-readable JSON reports.
- Preserve or embed title, artist, album, and artwork where supported; sidecars retain the complete NCM metadata.
- Verify output with SHA-256 rereads and full FFmpeg decoding; compare decoded PCM for lossless conversions.
- Never overwrite existing output or delete source files; one failure does not stop the batch.
- Process everything locally without uploading audio, artwork, metadata, or paths.

### Quick start

Python 3.10+ is required. FFmpeg and FFprobe are required for transcoding and full decode verification. Tk is required for the GUI.

macOS with Homebrew Python 3.14:

```sh
brew install ffmpeg python-tk@3.14
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Ubuntu / Debian:

```sh
sudo apt install ffmpeg python3-tk python3-venv
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Windows (common setup; not yet covered by this project's hardware validation):

```powershell
winget install Gyan.FFmpeg
git clone https://github.com/evening0twilight/ncm.git
cd ncm
py -m venv .venv
.venv\Scripts\python -m pip install -e .
```

### Usage

Launch the desktop app:

```sh
.venv/bin/ncm-restore-gui
```

On Windows:

```powershell
.venv\Scripts\ncm-restore-gui.exe
```

In the GUI, drag files or folders onto the blue drop zone, choose an output directory and target format, then click **Start conversion**. Leave the output field empty to create a `recovered` folder beside each source file.

CLI examples:

```sh
# Restore one NCM file without re-encoding
.venv/bin/ncm-restore '/path/song.ncm'

# Recursively convert a folder to lossless ALAC/M4A
.venv/bin/ncm-restore -r '/path/NCM Music' --to alac -o '/path/Converted'

# Batch convert NCM to MP3 and write a JSON report
.venv/bin/ncm-restore -r '/path/NCM Music' --to mp3 -o '/path/MP3' --report '/path/report.json'

# Show every option
.venv/bin/ncm-restore --help
```

### Output formats

| `--to` | Output | Quality and defaults | Artwork |
|---|---|---|---|
| `original` | Embedded FLAC or MP3 | Exact audio bytes; default and recommended | Sidecar |
| `wav` | WAV / PCM | Lossless; preserves rate, channels, and known bit depth | Sidecar |
| `flac` | FLAC | Lossless; preserves rate, channels, and known bit depth | Embedded when possible + sidecar |
| `alac` | ALAC / M4A | Lossless; preserves rate, channels, and known bit depth | Embedded when possible + sidecar |
| `mp3` | MP3 | Lossy; 320 kb/s, up to 48 kHz | Embedded when possible + sidecar |
| `aac` | AAC / M4A | Lossy; 256 kb/s, up to 96 kHz | Embedded when possible + sidecar |
| `opus` | Opus | Lossy; 192 kb/s VBR, 48 kHz | Sidecar |

Each result reports its actual codec, sample rate, channel count, bit depth, SHA-256, metadata, and artwork status. Existing filenames are never overwritten; a suffix such as `song (2).flac` is used instead.

### Validation status

The current release passes 11 automated tests. Four real NCM samples were restored to FLAC on macOS without changing the source hashes, and every restored file passed a full FFmpeg decode. WAV, FLAC, and ALAC lossless conversions matched decoded PCM hashes. See [VALIDATION.md](VALIDATION.md).

The GUI starts successfully and its selection/batch logic is tested, but automated mouse interaction has not been completed. Windows, Linux, and individual playback devices have not received hardware compatibility certification.

---

<a id="日本語"></a>

## 日本語

### 概要

NCM Restore Local は、ローカルに保存された NetEase Cloud Music の `.ncm` ファイルを扱うオープンソース変換ツールです。既定では、NCM 内部の FLAC または MP3 を再エンコードせずにそのまま復元します。再生機器に合わせて、FFmpeg を使った別形式への変換もできます。

デスクトップ GUI とコマンドラインの両方を備え、単一ファイル、フォルダーの一括変換、JSON レポートに対応しています。

### 主な機能

- 内部の FLAC/MP3 を再エンコードせずに復元。
- NCM を WAV、FLAC、ALAC/M4A、MP3、AAC/M4A、Opus に変換。
- 角丸カードを採用したモダン GUI。ドラッグ＆ドロップ、形式選択、進行状況、個別結果に対応。
- Unicode パスと JSON レポートに対応した一括 CLI。
- 対応形式ではタイトル、アーティスト、アルバム、アートワークを埋め込み、完全な情報はサイドカーファイルにも保存。
- SHA-256 の再読み込み、FFmpeg の全曲デコード、可逆変換時の PCM 一致確認。
- 既存ファイルを上書きせず、元の NCM を変更・削除しない安全な処理。
- 音声やメタデータをアップロードしないローカル処理。

### インストール

Python 3.10 以上が必要です。変換と完全デコード検証には FFmpeg/FFprobe、GUI には Tk が必要です。

macOS（Homebrew Python 3.14）：

```sh
brew install ffmpeg python-tk@3.14
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Ubuntu / Debian：

```sh
sudo apt install ffmpeg python3-tk python3-venv
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

### 使い方

GUI を起動：

```sh
.venv/bin/ncm-restore-gui
```

GUI の青い領域へファイルまたはフォルダーをドラッグし、出力先と変換形式を選択して「変換開始」を押します。出力先を空欄にすると、元ファイルと同じ場所に `recovered` フォルダーを作成します。

コマンドライン例：

```sh
# 再エンコードせずに 1 ファイルを復元
.venv/bin/ncm-restore '/path/song.ncm'

# フォルダーを再帰的に ALAC/M4A へ変換
.venv/bin/ncm-restore -r '/path/NCM Music' --to alac -o '/path/Converted'

# MP3 に一括変換し JSON レポートを保存
.venv/bin/ncm-restore -r '/path/NCM Music' --to mp3 -o '/path/MP3' --report '/path/report.json'
```

### 対応形式

| `--to` | 出力 | 品質と設定 |
|---|---|---|
| `original` | 内部 FLAC / MP3 | 元の音声バイトを保持。既定・推奨 |
| `wav` | WAV / PCM | 可逆。サンプルレート、チャンネル、既知のビット深度を保持 |
| `flac` | FLAC | 可逆。サンプルレート、チャンネル、既知のビット深度を保持 |
| `alac` | ALAC / M4A | 可逆。サンプルレート、チャンネル、既知のビット深度を保持 |
| `mp3` | MP3 | 非可逆。320 kb/s、最大 48 kHz |
| `aac` | AAC / M4A | 非可逆。256 kb/s、最大 96 kHz |
| `opus` | Opus | 非可逆。192 kb/s VBR、48 kHz |

現在のリリースは 11 件の自動テストに合格しています。macOS 上で 4 件の実 NCM を FLAC に復元し、元ファイルのハッシュ不変と FFmpeg の全曲デコードを確認しました。WAV、FLAC、ALAC はデコード後の PCM ハッシュも一致しています。詳細は [VALIDATION.md](VALIDATION.md) を参照してください。

GUI の起動と主要ロジックは確認済みですが、マウス操作の自動検証、Windows/Linux 実機、個別再生機器の互換性保証はまだありません。

---

<a id="한국어"></a>

## 한국어

### 소개

NCM Restore Local은 로컬에 저장된 NetEase Cloud Music `.ncm` 파일을 위한 오픈 소스 변환 도구입니다. 기본 모드는 NCM 안의 FLAC 또는 MP3 오디오 바이트를 재인코딩 없이 그대로 복원합니다. 재생 기기에 다른 형식이 필요하면 FFmpeg를 사용해 일반 오디오 형식으로 변환할 수 있습니다.

데스크톱 GUI와 명령줄을 모두 제공하며 단일 파일, 폴더 일괄 변환, JSON 결과 보고서를 지원합니다.

### 주요 기능

- 내부 FLAC/MP3를 재인코딩 없이 복원.
- NCM을 WAV, FLAC, ALAC/M4A, MP3, AAC/M4A, Opus로 변환.
- 둥근 카드 레이아웃, 드래그 앤 드롭, 형식 선택, 진행률, 파일별 결과를 제공하는 현대적인 GUI.
- Unicode 경로와 JSON 보고서를 지원하는 일괄 CLI.
- 가능한 형식에 제목, 아티스트, 앨범, 표지를 삽입하고 전체 정보는 사이드카 파일에도 보존.
- SHA-256 재검증, FFmpeg 전체 디코딩, 무손실 변환의 PCM 일치 검사.
- 기존 출력을 덮어쓰지 않고 원본 NCM을 수정하거나 삭제하지 않음.
- 오디오와 메타데이터를 업로드하지 않는 완전한 로컬 처리.

### 설치

Python 3.10 이상이 필요합니다. 변환과 전체 디코딩 검증에는 FFmpeg/FFprobe가 필요하고 GUI에는 Tk가 필요합니다.

macOS（Homebrew Python 3.14）：

```sh
brew install ffmpeg python-tk@3.14
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Ubuntu / Debian：

```sh
sudo apt install ffmpeg python3-tk python3-venv
git clone https://github.com/evening0twilight/ncm.git
cd ncm
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

### 사용법

GUI 실행：

```sh
.venv/bin/ncm-restore-gui
```

GUI의 파란 영역에 파일 또는 폴더를 끌어 놓고 출력 폴더와 대상 형식을 선택한 후 “변환 시작”을 누릅니다. 출력 폴더를 비워 두면 각 원본 옆에 `recovered` 폴더가 생성됩니다.

명령줄 예시：

```sh
# 재인코딩 없이 NCM 한 개 복원
.venv/bin/ncm-restore '/path/song.ncm'

# 폴더를 재귀 검색해 ALAC/M4A로 변환
.venv/bin/ncm-restore -r '/path/NCM Music' --to alac -o '/path/Converted'

# MP3로 일괄 변환하고 JSON 보고서 저장
.venv/bin/ncm-restore -r '/path/NCM Music' --to mp3 -o '/path/MP3' --report '/path/report.json'
```

### 지원 형식

| `--to` | 출력 | 품질 및 설정 |
|---|---|---|
| `original` | 내부 FLAC / MP3 | 원본 오디오 바이트 유지. 기본값 및 권장 |
| `wav` | WAV / PCM | 무손실. 샘플레이트, 채널, 확인된 비트 심도 유지 |
| `flac` | FLAC | 무손실. 샘플레이트, 채널, 확인된 비트 심도 유지 |
| `alac` | ALAC / M4A | 무손실. 샘플레이트, 채널, 확인된 비트 심도 유지 |
| `mp3` | MP3 | 손실 압축. 320 kb/s, 최대 48 kHz |
| `aac` | AAC / M4A | 손실 압축. 256 kb/s, 최대 96 kHz |
| `opus` | Opus | 손실 압축. 192 kb/s VBR, 48 kHz |

현재 릴리스는 자동 테스트 11개를 통과했습니다. macOS에서 실제 NCM 파일 4개를 FLAC으로 복원했으며 원본 해시가 변하지 않았고 모든 결과가 FFmpeg 전체 디코딩을 통과했습니다. WAV, FLAC, ALAC 무손실 변환은 디코딩된 PCM 해시도 일치했습니다. 자세한 내용은 [VALIDATION.md](VALIDATION.md)를 확인하세요.

GUI 실행과 주요 로직은 검증했지만 자동 마우스 조작, Windows/Linux 실기기, 개별 재생 장치 호환성은 아직 보증하지 않습니다.

---

<a id="privacy-and-scope"></a>

## Privacy and scope · 隐私与范围

- Conversion runs locally. The application does not request network access at runtime.
- The repository contains no commercial music, converted audio, local paths, or private sample fingerprints.
- Use the software only with files you are authorized to access, and follow applicable laws and content licenses.
- This project restores or converts local files; it does not download music, authenticate accounts, or bypass online access controls.
- 本工具仅处理你有权使用的本地文件；运行时不上传音频、封面、元数据或文件路径。

## Development

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests generate short synthetic FLAC/MP3 and NCM fixtures at runtime. See [VALIDATION.md](VALIDATION.md) for the verified boundary, [THIRD_PARTY.md](THIRD_PARTY.md) for third-party attribution, and [LICENSE](LICENSE) for the MIT license.

## Search keywords

NCM converter · NCM to MP3 · NCM to FLAC · NCM to WAV · NetEase Cloud Music converter · 网易云音乐 NCM 转换 · NCM 解密 · NCM 無損変換 · NCM 변환 · local audio converter · batch audio converter · Python Tkinter FFmpeg
