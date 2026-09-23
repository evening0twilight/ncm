"""Command-line interface for local NCM restoration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import NcmError, restore


def _sources(paths: list[Path], recursive: bool) -> tuple[list[Path], list[dict[str, str]]]:
    found: list[Path] = []
    errors: list[dict[str, str]] = []
    seen: set[Path] = set()
    for path in paths:
        if path.is_file():
            if path.suffix.lower() != ".ncm":
                errors.append({"source": str(path), "error": "文件扩展名不是 .ncm"})
                continue
            candidates = [path]
        elif path.is_dir():
            candidates = [p for p in (path.rglob("*") if recursive else path.iterdir()) if p.is_file() and p.suffix.lower() == ".ncm"]
            if not candidates:
                errors.append({"source": str(path), "error": "目录中没有 .ncm 文件"})
        else:
            errors.append({"source": str(path), "error": "路径不存在或不可访问"})
            continue
        for candidate in sorted(candidates):
            identity = candidate.resolve()
            if identity not in seen:
                found.append(candidate)
                seen.add(identity)
    return found, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ncm-restore",
        description="本地恢复 .ncm 中原始的 FLAC/MP3 音频字节；不重新编码，也不改动源文件。",
    )
    parser.add_argument("paths", type=Path, nargs="+", help=".ncm 文件或包含 .ncm 的目录，可给多个")
    parser.add_argument("-o", "--output-dir", type=Path, help="输出目录；默认是每个源文件旁的 recovered 目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归搜索输入目录")
    parser.add_argument("--report", type=Path, help="将结果写入新的 JSON 报告文件；不覆盖已有文件")
    args = parser.parse_args(argv)

    try:
        sources, failures = _sources(args.paths, args.recursive)
    except OSError as exc:
        print(f"无法扫描输入目录：{exc}", file=sys.stderr)
        return 2
    successes = []
    for source in sources:
        destination = args.output_dir if args.output_dir else source.parent / "recovered"
        try:
            result = restore(source, destination)
            successes.append(result)
            print(f"✓ {source} → {result['output']} [{result['validation']}]")
            if result["warning"]:
                print(f"  提示：{result['warning']}", file=sys.stderr)
        except (NcmError, OSError, ValueError) as exc:
            failures.append({"source": str(source), "error": str(exc)})
            print(f"✗ {source}: {exc}", file=sys.stderr)
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
