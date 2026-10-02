"""Helpers for collision-safe Python analysis result directories."""

from __future__ import annotations

from pathlib import Path


def reserve_output_directory(output_dir: Path, output_kind: str) -> None:
    """Atomically claim a fresh output directory without reusing old results."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Refusing to reuse existing {output_kind} output directory: {output_dir}"
        ) from exc


def write_completion_marker(output_dir: Path, marker_name: str, contents: str) -> None:
    """Publish a completion marker only after all result files have closed."""
    marker = output_dir / marker_name
    temporary_marker = output_dir / f".{marker_name}.tmp"
    with temporary_marker.open("x", encoding="utf-8") as stream:
        stream.write(contents)
    temporary_marker.replace(marker)
