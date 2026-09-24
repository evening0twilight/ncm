"""End-to-end conversion and batch/UI logic using generated audio only."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_restore import _pack_ncm
from ncm_restore.core import NcmError
from ncm_restore.gui import format_hint, merge_input_paths, target_from_label
from ncm_restore.transcode import FORMATS, _probe, convert
from ncm_restore.workflow import collect_sources, run_batch


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class TranscodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        wav = self.root / "input.wav"
        flac = self.root / "input.flac"
        cover = self.root / "cover.png"
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=192000:duration=0.3", "-c:a", "pcm_s24le", "-y", str(wav),
        ], check=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(wav), "-c:a", "flac", "-y", str(flac)], check=True)
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "color=c=red:s=32x32:d=0.1", "-frames:v", "1", "-y", str(cover),
        ], check=True)
        self.audio = flac.read_bytes()
        self.source = self.root / "中文样例.ncm"
        self.source.write_bytes(_pack_ncm(self.audio, {
            "format": "flac", "musicName": "标题", "artist": [["艺术家", 1]], "album": "专辑",
        }, cover.read_bytes()))

    def test_every_target_codec_rate_channels_and_lossless_pcm(self):
        expected = {
            "wav": ("pcm_s24le", 192000), "flac": ("flac", 192000),
            "alac": ("alac", 192000), "mp3": ("mp3", 48000),
            "aac": ("aac", 96000), "opus": ("opus", 48000),
        }
        for target, (codec, rate) in expected.items():
            with self.subTest(target=target):
                result = convert(self.source, self.root / "output", target)
                self.assertEqual(result["codec"], codec)
                self.assertEqual(result["sample_rate"], rate)
                self.assertEqual(result["channels"], 1)
                self.assertEqual(result["source_bit_depth"], 24)
                self.assertTrue(Path(result["output"]).exists())
                self.assertTrue(Path(result["output"]).with_suffix(".ncm-metadata.json").exists())
                if FORMATS[target]["lossless"]:
                    self.assertEqual(result["validation"], "full_decode_and_pcm_match")
                    self.assertEqual(result["output_bit_depth"], 24)
                else:
                    self.assertEqual(result["validation"], "full_decode")
                if target in ("wav", "opus"):
                    self.assertFalse(result["cover_embedded"])
                    self.assertTrue(any("封面仅保存在侧车" in note for note in result["notes"]))
                else:
                    self.assertTrue(result["cover_embedded"])
                self.assertEqual(_probe(Path(result["output"]), shutil.which("ffprobe"))["audio"]["codec_name"], codec)

    def test_original_collision_and_missing_ffmpeg(self):
        first = convert(self.source, self.root / "output", "original")
        second = convert(self.source, self.root / "output", "original")
        self.assertEqual(Path(first["output"]).read_bytes(), self.audio)
        self.assertEqual(Path(second["output"]).read_bytes(), self.audio)
        self.assertNotEqual(first["output"], second["output"])
        with patch("ncm_restore.transcode.shutil.which", return_value=None):
            with self.assertRaisesRegex(NcmError, "FFmpeg"):
                convert(self.source, self.root / "missing", "mp3")
        self.assertFalse((self.root / "missing").exists())

    def test_transcoded_collision_and_invalid_cover_fallback(self):
        first = convert(self.source, self.root / "out", "mp3")
        second = convert(self.source, self.root / "out", "mp3")
        self.assertNotEqual(first["output"], second["output"])
        self.assertTrue(Path(first["output"]).exists())
        self.assertTrue(Path(second["output"]).exists())
        bad_cover = self.root / "bad-cover.ncm"
        bad_cover.write_bytes(_pack_ncm(self.audio, {"musicName": "标题", "format": "flac"}, b"\xff\xd8\xffnot-a-jpeg"))
        result = convert(bad_cover, self.root / "fallback", "flac")
        self.assertFalse(result["cover_embedded"])
        self.assertTrue(any("封面仅保存在侧车" in note for note in result["notes"]))
        self.assertTrue(any(Path(path).suffix == ".jpg" for path in result["sidecars"]))

    def test_lossy_source_to_lossless_target_is_labeled(self):
        mp3 = self.root / "tone.mp3"
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=0.3", "-c:a", "libmp3lame", "-y", str(mp3),
        ], check=True)
        source = self.root / "lossy.ncm"
        source.write_bytes(_pack_ncm(mp3.read_bytes(), {"format": "mp3"}))
        result = convert(source, self.root / "out", "flac")
        self.assertEqual(result["source_format"], "mp3")
        self.assertTrue(any("不能恢复已损失音质" in note for note in result["notes"]))

    def test_failed_encoder_leaves_no_outputs(self):
        with patch("ncm_restore.transcode._arguments", return_value=["-c:a", "no-such-encoder"]):
            with self.assertRaisesRegex(NcmError, "FFmpeg 转换失败"):
                convert(self.source, self.root / "failed", "mp3")
        self.assertEqual(list((self.root / "failed").iterdir()), [])

    def test_gui_choice_and_batch_collection(self):
        for target, profile in FORMATS.items():
            self.assertEqual(target_from_label(profile["label"]), target)
        self.assertRaises(ValueError, target_from_label, "invalid")
        folder = self.root / "文件夹"
        folder.mkdir()
        nested = folder / "子目录"
        nested.mkdir()
        duplicate = nested / "中文样例.ncm"
        duplicate.write_bytes(self.source.read_bytes())
        found, errors = collect_sources([folder, duplicate], recursive=True)
        self.assertEqual(errors, [])
        self.assertEqual(found, [duplicate])
        events = []
        starts = []
        successes, failures = run_batch(found, self.root / "batch", "original", lambda *event: events.append(event), lambda *event: starts.append(event))
        self.assertEqual((len(successes), len(failures), len(events)), (1, 0, 1))
        self.assertEqual(starts, [(1, 1, duplicate)])
        self.assertTrue(events[0][-1])

    def test_gui_drop_validation_and_format_guidance(self):
        folder = self.root / "拖拽文件夹"
        folder.mkdir()
        ncm = self.root / "有 空格.ncm"
        ncm.write_bytes(self.source.read_bytes())
        text = self.root / "不是音频.txt"
        text.write_text("not ncm")

        merged, rejected = merge_input_paths(
            [ncm],
            [ncm, folder, text, self.root / "missing.ncm"],
        )

        self.assertEqual(merged, [ncm, folder])
        self.assertEqual(len(rejected), 2)
        self.assertTrue(any("不是 NCM" in item for item in rejected))
        self.assertTrue(any("路径不存在" in item for item in rejected))
        self.assertIn("不重新编码", format_hint("original"))
        self.assertIn("Apple", format_hint("alac"))


if __name__ == "__main__":
    unittest.main()
