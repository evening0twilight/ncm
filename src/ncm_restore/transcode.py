"""Optional FFmpeg conversion. The default restore path never calls this module."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .core import NcmError, _sha256, _unique_path, _verify_audio, restore

# Lossless describes the target codec, not the quality of a lossy NCM source.
FORMATS = {
    "original": {"label": "原样恢复（不重新编码）", "lossless": None, "ext": None},
    "wav": {"label": "WAV / PCM（无损）", "lossless": True, "ext": ".wav"},
    "flac": {"label": "FLAC（无损）", "lossless": True, "ext": ".flac"},
    "alac": {"label": "ALAC / M4A（无损）", "lossless": True, "ext": ".m4a"},
    "mp3": {"label": "MP3 320 kb/s（有损）", "lossless": False, "ext": ".mp3"},
    "aac": {"label": "AAC / M4A 256 kb/s（有损）", "lossless": False, "ext": ".m4a"},
    "opus": {"label": "Opus / OGG 192 kb/s（有损）", "lossless": False, "ext": ".opus"},
}


def _tools() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise NcmError("目标格式转换需要 FFmpeg 和 FFprobe；请先安装 FFmpeg")
    return ffmpeg, ffprobe


def _probe(path: Path, ffprobe: str) -> dict[str, Any]:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise NcmError(f"FFprobe 无法读取音频：{result.stderr.strip()[:400]}")
    data = json.loads(result.stdout)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise NcmError("输出中没有音频流")
    tags = {**data.get("format", {}).get("tags", {}), **audio.get("tags", {})}
    return {"audio": audio, "streams": data.get("streams", []), "tags": tags}


def _pcm_hash(path: Path, ffmpeg: str) -> str:
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(path),
         "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "hash", "-hash", "SHA256", "-"],
        capture_output=True, text=True,
    )
    if result.returncode or not result.stdout.startswith("SHA256="):
        raise NcmError(f"PCM 校验失败：{result.stderr.strip()[:400]}")
    return result.stdout.strip()


def _depth(stream: dict[str, Any]) -> int:
    for field in ("bits_per_raw_sample", "bits_per_sample"):
        try:
            value = int(stream.get(field) or 0)
            if value:
                return value
        except (ValueError, TypeError):
            pass
    return 16 if stream.get("sample_fmt") in ("s16", "s16p") else 24


def _rate(target: str, source_rate: int) -> int:
    if target == "opus":
        return 48000
    if target == "mp3":
        return min(source_rate, 48000)
    if target == "aac":
        return min(source_rate, 96000)
    return source_rate


def _arguments(target: str, depth: int) -> list[str]:
    if target == "wav":
        return ["-c:a", "pcm_s16le" if depth <= 16 else "pcm_s24le" if depth <= 24 else "pcm_s32le"]
    if target == "flac":
        return ["-c:a", "flac", "-sample_fmt", "s16" if depth <= 16 else "s32"]
    if target == "alac":
        return ["-c:a", "alac", "-sample_fmt", "s16p" if depth <= 16 else "s32p"]
    if target == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", "320k", "-id3v2_version", "3"]
    if target == "aac":
        return ["-c:a", "aac", "-b:a", "256k"]
    if target == "opus":
        return ["-c:a", "libopus", "-b:a", "192k", "-vbr", "on"]
    raise ValueError(f"未知目标格式：{target}")


def _tags(meta: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(meta, dict):
        return {}
    result = {}
    if isinstance(meta.get("musicName"), str):
        result["title"] = meta["musicName"]
    if isinstance(meta.get("album"), str):
        result["album"] = meta["album"]
    names = [a[0] for a in meta.get("artist", []) if isinstance(a, list) and a and isinstance(a[0], str)] if isinstance(meta.get("artist"), list) else []
    if names:
        result["artist"] = "; ".join(names)
    return result


def _destination_directory(base: Path, source: Path, organize: bool) -> tuple[Path, bool]:
    base.mkdir(parents=True, exist_ok=True)
    if not organize:
        return base, False
    stem = source.stem or "音频"
    number = 1
    while True:
        name = stem if number == 1 else f"{stem} ({number})"
        candidate = base / name
        try:
            candidate.mkdir()
            return candidate, True
        except FileExistsError:
            number += 1


def convert(
    source: Path,
    output_dir: Path,
    target: str = "original",
    *,
    export_metadata: bool = True,
    export_cover: bool = True,
    organize: bool = False,
) -> dict[str, Any]:
    """Restore original bytes or encode a requested target without modifying source."""
    if target not in FORMATS:
        raise ValueError(f"未知目标格式：{target}")
    source, output_dir = Path(source), Path(output_dir)
    tools = _tools() if target != "original" else None
    organize = bool(organize and (export_metadata or export_cover))
    destination_dir, created_directory = _destination_directory(output_dir, source, organize)
    if target == "original":
        try:
            result = restore(
                source,
                destination_dir,
                export_metadata=export_metadata,
                export_cover=export_cover,
            )
        except Exception:
            if created_directory:
                try:
                    destination_dir.rmdir()
                except OSError:
                    pass
            raise
        notes = []
        if result["sidecars"]:
            notes.append("已按选择导出附加文件")
        else:
            notes.append("仅输出音频文件")
        result.update({"target": target, "quality": "原样恢复", "metadata_embedded": None,
                       "cover_embedded": None, "notes": notes, "organized": organize,
                       "output_directory": str(destination_dir)})
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                stream = _probe(Path(result["output"]), ffprobe)["audio"]
                result.update({"codec": stream["codec_name"], "sample_rate": int(stream["sample_rate"]),
                               "channels": int(stream["channels"]), "output_bit_depth": _depth(stream) if result["format"] == "flac" else None})
            except (NcmError, ValueError, KeyError) as exc:
                result["notes"].append(f"FFprobe 未能补充流参数：{exc}")
        return result

    assert tools is not None
    ffmpeg, ffprobe = tools
    temporary: Path | None = None
    published: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix=".ncm-work-", dir=destination_dir) as work_name:
            work = Path(work_name)
            recovered = restore(source, work)
            original = Path(recovered["output"])
            input_info = _probe(original, ffprobe)["audio"]
            source_rate = int(input_info["sample_rate"])
            channels = int(input_info["channels"])
            depth = _depth(input_info)
            rate = _rate(target, source_rate)
            meta_path = original.with_suffix(".ncm-metadata.json")
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
            cover = next((p for p in recovered["sidecars"] if ".cover." in p), None)
            cover_path = Path(cover) if cover else None
            can_embed_cover = target in ("flac", "alac", "mp3", "aac") and cover_path is not None and cover_path.suffix in (".jpg", ".png")
            with tempfile.NamedTemporaryFile(prefix=".ncm-encode-", suffix=FORMATS[target]["ext"], dir=destination_dir, delete=False) as temp:
                temporary = Path(temp.name)
            temporary.unlink()  # FFmpeg creates this pathname; it must not inherit an empty file.

            def encode(embed_cover: bool) -> subprocess.CompletedProcess[str]:
                args = [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(original)]
                if embed_cover:
                    args += ["-i", str(cover_path)]
                args += ["-map", "0:a:0"]
                if embed_cover:
                    args += ["-map", "1:v:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
                args += ["-map_metadata", "0"]
                for key, value in _tags(meta).items():
                    args += ["-metadata", f"{key}={value}"]
                args += ["-ar", str(rate), *_arguments(target, depth), str(temporary)]
                return subprocess.run(args, capture_output=True, text=True)

            encoded = encode(can_embed_cover)
            cover_fallback = False
            if encoded.returncode and can_embed_cover:
                temporary.unlink(missing_ok=True)
                encoded = encode(False)
                cover_fallback = True
            if encoded.returncode:
                raise NcmError(f"FFmpeg 转换失败：{encoded.stderr.strip()[:500]}")

            if _verify_audio(temporary) != "byte_verified_and_full_decode":
                raise NcmError("FFmpeg 完整解码校验不可用")
            output_info = _probe(temporary, ffprobe)
            stream = output_info["audio"]
            expected_codec = {"wav": "pcm_s16le" if depth <= 16 else "pcm_s24le" if depth <= 24 else "pcm_s32le",
                              "flac": "flac", "alac": "alac", "mp3": "mp3", "aac": "aac", "opus": "opus"}[target]
            if stream.get("codec_name") != expected_codec:
                raise NcmError("输出音频 codec 不符合目标设置")
            if int(stream["sample_rate"]) != rate or int(stream["channels"]) != channels:
                raise NcmError("输出采样率或声道数不符合目标设置")
            if FORMATS[target]["lossless"] and recovered["format"] == "flac":
                if _pcm_hash(original, ffmpeg) != _pcm_hash(temporary, ffmpeg):
                    raise NcmError("无损转换前后 PCM 不一致")
            tags = {key.lower(): value for key, value in output_info["tags"].items()}
            requested_tags = _tags(meta)
            missing_tags = [key for key, value in requested_tags.items() if tags.get(key) != value]
            cover_embedded = any(s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") == 1 for s in output_info["streams"])
            sidecar_paths = [
                original.with_suffix(".ncm-metadata.json") if export_metadata and meta_path.exists() else None,
                cover_path if export_cover else None,
            ]
            sidecar_paths = [p for p in sidecar_paths if p is not None]
            while True:
                candidate = _unique_path(
                    destination_dir,
                    source.stem,
                    FORMATS[target]["ext"],
                    meta if export_metadata else None,
                    cover_path.read_bytes() if export_cover and cover_path else b"",
                )
                try:
                    os.link(temporary, candidate)
                    published.append(candidate)
                    break
                except FileExistsError:
                    continue
            output_sidecars = []
            for path in sidecar_paths:
                destination = candidate.with_suffix(path.suffix if ".cover." not in path.name else ".cover" + path.suffix)
                if path.name.endswith(".ncm-metadata.json"):
                    destination = candidate.with_suffix(".ncm-metadata.json")
                with destination.open("xb") as out:
                    published.append(destination)
                    out.write(path.read_bytes())
                output_sidecars.append(str(destination))
            notes = []
            if rate != source_rate:
                notes.append(f"采样率从 {source_rate} Hz 转为 {rate} Hz（目标编码器限制）")
            if export_cover and cover_path and not cover_embedded:
                notes.append("封面仅保存在侧车" + ("（嵌入尝试失败）" if cover_fallback else ""))
            if missing_tags:
                suffix = "，完整元数据见侧车" if export_metadata else ""
                notes.append("以下标签未在输出中核实" + suffix + "：" + ", ".join(missing_tags))
            if recovered["format"] == "mp3" and FORMATS[target]["lossless"]:
                notes.append("源音频为有损 MP3，转成无损格式不能恢复已损失音质")
            return {
                "source": str(source), "output": str(candidate), "target": target,
                "format": target, "quality": "无损编码" if FORMATS[target]["lossless"] else "有损编码",
                "source_format": recovered["format"], "codec": stream["codec_name"],
                "source_sample_rate": source_rate, "sample_rate": rate, "channels": channels,
                "source_bit_depth": depth if recovered["format"] == "flac" else None,
                "output_bit_depth": _depth(stream) if FORMATS[target]["lossless"] else None,
                "audio_bytes": candidate.stat().st_size, "sha256": _sha256(candidate),
                "validation": "full_decode_and_pcm_match" if FORMATS[target]["lossless"] and recovered["format"] == "flac" else "full_decode",
                "metadata_embedded": not missing_tags if requested_tags else None,
                "cover_embedded": cover_embedded if cover_path else None,
                "sidecars": output_sidecars, "notes": notes, "warning": recovered["warning"],
                "organized": organize, "output_directory": str(destination_dir),
            }
    except Exception:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if created_directory:
            try:
                destination_dir.rmdir()
            except OSError:
                pass
