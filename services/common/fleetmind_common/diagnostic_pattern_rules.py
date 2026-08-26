from __future__ import annotations

PATTERN_RULES_VERSION = "fm-diagnostic-patterns-6.11-v1"

PATTERN_DIMENSIONS = (
    "hypothesisClass",
    "firmware",
    "factory",
    "pumpRevision",
    "model",
)

# Deterministic descriptive similarity weights. These are investigation
# heuristics only; they are not learned probabilities, causal attribution,
# or private failure truth.
SIMILARITY_WEIGHTS = {
    "hypothesisClass": 0.35,
    "reviewPriority": 0.15,
    "episodeState": 0.10,
    "firmware": 0.15,
    "factory": 0.10,
    "pumpRevision": 0.10,
    "model": 0.05,
}

DEFAULT_CLUSTER_MIN_CASES = 2
MAX_CLUSTER_CASE_IDS = 50


def similarity_score(
    left: dict,
    right: dict,
) -> tuple[float, list[str]]:
    score = 0.0
    matched: list[str] = []

    comparisons = (
        ("hypothesisClass", "hypothesisClass"),
        ("reviewPriority", "reviewPriority"),
        ("episodeState", "episodeState"),
        ("firmware", "firmware"),
        ("factory", "factory"),
        ("pumpRevision", "pumpRevision"),
        ("model", "model"),
    )

    for payload_key, weight_key in comparisons:
        left_value = left.get(payload_key)
        right_value = right.get(payload_key)
        if (
            left_value is not None
            and right_value is not None
            and left_value == right_value
        ):
            score += SIMILARITY_WEIGHTS[weight_key]
            matched.append(payload_key)

    return round(score, 6), matched
