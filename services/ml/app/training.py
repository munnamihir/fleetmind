from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from fleetmind_common.ml_features import FeatureExample, assert_no_leakage


# Context fields intentionally remain in FeatureExample for display/auditing, but
# FleetMind does not fit them. Keeping this empty prevents the model from learning
# shortcuts such as firmware or pump revision.
CATEGORICAL_FEATURES: list[str] = []


@dataclass
class TrainedModel:
    pipeline: Pipeline
    calibration_coef: float
    calibration_intercept: float
    threshold: float
    metrics: dict
    calibration_bins: list[dict]
    feature_importance: list[dict]

    def calibrate(self, raw_probabilities: np.ndarray) -> np.ndarray:
        clipped = np.clip(raw_probabilities.astype(float), 1e-6, 1 - 1e-6)
        logits = np.log(clipped / (1.0 - clipped))
        calibrated_logits = self.calibration_coef * logits + self.calibration_intercept
        return 1.0 / (1.0 + np.exp(-calibrated_logits))

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        raw = self.pipeline.predict_proba(frame)[:, 1]
        return self.calibrate(raw)


def examples_to_frame(examples: Sequence[FeatureExample]) -> tuple[pd.DataFrame, np.ndarray]:
    if not examples:
        return pd.DataFrame(), np.asarray([], dtype=int)
    for example in examples:
        assert_no_leakage(example.features)
    frame = pd.DataFrame([example.features for example in examples])
    labels = np.asarray([example.label for example in examples], dtype=int)
    return frame, labels


def numeric_features(frame: pd.DataFrame) -> list[str]:
    return [
        column
        for column in frame.columns
        if column not in CATEGORICAL_FEATURES and pd.api.types.is_numeric_dtype(frame[column])
    ]


