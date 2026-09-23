"""Command-line interface for local NCM restoration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .transcode import FORMATS
from .workflow import collect_sources, run_batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ncm-restore",
        description="本地恢复 .ncm 原始音频，或明确选择目标格式转码；不改动源文件。",
    )
    parser.add_argument("paths", type=Path, nargs="+", help=".ncm 文件或包含 .ncm 的目录，可给多个")
    parser.add_argument("-o", "--output-dir", type=Path, help="输出目录；默认是每个源文件旁的 recovered 目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归搜索输入目录")
    parser.add_argument("--to", choices=FORMATS, default="original", help="目标格式；默认 original 原样恢复。无损：wav/flac/alac；有损：mp3/aac/opus")
    parser.add_argument("--report", type=Path, help="将结果写入新的 JSON 报告文件；不覆盖已有文件")
    args = parser.parse_args(argv)

    try:
        sources, failures = collect_sources(args.paths, args.recursive)
    except OSError as exc:
        print(f"无法扫描输入目录：{exc}", file=sys.stderr)
        return 2
    def report_item(index: int, total: int, item: dict, ok: bool) -> None:
        if ok:
            print(f"✓ [{index}/{total}] {item['source']} → {item['output']} [{item['validation']}]")
            for note in item.get("notes", []):
                print(f"  提示：{note}", file=sys.stderr)
            if item.get("warning"):
                print(f"  提示：{item['warning']}", file=sys.stderr)
        else:
            print(f"✗ [{index}/{total}] {item['source']}: {item['error']}", file=sys.stderr)

    successes, conversion_failures = run_batch(sources, args.output_dir, args.to, report_item)
    failures.extend(conversion_failures)
    report = {"successes": successes, "failures": failures}
    if args.report:
        try:
            with args.report.open("x", encoding="utf-8") as out:
                json.dump(report, out, ensure_ascii=False, indent=2)
                out.write("\n")
        except OSError as exc:
            print(f"报告写入失败：{exc}", file=sys.stderr)
            return 2
    print(f"完成：成功 {len(successes)}，失败 {len(failures)}", file=sys.stderr)
    for failure in failures:
        print(f"  {failure['source']}: {failure['error']}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
