#!/usr/bin/env python3
"""Train on nominal AeroSim telemetry and evaluate on a fault-injected run."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from output_safety import reserve_output_directory, write_completion_marker


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
NUMERIC_COLUMNS = [column for column in REQUIRED_COLUMNS if column != "actuator_fault_active"]
FEATURE_COLUMNS = [
    "actuator_command",
    "actuator_position",
    "actuator_tracking_error",
    "actuator_position_change",
]
RANDOM_SEED = 42
CONTAMINATION = 0.05
N_ESTIMATORS = 200
TRAINING_FRACTION = 0.80
RULE_PERSISTENCE_SAMPLES = 3
MIN_TRACKING_ERROR_THRESHOLD = 0.05


def load_telemetry(path: Path, run_name: str) -> pd.DataFrame:
    """Read a telemetry CSV and reject schema, missing, or invalid values."""
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(f"Could not read {run_name} telemetry at {path}: {exc}") from exc

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"{run_name} telemetry is missing columns: {', '.join(missing_columns)}")
    if frame.empty:
        raise ValueError(f"{run_name} telemetry contains no data rows")

    frame = frame[REQUIRED_COLUMNS].copy()
    for column in NUMERIC_COLUMNS:
        raw = frame[column]
        converted = pd.to_numeric(raw, errors="coerce")
        invalid = converted.isna() | ~np.isfinite(converted.to_numpy(dtype=float))
        if invalid.any():
            row_number = int(np.flatnonzero(invalid.to_numpy())[0]) + 2
            raise ValueError(
                f"{run_name} telemetry has missing or non-numeric {column} at CSV row {row_number}"
            )
        frame[column] = converted.astype(float)

    raw_labels = frame["actuator_fault_active"].astype("string").str.strip().str.lower()
    labels = raw_labels.map({"true": True, "false": False, "1": True, "0": False})
    if labels.isna().any():
        row_number = int(np.flatnonzero(labels.isna().to_numpy())[0]) + 2
        raise ValueError(
            f"{run_name} telemetry has a missing or invalid actuator_fault_active at CSV row {row_number}"
        )
    frame["actuator_fault_active"] = labels.astype(bool)

    times = frame["simulation_time_s"].to_numpy()
    if not np.isfinite(times).all() or (np.diff(times) <= 0.0).any():
        raise ValueError(f"{run_name} simulation_time_s must be finite and strictly increasing")
    return frame


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Build features without simulation time or the fault ground-truth label."""
    features = frame[["actuator_command", "actuator_position"]].copy()
    features["actuator_tracking_error"] = (
        features["actuator_command"] - features["actuator_position"]
    )
    # A stuck actuator stops changing position while its command can still differ.
    # This is a one-step difference, not an absolute simulation-time feature.
    changes = features["actuator_position"].diff()
    if len(changes) > 1:
        # The CSV starts after the first update, so approximate its missing
        # previous-sample delta from the next observed interval.
        changes.iloc[0] = changes.iloc[1]
    else:
        changes = changes.fillna(0.0)
    features["actuator_position_change"] = changes
    return features[FEATURE_COLUMNS]


def derive_stuck_rule_thresholds(nominal_training_features: pd.DataFrame) -> tuple[float, float]:
    """Derive tracking and near-zero-motion thresholds from nominal training data."""
    absolute_changes = nominal_training_features["actuator_position_change"].abs()
    moving_samples = absolute_changes[absolute_changes > 1e-12]
    if moving_samples.empty:
        raise ValueError("Nominal training data has no measurable actuator movement")

    typical_step_movement = float(moving_samples.median())
    no_motion_tolerance = max(1e-12, typical_step_movement * 0.01)
    stationary = absolute_changes <= no_motion_tolerance
    stationary_errors = nominal_training_features.loc[
        stationary, "actuator_tracking_error"
    ].abs()
    baseline_error = (
        float(stationary_errors.quantile(0.99)) if not stationary_errors.empty else 0.0
    )
    tracking_error_threshold = max(
        MIN_TRACKING_ERROR_THRESHOLD,
        baseline_error + 3.0 * typical_step_movement,
    )
    return tracking_error_threshold, no_motion_tolerance


