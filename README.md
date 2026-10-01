# AeroSim-Core

AeroSim-Core is a small C++17 software-simulation project for exploring fixed-step simulation, actuator behavior, telemetry, timing measurements, and a Python anomaly-analysis workflow. It is designed to be easy to build and inspect on a desktop machine.

> **Scope:** the aircraft motion is a deterministic, straight-line constant-speed kinematic model. It holds lateral position and altitude constant. It is not validated aircraft aerodynamics, a flight-qualified digital twin, or evidence of UAV operational safety. The timing harness measures desktop scheduling and does not provide hard real-time guarantees.

[![CI](https://github.com/NagaSekhar23/AeroSim-Core/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/NagaSekhar23/AeroSim-Core/actions/workflows/ci.yml)

## What it demonstrates

- A reusable C++ core library and a CMake-built command-line simulator.
- A deterministic 100 Hz (`0.01 s`) update step and a rate-limited software actuator with simulation-time stuck-actuator fault injection.
- CSV telemetry with exclusive file creation and an experiment completion marker.
- CTest coverage for simulation, actuator validation and faults, timing statistics, telemetry, and experiment output completion.
- A Python Isolation Forest analysis and a separate persistence-based stuck-actuator rule, plus synthetic robustness scenarios and C++/Python parity checks.
- Separate computation and desktop timing benchmark programs. Benchmarks are measurement tools, not CI pass/fail gates.

## Build and run C++

Requirements: CMake 3.16 or newer and a C++17 compiler (AppleClang/Clang or GCC). No third-party C++ libraries are needed.

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
./build/aerosim
```

Generate a matched nominal and fault-injected telemetry experiment. Use a new output directory for each run; existing files are not overwritten.

```bash
./build/aerosim_experiments \
  --output-dir telemetry/my-run \
  --fault-time 0.75
```

The experiment runs for two simulation seconds (200 steps) per scenario. Its completion marker is written only after both CSV files close successfully. See [the telemetry guide](TELEMETRY.md) for the schema and how to interpret incomplete output.

## Python analysis

Python 3.12 or newer is used for analysis and its tests; it is optional for building the C++ simulator. From the repository root, create an isolated environment and install the locked packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements-lock.txt
```

Run tests, then analyze a telemetry pair:

```bash
python -m unittest discover -s python/tests -v
python python/anomaly_analysis.py \
  --nominal telemetry/my-run/nominal.csv \
  --fault telemetry/my-run/fault_injected.csv \
  --output-dir analysis_output/my-run \
  --seed 42 \
  --contamination 0.05 \
  --fault-time-s 0.75
```

The Isolation Forest is fit on nominal observations only. Fault labels are evaluation ground truth, not detector inputs. A separate rule-based detector is reported alongside the model. The scenario generator also contains Python equations; parity tests compare matching scenarios against the compiled C++ experiment runner. Other generated robustness scenarios are Python-generated and are not all cross-language checked. Analysis on small synthetic data can produce false alarms or missed detections and does not establish real-world robustness. See the [Python guide](python/README.md).

## Project layout

```text
include/                 Public C++ state, simulator, actuator, telemetry, timing headers
src/                     Simulator, actuator, timing, telemetry, experiment and test sources
cmake/                   CMake-driven experiment-output regression test
python/                  Analysis, robustness, benchmark runner, lock files and unit tests
docs/                    Architecture, testing and benchmark guides
.github/workflows/ci.yml C++ and Python continuous-integration jobs
TELEMETRY.md             CSV schema and output-completion semantics
```

For design responsibilities, test commands and measured-performance methodology, see [Architecture](docs/ARCHITECTURE.md), [Testing](docs/TESTING.md), [Benchmarks](docs/BENCHMARKS.md), and [Telemetry](TELEMETRY.md).

## User guide

The [Markdown user guide](docs/USER_GUIDE.md) is the easiest version to read directly on GitHub. The [Word user and developer guide](docs/AeroSim-Core_User_and_Developer_Guide.docx) is also available to download.

## Continuous integration

The GitHub Actions workflow builds and runs CTest on Ubuntu and macOS. Its Python job uses Python 3.12, installs `python/requirements-lock.txt` in a virtual environment, builds the C++ experiment runner, generates fresh test telemetry, and runs the Python unit tests. Benchmark measurements are not CI gates. A workflow result verifies only the checks in that run; it does not validate flight dynamics or real-time behavior.
