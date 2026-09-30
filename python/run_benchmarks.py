#!/usr/bin/env python3
"""Run reproducible compute and desktop scheduling benchmarks for AeroSim-Core."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def summarize(values: list[float | int]) -> dict[str, float | int]:
    ordered = sorted(values)
    percentile_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "sample_count": len(values),
        "mean": sum(values) / len(values),
        "median": float(statistics.median(values)),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "p95_nearest_rank": ordered[percentile_index],
    }


def run_command(command: list[str]) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def collect_cpu_model() -> tuple[str | None, str]:
    if platform.system() == "Darwin":
        command = ["sysctl", "-n", "machdep.cpu.brand_string"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError:
            return None, "sysctl machdep.cpu.brand_string unavailable"
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), "sysctl -n machdep.cpu.brand_string"
        return None, "sysctl -n machdep.cpu.brand_string unavailable"

    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition(":")
                if separator and key.strip().lower() in {"model name", "hardware", "model"}:
                    return value.strip(), "/proc/cpuinfo"
        except OSError:
            pass
        return None, "/proc/cpuinfo did not report a CPU model"

    return None, "no CPU-model probe is defined for this operating system"


def prepare_output_path(requested_path: Path | None) -> tuple[Path, str]:
    if requested_path is None:
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            + "-"
            + uuid.uuid4().hex[:8]
        )
        output_path = Path("benchmark_results") / f"aerosim-benchmark-{run_id}.json"
    else:
        output_path = requested_path
        run_id = output_path.stem

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except FileExistsError as error:
        if output_path.parent.exists() and not output_path.parent.is_dir():
            raise NotADirectoryError(
                f"benchmark output parent is not a directory: {output_path.parent}"
            ) from error
        raise

    if output_path.is_dir():
        raise IsADirectoryError(
            f"benchmark output path is a directory; provide a report filename: {output_path}"
        )
    if output_path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing benchmark report; choose a new output path: {output_path}"
        )
    return output_path, run_id


def parse_timing_output(output: str) -> dict[str, float | int]:
    patterns = {
        "target_period_ms": rf"^Target period: ({NUMBER}) ms$",
        "simulation_steps": r"^Simulation steps: (\d+)$",
        "step_execution_average_ms": rf"^Step execution time \(ms\): average=({NUMBER}), minimum=({NUMBER}), maximum=({NUMBER})$",
        "scheduling_error_ms": rf"^Absolute scheduling error \(ms\): average=({NUMBER}), maximum=({NUMBER})$",
        "late_step_starts": r"^Late step starts: (\d+) \(.*\)$",
        "full_period_late_steps": r"^Full-period-late steps: (\d+) \(.*\)$",
    }
    matches: dict[str, re.Match[str]] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, output, re.MULTILINE)
        if match is None:
            raise ValueError(f"Could not parse {key} from aerosim_timing output")
        matches[key] = match

    execution = matches["step_execution_average_ms"]
    scheduling = matches["scheduling_error_ms"]
    return {
        "target_period_ms": float(matches["target_period_ms"].group(1)),
        "simulation_steps": int(matches["simulation_steps"].group(1)),
        "step_execution_average_ms": float(execution.group(1)),
        "step_execution_minimum_ms": float(execution.group(2)),
        "step_execution_maximum_ms": float(execution.group(3)),
        "scheduling_error_average_ms": float(scheduling.group(1)),
        "scheduling_error_maximum_ms": float(scheduling.group(2)),
        "late_step_starts": int(matches["late_step_starts"].group(1)),
        "full_period_late_steps": int(matches["full_period_late_steps"].group(1)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=Path("build"))
    parser.add_argument("--steps", type=int, default=1_000_000)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--timing-duration", type=float, default=0.25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.steps < 1 or args.repetitions < 2 or not math.isfinite(args.timing_duration) or args.timing_duration <= 0:
        parser.error("steps must be positive, repetitions at least 2, and timing duration positive")
    return args


def main() -> int:
    args = parse_args()
    output_path, run_id = prepare_output_path(args.output)
    compute_executable = args.build_dir / "aerosim_compute_benchmark"
    timing_executable = args.build_dir / "aerosim_timing"
    for executable in (compute_executable, timing_executable):
        if not executable.is_file():
            raise FileNotFoundError(f"benchmark executable not found: {executable}")

    compute_repetitions: list[dict[str, Any]] = []
    compiler_context: dict[str, str] | None = None
    final_state_reference: tuple[float, float, float] | None = None
    for _ in range(args.repetitions):
        result = json.loads(run_command([str(compute_executable), str(args.steps)]))
        context = {
            "compiler_id": result["compiler_id"],
            "compiler_version": result["compiler_version"],
            "build_configuration": result["build_configuration"] or "unspecified",
        }
        if compiler_context is None:
            compiler_context = context
        elif context != compiler_context:
            raise ValueError("compiler/build metadata changed between compute repetitions")

        state = (
            result["final_simulation_time_s"],
            result["final_position_x_m"],
            result["final_actuator_position"],
        )
        if final_state_reference is None:
            final_state_reference = state
        elif state != final_state_reference:
            raise ValueError("identical compute repetitions produced different final state")
        compute_repetitions.append(result)

    timing_repetitions = [
        parse_timing_output(run_command([
            str(timing_executable), str(args.timing_duration)
        ]))
        for _ in range(args.repetitions)
    ]

    compute_ns_per_step = [item["nanoseconds_per_step"] for item in compute_repetitions]
    compute_throughput = [item["steps_per_second"] for item in compute_repetitions]
    timing_summary_fields = {
        "step_execution_average_ms": "per_run_average_step_execution_ms",
        "scheduling_error_average_ms": "per_run_average_scheduling_error_ms",
        "scheduling_error_maximum_ms": "per_run_maximum_scheduling_error_ms",
        "late_step_starts": "late_step_starts_per_run",
        "full_period_late_steps": "full_period_late_steps_per_run",
        "simulation_steps": "steps_per_run",
    }
    cpu_model, cpu_model_source = collect_cpu_model()

    output = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            **(compiler_context or {}),
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "platform_description": platform.platform(),
            "machine_architecture": platform.machine(),
            "processor_reported_by_platform": platform.processor(),
            "cpu_model": cpu_model,
            "cpu_model_source": cpu_model_source,
            "logical_cpu_count_reported_by_python": os.cpu_count(),
            "python_version": platform.python_version(),
        },
        "method": {
            "deterministic_inputs": "Fresh default UAVSimulator, actuator command 0.8, no injected fault.",
            "percentile_definition": "p95 uses nearest rank: sorted value at rank ceil(0.95 * sample_count), one-based.",
            "compute_measurement": "Elapsed steady_clock time around simulator.step() loop only; a separate fixed 10,000-step warm-up, construction, and command setup are excluded.",
            "desktop_timing_measurement": "Repeated existing aerosim_timing runs; includes its sleeps and OS scheduling. This is reported separately from compute throughput.",
        },
        "compute_benchmark": {
            "steps_per_repetition": args.steps,
            "warmup_steps_per_repetition": compute_repetitions[0]["warmup_step_count"],
            "repetitions": args.repetitions,
            "simulation_time_per_repetition_s": compute_repetitions[0]["final_simulation_time_s"],
            "step_execution_ns_per_step": summarize(compute_ns_per_step),
            "simulation_throughput_steps_per_second": summarize(compute_throughput),
            "final_state_per_repetition": {
                "simulation_time_s": final_state_reference[0],
                "position_x_m": final_state_reference[1],
                "actuator_position": final_state_reference[2],
            },
            "raw_repetitions": compute_repetitions,
        },
        "desktop_timing_harness": {
            "requested_wall_duration_s_per_repetition": args.timing_duration,
            "target_period_ms": timing_repetitions[0]["target_period_ms"],
            "repetitions": args.repetitions,
            "summaries": {
                summary_name: summarize([item[field] for item in timing_repetitions])
                for field, summary_name in timing_summary_fields.items()
            },
            "raw_repetitions": timing_repetitions,
        },
    }

    try:
        with output_path.open("x", encoding="utf-8") as report_file:
            json.dump(output, report_file, indent=2, sort_keys=True)
            report_file.write("\n")
    except FileExistsError as error:
        raise FileExistsError(
            f"refusing to overwrite existing benchmark report; choose a new output path: {output_path}"
        ) from error
    except IsADirectoryError as error:
        raise IsADirectoryError(
            f"benchmark output path is a directory; provide a report filename: {output_path}"
        ) from error

    print(f"Wrote benchmark report: {output_path}")
    print(f"Compute mean: {output['compute_benchmark']['step_execution_ns_per_step']['mean']:.3f} ns/step")
    print(f"Compute mean throughput: {output['compute_benchmark']['simulation_throughput_steps_per_second']['mean']:.1f} steps/s")
    print(f"Timing harness mean step execution: {output['desktop_timing_harness']['summaries']['per_run_average_step_execution_ms']['mean']:.6f} ms")
    print(f"Timing harness mean absolute scheduling error: {output['desktop_timing_harness']['summaries']['per_run_average_scheduling_error_ms']['mean']:.6f} ms")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"Benchmark runner error: {error}", file=sys.stderr)
        raise SystemExit(1)
