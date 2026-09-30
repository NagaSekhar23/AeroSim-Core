# Build and test

AeroSim-Core requires CMake 3.16 or newer and a C++17 compiler. Python 3.12 or newer is needed only for analysis and Python tests. C++ uses no external libraries. Python dependencies are kept out of system Python in a virtual environment; see [Python setup](../python/README.md).

## C++ configure, build and CTest

From the repository root:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
```

The CMake warning helper applies `-Wall -Wextra -Wpedantic` to GCC, Clang, and AppleClang targets. It does not enable `-Werror`. The current CTest suite registers 20 tests across these groups:

- Initial state, fixed-step movement, held altitude/Y, and simulation time.
- Actuator bounds, rate limiting, command tracking, invalid finite/non-finite values, and fault activation/freezing.
- Deterministic timing-statistics thresholds. These tests use supplied samples; they do not assert operating-system timing.
- Telemetry schema/values, numeric validation, fault records, and output path behavior.
- Experiment output completion, including incomplete-output and existing-path cases.

Useful focused invocations:

```bash
ctest --test-dir build -R 'initial_state|forward_movement|fixed_altitude_and_y|simulation_time_step' --output-on-failure
ctest --test-dir build -R 'timing_statistics' --output-on-failure
ctest --test-dir build -R 'telemetry_|experiment_output_completion' --output-on-failure
```

CTest invokes the executable and provides a nonzero result if a registered test fails. It does not test flight behavior or guarantee a timing outcome on a desktop OS.

## Python unit tests and C++ parity

Create the environment and install the lock file once as described in the [Python guide](../python/README.md). Then, from the repository root:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target aerosim_experiments
AEROSIM_EXPERIMENTS=./build/aerosim_experiments \
  .venv/bin/python -m unittest discover -s python/tests -v
```

The parity tests need the actual compiled experiment-runner executable. The environment variable above makes its path explicit; the tests otherwise use their documented default. They compare matching C++ and Python telemetry, including header order, numeric state and actuator values, and simulation-time fault behavior within floating-point tolerances. The checks cover the matched experiment command schedule and zero-time activation case, not every synthetic robustness scenario.

The Python tests use temporary directories for their outputs. The experiment output CTest uses a build-tree test directory. Do not point tests at historical benchmark, telemetry, or analysis result directories.

## CI scope

`.github/workflows/ci.yml` has C++ configure/build/CTest jobs on Ubuntu and macOS, plus a Python 3.12 job that installs the locked dependencies, builds the experiment executable, creates fresh test telemetry, and runs Python `unittest`. The benchmark runner is intentionally excluded as a pass/fail gate. Inspection of workflow YAML is not the same as a successful GitHub Actions run; consult the repository's Actions page for the status of a particular commit. Even a passing workflow verifies software checks only, not model fidelity, flight readiness, or hard real-time behavior.
