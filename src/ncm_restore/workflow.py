"""Batch orchestration shared by CLI and GUI; no UI dependency."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .core import NcmError
from .transcode import convert


def collect_sources(paths: list[Path], recursive: bool) -> tuple[list[Path], list[dict[str, str]]]:
    found: list[Path] = []
    errors: list[dict[str, str]] = []
    seen: set[Path] = set()
    for path in paths:
        try:
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
        except OSError as exc:
            errors.append({"source": str(path), "error": str(exc)})
    return found, errors


def run_batch(
    sources: list[Path], output_dir: Path | None, target: str,
    on_result: Callable[[int, int, dict, bool], None] | None = None,
    on_start: Callable[[int, int, Path], None] | None = None,
    *,
    export_metadata: bool = True,
    export_cover: bool = True,
    organize: bool = False,
) -> tuple[list[dict], list[dict]]:
    successes: list[dict] = []
    failures: list[dict] = []
    for index, source in enumerate(sources, 1):
        if on_start:
            on_start(index, len(sources), source)
        try:
            result = convert(
                source,
                output_dir or source.parent / "recovered",
                target,
                export_metadata=export_metadata,
                export_cover=export_cover,
                organize=organize,
            )
            successes.append(result)
            if on_result:
                on_result(index, len(sources), result, True)
        except (NcmError, OSError, ValueError, RuntimeError) as exc:
            failure = {"source": str(source), "error": str(exc)}
            failures.append(failure)
            if on_result:
                on_result(index, len(sources), failure, False)
    return successes, failures
