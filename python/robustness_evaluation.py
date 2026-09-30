#!/usr/bin/env python3
"""Deterministic synthetic robustness checks for the AeroSim actuator detectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from anomaly_analysis import (
    CONTAMINATION,
    FEATURE_COLUMNS,
    N_ESTIMATORS,
    RANDOM_SEED,
    TRAINING_FRACTION,
    build_features,
    detect_stuck_actuator,
    derive_stuck_rule_thresholds,
    load_telemetry,
)


TIME_STEP_S = 0.01
RUN_DURATION_S = 2.0
INITIAL_COMMAND = 0.8
CHANGED_COMMAND = -0.4
ACTUATOR_MINIMUM = -1.0
ACTUATOR_MAXIMUM = 1.0
ACTUATOR_RATE_LIMIT_PER_S = 2.0
DEFAULT_FAULT_TIMES_S = (0.25, 0.75, 1.25)
RULE_PERSISTENCE_SAMPLES = 3


def generate_scenario(
    *,
    fault_time_s: float | None,
    change_command_time_s: float | None,
) -> pd.DataFrame:
    """Reproduce the current C++ fixed-step kinematics and actuator update order."""
    steps = int(round(RUN_DURATION_S / TIME_STEP_S))
    time_s = 0.0
    x_m = 0.0
    y_m = 0.0
    altitude_m = 100.0
    speed_mps = 20.0
    command = INITIAL_COMMAND
    position = 0.0
    # The C++ simulator activates a configured fault immediately when its
    # activation time is at or before the current simulation time (initially 0).
    fault_active = fault_time_s is not None and fault_time_s <= time_s
    rows: list[dict[str, Any]] = []

    for _ in range(steps):
        if change_command_time_s is not None and time_s >= change_command_time_s:
            command = CHANGED_COMMAND

        if not fault_active:
            maximum_change = ACTUATOR_RATE_LIMIT_PER_S * TIME_STEP_S
            position_error = command - position
            limited_change = float(np.clip(position_error, -maximum_change, maximum_change))
            position = float(np.clip(
                position + limited_change, ACTUATOR_MINIMUM, ACTUATOR_MAXIMUM
            ))

        x_m += speed_mps * TIME_STEP_S
        time_s += TIME_STEP_S
        if fault_time_s is not None and not fault_active and time_s >= fault_time_s:
            fault_active = True

        rows.append({
            "simulation_time_s": time_s,
            "position_x_m": x_m,
            "position_y_m": y_m,
            "altitude_m": altitude_m,
            "forward_speed_mps": speed_mps,
            "actuator_command": command,
            "actuator_position": position,
            "actuator_fault_active": fault_active,
        })

    return pd.DataFrame(rows)


def build_scenario_matrix(fault_times_s: tuple[float, ...]) -> list[dict[str, Any]]:
    if len(set(fault_times_s)) != len(fault_times_s):
        raise ValueError("fault activation times must not contain duplicates")
    scenarios: list[dict[str, Any]] = [
        {
            "scenario": "nominal_holdout",
            "kind": "nominal_only",
            "source": "last 20% of supplied nominal CSV",
        },
        {
            "scenario": "nominal_constant_command",
            "kind": "nominal_only",
            "command_schedule": "constant at 0.8 actuator units",
            "frame": generate_scenario(
                fault_time_s=None, change_command_time_s=None,
            ),
        },
    ]
    for fault_time in fault_times_s:
        if not 0.0 < fault_time < RUN_DURATION_S:
            raise ValueError(
                f"fault activation times must be between 0 and {RUN_DURATION_S} seconds"
            )
        stamp = f"{fault_time:.2f}".replace(".", "p")
        scenarios.append({
            "scenario": f"fault_constant_t{stamp}",
            "kind": "fault_injected",
            "fault_time_s": fault_time,
            "command_schedule": "constant at 0.8 actuator units",
            "frame": generate_scenario(
                fault_time_s=fault_time, change_command_time_s=None,
            ),
        })
        scenarios.append({
            "scenario": f"fault_postchange_t{stamp}",
            "kind": "fault_injected",
            "fault_time_s": fault_time,
            "command_change_time_s": fault_time + 0.1,
            "command_schedule": "command changes from 0.8 to -0.4 at fault time + 0.1 s",
            "frame": generate_scenario(
                fault_time_s=fault_time, change_command_time_s=fault_time + 0.1,
            ),
        })

    scenarios.append({
        "scenario": "fault_prechange_t0p75",
        "kind": "fault_injected",
        "fault_time_s": 0.75,
        "command_change_time_s": 0.5,
        "command_schedule": "command changes from 0.8 to -0.4 at 0.5 s before the fault",
        "frame": generate_scenario(
            fault_time_s=0.75, change_command_time_s=0.5,
        ),
    })
    return scenarios


def summarize_scenario(
    ground_truth: np.ndarray,
    predictions: np.ndarray,
    times_s: np.ndarray,
    fault_time_s: float | None,
) -> dict[str, Any]:
    positive = ground_truth.astype(bool)
    predicted = predictions.astype(bool)
    tp = int(np.count_nonzero(positive & predicted))
    fp = int(np.count_nonzero(~positive & predicted))
    tn = int(np.count_nonzero(~positive & ~predicted))
    fn = int(np.count_nonzero(positive & ~predicted))

    precision_denominator = tp + fp
    recall_denominator = tp + fn
    f1_denominator = 2 * tp + fp + fn
    fpr_denominator = fp + tn
    precision = tp / precision_denominator if precision_denominator else None
    recall = tp / recall_denominator if recall_denominator else None
    f1 = 2 * tp / f1_denominator if f1_denominator else None
    fpr = fp / fpr_denominator if fpr_denominator else None

    first_any = np.flatnonzero(predicted)
    actual_fault_detection = np.flatnonzero(
        predicted & positive & (times_s >= fault_time_s)
    ) if fault_time_s is not None else np.array([], dtype=int)
    first_any_time = float(times_s[first_any[0]]) if len(first_any) else None
    first_active_detection_time = (
        float(times_s[actual_fault_detection[0]]) if len(actual_fault_detection) else None
    )
    latency = (
        first_active_detection_time - fault_time_s
        if first_active_detection_time is not None and fault_time_s is not None
        else None
    )

    undefined: dict[str, str] = {}
    if precision is None:
        undefined["precision"] = "no predicted positive observations"
    if recall is None:
        undefined["recall"] = "no positive ground-truth observations"
    if f1 is None:
        undefined["f1"] = "no positive ground-truth or predicted observations"
    if fpr is None:
        undefined["false_positive_rate"] = "no negative ground-truth observations"
    if fault_time_s is None:
        undefined["detection_latency_s"] = "nominal-only scenario has no fault onset"
    elif first_active_detection_time is None:
        undefined["detection_latency_s"] = "no anomaly detected during active fault observations"

    return {
        "observations": int(len(positive)),
        "fault_active_observations": int(positive.sum()),
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "false_positive_rate": fpr,
        "first_predicted_anomaly_time_s": first_any_time,
        "first_predicted_anomaly_during_fault_time_s": first_active_detection_time,
        "detection_latency_s": latency,
        "undefined_metrics": undefined,
    }


def evaluate_robustness(
    nominal_path: Path,
    output_dir: Path,
    *,
    seed: int = RANDOM_SEED,
    contamination: float = CONTAMINATION,
    fault_times_s: tuple[float, ...] = DEFAULT_FAULT_TIMES_S,
) -> dict[str, Any]:
    if not 0.0 < contamination < 0.5:
        raise ValueError("contamination must be greater than 0 and less than 0.5")
    nominal = load_telemetry(nominal_path, "Nominal")
    if nominal["actuator_fault_active"].any():
        raise ValueError("The model training file must contain nominal telemetry only")

    nominal_features = build_features(nominal)
    split_at = int(len(nominal) * TRAINING_FRACTION)
    if split_at < 2 or split_at >= len(nominal):
        raise ValueError("Nominal telemetry needs at least three rows for training and holdout")
    train_features = nominal_features.iloc[:split_at]
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=contamination,
        max_samples="auto",
        random_state=seed,
        n_jobs=1,
    )
    # Fault-scenario data is generated below and is never passed to fit().
    model.fit(train_features)
    rule_error_threshold, rule_motion_tolerance = derive_stuck_rule_thresholds(train_features)

    scenarios = build_scenario_matrix(fault_times_s)
    scenarios[0]["frame"] = nominal.iloc[split_at:].copy()
    scenarios[0]["source"] = "last 20% of supplied nominal CSV"

    results: dict[str, Any] = {}
    flattened: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    for scenario in scenarios:
        name = scenario["scenario"]
        frame = scenario["frame"]
        features = (
            nominal_features.iloc[split_at:].copy()
            if name == "nominal_holdout"
            else build_features(frame)
        )
        fault_time = scenario.get("fault_time_s")
        ground_truth = frame["actuator_fault_active"].to_numpy(dtype=bool)
        times = frame["simulation_time_s"].to_numpy(dtype=float)

        model_flags = model.predict(features) == -1
        model_scores = -model.decision_function(features)
        rule_flags = detect_stuck_actuator(
            features, rule_error_threshold, rule_motion_tolerance,
            persistence_samples=RULE_PERSISTENCE_SAMPLES,
        )
        model_metrics = summarize_scenario(
            ground_truth, model_flags, times, fault_time
        )
        rule_metrics = summarize_scenario(
            ground_truth, rule_flags, times, fault_time
        )

        prediction = frame[[
            "simulation_time_s", "actuator_command", "actuator_position", "actuator_fault_active"
        ]].copy()
        prediction["actuator_tracking_error"] = features["actuator_tracking_error"].to_numpy()
        prediction["actuator_position_change"] = features["actuator_position_change"].to_numpy()
        prediction["isolation_forest_anomaly_score"] = model_scores
        prediction["isolation_forest_predicted_anomaly"] = model_flags
        prediction["rule_based_predicted_anomaly"] = rule_flags
        prediction.insert(0, "scenario", name)
        prediction_frames.append(prediction)

        result = {
            "kind": scenario["kind"],
            "source": scenario.get("source", "generated deterministically from documented C++ model equations"),
            "fault_activation_time_s": fault_time,
            "command_change_time_s": scenario.get("command_change_time_s"),
            "command_schedule": scenario.get("command_schedule", "nominal holdout"),
            "isolation_forest": model_metrics,
            "rule_based_stuck_actuator": rule_metrics,
        }
        results[name] = result
        for detector_name, detector_metrics in (
            ("isolation_forest", model_metrics),
            ("rule_based_stuck_actuator", rule_metrics),
        ):
            flattened.append({
                "scenario": name,
                "kind": scenario["kind"],
                "detector": detector_name,
                "fault_activation_time_s": fault_time,
                "command_schedule": result["command_schedule"],
                **{key: detector_metrics[key] for key in (
                    "observations", "fault_active_observations", "true_positives",
                    "false_positives", "true_negatives", "false_negatives",
                    "precision", "recall", "f1_score", "false_positive_rate",
                    "first_predicted_anomaly_time_s",
                    "first_predicted_anomaly_during_fault_time_s", "detection_latency_s",
                )},
                "undefined_metrics": json.dumps(detector_metrics["undefined_metrics"], sort_keys=True),
            })

    report: dict[str, Any] = {
        "nominal_training_source": str(nominal_path),
        "nominal_training_observations": int(len(train_features)),
        "nominal_training_fault_labels_active": int(nominal.iloc[:split_at]["actuator_fault_active"].sum()),
        "excluded_model_features": ["simulation_time_s", "actuator_fault_active"],
        "model_features": FEATURE_COLUMNS,
        "random_seed": seed,
        "isolation_forest": {
            "n_estimators": N_ESTIMATORS,
            "contamination": contamination,
            "max_samples": "auto",
            "random_state": seed,
            "n_jobs": 1,
        },
        "rule_based_stuck_actuator": {
            "tracking_error_threshold": rule_error_threshold,
            "near_zero_position_change_tolerance": rule_motion_tolerance,
            "persistence_samples": RULE_PERSISTENCE_SAMPLES,
            "simulation_time_step_s": TIME_STEP_S,
        },
        "scenario_assumptions": {
            "run_duration_s": RUN_DURATION_S,
            "simulation_time_step_s": TIME_STEP_S,
            "initial_state": {"x_m": 0.0, "y_m": 0.0, "altitude_m": 100.0, "forward_speed_mps": 20.0},
            "actuator": {
                "initial_position": 0.0,
                "limits": [ACTUATOR_MINIMUM, ACTUATOR_MAXIMUM],
                "rate_limit_per_s": ACTUATOR_RATE_LIMIT_PER_S,
                "initial_command": INITIAL_COMMAND,
                "changed_command": CHANGED_COMMAND,
            },
            "update_order": "actuator updates, simulation time advances, then fault activates at or after configured time",
            "generated_scenarios_are_synthetic": True,
            "fault_labels_used_only_for_evaluation": True,
        },
        "metric_semantics": {
            "positive_class": "actuator_fault_active",
            "false_positive_rate": "FP / (FP + TN) within each scenario",
            "nominal_only_positive_metrics": "precision, recall, and F1 are null when their denominators are zero",
            "detection_latency": "first predicted observation with an active ground-truth fault minus configured activation time",
        },
        "scenarios": results,
        "limitations": [
            "Synthetic robustness checks mirror the current software simulator; they are not hardware tests.",
            "The Isolation Forest is fit only on nominal CSV rows and does not use labels or simulation time as features.",
            "A stuck actuator at its commanded position has no observable tracking error and cannot be detected from these signals alone.",
            "These small deterministic cases do not establish robust detection or real-world flight readiness.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    expected = [output_dir / "metrics.json", output_dir / "per_scenario_metrics.csv"]
    if any(path.exists() for path in expected) or (output_dir / "predictions").exists():
        raise FileExistsError(f"Refusing to overwrite robustness results in {output_dir}")

    (output_dir / "predictions").mkdir()
    pd.DataFrame(flattened).to_csv(output_dir / "per_scenario_metrics.csv", index=False)
    for prediction in prediction_frames:
        name = str(prediction["scenario"].iloc[0])
        prediction.drop(columns=["scenario"]).to_csv(
            output_dir / "predictions" / f"{name}.csv", index=False
        )
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as metrics_file:
        json.dump(report, metrics_file, indent=2, allow_nan=False)
        metrics_file.write("\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nominal", type=Path, default=Path("telemetry/my-run/nominal.csv"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis_output/robustness-evaluation-next")
    )
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--contamination", type=float, default=CONTAMINATION)
    parser.add_argument(
        "--fault-times-s", type=float, nargs="+", default=DEFAULT_FAULT_TIMES_S,
        help="Simulation-time fault onsets (default: 0.25 0.75 1.25)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = evaluate_robustness(
            args.nominal,
            args.output_dir,
            seed=args.seed,
            contamination=args.contamination,
            fault_times_s=tuple(args.fault_times_s),
        )
    except (ValueError, OSError) as exc:
        print(f"Robustness evaluation error: {exc}", file=__import__("sys").stderr)
        return 1
    print(json.dumps(report["scenarios"], indent=2))
    print(f"Saved robustness evaluation to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
