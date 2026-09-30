# AeroSim telemetry anomaly analysis

This is an experimental Python pipeline for the CSV files produced by the C++
experiment runner. It uses Isolation Forest trained only on nominal telemetry.
The nominal run is split chronologically: the first 80% trains the detector,
and the final 20% estimates the nominal false-positive rate. The complete
fault-injected run is evaluated against `actuator_fault_active` as ground truth.

## Install into an isolated virtual environment

Python 3.12 or newer is required for the analysis environment. The C++ core
build has no Python package dependency. The benchmark orchestration script uses
only the Python standard library; the packages below are for telemetry analysis,
robustness evaluation, plotting, and their unit tests. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r python/requirements-lock.txt
```

The packages are installed in `.venv`; this does not install them into system
Python. The lock file pins the direct and transitive runtime packages; `pip`
itself is not pinned. `python/requirements.txt` contains bounded direct
dependency ranges for intentional updates. If package installation cannot
reach the package index, the analysis
cannot run until those dependencies are available in the virtual environment.

## Run from the repository root

Generate telemetry first if `telemetry/my-run/` does not already exist. The
experiment runner writes into a fresh directory and refuses to replace output
files:

```bash
cmake -S . -B build
cmake --build build --target aerosim_experiments
./build/aerosim_experiments \
  --output-dir telemetry/my-run \
  --fault-time 0.75
```

Then run the analysis from the repository root:

```bash
source .venv/bin/activate
python python/anomaly_analysis.py \
  --nominal telemetry/my-run/nominal.csv \
  --fault telemetry/my-run/fault_injected.csv \
  --output-dir analysis_output/my-run-review \
  --seed 42 \
  --contamination 0.05 \
  --fault-time-s 0.75
```

If the configured activation time is known, it can be supplied with
`--fault-time-s 0.75`. Otherwise, the pipeline infers it from the first active
fault record in the fault CSV. Use a fresh output directory each time; the
pipeline refuses to replace existing result files.

The output directory contains:

- `metrics.json`: confusion counts, precision, recall, F1, detection times and
  latency, nominal false-positive rate, feature list, and model settings.
- `fault_predictions.csv`: fault-run ground truth, predictions, scores, and
  actuator tracking features.
- `actuator_tracking.png`: nominal and fault-run commands and actual positions.
- `anomaly_scores.png`: fault-run anomaly scores/flags and activation time.
- `detector_flags.png`: Isolation Forest and rule-based detection flags together.

The model features are `actuator_command`, `actuator_position`, their
difference (`actuator_tracking_error`), and the one-step actuator position
change. The position-change feature helps represent a stuck actuator when its
command remains different from its actual position. It assumes the fixed
100 Hz simulation step. Simulation time and the fault flag are excluded from
model input. Default Isolation Forest settings are 200 trees,
`contamination=0.05`, `max_samples="auto"`, one worker, and `random_state=42`.
The seed and contamination can be overridden from the command line.

The report keeps Isolation Forest and a separate stuck-actuator rule distinct.
The rule uses a tracking error threshold derived from nominal training data
(nominal stationary error's 99th percentile plus three typical moving-step
increments, with a 0.05 position-unit minimum) and near-zero movement defined
as 1% of typical nominal per-step movement. It requires three consecutive
samples; at 100 Hz this is 0.03 seconds. It does not use fault labels to fit its
thresholds. On this dataset the row-wise Isolation Forest missed the fault
because its command/position/error combination occurs during a normal actuator
transient and it does not represent persistence as a sequence. The rule adds
that temporal persistence check. Its thresholds are a simple software baseline,
not flight-qualified limits.

Run the Python unit tests with:

```bash
source .venv/bin/activate
python -m unittest discover -s python/tests -v
```

The parity tests invoke `build/aerosim_experiments`; build that target first.
If it is in a different location, set `AEROSIM_EXPERIMENTS` to its executable
path for the test command. CI builds the target and sets this variable explicitly.

## Run the deterministic robustness matrix

From the repository root, use a fresh output directory:

```bash
source .venv/bin/activate
python python/robustness_evaluation.py \
  --nominal telemetry/my-run/nominal.csv \
  --output-dir analysis_output/robustness-evaluation-next \
  --seed 42 \
  --contamination 0.05 \
  --fault-times-s 0.25 0.75 1.25
```

The matrix includes a held-out nominal segment, a constant-command nominal
run, constant-command stuck faults at three simulation times, command changes
0.1 seconds after each of those faults, and a command change before a 0.75 s
fault. Generated cases use the current software model settings: 2 seconds at
100 Hz, initial actuator position 0, limits -1 to 1, rate limit 2 position
units/s, and initial command 0.8. The command changes to -0.4 in the scheduled
cases. The simulator updates the actuator, advances simulation time, and then
activates a configured fault at the first step at or beyond its time.

The Python generator remains in place so these deterministic scenario variants
do not change. A Python parity test runs the actual C++ experiment runner and
compares its matching default 0.5-second command-change nominal and 0.75-second
fault-injected telemetry against the Python equations, including field order,
state values, actuator tracking error, and fault activation/stuck behavior.
That parity check covers the runner's schedule; other robustness command
schedules are still generated in Python. Build `aerosim_experiments` before
running the Python test suite. The scenarios are software-model checks, not
aircraft flight-dynamics validation.

The Isolation Forest is fit once using only the first 80% of the nominal CSV.
Its inputs exclude time and the fault label. The rule thresholds are derived
from that same nominal training portion. Per-scenario results distinguish the
two detectors and include confusion counts, precision, recall, F1, false
positive rate, and detection latency. Metrics with zero denominators are JSON
`null` and include an explanation in `undefined_metrics`. Output files are
`metrics.json`, `per_scenario_metrics.csv`, and a CSV per scenario under
`predictions/`. Existing outputs are never replaced.

A fault that freezes an actuator exactly at its commanded position produces no
tracking error. With these telemetry signals, that case is not observable to
the current stuck-actuator rule; the matrix includes such a case so this limit
is visible. Synthetic results do not establish general robustness or real
flight readiness.

This small, synthetic software simulation is for experimentation only. It does
not model validated aircraft flight dynamics, and anomaly scores can produce
false positives, including during normal actuator transitions.
