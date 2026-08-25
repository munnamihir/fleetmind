from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
try:
    from xgboost import XGBClassifier
except ImportError:  # Local unit-test environments may not install ML extras.
    XGBClassifier = None

XGBOOST_AVAILABLE = XGBClassifier is not None

from fleetmind_common.diagnostic_dataset import (
    DIAGNOSTIC_CLASSES,
    DiagnosticExample,
    diagnostic_feature_schema,
)


DIAGNOSTIC_MODEL_LINEAGE = "fm-diagnostics-6.3-v1"


@dataclass(frozen=True)
class DiagnosticMetrics:
    macro_f1: float
    balanced_accuracy: float
    top2_accuracy: float
    multiclass_brier: float
    per_class: Dict[str, Dict[str, float]]
    confusion_matrix: List[List[int]]


@dataclass(frozen=True)
class DiagnosticModelComparison:
    feature_names: Tuple[str, ...]
    feature_schema_hash: str
    baseline_metrics: DiagnosticMetrics
    logistic_metrics: DiagnosticMetrics
    xgboost_metrics: DiagnosticMetrics
    champion: str


class TransparentDiagnosticBaseline:
    """Inspectable, robust-z-score diagnostic baseline.

    This is intentionally not a learned black box. Training stores median/IQR
    reference ranges from development data, then applies named physical evidence
    rules to create class scores.
    """

    EVIDENCE_FEATURES = (
        "pump_current_per_1k_rpm_last",
        "pump_rpm_per_amp_last",
        "coolant_ambient_delta_c_last",
        "battery_ambient_delta_c_last",
        "cell_imbalance_v_last",
        "cell_imbalance_v_slope_per_1k_mi",
        "inverter_ambient_delta_c_last",
        "motor_ambient_delta_c_last",
        "motor_inverter_delta_c_last",
        "coolant_peer_residual_c_last",
        "thermal_peer_spread_c_last",
        "corr_abs_pack_current_inverter_temp",
        "corr_abs_pack_current_motor_temp",
    )

    def __init__(self) -> None:
        self.center_: Dict[str, float] = {}
        self.scale_: Dict[str, float] = {}

    def fit(self, examples: Sequence[DiagnosticExample]):
        if not examples:
            raise ValueError("Baseline requires training examples")

        for feature in self.EVIDENCE_FEATURES:
            values = np.asarray(
                [float(example.features[feature]) for example in examples],
                dtype=float,
            )
            q25, median, q75 = np.percentile(values, [25, 50, 75])
            iqr = float(q75 - q25)
            self.center_[feature] = float(median)
            self.scale_[feature] = max(iqr / 1.349, 1e-6)

        return self

    def _z(self, features: Mapping[str, float], name: str) -> float:
        return (
            float(features[name]) - self.center_[name]
        ) / self.scale_[name]

    def _scores(self, features: Mapping[str, float]) -> np.ndarray:
        z = lambda name: self._z(features, name)

        pump = (
            1.35 * max(z("pump_current_per_1k_rpm_last"), 0.0)
            + 1.20 * max(-z("pump_rpm_per_amp_last"), 0.0)
            + 0.45 * max(z("coolant_ambient_delta_c_last"), 0.0)
        )

        battery = (
            1.55 * max(z("cell_imbalance_v_last"), 0.0)
            + 1.10 * max(z("cell_imbalance_v_slope_per_1k_mi"), 0.0)
            + 0.50 * max(z("battery_ambient_delta_c_last"), 0.0)
        )

        inverter = (
            1.40 * max(z("inverter_ambient_delta_c_last"), 0.0)
            + 0.60 * max(z("corr_abs_pack_current_inverter_temp"), 0.0)
            + 0.40 * max(-z("motor_inverter_delta_c_last"), 0.0)
        )

        motor = (
            1.40 * max(z("motor_ambient_delta_c_last"), 0.0)
            + 0.60 * max(z("corr_abs_pack_current_motor_temp"), 0.0)
            + 0.40 * max(z("motor_inverter_delta_c_last"), 0.0)
        )

        sensor = (
            1.70 * max(z("coolant_peer_residual_c_last"), 0.0)
            + 0.70 * max(z("thermal_peer_spread_c_last"), 0.0)
            - 0.25 * max(z("pump_current_per_1k_rpm_last"), 0.0)
        )
        sensor = max(sensor, 0.0)

        anomaly = max(pump, battery, inverter, motor, sensor)
        healthy = max(0.0, 2.2 - anomaly)

        return np.asarray(
            [healthy, pump, battery, inverter, motor, sensor],
            dtype=float,
        )

    def predict_proba(
        self,
        examples: Sequence[DiagnosticExample],
    ) -> np.ndarray:
        if not self.center_:
            raise ValueError("Baseline is not fitted")

        scores = np.vstack(
            [self._scores(example.features) for example in examples]
        )
        scores = scores - scores.max(axis=1, keepdims=True)
        exp_scores = np.exp(scores)
        return exp_scores / exp_scores.sum(axis=1, keepdims=True)