def detect_stuck_actuator(
    features: pd.DataFrame,
    tracking_error_threshold: float,
    no_motion_tolerance: float,
    persistence_samples: int = RULE_PERSISTENCE_SAMPLES,
) -> np.ndarray:
    """Flag persistent command error while the actual actuator is nearly still."""
    candidate = (
        features["actuator_tracking_error"].abs().to_numpy() > tracking_error_threshold
    ) & (
        features["actuator_position_change"].abs().to_numpy() <= no_motion_tolerance
    )
    detections = np.zeros(len(candidate), dtype=bool)
    consecutive = 0
    for index, is_candidate in enumerate(candidate):
        consecutive = consecutive + 1 if is_candidate else 0
        detections[index] = consecutive >= persistence_samples
    return detections


def summarize_detector(
    ground_truth: np.ndarray,
    predictions: np.ndarray,
    times: np.ndarray,
    fault_time: float,
    nominal_predictions: np.ndarray,
) -> dict[str, Any]:
    tn, fp, fn, tp = confusion_matrix(
        ground_truth.astype(int), predictions.astype(int), labels=[0, 1]
    ).ravel()
    first_any_indices = np.flatnonzero(predictions)
    active_fault_detections = np.flatnonzero(
        predictions & ground_truth.astype(bool) & (times >= fault_time)
    )
    first_any = float(times[first_any_indices[0]]) if len(first_any_indices) else None
    first_after = (
        float(times[active_fault_detections[0]]) if len(active_fault_detections) else None
    )
    return {
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "precision": float(precision_score(ground_truth, predictions, zero_division=0)),
        "recall": float(recall_score(ground_truth, predictions, zero_division=0)),
        "f1_score": float(f1_score(ground_truth, predictions, zero_division=0)),
        "fault_run_false_positive_rate": (
            float(fp / (fp + tn)) if fp + tn else 0.0
        ),
        "first_detected_anomaly_time_s": first_any,
        "first_detected_anomaly_at_or_after_fault_time_s": first_after,
        "detection_latency_s": float(first_after - fault_time) if first_after is not None else None,
        "nominal_false_positives": int(nominal_predictions.sum()),
        "nominal_validation_observations": int(len(nominal_predictions)),
        "nominal_false_positive_rate": (
            float(nominal_predictions.mean()) if len(nominal_predictions) else 0.0
        ),
    }


def validate_matched_runs(nominal: pd.DataFrame, fault: pd.DataFrame) -> None:
    if nominal["actuator_fault_active"].any():
        raise ValueError("Nominal telemetry must not contain active actuator fault labels")
    if not fault["actuator_fault_active"].any():
        raise ValueError("Fault-injected telemetry has no active fault records")
    if len(nominal) != len(fault) or not np.allclose(
        nominal["simulation_time_s"].to_numpy(),
        fault["simulation_time_s"].to_numpy(),
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("Nominal and fault-injected telemetry must use the same simulation time grid")

    active = fault["actuator_fault_active"].to_numpy(dtype=bool)
    first_active = int(np.flatnonzero(active)[0])
    if active[first_active:].sum() != len(active) - first_active:
        raise ValueError("Fault-injected telemetry must keep the fault active after activation")

    shared_columns = [
        "position_x_m",
        "position_y_m",
        "altitude_m",
        "forward_speed_mps",
        "actuator_command",
    ]
    for column in shared_columns:
        if not np.allclose(
            nominal[column].to_numpy(dtype=float),
            fault[column].to_numpy(dtype=float),
            rtol=0.0,
            atol=1e-12,
        ):
            raise ValueError(
                f"Nominal and fault-injected telemetry must have matching {column} values"
            )
    if not np.allclose(
        nominal["actuator_position"].to_numpy(dtype=float)[: first_active + 1],
        fault["actuator_position"].to_numpy(dtype=float)[: first_active + 1],
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError(
            "Nominal and fault-injected telemetry must have matching actuator positions "
            "through fault activation"
        )


def make_plots(
    nominal: pd.DataFrame,
    fault: pd.DataFrame,
    fault_predictions: pd.DataFrame,
    fault_time: float,
    output_dir: Path,
) -> None:
    fig, axis = plt.subplots(figsize=(10, 5))
    axis.plot(nominal["simulation_time_s"], nominal["actuator_command"],
              label="Nominal command", color="tab:blue", alpha=0.7)
    axis.plot(nominal["simulation_time_s"], nominal["actuator_position"],
              label="Nominal actual position", color="tab:blue", linestyle="--")
    axis.plot(fault["simulation_time_s"], fault["actuator_command"],
              label="Fault run command", color="tab:orange", alpha=0.7)
    axis.plot(fault["simulation_time_s"], fault["actuator_position"],
              label="Fault run actual position", color="tab:red", linestyle="--")
    axis.axvline(fault_time, color="black", linestyle=":", label="Fault activation")
    axis.set(title="Actuator command and actual position", xlabel="Simulation time (s)",
             ylabel="Actuator position (configured units)")
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "actuator_tracking.png", dpi=150)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(10, 5))
    scores = fault_predictions["isolation_forest_anomaly_score"].to_numpy()
    times = fault_predictions["simulation_time_s"].to_numpy()
    flags = fault_predictions["isolation_forest_predicted_anomaly"].to_numpy(dtype=bool)
    axis.plot(times, scores, color="tab:blue", label="Isolation Forest score (higher = stranger)")
    if flags.any():
        axis.scatter(times[flags], scores[flags], color="tab:red", marker="x",
                     label="Isolation Forest anomaly", zorder=3)
    axis.axhline(0.0, color="gray", linestyle="--", label="Isolation Forest threshold")
    axis.axvline(fault_time, color="black", linestyle=":", label="Fault activation")
    axis.set(title="Fault-run anomaly scores", xlabel="Simulation time (s)",
             ylabel="Negative decision function")
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "anomaly_scores.png", dpi=150)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(10, 4))
    axis.step(times, fault_predictions["isolation_forest_predicted_anomaly"].astype(int),
              where="post", label="Isolation Forest", color="tab:blue")
    axis.step(times, fault_predictions["rule_based_predicted_anomaly"].astype(int),
              where="post", label="Tracking-error persistence rule", color="tab:orange")
    axis.axvline(fault_time, color="black", linestyle=":", label="Fault activation")
    axis.set(title="Detector flags", xlabel="Simulation time (s)",
             ylabel="Anomaly flag (0 = no, 1 = yes)", ylim=(-0.1, 1.1))
    axis.set_yticks([0, 1])
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "detector_flags.png", dpi=150)
    plt.close(fig)


