# Benchmark methodology

AeroSim-Core has two distinct measurements: no-sleep simulator computation and a desktop wall-clock timing harness. Do not combine them into one “real-time performance” claim. Neither measurement demonstrates hard real-time behavior.

## Build and invoke

Use a Release build for optimized compute measurements. The Python runner uses only the standard library; analysis dependencies are not needed for the benchmark itself.

```bash
cmake -S . -B build-bench -DCMAKE_BUILD_TYPE=Release
cmake --build build-bench --target aerosim_compute_benchmark aerosim_timing
python3 python/run_benchmarks.py \
  --build-dir build-bench \
  --steps 1000000 \
  --repetitions 7 \
  --timing-duration 0.25
```

Arguments default to `build`, 1,000,000 steps, 7 repetitions, and a 0.25-second requested timing run. At least two repetitions are required. The default report path is unique under `benchmark_results/`; an explicitly supplied `--output PATH` is rejected if it already exists. Existing reports should be retained. Example for a chosen fresh path:

```bash
python3 python/run_benchmarks.py \
  --build-dir build-bench --steps 1000000 --repetitions 7 \
  --timing-duration 0.25 \
  --output benchmark_results/my-new-run.json
```

## No-sleep compute measurement

`aerosim_compute_benchmark` constructs a fresh default simulator, applies command `0.8`, then measures only a repeated `UAVSimulator::step()` loop with `std::chrono::steady_clock`. Each process first performs 10,000 warm-up steps on a separate simulator; construction, warm-up, command setup, process startup, and output are outside the measured loop. The final state is serialized so outputs remain observable and identical inputs can be checked across repetitions. The measured values are elapsed nanoseconds per step and steps per second. The model is so small that compiler, optimization, host load, and clock granularity can have substantial effects.

## Desktop timing harness

`aerosim_timing [DURATION_SECONDS]` defaults to 0.25 seconds. It targets a 10 ms period using `steady_clock`, `sleep_until`, and successive absolute deadlines. It reports simulator-call execution times separately from the absolute scheduling error.

- Absolute scheduling error: absolute step-start difference from that step's intended deadline; average and maximum in milliseconds.
- Late step starts: step starts strictly after their deadline.
- Full-period-late steps: step starts at least 10 ms after their intended deadline; each such step counts once, even if delayed by more than one period.
- Step execution time: duration of the simulator step call in milliseconds.

The harness's measured delays include desktop OS scheduling and sleep behavior. It is a measurement harness, not a hard real-time scheduler.

## Repetitions, summaries and metadata

The runner performs the requested number of independent executable invocations for each measurement. JSON retains raw per-run values and summarizes sample count, mean, median, minimum, maximum, and nearest-rank p95. Nearest rank uses the sorted observation at one-based rank `ceil(0.95 * N)`; for seven samples this is the maximum sample. The timing summary fields that represent averages are per-run averages before across-run summaries are calculated.

The report records compiler ID/version and build configuration from the C++ executable, operating system and release, platform string, architecture, Python-reported processor and logical CPU count, Python version, run parameters, and CPU model when the operating system probe provides one. Unavailable values are recorded as unavailable/null rather than guessed. These are reported metadata, not a complete controlled hardware environment description.

## Existing example report

`benchmark_results/phase6-audit.json` is an existing seven-repetition local report for one million steps per compute repetition and 0.25-second requested desktop timing repetitions. It reports AppleClang 21.0.0.21000334, Release, Darwin 27.0.0, arm64, Python 3.14.7, eight logical CPUs reported by Python, and no CPU model from the probe. Its compute summary reports mean 10.10367842857143 ns/step, median 9.816833, minimum 9.398917, maximum and nearest-rank p95 12.049125; mean throughput is 99,649,717.63858034 steps/s. The timing section reports a mean of per-run average step execution of 0.000292142857 ms, average scheduling error 1.840329142857 ms, maximum scheduling error 14.531541 ms, and one full-period-late step in one of seven runs.

These values describe that report only. The CPU model is unavailable, this is not a controlled comparison, and one run does not establish repeatability beyond its recorded repetitions. Do not compare it to results from a different machine or claim a performance improvement without equivalent repeated measurements. Historical reports are preserved; new reports should use new paths.
