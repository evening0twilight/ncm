"""Bounded NCM parser and byte-for-byte audio restoration.

The format details were checked against MIT-licensed ncmdump-py and pyNCMDUMP.
This implementation is independently written and does not bundle their code.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"CTENFDAM"
CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")
META_KEY = bytes.fromhex("2331346c6a6b5f215c5d2630553c2728")
CHUNK = 1024 * 1024
MAX_KEY = 1024 * 1024
MAX_META = 8 * 1024 * 1024
MAX_COVER = 32 * 1024 * 1024


class NcmError(Exception):
    """Invalid, unsupported, or incomplete NCM data."""


def _read_exact(stream: BinaryIO, count: int) -> bytes:
    data = stream.read(count)
    if len(data) != count:
        raise NcmError("NCM 文件截断")
    return data


def _block(stream: BinaryIO, maximum: int) -> bytes:
    length = struct.unpack("<I", _read_exact(stream, 4))[0]
    if length > maximum:
        raise NcmError(f"NCM 数据块过大：{length} 字节")
    return _read_exact(stream, length)


def _aes_unpad(data: bytes, key: bytes) -> bytes:
    if not data or len(data) % 16:
        raise NcmError("AES 数据长度无效")
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    try:
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(plain) + unpadder.finalize()
    except ValueError as exc:
        raise NcmError("AES 填充校验失败") from exc


def _key_box(key: bytes) -> bytes:
    if not key:
        raise NcmError("NCM 音频密钥为空")
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + key[i % len(key)]) & 0xFF
        box[i], box[j] = box[j], box[i]
    return bytes(box)


def _xor_audio(data: bytes, box: bytes, offset: int) -> bytes:
    # NCM uses a fixed, position-indexed lookup, rather than standard RC4 PRGA.
    mask = bytes(
        box[(box[j] + box[(box[j] + j) & 0xFF]) & 0xFF]
        for j in range(256)
    )
    return bytes(byte ^ mask[(offset + i + 1) & 0xFF] for i, byte in enumerate(data))


def _metadata(raw: bytes) -> tuple[dict[str, Any] | None, str | None]:
    if not raw:
        return None, "NCM 未包含元数据"
    try:
        clear = bytes(b ^ 0x63 for b in raw)
        prefix = b"163 key(Don't modify):"
        if not clear.startswith(prefix):
            raise NcmError("元数据前缀不匹配")
        encrypted = base64.b64decode(clear[len(prefix):], validate=True)
        payload = _aes_unpad(encrypted, META_KEY)
        if not payload.startswith(b"music:"):
            raise NcmError("元数据 JSON 前缀不匹配")
        value = json.loads(payload[len(b"music:"):].decode("utf-8"))
        if not isinstance(value, dict):
            raise NcmError("元数据不是 JSON 对象")
        return value, None
    except (ValueError, UnicodeError, binascii.Error, NcmError) as exc:
        return None, f"NCM 元数据无法解析：{exc}"


@dataclass
class Header:
    box: bytes
    metadata: dict[str, Any] | None
    metadata_warning: str | None
    cover: bytes
    payload_offset: int


def parse_header(stream: BinaryIO) -> Header:
    if _read_exact(stream, 8) != MAGIC:
        raise NcmError("不是受支持的 NCM 文件（文件头不匹配）")
    _read_exact(stream, 2)  # version/reserved bytes
    key_data = bytes(b ^ 0x64 for b in _block(stream, MAX_KEY))
    key_clear = _aes_unpad(key_data, CORE_KEY)
    prefix = b"neteasecloudmusic"
    if not key_clear.startswith(prefix):
        raise NcmError("音频密钥前缀不匹配")
    box = _key_box(key_clear[len(prefix):])
    metadata, warning = _metadata(_block(stream, MAX_META))
    _read_exact(stream, 5)  # CRC/reserved area; semantics are not established
    cover_space = struct.unpack("<I", _read_exact(stream, 4))[0]
    cover_size = struct.unpack("<I", _read_exact(stream, 4))[0]
    if cover_space > MAX_COVER or cover_size > cover_space:
        raise NcmError("封面数据长度无效或过大")
    cover = _read_exact(stream, cover_size)
    _read_exact(stream, cover_space - cover_size)
    return Header(box, metadata, warning, cover, stream.tell())


def _audio_type(first: bytes) -> str:
    if first.startswith(b"fLaC"):
        return "flac"
    if first.startswith(b"ID3") or (len(first) >= 2 and first[0] == 0xFF and first[1] & 0xE0 == 0xE0):
        return "mp3"
    raise NcmError("解密后不是可识别的 FLAC 或 MP3；可能是损坏或未支持的 NCM 变体")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_audio(path: Path) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return "byte_verified_only (ffmpeg unavailable)"
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(path),
         "-map", "0:a:0", "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    if result.returncode:
        raise NcmError(f"ffmpeg 完整解码失败：{result.stderr.strip()[:500]}")
    return "byte_verified_and_full_decode"


def _sidecar_paths(audio: Path, metadata: dict[str, Any] | None, cover: bytes) -> list[Path]:
    paths = []
    if metadata is not None:
        paths.append(audio.with_suffix(".ncm-metadata.json"))
    if cover:
        extension = ".cover.jpg" if cover.startswith(b"\xff\xd8") else ".cover.png" if cover.startswith(b"\x89PNG") else ".cover.bin"
        paths.append(audio.with_suffix(extension))
    return paths


def _unique_path(directory: Path, stem: str, suffix: str, metadata: dict[str, Any] | None, cover: bytes) -> Path:
    number = 1
    while True:
        name = stem if number == 1 else f"{stem} ({number})"
        candidate = directory / f"{name}{suffix}"
        if not any(path.exists() for path in [candidate, *_sidecar_paths(candidate, metadata, cover)]):
            return candidate
        number += 1


def restore(
    source: Path,
    output_dir: Path,
    *,
    export_metadata: bool = True,
    export_cover: bool = True,
) -> dict[str, Any]:
    """Restore audio and optional sidecars; never alter the source or overwrite output."""
    source = Path(source)
    output_dir = Path(output_dir)
    if not source.is_file():
        raise NcmError("源文件不存在或不是普通文件")
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    published: list[Path] = []
    try:
        with source.open("rb") as src:
            before = os.fstat(src.fileno())
            header = parse_header(src)
            start = src.read(16)
            if not start:
                raise NcmError("NCM 音频载荷为空")
            kind = _audio_type(_xor_audio(start, header.box, 0))
            src.seek(header.payload_offset)
            with tempfile.NamedTemporaryFile(prefix=".ncm-restore-", suffix=f".{kind}", dir=output_dir, delete=False) as tmp:
                temporary = Path(tmp.name)
                digest = hashlib.sha256()
                offset = 0
                for encrypted in iter(lambda: src.read(CHUNK), b""):
                    recovered = _xor_audio(encrypted, header.box, offset)
                    tmp.write(recovered)
                    digest.update(recovered)
                    offset += len(encrypted)
                tmp.flush()
                os.fsync(tmp.fileno())
            after = os.fstat(src.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise NcmError("源文件在恢复过程中发生变化，请重试")
        if _sha256(temporary) != digest.hexdigest():
            raise NcmError("输出文件回读 SHA-256 校验失败")
        validation = _verify_audio(temporary)
        collision_metadata = header.metadata if export_metadata else None
        collision_cover = header.cover if export_cover else b""
        candidate = _unique_path(output_dir, source.stem, f".{kind}", collision_metadata, collision_cover)
        # Hard-link publication is atomic and fails if another process claimed the name.
        while True:
            try:
                os.link(temporary, candidate)
                published.append(candidate)
                break
            except FileExistsError:
                candidate = _unique_path(output_dir, source.stem, f".{kind}", collision_metadata, collision_cover)
        sidecars: list[str] = []
        for suffix, data, enabled in (
            (
                ".ncm-metadata.json",
                json.dumps(header.metadata, ensure_ascii=False, indent=2).encode("utf-8") if header.metadata is not None else None,
                export_metadata,
            ),
            (
                ".cover.jpg" if header.cover.startswith(b"\xff\xd8") else ".cover.png" if header.cover.startswith(b"\x89PNG") else ".cover.bin",
                header.cover or None,
                export_cover,
            ),
        ):
            if data is None or not enabled:
                continue
            path = candidate.with_suffix(suffix)
            try:
                with path.open("xb") as out:
                    published.append(path)
                    out.write(data)
                sidecars.append(str(path))
            except FileExistsError:
                # A sidecar collision must not silently attach unrelated metadata.
                raise NcmError(f"附属文件已存在：{path}")
        return {
            "source": str(source), "output": str(candidate), "format": kind,
            "audio_bytes": offset, "sha256": digest.hexdigest(),
            "validation": validation, "sidecars": sidecars,
            "warning": header.metadata_warning,
        }
    except Exception:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
