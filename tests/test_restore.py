"""Synthetic fixtures only: no commercial audio is stored in this repository."""

import base64
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ncm_restore.cli import main
from ncm_restore.core import CORE_KEY, META_KEY, NcmError, restore


def _encrypt_block(plain: bytes, key: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return cipher.update(padded) + cipher.finalize()


def _pack_ncm(audio: bytes, metadata: dict, cover: bytes = b"") -> bytes:
    music_key = b"synthetic-test-key"
    key = _encrypt_block(b"neteasecloudmusic" + music_key, CORE_KEY)
    key = bytes(byte ^ 0x64 for byte in key)
    meta = _encrypt_block(b"music:" + json.dumps(metadata, ensure_ascii=False).encode(), META_KEY)
    meta = b"163 key(Don't modify):" + base64.b64encode(meta)
    meta = bytes(byte ^ 0x63 for byte in meta)

    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + music_key[i % len(music_key)]) & 255
        box[i], box[j] = box[j], box[i]
    mask = [box[(box[k] + box[(box[k] + k) & 255]) & 255] for k in range(256)]
    encrypted = bytes(byte ^ mask[(i + 1) & 255] for i, byte in enumerate(audio))
    return (
        b"CTENFDAM\x01\x61" + struct.pack("<I", len(key)) + key
        + struct.pack("<I", len(meta)) + meta
        + b"\x00" * 5 + struct.pack("<II", len(cover) + 3, len(cover))
        + cover + b"\x00" * 3 + encrypted
    )


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required for full-decode fixture")
class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _audio(self, kind: str) -> bytes:
        output = self.root / f"tone.{kind}"
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=0.3", "-c:a", "flac" if kind == "flac" else "libmp3lame",
            "-y", str(output),
        ], check=True)
        return output.read_bytes()

    def test_exact_flac_with_chinese_path_and_sidecars(self):
        audio = self._audio("flac")
        # Deliberately wrong wrapper hint: the audio signature decides the suffix.
        metadata = {"musicName": "测试音频", "artist": [["测试者", 1]], "format": "mp3"}
        source = self.root / "中文路径.ncm"
        source.write_bytes(_pack_ncm(audio, metadata, b"\xff\xd8\xffsynthetic-cover"))
        original = source.read_bytes()
        # Force many audio chunks to check cipher positioning across boundaries.
        with patch("ncm_restore.core.CHUNK", 257):
            result = restore(source, self.root / "输出")
        self.assertEqual(Path(result["output"]).read_bytes(), audio)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(result["validation"], "byte_verified_and_full_decode")
        self.assertEqual(json.loads((self.root / "输出/中文路径.ncm-metadata.json").read_text()), metadata)
        self.assertTrue((self.root / "输出/中文路径.cover.jpg").exists())

    def test_without_ffmpeg_is_explicitly_lower_confidence(self):
        audio = self._audio("flac")
        source = self.root / "offline.ncm"
        source.write_bytes(_pack_ncm(audio, {"format": "flac"}))
        with patch("ncm_restore.core.shutil.which", return_value=None):
            result = restore(source, self.root / "out")
        self.assertEqual(result["validation"], "byte_verified_only (ffmpeg unavailable)")
        self.assertEqual(Path(result["output"]).read_bytes(), audio)

    def test_mp3_collision_batch_and_failure_report(self):
        audio = self._audio("mp3")
        folder = self.root / "批量"
        folder.mkdir()
        (folder / "a.ncm").write_bytes(_pack_ncm(audio, {"format": "mp3"}))
        (folder / "bad.ncm").write_bytes(b"bad")
        output = self.root / "out"
        report1 = self.root / "report1.json"
        self.assertEqual(main([str(folder), "-o", str(output), "--report", str(report1)]), 1)
        self.assertEqual((output / "a.mp3").read_bytes(), audio)
        self.assertEqual(len(json.loads(report1.read_text())["failures"]), 1)
        report2 = self.root / "report2.json"
        self.assertEqual(main([str(folder / "a.ncm"), "-o", str(output), "--report", str(report2)]), 0)
        self.assertEqual((output / "a (2).mp3").read_bytes(), audio)
        self.assertEqual((output / "a.mp3").read_bytes(), audio)

    def test_invalid_structure_leaves_no_audio(self):
        source = self.root / "truncated.ncm"
        source.write_bytes(_pack_ncm(self._audio("flac"), {"format": "flac"})[:35])
        with self.assertRaises(NcmError):
            restore(source, self.root / "out")
        self.assertFalse(list((self.root / "out").glob("*.flac")))


if __name__ == "__main__":
    unittest.main()