def _matrix(
    examples: Sequence[DiagnosticExample],
    feature_names: Sequence[str],
) -> np.ndarray:
    return np.asarray(
        [
            [float(example.features[name]) for name in feature_names]
            for example in examples
        ],
        dtype=float,
    )


def _labels(examples: Sequence[DiagnosticExample]) -> np.ndarray:
    class_to_index = {
        label: index
        for index, label in enumerate(DIAGNOSTIC_CLASSES)
    }
    return np.asarray(
        [class_to_index[example.label] for example in examples],
        dtype=int,
    )


def _align_probabilities(
    probabilities: np.ndarray,
    model_classes: Sequence[int],
) -> np.ndarray:
    aligned = np.zeros(
        (probabilities.shape[0], len(DIAGNOSTIC_CLASSES)),
        dtype=float,
    )
    for source_index, class_index in enumerate(model_classes):
        aligned[:, int(class_index)] = probabilities[:, source_index]
    row_sums = aligned.sum(axis=1, keepdims=True)
    row_sums[row_sums <= 0.0] = 1.0
    return aligned / row_sums


def evaluate_diagnostic_probabilities(
    examples: Sequence[DiagnosticExample],
    probabilities: np.ndarray,
) -> DiagnosticMetrics:
    if not examples:
        raise ValueError("Evaluation requires examples")
    if probabilities.shape != (
        len(examples),
        len(DIAGNOSTIC_CLASSES),
    ):
        raise ValueError("Probability matrix has the wrong shape")

    y_true = _labels(examples)
    y_pred = np.argmax(probabilities, axis=1)

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=np.arange(len(DIAGNOSTIC_CLASSES)),
        zero_division=0,
    )

    per_class = {
        label: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": float(support[index]),
        }
        for index, label in enumerate(DIAGNOSTIC_CLASSES)
    }

    top2 = np.argsort(probabilities, axis=1)[:, -2:]
    top2_accuracy = float(
        np.mean(
            [
                truth in candidates
                for truth, candidates in zip(y_true, top2)
            ]
        )
    )

    one_hot = np.eye(len(DIAGNOSTIC_CLASSES))[y_true]
    brier = float(
        np.mean(
            np.sum((probabilities - one_hot) ** 2, axis=1)
        )
    )

    return DiagnosticMetrics(
        macro_f1=float(
            f1_score(
                y_true,
                y_pred,
                labels=np.arange(len(DIAGNOSTIC_CLASSES)),
                average="macro",
                zero_division=0,
            )
        ),
        balanced_accuracy=float(
            balanced_accuracy_score(y_true, y_pred)
        ),
        top2_accuracy=top2_accuracy,
        multiclass_brier=brier,
        per_class=per_class,
        confusion_matrix=confusion_matrix(
            y_true,
            y_pred,
            labels=np.arange(len(DIAGNOSTIC_CLASSES)),
        ).astype(int).tolist(),
    )


