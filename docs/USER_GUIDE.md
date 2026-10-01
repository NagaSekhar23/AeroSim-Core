# AeroSim-Core user and developer guide

This guide explains how to find and open AeroSim-Core, build and test it, generate telemetry, run the Python analysis, and continue work safely. It complements this repository's technical references; if commands or dependency details change, use the current [README](../README.md) and [Python guide](../python/README.md) as the source of truth.

AeroSim-Core is a software-only fixed-wing UAV simulation and telemetry-analysis demonstrator. It combines a deterministic, simplified C++17 kinematic simulation, a rate-limited actuator model, simulation-time stuck-actuator injection, CSV telemetry, desktop timing measurements, and Python anomaly analysis. It is not a validated aircraft aerodynamic model, flight-qualified software, a safety certification, or a hard real-time system.

The [Word version is available for download](AeroSim-Core_User_and_Developer_Guide.docx). The Markdown version is easiest to read directly on GitHub.

## 1. What the project does

- Advances a simple simulation at a fixed 100 Hz rate: each simulation step represents 0.01 seconds.
- Clamps actuator commands to configured limits and limits actuator movement rate.
- Can freeze the software actuator at its actual position when configured simulation time is reached.
- Writes CSV telemetry for nominal and fault-injected experiments.
- Analyzes telemetry with an Isolation Forest trained only on nominal data and a separate persistence-based rule detector.
- Uses CMake and CTest for C++ builds and tests, and Python unit tests for analysis tools. GitHub Actions runs C++ jobs on Ubuntu and macOS and Python tests on Ubuntu.

The model holds lateral position and altitude constant while moving forward at constant speed. It does not model realistic aerodynamic forces or validated flight dynamics. The desktop timing harness cannot guarantee deadlines under a general-purpose operating system.

## 2. Open the project

### Open the repository in a browser

