import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robustness_evaluation import (  # noqa: E402
    build_scenario_matrix,
    evaluate_robustness,
    generate_scenario,
    load_telemetry,
    summarize_scenario,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RobustnessEvaluationTests(unittest.TestCase):
    def test_python_scenarios_match_cpp_experiment_telemetry(self):
        configured_runner = os.environ.get("AEROSIM_EXPERIMENTS")
        runner = Path(configured_runner) if configured_runner else PROJECT_ROOT / "build/aerosim_experiments"
        runner = runner.resolve()
        self.assertTrue(
            runner.is_file(),
            f"C++ experiment runner not found at {runner}; build aerosim_experiments first",
        )

        fault_time_s = 0.75
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "cpp-run"
            completed = subprocess.run(
                [str(runner), "--output-dir", str(output_dir),
                 "--fault-time", str(fault_time_s)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"C++ experiment runner failed:\n{completed.stderr}",
            )

            marker = (output_dir / "experiment_complete.txt").read_text(encoding="utf-8")
            self.assertEqual(
                marker,
                "AeroSim-Core experiment complete\n"
                "nominal_rows=200\n"
                "fault_injected_rows=200\n"
                "fault_activation_time_s=0.75\n",
            )

            expected_columns = [
                "simulation_time_s", "position_x_m", "position_y_m", "altitude_m",
                "forward_speed_mps", "actuator_command", "actuator_position",
                "actuator_fault_active",
            ]
            expected_scenarios = {
                "nominal.csv": generate_scenario(
                    fault_time_s=None, change_command_time_s=0.5,
                ),
                "fault_injected.csv": generate_scenario(
                    fault_time_s=fault_time_s, change_command_time_s=0.5,
                ),
            }
            numeric_columns = [column for column in expected_columns
                               if column != "actuator_fault_active"]
            for filename, expected in expected_scenarios.items():
                path = output_dir / filename
                self.assertEqual(list(pd.read_csv(path, nrows=0).columns), expected_columns)
                actual = load_telemetry(path, filename)
                self.assertEqual(len(actual), 200)
                for column in numeric_columns:
                    np.testing.assert_allclose(
                        actual[column].to_numpy(dtype=float),
                        expected[column].to_numpy(dtype=float),
                        rtol=0.0,
                        atol=1e-12,
                        err_msg=f"{filename}: {column} differs from Python scenario",
                    )
                self.assertEqual(
                    actual["actuator_fault_active"].tolist(),
                    expected["actuator_fault_active"].tolist(),
                    f"{filename}: fault labels differ from Python scenario",
                )

                # Tracking error is a derived analysis feature, not a CSV column.
                cpp_tracking_error = actual["actuator_command"] - actual["actuator_position"]
                python_tracking_error = expected["actuator_command"] - expected["actuator_position"]
                np.testing.assert_allclose(
                    cpp_tracking_error.to_numpy(dtype=float),
                    python_tracking_error.to_numpy(dtype=float),
                    rtol=0.0,
                    atol=1e-12,
                    err_msg=f"{filename}: actuator tracking error differs",
                )

            # Telemetry records begin after the first update; the C++ initial
            # state itself is also checked by the initial_state CTest case.
            nominal = load_telemetry(output_dir / "nominal.csv", "Nominal")
            self.assertAlmostEqual(nominal.iloc[0]["simulation_time_s"], 0.01, delta=1e-12)
            self.assertAlmostEqual(nominal.iloc[0]["position_x_m"], 0.2, delta=1e-12)
            self.assertEqual(nominal.iloc[0]["position_y_m"], 0.0)
            self.assertEqual(nominal.iloc[0]["altitude_m"], 100.0)
            self.assertEqual(nominal.iloc[0]["forward_speed_mps"], 20.0)
            self.assertAlmostEqual(nominal.iloc[0]["actuator_position"], 0.02, delta=1e-12)

            fault = load_telemetry(output_dir / "fault_injected.csv", "Fault-injected")
            activation_rows = fault.index[fault["actuator_fault_active"]]
            self.assertGreater(len(activation_rows), 0)
            activation_index = activation_rows[0]
            self.assertGreaterEqual(
                fault.loc[activation_index, "simulation_time_s"], fault_time_s
            )
            self.assertFalse(fault.loc[activation_index - 1, "actuator_fault_active"])
            self.assertTrue(
                (fault.loc[activation_index:, "actuator_position"].diff().dropna().abs()
                 <= 1e-12).all()
            )

    def test_zero_time_fault_matches_cpp_immediate_activation(self):
        configured_runner = os.environ.get("AEROSIM_EXPERIMENTS")
        runner = Path(configured_runner) if configured_runner else PROJECT_ROOT / "build/aerosim_experiments"
        runner = runner.resolve()
        self.assertTrue(
            runner.is_file(),
            f"C++ experiment runner not found at {runner}; build aerosim_experiments first",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "cpp-zero-fault"
            completed = subprocess.run(
                [str(runner), "--output-dir", str(output_dir), "--fault-time", "0"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"C++ experiment runner failed:\n{completed.stderr}",
            )
            expected = generate_scenario(
                fault_time_s=0.0, change_command_time_s=0.5,
            )
            actual = load_telemetry(output_dir / "fault_injected.csv", "Fault-injected")
            self.assertEqual(actual["actuator_fault_active"].tolist(), [True] * 200)
            self.assertEqual(actual["actuator_position"].iloc[0], 0.0)
            for column in (
                "simulation_time_s", "position_x_m", "position_y_m", "altitude_m",
                "forward_speed_mps", "actuator_command", "actuator_position",
            ):
                np.testing.assert_allclose(
                    actual[column].to_numpy(dtype=float),
                    expected[column].to_numpy(dtype=float),
                    rtol=0.0,
                    atol=1e-12,
                    err_msg=f"zero-time fault: {column} differs from C++",
                )

    def test_scenario_generation_is_deterministic_and_sticks_at_fault_time(self):
        first = generate_scenario(fault_time_s=0.25, change_command_time_s=0.35)
        second = generate_scenario(fault_time_s=0.25, change_command_time_s=0.35)
        pd.testing.assert_frame_equal(first, second)

        activation_index = first.index[first["actuator_fault_active"]][0]
        self.assertAlmostEqual(first.loc[activation_index, "simulation_time_s"], 0.25)
        self.assertTrue((first.loc[activation_index:, "actuator_position"].diff().dropna() == 0).all())
        self.assertEqual(first.iloc[-1]["actuator_command"], -0.4)

    def test_scenario_matrix_has_nominal_constant_and_varied_fault_cases(self):
        scenarios = build_scenario_matrix((0.25, 0.75, 1.25))
        names = {scenario["scenario"] for scenario in scenarios}
        self.assertIn("nominal_holdout", names)
        self.assertIn("nominal_constant_command", names)
        self.assertIn("fault_constant_t0p25", names)
        self.assertIn("fault_postchange_t1p25", names)
        self.assertIn("fault_prechange_t0p75", names)
        nominal_constant = next(s for s in scenarios if s["scenario"] == "nominal_constant_command")
        self.assertFalse(nominal_constant["frame"]["actuator_fault_active"].any())
        self.assertTrue((nominal_constant["frame"]["actuator_command"] == 0.8).all())

    def test_metrics_mark_undefined_values_explicitly(self):
        no_fault = summarize_scenario(
            np.array([False, False, False]),
            np.array([False, False, False]),
            np.array([0.01, 0.02, 0.03]),
            None,
        )
        self.assertIsNone(no_fault["precision"])
        self.assertIsNone(no_fault["recall"])
        self.assertIsNone(no_fault["f1_score"])
        self.assertEqual(no_fault["false_positive_rate"], 0.0)
        self.assertIn("recall", no_fault["undefined_metrics"])
        self.assertIn("detection_latency_s", no_fault["undefined_metrics"])

        all_fault = summarize_scenario(
            np.array([True, True]), np.array([True, True]), np.array([0.01, 0.02]), 0.01
        )
        self.assertIsNone(all_fault["false_positive_rate"])
        self.assertIn("false_positive_rate", all_fault["undefined_metrics"])

    def test_evaluation_trains_from_nominal_and_writes_separate_results(self):
        nominal_path = PROJECT_ROOT / "telemetry/my-run/nominal.csv"
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "robustness"
            report = evaluate_robustness(nominal_path, output, seed=42)

            self.assertEqual(report["nominal_training_observations"], 160)
            self.assertEqual(report["nominal_training_fault_labels_active"], 0)
            self.assertEqual(len(report["scenarios"]), 9)
            self.assertIsNone(report["scenarios"]["nominal_constant_command"]
                              ["rule_based_stuck_actuator"]["recall"])
            self.assertTrue((output / "metrics.json").is_file())
            self.assertTrue((output / "per_scenario_metrics.csv").is_file())
            self.assertEqual(len(list((output / "predictions").glob("*.csv"))), 9)
            with self.assertRaises(FileExistsError):
                evaluate_robustness(nominal_path, output, seed=42)


if __name__ == "__main__":
    unittest.main()