def fit_compare_diagnostic_models(
    train: Sequence[DiagnosticExample],
    validation: Sequence[DiagnosticExample],
    *,
    random_state: int = 61,
) -> Tuple[
    TransparentDiagnosticBaseline,
    Pipeline,
    XGBClassifier,
    DiagnosticModelComparison,
]:
    if not train:
        raise ValueError("Training examples are required")
    if not XGBOOST_AVAILABLE:
        raise RuntimeError(
            "xgboost is required to train the Phase 6.3 model comparison; "
            "install the ML service requirements or run inside the ml-trainer container"
        )
    if not validation:
        raise ValueError("Validation examples are required")

    train_classes = {example.label for example in train}
    missing = [
        label
        for label in DIAGNOSTIC_CLASSES
        if label not in train_classes
    ]
    if missing:
        raise ValueError(
            f"Training data is missing diagnostic classes: {missing}"
        )

    feature_names, schema_hash = diagnostic_feature_schema(train)
    validation_names, validation_hash = diagnostic_feature_schema(
        validation
    )
    if feature_names != validation_names or schema_hash != validation_hash:
        raise ValueError(
            "Train/validation diagnostic feature schemas do not match"
        )

    x_train = _matrix(train, feature_names)
    y_train = _labels(train)
    x_validation = _matrix(validation, feature_names)

    baseline = TransparentDiagnosticBaseline().fit(train)
    baseline_probabilities = baseline.predict_proba(validation)

    logistic = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    max_iter=1500,
                    class_weight="balanced",
                    solver="lbfgs",
                    random_state=random_state,
                ),
            ),
        ]
    )
    logistic.fit(x_train, y_train)
    logistic_model = logistic.named_steps["model"]
    logistic_probabilities = _align_probabilities(
        logistic.predict_proba(x_validation),
        logistic_model.classes_,
    )

    xgb = XGBClassifier(
        objective="multi:softprob",
        num_class=len(DIAGNOSTIC_CLASSES),
        n_estimators=120,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.90,
        colsample_bytree=0.85,
        reg_lambda=2.0,
        min_child_weight=2.0,
        eval_metric="mlogloss",
        random_state=random_state,
        n_jobs=1,
        tree_method="hist",
    )
    xgb.fit(x_train, y_train)
    xgb_probabilities = _align_probabilities(
        xgb.predict_proba(x_validation),
        xgb.classes_,
    )

    baseline_metrics = evaluate_diagnostic_probabilities(
        validation,
        baseline_probabilities,
    )
    logistic_metrics = evaluate_diagnostic_probabilities(
        validation,
        logistic_probabilities,
    )
    xgboost_metrics = evaluate_diagnostic_probabilities(
        validation,
        xgb_probabilities,
    )

    candidates = {
        "transparent_baseline": baseline_metrics,
        "multinomial_logistic": logistic_metrics,
        "xgboost_multiclass": xgboost_metrics,
    }
    champion = max(
        candidates,
        key=lambda name: (
            candidates[name].macro_f1,
            candidates[name].balanced_accuracy,
            candidates[name].top2_accuracy,
            -candidates[name].multiclass_brier,
        ),
    )

    comparison = DiagnosticModelComparison(
        feature_names=feature_names,
        feature_schema_hash=schema_hash,
        baseline_metrics=baseline_metrics,
        logistic_metrics=logistic_metrics,
        xgboost_metrics=xgboost_metrics,
        champion=champion,
    )

    return baseline, logistic, xgb, comparison


def predict_ranked_hypotheses(
    model,
    examples: Sequence[DiagnosticExample],
    *,
    feature_names: Sequence[str],
    top_k: int = 3,
) -> List[List[Dict[str, float]]]:
    if top_k < 1 or top_k > len(DIAGNOSTIC_CLASSES):
        raise ValueError("top_k is out of range")

    if isinstance(model, TransparentDiagnosticBaseline):
        probabilities = model.predict_proba(examples)
    else:
        matrix = _matrix(examples, feature_names)
        probabilities = _align_probabilities(
            model.predict_proba(matrix),
            model.classes_,
        )

    ranked: List[List[Dict[str, float]]] = []
    for row in probabilities:
        indexes = np.argsort(row)[::-1][:top_k]
        ranked.append(
            [
                {
                    "class": DIAGNOSTIC_CLASSES[int(index)],
                    "confidence": float(row[int(index)]),
                }
                for index in indexes
            ]
        )
    return ranked