def _fit_calibration(raw: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    positives = int(labels.sum()) if len(labels) else 0
    negatives = int(len(labels) - positives)
    # Tiny calibration sets can make Platt scaling dramatically overconfident.
    # Keep raw probabilities until both classes have enough support.
    if len(raw) < 50 or positives < 10 or negatives < 10:
        return 1.0, 0.0
    clipped = np.clip(raw.astype(float), 1e-6, 1 - 1e-6)
    logits = np.log(clipped / (1.0 - clipped)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1000.0, solver="lbfgs", max_iter=1000)
    calibrator.fit(logits, labels)
    return float(calibrator.coef_[0][0]), float(calibrator.intercept_[0])


def _apply_calibration(raw: np.ndarray, coef: float, intercept: float) -> np.ndarray:
    clipped = np.clip(raw.astype(float), 1e-6, 1 - 1e-6)
    logits = np.log(clipped / (1.0 - clipped))
    calibrated_logits = coef * logits + intercept
    return 1.0 / (1.0 + np.exp(-calibrated_logits))


def choose_threshold(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """Choose an operational threshold from validation negatives only.

    FleetMind targets roughly a 2% false-positive rate in validation instead of
    optimizing a threshold against the frozen benchmark.
    """

    if len(probabilities) == 0:
        return 0.5
    negatives = probabilities[labels == 0]
    if len(negatives) >= 20:
        return float(np.clip(np.quantile(negatives, 0.98), 0.001, 0.95))
    if len(set(labels.tolist())) < 2:
        return 0.5
    best = (0.5, -1.0, -1.0)
    for threshold in np.linspace(0.01, 0.90, 90):
        predicted = (probabilities >= threshold).astype(int)
        f1 = f1_score(labels, predicted, zero_division=0)
        recall = recall_score(labels, predicted, zero_division=0)
        if (f1, recall) > (best[1], best[2]):
            best = (float(threshold), float(f1), float(recall))
    return best[0]


def _safe_auc(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    if len(set(labels.tolist())) < 2:
        return None
    return float(roc_auc_score(labels, probabilities))


def _safe_pr_auc(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    if len(set(labels.tolist())) < 2:
        return None
    return float(average_precision_score(labels, probabilities))


def evaluation_metrics(labels: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict:
    predicted = (probabilities >= threshold).astype(int)
    cm = confusion_matrix(labels, predicted, labels=[0, 1])
    tn, fp, fn, tp = [int(value) for value in cm.ravel()]
    return {
        "rocAuc": _safe_auc(labels, probabilities),
        "prAuc": _safe_pr_auc(labels, probabilities),
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "recall": float(recall_score(labels, predicted, zero_division=0)),
        "f1": float(f1_score(labels, predicted, zero_division=0)),
        "brierScore": float(brier_score_loss(labels, probabilities)),
        "positiveRate": float(labels.mean()) if len(labels) else 0.0,
        "confusionMatrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def calibration_bins(labels: np.ndarray, probabilities: np.ndarray, bins: int = 6) -> list[dict]:
    rows: list[dict] = []
    edges = np.linspace(0.0, 1.0, bins + 1)
    for index in range(bins):
        low = edges[index]
        high = edges[index + 1]
        mask = (probabilities >= low) & (
            probabilities < high if index < bins - 1 else probabilities <= high
        )
        count = int(mask.sum())
        if not count:
            continue
        rows.append(
            {
                "lower": float(low),
                "upper": float(high),
                "count": count,
                "meanPrediction": float(probabilities[mask].mean()),
                "observedRate": float(labels[mask].mean()),
            }
        )
    return rows


def _preprocessor(frame: pd.DataFrame, *, scale_numeric: bool) -> tuple[ColumnTransformer, list[str]]:
    numeric = numeric_features(frame)
    numeric_steps: list[tuple[str, object]] = [("imputer", SimpleImputer(strategy="median"))]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))
    preprocess = ColumnTransformer(
        transformers=[
            (
                "categorical",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
            ("numeric", Pipeline(steps=numeric_steps), numeric),
        ],
        remainder="drop",
    )
    return preprocess, numeric


def _early_warning_metrics(
    benchmark_examples: Sequence[FeatureExample],
    probabilities: np.ndarray,
    threshold: float,
) -> dict:
    failure_vehicle_leads: dict[str, list[float]] = {}
    for example, probability in zip(benchmark_examples, probabilities.tolist()):
        if example.label != 1 or example.miles_to_failure is None:
            continue
        failure_vehicle_leads.setdefault(example.vehicle_id, [])
        if probability >= threshold:
            failure_vehicle_leads[example.vehicle_id].append(float(example.miles_to_failure))
    detected_leads = [max(values) for values in failure_vehicle_leads.values() if values]
    failure_vehicle_count = len(failure_vehicle_leads)
    return {
        "failureVehiclesEvaluated": failure_vehicle_count,
        "failureVehiclesDetected": len(detected_leads),
        "vehicleDetectionRate": (
            len(detected_leads) / failure_vehicle_count if failure_vehicle_count else None
        ),
        "medianLeadMiles": float(np.median(detected_leads)) if detected_leads else None,
    }


def _calibration_metadata(coef: float, intercept: float) -> dict:
    applied = not (abs(coef - 1.0) < 1e-12 and abs(intercept) < 1e-12)
    return {
        "applied": applied,
        "method": (
            "Platt scaling on vehicle-isolated validation windows"
            if applied
            else "identity fallback: validation calibration support below minimum"
        ),
        "coefficient": coef,
        "intercept": intercept,
    }


def _evaluate_pipeline(
    pipeline: Pipeline,
    validation_examples: Sequence[FeatureExample],
    benchmark_examples: Sequence[FeatureExample],
    feature_importance: list[dict],
) -> TrainedModel:
    validation_frame, validation_labels = examples_to_frame(validation_examples)
    benchmark_frame, benchmark_labels = examples_to_frame(benchmark_examples)
    if benchmark_frame.empty:
        raise ValueError("Frozen benchmark data is empty")

    validation_raw = (
        pipeline.predict_proba(validation_frame)[:, 1]
        if not validation_frame.empty
        else np.asarray([], dtype=float)
    )
    coef, intercept = _fit_calibration(validation_raw, validation_labels)
    validation_prob = _apply_calibration(validation_raw, coef, intercept)
    threshold = choose_threshold(validation_prob, validation_labels)

    benchmark_raw = pipeline.predict_proba(benchmark_frame)[:, 1]
    benchmark_prob = _apply_calibration(benchmark_raw, coef, intercept)
    metrics = evaluation_metrics(benchmark_labels, benchmark_prob, threshold)
    metrics["earlyWarning"] = _early_warning_metrics(
        benchmark_examples, benchmark_prob, threshold
    )
    metrics["threshold"] = threshold
    metrics["thresholdPolicy"] = (
        "98th percentile of validation negative scores (~2% validation false-positive target)"
    )
    metrics["calibration"] = _calibration_metadata(coef, intercept)

    return TrainedModel(
        pipeline=pipeline,
        calibration_coef=coef,
        calibration_intercept=intercept,
        threshold=threshold,
        metrics=metrics,
        calibration_bins=calibration_bins(benchmark_labels, benchmark_prob),
        feature_importance=feature_importance,
    )


def train_xgboost(
    train_examples: Sequence[FeatureExample],
    validation_examples: Sequence[FeatureExample],
    benchmark_examples: Sequence[FeatureExample],
    *,
    random_state: int = 20260824,
) -> TrainedModel:
    train_frame, train_labels = examples_to_frame(train_examples)
    if train_frame.empty or len(set(train_labels.tolist())) < 2:
        raise ValueError("Training data must contain both positive and negative examples")

    preprocess, _ = _preprocessor(train_frame, scale_numeric=False)
    positives = max(1, int(train_labels.sum()))
    negatives = max(1, int(len(train_labels) - positives))
    scale_pos_weight = min(50.0, max(1.0, negatives / positives))

    classifier = XGBClassifier(
        n_estimators=220,
        max_depth=4,
        learning_rate=0.045,
        min_child_weight=3,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=2.0,
        reg_alpha=0.05,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=random_state,
        n_jobs=2,
        scale_pos_weight=scale_pos_weight,
    )
    pipeline = Pipeline(steps=[("preprocess", preprocess), ("model", classifier)])
    pipeline.fit(train_frame, train_labels)

    transformed_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    importances = pipeline.named_steps["model"].feature_importances_
    ranked = sorted(
        zip(transformed_names.tolist(), importances.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )[:15]
    feature_importance = [
        {
            "feature": name.replace("categorical__", "").replace("numeric__", ""),
            "importance": float(value),
        }
        for name, value in ranked
    ]

    return _evaluate_pipeline(
        pipeline, validation_examples, benchmark_examples, feature_importance
    )


def train_logistic_baseline(
    train_examples: Sequence[FeatureExample],
    validation_examples: Sequence[FeatureExample],
    benchmark_examples: Sequence[FeatureExample],
    *,
    random_state: int = 20260824,
) -> TrainedModel:
    """Fit a deliberately simple sensor-only baseline on the identical cohorts."""

    train_frame, train_labels = examples_to_frame(train_examples)
    if train_frame.empty or len(set(train_labels.tolist())) < 2:
        raise ValueError("Training data must contain both positive and negative examples")

    preprocess, _ = _preprocessor(train_frame, scale_numeric=True)
    classifier = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=2000,
        random_state=random_state,
    )
    pipeline = Pipeline(steps=[("preprocess", preprocess), ("model", classifier)])
    pipeline.fit(train_frame, train_labels)

    transformed_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    coefficients = np.abs(pipeline.named_steps["model"].coef_[0])
    total = float(coefficients.sum()) or 1.0
    ranked = sorted(
        zip(transformed_names.tolist(), (coefficients / total).tolist()),
        key=lambda item: item[1],
        reverse=True,
    )[:15]
    feature_importance = [
        {
            "feature": name.replace("categorical__", "").replace("numeric__", ""),
            "importance": float(value),
        }
        for name, value in ranked
    ]

    return _evaluate_pipeline(
        pipeline, validation_examples, benchmark_examples, feature_importance
    )


def metric_delta(xgboost: dict, baseline: dict) -> dict:
    def delta(key: str) -> float | None:
        left = xgboost.get(key)
        right = baseline.get(key)
        if left is None or right is None:
            return None
        return float(left - right)

    return {
        "rocAuc": delta("rocAuc"),
        "prAuc": delta("prAuc"),
        "precision": delta("precision"),
        "recall": delta("recall"),
        "f1": delta("f1"),
        # Lower Brier is better, so positive means XGBoost improved calibration/error.
        "brierImprovement": (
            float(baseline["brierScore"] - xgboost["brierScore"])
            if baseline.get("brierScore") is not None and xgboost.get("brierScore") is not None
            else None
        ),
    }


def save_artifact(model: TrainedModel, path: str | Path, metadata: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": model.pipeline,
            "calibrationCoefficient": model.calibration_coef,
            "calibrationIntercept": model.calibration_intercept,
            "threshold": model.threshold,
            "metadata": metadata,
        },
        destination,
    )


def json_dumps(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
