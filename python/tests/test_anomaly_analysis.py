import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anomaly_analysis import (  # noqa: E402
    FEATURE_COLUMNS,
    build_features,
    load_telemetry,
    run_analysis,
    summarize_detector,
)


REQUIRED_COLUMNS = [
    "simulation_time_s",
    "position_x_m",
    "position_y_m",
    "altitude_m",
    "forward_speed_mps",
    "actuator_command",
    "actuator_position",
    "actuator_fault_active",
]


def sample_frame(count: int, has_fault: bool) -> pd.DataFrame:
    times = [0.01 * index for index in range(1, count + 1)]
    commands = [0.8 if time < 0.1 else -0.4 for time in times]
    positions = [min(0.8, index * 0.02) for index in range(count)]
    labels = [has_fault and index >= count - 5 for index in range(count)]
    if has_fault:
        positions[-5:] = [positions[-6]] * 5
    return pd.DataFrame({
        "simulation_time_s": times,
        "position_x_m": [time * 20.0 for time in times],
        "position_y_m": [0.0] * count,
        "altitude_m": [100.0] * count,
        "forward_speed_mps": [20.0] * count,
        "actuator_command": commands,
        "actuator_position": positions,
        "actuator_fault_active": labels,
    })


class AnomalyAnalysisTests(unittest.TestCase):
    def test_schema_and_numeric_validation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "bad.csv"
            frame = sample_frame(4, False).drop(columns=["altitude_m"])
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "missing columns.*altitude_m"):
                load_telemetry(path, "test")

            frame = sample_frame(4, False)
            # pandas 3 rejects assigning a string into a numeric column. Make
            # the malformed test input object-typed so validation sees the CSV value.
            frame["actuator_position"] = frame["actuator_position"].astype(object)
            frame.loc[1, "actuator_position"] = "not-a-number"
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "non-numeric actuator_position"):
                load_telemetry(path, "test")

            frame = sample_frame(8, True)
            frame.to_csv(path, index=False)
            loaded = load_telemetry(path, "fault")
            self.assertTrue(pd.api.types.is_bool_dtype(loaded["actuator_fault_active"]))
            self.assertEqual(
                loaded["actuator_fault_active"].tolist(),
                [False, False, False, True, True, True, True, True],
            )

    def test_metric_classes_and_detection_latency(self):
        truth = pd.Series([False, False, True, True]).to_numpy()
        predicted = pd.Series([True, False, False, True]).to_numpy()
        metrics = summarize_detector(
            truth,
            predicted,
            pd.Series([0.01, 0.02, 0.03, 0.04]).to_numpy(),
            0.03,
            pd.Series([True, False]).to_numpy(),
        )
        self.assertEqual(
            (metrics["true_positives"], metrics["false_positives"],
             metrics["true_negatives"], metrics["false_negatives"]),
            (1, 1, 1, 1),
        )
        self.assertEqual(metrics["first_detected_anomaly_time_s"], 0.01)
        self.assertAlmostEqual(metrics["detection_latency_s"], 0.01)
        self.assertEqual(metrics["fault_run_false_positive_rate"], 0.5)
        self.assertEqual(metrics["nominal_false_positive_rate"], 0.5)

    def test_features_exclude_time_and_ground_truth(self):
        frame = sample_frame(3, False)
        features = build_features(frame)
        self.assertEqual(list(features.columns), FEATURE_COLUMNS)
        self.assertNotIn("simulation_time_s", features.columns)
        self.assertNotIn("actuator_fault_active", features.columns)
        self.assertAlmostEqual(
            features.loc[0, "actuator_tracking_error"],
            frame.loc[0, "actuator_command"] - frame.loc[0, "actuator_position"],
        )

    def test_pipeline_writes_reports_predictions_and_plots(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            nominal_path = root / "nominal.csv"
            fault_path = root / "fault.csv"
            output_path = root / "analysis"
            sample_frame(30, False).to_csv(nominal_path, index=False)
            sample_frame(30, True).to_csv(fault_path, index=False)

            metrics = run_analysis(nominal_path, fault_path, output_path, seed=7)

            self.assertEqual(metrics["evaluated_observations"], 30)
            self.assertEqual(metrics["nominal_training_observations"], 24)
            self.assertEqual(metrics["nominal_validation_observations"], 6)
            self.assertEqual(metrics["features"], FEATURE_COLUMNS)
            self.assertIn("isolation_forest", metrics["detectors"])
            self.assertIn("rule_based_stuck_actuator", metrics["detectors"])
            self.assertEqual(
                metrics["detectors"]["rule_based_stuck_actuator"]["false_positives"], 0
            )
            for filename in (
                "metrics.json",
                "fault_predictions.csv",
                "actuator_tracking.png",
                "anomaly_scores.png",
                "detector_flags.png",
            ):
                self.assertTrue((output_path / filename).is_file(), filename)

            with self.assertRaises(FileExistsError):
                run_analysis(nominal_path, fault_path, output_path, seed=7)


if __name__ == "__main__":
    unittest.main()
