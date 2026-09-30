# Experiment CSV telemetry

Build the experiment runner and tests with CMake, then run the full test suite:

```bash
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

Generate a matched nominal and fault-injected experiment pair:

```bash
./build/aerosim_experiments --output-dir telemetry/my-run --fault-time 0.75
```

The runner simulates two seconds at a fixed 0.01-second step and writes
`nominal.csv` and `fault_injected.csv` into the selected output directory. Both
runs use identical initial conditions and actuator commands; only fault
injection differs. The shared command is `0.8` initially and changes to `-0.4`
at simulation time 0.5 seconds. The fault time is configurable from 0 through
2 simulation seconds. The writer refuses to replace existing CSV files, so use
a fresh output directory for each run.

The runner also writes `experiment_complete.txt` only after both CSV files have
been written and closed successfully. A complete marker contains the exact
status line, expected 200-row count for each CSV, and configured fault time.
Consumers should treat a run as complete only when the marker is present and
its contents match that format and the CSV files are readable with the expected
headers and row counts. If the runner fails after writing one CSV, that partial
CSV is intentionally retained and no valid completion marker is published.
Existing CSVs and completion markers are never replaced; choose a new output
directory for each experiment.

Each CSV contains one header and 200 data rows, one for each simulation step.
The schema is:

| Column | Meaning | Unit / values |
| --- | --- | --- |
| `simulation_time_s` | Elapsed simulator time | seconds |
| `position_x_m` | Forward position | metres |
| `position_y_m` | Sideways position | metres |
| `altitude_m` | Altitude coordinate; datum is unspecified. Initialized to 100 m and held constant by the current model. | metres |
| `forward_speed_mps` | Forward speed | metres per second |
| `actuator_command` | Clamped requested actuator position | configured position units |
| `actuator_position` | Actual software actuator position | configured position units |
| `actuator_fault_active` | Whether the stuck-actuator fault is active | `true` or `false` |

The CSV contains no wall-clock measurements. Numeric output uses a fixed locale
and sufficient precision for repeatable records when inputs and settings match.
Output files are created exclusively, so an existing file or symbolic-link
destination cannot be truncated by a check-then-open race.

The UAV movement model remains a simplified constant-speed kinematic model.
It holds Y and altitude fixed and does not represent validated aircraft flight
dynamics or realistic aerodynamic forces. The software actuator is also a
simple rate-limited position model.

## Desktop timing harness

Build the timing executable with CMake, then run it with the default 0.25-second
wall-clock duration or provide a positive duration in seconds:

```bash
./build/aerosim_timing
./build/aerosim_timing 1.0
```

The harness targets the simulator's fixed 10 ms (100 Hz) period. It uses
`std::chrono::steady_clock` and successive absolute deadlines based on the
previous intended deadline. Simulation time remains the number of simulator
steps multiplied by the fixed simulation step; it is separate from wall-clock
time.

Timing output definitions:

- **Absolute scheduling error** is the absolute difference between a step's
  wall-clock start and its intended deadline. Average and maximum values are
  reported in milliseconds over all steps.
- **Late step starts** counts each step whose start is strictly after its
  intended deadline, regardless of how small the delay is.
- **Full-period-late steps** counts each step whose start is at least one full
  simulation period (10 ms) after its intended deadline. A step more than one
  period late still contributes one to this per-step count; this is not a count
  of every elapsed deadline.
- Execution-time average, minimum, and maximum measure the simulator step call
  and are reported in milliseconds.

This is a desktop scheduling measurement. Operating-system scheduling and
`sleep_until` do not provide hard real-time guarantees.

## Reproducible C++ benchmarks

The compute benchmark repeatedly calls `UAVSimulator::step()` without sleeping.
The Python standard-library runner repeats that executable and, separately,
repeats the desktop timing harness. Thus compute throughput and scheduling delay
are reported as different measurements. Each compute repetition starts a fresh
simulator with the default initial state, actuator command `0.8`, and no fault;
each process also runs 10,000 fixed warm-up steps on a separate simulator before
measurement. Construction, warm-up, command setup, process startup, and result
printing are excluded from compute-loop timing. The timing-harness repetitions
include its waits and desktop scheduler delays.

Build an optimized benchmark configuration and run seven repetitions of one
million compute steps plus seven 0.25-second desktop timing runs:

```bash
cmake -S . -B build-bench -DCMAKE_BUILD_TYPE=Release
cmake --build build-bench --target aerosim_compute_benchmark aerosim_timing
python3 python/run_benchmarks.py \
  --build-dir build-bench \
  --steps 1000000 \
  --repetitions 7 \
  --timing-duration 0.25
```

Without `--output`, the runner creates a unique timestamped report path. If an
explicit output path is supplied, it refuses to overwrite it. Reports contain
raw repetition values, mean, median,
minimum, maximum, and nearest-rank 95th percentile (the value at one-based rank
`ceil(0.95 * N)`), along with compiler ID/version, CMake build configuration,
operating-system/platform strings, architecture, Python version, step count,
duration, and repetition count. CPU model is collected from the OS when
available; otherwise the report records it as unavailable. The processor field
is whatever Python's `platform.processor()` reports and may be generic; the
runner does not guess a CPU model.
Compute per-step time is elapsed nanoseconds divided by measured steps, and
throughput is measured steps per elapsed second. The desktop harness summaries
retain its step execution and scheduling metrics, including late-start and
full-period-late counts.

The JSON reports are separate from telemetry and analysis results. Benchmark
numbers depend on compiler, build configuration, machine load, and OS scheduling;
compare runs only under equivalent conditions. They do not establish hard
real-time behavior or performance relative to another machine.