Visit [github.com/NagaSekhar23/AeroSim-Core](https://github.com/NagaSekhar23/AeroSim-Core). Read `README.md` for the quick start, use `docs/` for architecture, testing, benchmarks, and this guide, and read [TELEMETRY.md](../TELEMETRY.md) for the CSV schema. The GitHub Actions page shows workflow results for specific commits; a green result applies to that run only.

### Download a ZIP

On the repository page, choose **Code → Download ZIP**, extract the archive to a known folder, and open it in your editor. A ZIP is convenient for reading, but does not provide the normal Git workflow for saving and pushing changes.

### Clone with Git

For development, clone the repository and enter it:

```bash
git clone https://github.com/NagaSekhar23/AeroSim-Core.git
cd AeroSim-Core
```

If Visual Studio Code's `code` command is available, open the folder with:

```bash
code .
```

Otherwise use the editor's **Open Folder** or **Open Project** command and select the directory containing `CMakeLists.txt`.

## 3. Prerequisites

- Git, to clone and update the repository.
- CMake 3.16 or newer.
- A C++17-capable compiler. On macOS, Apple Clang is provided by Xcode Command Line Tools; Linux needs a C++ toolchain.
- Python 3.12 or newer for analysis and Python tests.
- A terminal. A code editor is helpful but optional.

The C++ project has no third-party library dependency. Keep Python packages in the project's virtual environment rather than system Python. Follow official installation instructions for your operating system, and compile locally instead of copying build products from another computer.

## 4. Build and test the C++ project

Run these commands from the project root, the directory containing `CMakeLists.txt`:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

CMake configures targets, the compiler builds them, and CTest runs the registered C++ tests. Their number may change as the project evolves. To see available build targets:

```bash
cmake --build build --target help
```

If CMake cannot find a compiler, install your platform's C++ development tools and reopen the terminal. If the build directory has stale configuration after changing compiler or branch, it is generated output and can be removed before configuring again. Do not remove source files or project data as a troubleshooting step.

## 5. Run the simulator and timing tools

The active application entry point is `src/main.cpp`, built as `build/aerosim`. Root-level `main.cpp` and `main.cpp.backup` are not the active CMake entry point.

After building all C++ targets:

```bash
./build/aerosim
```

The desktop 100 Hz timing harness defaults to a 0.25-second wall-clock run; an optional argument sets its duration in seconds:

```bash
./build/aerosim_timing
./build/aerosim_timing 1.0
```

The no-sleep compute benchmark is a separate executable and accepts a positive step count:

```bash
./build/aerosim_compute_benchmark 1000000
```

These tools measure software execution and desktop scheduling. They do not establish hard real-time behavior. See [Benchmark methodology](BENCHMARKS.md) for repeated measurements and interpretation.

## 6. Generate telemetry

The experiment runner generates matched nominal and fault-injected runs. Each is two simulation seconds (200 steps) at 100 Hz. Both use the same initial state and command schedule; fault time is in simulation seconds.

```bash
cmake --build build --target aerosim_experiments
./build/aerosim_experiments \
  --output-dir telemetry/my-run \
  --fault-time 0.75
```

Choose a fresh output directory for each run. The runner refuses to overwrite existing output files. It writes `experiment_complete.txt` after both CSV files close successfully. A failed experiment may leave partial CSV data; do not treat it as complete without a valid marker and readable CSVs with the expected schema and row counts. Details are in [TELEMETRY.md](../TELEMETRY.md).

## 7. Set up Python analysis

Use a virtual environment so project packages remain separate from system Python. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r python/requirements-lock.txt
```

The lock file contains resolved Python package versions. `python/requirements.txt` contains bounded direct dependencies for intentional updates. See [python/README.md](../python/README.md) for dependency scope and detailed analysis instructions. If package installation cannot reach the package index, analysis cannot run until the dependencies are available locally.

Run Python tests after building the C++ experiment runner. The parity tests need its path:

```bash
cmake --build build --target aerosim_experiments
AEROSIM_EXPERIMENTS=./build/aerosim_experiments \
  .venv/bin/python -m unittest discover -s python/tests -v
```

## 8. Analyze telemetry and robustness scenarios

Generate a telemetry pair first if you do not already have a complete one. Then analyze it from the repository root, using a new output directory:

```bash
.venv/bin/python python/anomaly_analysis.py \
  --nominal telemetry/my-run/nominal.csv \
  --fault telemetry/my-run/fault_injected.csv \
  --output-dir analysis_output/my-run \
  --seed 42 \
  --contamination 0.05 \
  --fault-time-s 0.75
```

The Isolation Forest uses actuator command, actuator position, tracking error, and actuator position change. It is trained on nominal telemetry only; simulation time and the fault label are excluded from model features. A separate persistence-based rule detector is reported alongside it. The robustness evaluator can run a deterministic matrix of nominal and synthetic stuck-actuator cases:

```bash
.venv/bin/python python/robustness_evaluation.py \
  --nominal telemetry/my-run/nominal.csv \
  --output-dir analysis_output/robustness-evaluation-next \
  --seed 42 \
  --contamination 0.05 \
  --fault-times-s 0.25 0.75 1.25
```

Use a fresh output path; analysis tools preserve existing results and refuse to replace them. Some robustness scenarios are generated by Python equations. Parity tests compare matching default experiment scenarios and the time-zero fault case against the compiled C++ runner, but do not cross-check every generated command schedule. These synthetic tests do not establish broad detector robustness or flight readiness.

## 9. Resume work after a break

1. Open the repository on GitHub or open its local folder in your editor.
2. In a terminal at the repository root, inspect local changes before updating:

   ```bash
   git status
   git pull
   ```

   If there are local changes, review and preserve them before pulling; do not discard work just to make the command succeed.
3. Read `README.md` and inspect the latest commit and Actions result for that commit.
4. Configure, build, and test before changing code:

   ```bash
   cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
   cmake --build build --parallel
   ctest --test-dir build --output-on-failure
   ```
5. Activate `.venv` and use [python/README.md](../python/README.md) for Python tests and analysis.
6. Make one focused change at a time. Review the diff and test results before committing.
7. After pushing a commit, check the Actions result for that commit rather than assuming it passed.

## 10. Use Git safely

Before and after editing, inspect the repository:

```bash
git status
git diff
git diff --check
```

Stage only files related to the change. For example, if you changed only this guide and the root README:

```bash
git add docs/USER_GUIDE.md README.md
```

For source changes, stage the specific source and tests changed; avoid broad `git add` commands when unrelated files may be present. Then commit and push:

```bash
git commit -m "Describe the change clearly"
git push
```

Before committing, check that generated reports, build products, virtual environments, secrets, API keys, personal data, and unrelated files are not staged. Never commit passwords or access tokens. Inspect the staged diff yourself.

## 11. Troubleshooting

| Symptom | What to check |
| --- | --- |
| Repository page will not open | Check the URL, network connection, and GitHub availability. The intended URL is [github.com/NagaSekhar23/AeroSim-Core](https://github.com/NagaSekhar23/AeroSim-Core). |
| `cmake` or compiler is not found | Install CMake and your operating system's C++ development tools, then open a new terminal. |
| Build behaves unexpectedly after switching branches or toolchains | Remove only the generated `build/` directory and configure/build again. Confirm the directory before removing it. |
| Python imports fail | Activate `.venv` and install dependencies from `python/requirements-lock.txt` as documented in [python/README.md](../python/README.md). |
| Output file already exists | Select a fresh output directory or filename; do not overwrite experiment evidence. |
| Analysis reports missing telemetry | Run the documented telemetry workflow and verify file paths, CSV headers, row counts, and completion marker. |
| Git push is rejected | Run `git status`, inspect local changes, and fetch/pull carefully. Do not force-push as a first response. |
| GitHub Actions fails | Read the first meaningful job error, reproduce the corresponding build/test step locally, fix it, and push a new commit. |

## 12. Project limitations

A defensible description is “a simplified fixed-wing UAV kinematic simulation and telemetry-analysis demonstrator.” It is useful for discussing C++17, deterministic simulation steps, actuator behavior, fault injection, CSV telemetry, tests, desktop timing measurements, and Python anomaly detection.

Do not describe it as flight-certified software, a physically validated aerodynamic model, a complete digital twin of a real aircraft, or a hard real-time flight controller. The simulation holds Y, altitude, and forward speed constant; the actuator and stuck fault are simplified software models. Desktop timing does not guarantee deadlines, and anomaly results on synthetic data can include false positives and missed detections.

For a portfolio demonstration, show the repository, explain the system flow, run the tests, generate an example experiment, inspect its telemetry, and explain what the anomaly detector can and cannot establish.

## 13. Repository reference map

| Path | Purpose |
| --- | --- |
| [`README.md`](../README.md) | Project overview, quick start, and main workflows |
| [`TELEMETRY.md`](../TELEMETRY.md) | CSV schema and output/completion semantics |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System structure and component responsibilities |
| [`TESTING.md`](TESTING.md) | Build, test strategy, and test commands |
| [`BENCHMARKS.md`](BENCHMARKS.md) | Benchmark methodology and interpretation |
| [`python/README.md`](../python/README.md) | Python analysis workflow, dependencies, and model limitations |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | GitHub Actions configuration |
| [`CMakeLists.txt`](../CMakeLists.txt) | C++ targets, build settings, and registered tests |
| [`AeroSim-Core_User_and_Developer_Guide.docx`](AeroSim-Core_User_and_Developer_Guide.docx) | Downloadable Word version of this guide |

## 14. Keep this guide accurate

This guide is a practical overview. Exact executable names, CLI arguments, dependency files, and analysis commands can change; check the current root README and Python guide. When targets, scripts, telemetry fields, dependencies, or workflow steps change, update the relevant Markdown documentation and Word guide together. Rebuild the project, run CTest and Python tests, and review the intended files before committing.
