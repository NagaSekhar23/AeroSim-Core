# Experiment CSV telemetry

The C++ experiment runner writes a matched nominal and fault-injected pair, each two simulation seconds long at a fixed 0.01-second step (200 rows per CSV). From the repository root:

```bash
cmake -S . -B build
cmake --build build --target aerosim_experiments
./build/aerosim_experiments --output-dir telemetry/my-run --fault-time 0.75
```

Both scenarios use the same initial conditions and command schedule: actuator command `0.8` initially, then `-0.4` from simulation time 0.5 seconds. The selected fault time is in simulation seconds. The only scenario difference is whether the stuck-actuator fault is enabled. The writer records one row after each step, so the first record is at 0.01 s; there is no initial-state row at time zero.

## Schema

The CSV header and column order are stable:

| Column | Meaning | Unit / values |
| --- | --- | --- |
| `simulation_time_s` | Elapsed simulation time | seconds |
| `position_x_m` | Forward position | metres |
| `position_y_m` | Sideways position | metres |
| `altitude_m` | Altitude coordinate initialized to 100 and held constant; vertical datum is unspecified | metres |
| `forward_speed_mps` | Constant forward speed in this model | metres per second |
| `actuator_command` | Clamped requested actuator position | configured actuator position units |
| `actuator_position` | Actual software actuator position | configured actuator position units |
| `actuator_fault_active` | Whether the stuck-actuator fault is active | `true` or `false` |

There are no wall-clock fields. Numeric serialization uses a fixed locale and sufficient precision for deterministic records with identical settings and inputs. Non-finite values are rejected by the public telemetry writer API.

## Safe creation and completion semantics

Output files are created exclusively; the writer does not truncate an existing file or follow an existing destination as an output to replace. Choose a new directory for each experiment. A failed run may leave partial CSV output; partial files are retained for inspection and are not automatically removed.

`experiment_complete.txt` is created only after both CSV writers close successfully. It records the completion status, expected row count for each run, and configured fault time. Consumers should treat the experiment as complete only when the marker exists and has the expected contents, and both CSVs parse with the documented header and row counts. No old results are deleted or replaced. The Python analysis commands accept CSV paths directly and do not enforce completion-marker validation themselves; verify the marker before analyzing outputs from a run that may have failed.

The CSV reflects a constant-speed straight-line kinematic model, a scalar rate-limited software actuator, and ideal stuck-position injection. It does not represent validated aircraft aerodynamics, hardware behavior, or flight-qualified telemetry. For C++/Python parity limits and consumer workflows, see the [Python guide](python/README.md); benchmark definitions are in [Benchmarks](docs/BENCHMARKS.md).
