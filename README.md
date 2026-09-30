# AeroSim-Core

A small C++17 fixed-step software simulation and telemetry-analysis project.
The current aircraft motion is a straight, constant-speed kinematic model; it
holds lateral position and altitude fixed. It is not validated aerodynamics,
flight-qualified software, or a validated digital twin.

## C++ build and tests

Requires CMake 3.16 or newer and a C++17 compiler (AppleClang/Clang or GCC).
The CMake targets enable `-Wall -Wextra -Wpedantic` for GCC and Clang-family
compilers. From the project root:

```bash
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
./build/aerosim
```

The simulator uses a deterministic 0.01-second step. It also has a simple
rate-limited software actuator and simulation-time stuck-actuator fault. Those
are software models, not hardware or flight-dynamics models.

## Generate telemetry and run Python analysis

Python 3.12 or newer is used for optional analysis and testing; the C++ build
does not require Python. Create the telemetry pair in a new
output directory (the C++ runner refuses to replace existing results):

```bash
./build/aerosim_experiments \
  --output-dir telemetry/my-run \
  --fault-time 0.75
```

The runner writes `experiment_complete.txt` after both CSVs close successfully.
A missing or incomplete marker means the experiment did not finish; see
[`TELEMETRY.md`](TELEMETRY.md) for the marker format and validation guidance.

Create the documented isolated Python environment, run its tests, and analyze
that pair:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements-lock.txt
python -m unittest discover -s python/tests -v
python python/anomaly_analysis.py \
  --nominal telemetry/my-run/nominal.csv \
  --fault telemetry/my-run/fault_injected.csv \
  --output-dir analysis_output/a-new-run \
  --seed 42 \
  --contamination 0.05 \
  --fault-time-s 0.75
```

For the deterministic synthetic robustness matrix, use a fresh output path:

```bash
python python/robustness_evaluation.py \
  --nominal telemetry/my-run/nominal.csv \
  --output-dir analysis_output/a-new-robustness-run \
  --seed 42 \
  --contamination 0.05 \
  --fault-times-s 0.25 0.75 1.25
```

See [`python/README.md`](python/README.md) for the feature and detector details.
Analysis and robustness results are experimental software outputs; synthetic
evaluation does not establish real-world robustness or UAV safety.

## Benchmarks

The benchmark runner separately measures no-sleep simulator stepping and the
desktop timing harness. Build and run it using the instructions in
[`TELEMETRY.md`](TELEMETRY.md). Benchmark results depend on build, machine load,
and OS scheduling; they are not hard real-time claims or cross-machine
comparisons. C++ benchmarks are deliberately not CI pass/fail gates.

## Continuous integration

GitHub Actions builds and runs CTest on Linux and macOS, and runs the Python
unit tests on Linux after generating their required telemetry input. Performance
measurements are not run as CI gates.