def run_analysis(
    nominal_path: Path,
    fault_path: Path,
    output_dir: Path,
    seed: int = RANDOM_SEED,
    contamination: float = CONTAMINATION,
    fault_time_override: float | None = None,
) -> dict[str, Any]:
    if not 0.0 < contamination < 0.5:
        raise ValueError("contamination must be greater than 0 and less than 0.5")

    nominal = load_telemetry(nominal_path, "Nominal")
    fault = load_telemetry(fault_path, "Fault-injected")
    validate_matched_runs(nominal, fault)

    fault_active_times = fault.loc[fault["actuator_fault_active"], "simulation_time_s"]
    observed_fault_time = float(fault_active_times.iloc[0])
    fault_time = observed_fault_time if fault_time_override is None else fault_time_override
    if not math.isfinite(fault_time) or fault_time < 0.0:
        raise ValueError("fault activation time must be finite and non-negative")
    fault_times = fault["simulation_time_s"].to_numpy(dtype=float)
    expected_activation_index = int(np.searchsorted(fault_times, fault_time, side="left"))
    actual_activation_index = int(
        np.flatnonzero(fault["actuator_fault_active"].to_numpy(dtype=bool))[0]
    )
    if (
        expected_activation_index >= len(fault_times)
        or expected_activation_index != actual_activation_index
    ):
        raise ValueError(
            "Configured fault activation time is inconsistent with the fault telemetry labels"
        )

    split_at = int(len(nominal) * TRAINING_FRACTION)
    if split_at < 2 or split_at >= len(nominal):
        raise ValueError("Nominal telemetry needs at least three rows for training and validation")

    nominal_train = nominal.iloc[:split_at]
    nominal_validation = nominal.iloc[split_at:]
    train_features = build_features(nominal_train)
    validation_features = build_features(nominal_validation)
    fault_features = build_features(fault)

    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=contamination,
        max_samples="auto",
        random_state=seed,
        n_jobs=1,
    )
    model.fit(train_features)

    validation_predictions = model.predict(validation_features) == -1
    fault_model_predictions = model.predict(fault_features) == -1
    fault_scores = -model.decision_function(fault_features)

    tracking_error_threshold, no_motion_tolerance = derive_stuck_rule_thresholds(train_features)
    rule_nominal_predictions = detect_stuck_actuator(
        validation_features, tracking_error_threshold, no_motion_tolerance
    )
    rule_fault_predictions = detect_stuck_actuator(
        fault_features, tracking_error_threshold, no_motion_tolerance
    )

    ground_truth = fault["actuator_fault_active"].to_numpy(dtype=bool)
    fault_times = fault["simulation_time_s"].to_numpy()
    model_metrics = summarize_detector(
        ground_truth, fault_model_predictions, fault_times, fault_time, validation_predictions
    )
    rule_metrics = summarize_detector(
        ground_truth, rule_fault_predictions, fault_times, fault_time, rule_nominal_predictions
    )

    predictions = pd.DataFrame({
        "simulation_time_s": fault["simulation_time_s"],
        "actuator_command": fault["actuator_command"],
        "actuator_position": fault["actuator_position"],
        "actuator_tracking_error": fault_features["actuator_tracking_error"],
        "actuator_position_change": fault_features["actuator_position_change"],
        "actuator_fault_active": ground_truth,
        "isolation_forest_anomaly_score": fault_scores,
        "isolation_forest_predicted_anomaly": fault_model_predictions,
        "rule_based_predicted_anomaly": rule_fault_predictions,
    })

    metrics: dict[str, Any] = {
        "evaluated_observations": int(len(fault)),
        "configured_fault_activation_time_s": float(fault_time),
        "first_fault_active_telemetry_time_s": observed_fault_time,
        "fault_time_source": "command_line_override" if fault_time_override is not None
                             else "first_active_fault_record_in_csv",
        "nominal_training_observations": int(len(nominal_train)),
        "nominal_validation_observations": int(len(nominal_validation)),
        "features": FEATURE_COLUMNS,
        "excluded_model_columns": ["simulation_time_s", "actuator_fault_active"],
        "isolation_forest": {
            "n_estimators": N_ESTIMATORS,
            "contamination": contamination,
            "max_samples": "auto",
            "random_state": seed,
            "n_jobs": 1,
            "training_split": "first 80% of nominal rows in time order",
        },
        "rule_based_stuck_actuator": {
            "tracking_error_threshold": tracking_error_threshold,
            "no_motion_tolerance": no_motion_tolerance,
            "persistence_samples": RULE_PERSISTENCE_SAMPLES,
            "persistence_duration_s": RULE_PERSISTENCE_SAMPLES * 0.01,
            "threshold_method": (
                "max(0.05, 99th percentile of nominal stationary tracking error "
                "+ 3 times median nominal moving-step position change)"
            ),
        },
        "detectors": {
            "isolation_forest": model_metrics,
            "rule_based_stuck_actuator": rule_metrics,
        },
        "software_versions": {
            "python": __import__("platform").python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "limitations": [
            "This is an experimental software simulation, not validated flight dynamics.",
            "The dataset is small and synthetic; scores and rates may change on new runs.",
            "The nominal false-positive rate uses a chronological holdout from one nominal run.",
            "Position change is a one-step difference and assumes the fixed simulation sample interval.",
            "Isolation Forest can flag normal actuator transients as anomalies.",
        ],
    }

    reserve_output_directory(output_dir, "analysis")

    predictions.to_csv(output_dir / "fault_predictions.csv", index=False)
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as report:
        json.dump(metrics, report, indent=2, allow_nan=False)
        report.write("\n")
    make_plots(nominal, fault, predictions, fault_time, output_dir)
    write_completion_marker(
        output_dir, "analysis_complete.txt", "AeroSim-Core analysis complete\n"
    )
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nominal", type=Path, default=Path("telemetry/my-run/nominal.csv"))
    parser.add_argument("--fault", type=Path, default=Path("telemetry/my-run/fault_injected.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("analysis_output/my-run"))
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--contamination", type=float, default=CONTAMINATION)
    parser.add_argument(
        "--fault-time-s", type=float, default=None,
        help="Configured activation time in seconds; defaults to first active CSV record",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        metrics = run_analysis(
            args.nominal,
            args.fault,
            args.output_dir,
            seed=args.seed,
            contamination=args.contamination,
            fault_time_override=args.fault_time_s,
        )
    except (ValueError, OSError, FileExistsError) as exc:
        print(f"Analysis error: {exc}", file=__import__("sys").stderr)
        return 1

    print(json.dumps(metrics, indent=2))
    print(f"Saved analysis outputs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
