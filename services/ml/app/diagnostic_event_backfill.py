from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.diagnostic_event_rules import (
    CONFIDENCE_DEESCALATED,
    CONFIDENCE_ESCALATED,
    DIAGNOSTIC_EVENT_TYPES,
    EVENT_ESCALATION_PER_1K_MILES,
    EVENT_CONFIRMATION_WINDOWS,
    EVENT_COOLDOWN_ANCHORS,
    EVENT_INCIDENT_CONFIDENCE,
    EVENT_RECENT_POINTS,
    EVENT_RULES_VERSION,
    EVENT_STABLE_FRACTION,
    EVENT_VOLATILE_FRACTION,
    HYPOTHESIS_CHANGED,
    HYPOTHESIS_DESTABILIZED,
    HYPOTHESIS_EMERGED,
    HYPOTHESIS_STABILIZED,
)
from fleetmind_common.diagnostic_store import (
    DiagnosticEvent,
    DiagnosticModelRun,
    DiagnosticReplayPoint,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize deterministic diagnostic audit events from an "
            "existing persisted diagnostic replay."
        )
    )
    parser.add_argument(
        "--run-id",
        type=int,
        required=True,
        help="Persisted diagnostic_model_runs.id to materialize.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace events only for this explicit run id.",
    )
    return parser.parse_args()


def _json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _hypothesis_confidence(
    row: DiagnosticReplayPoint,
    target_class: str,
) -> float:
    for hypothesis in _json_list(row.hypotheses_json):
        if (
            isinstance(hypothesis, dict)
            and hypothesis.get("class") == target_class
        ):
            try:
                return float(hypothesis.get("confidence") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _event(
    *,
    run_id: int,
    experiment_id: str,
    generated_at: datetime,
    event_type: str,
    row: DiagnosticReplayPoint,
    previous_class: str | None,
    current_class: str | None,
    previous_confidence: float | None,
    current_confidence: float | None,
    confidence_delta: float | None = None,
    slope_per_1k_miles: float | None = None,
    details: dict | None = None,
) -> DiagnosticEvent:
    if event_type not in DIAGNOSTIC_EVENT_TYPES:
        raise ValueError(f"Unsupported diagnostic event type: {event_type}")

    return DiagnosticEvent(
        run_id=run_id,
        generated_at=generated_at,
        experiment_id=experiment_id,
        vehicle_id=row.vehicle_id,
        rules_version=EVENT_RULES_VERSION,
        event_type=event_type,
        anchor_timestamp=row.anchor_timestamp,
        anchor_mileage=float(row.anchor_mileage),
        previous_class=previous_class,
        current_class=current_class,
        previous_confidence=previous_confidence,
        current_confidence=current_confidence,
        confidence_delta=confidence_delta,
        slope_per_1k_miles=slope_per_1k_miles,
        evidence_json=row.evidence_json or "[]",
        details_json=json.dumps(details or {}, sort_keys=True),
    )


def build_diagnostic_events(
    replay_rows: list[DiagnosticReplayPoint],
    *,
    run_id: int,
    experiment_id: str,
) -> list[DiagnosticEvent]:
    """
    Derive event state changes only from persisted observable replay outputs.

    No failure-event table, simulator failure marker, benchmark label, or
    post-run telemetry is consulted.
    """

    grouped: dict[str, list[DiagnosticReplayPoint]] = defaultdict(list)
    for row in replay_rows:
        if row.run_id != run_id:
            raise ValueError("Replay row belongs to a different diagnostic run")
        if row.experiment_id != experiment_id:
            raise ValueError(
                "Replay row experiment does not match persisted diagnostic run"
            )
        grouped[row.vehicle_id].append(row)

    generated_at = datetime.now(timezone.utc)
    events: list[DiagnosticEvent] = []

    for vehicle_id in sorted(grouped):
        rows = sorted(
            grouped[vehicle_id],
            key=lambda item: (item.anchor_timestamp, item.id),
        )
        if len(rows) < 2:
            continue

        # Explicit hypothesis transitions.
        for previous, current in zip(rows, rows[1:]):
            if previous.top_class == current.top_class:
                continue

            emerged = (
                previous.top_class == "healthy"
                and current.top_class != "healthy"
                and float(current.top_confidence)
                >= EVENT_INCIDENT_CONFIDENCE
            )
            event_type = (
                HYPOTHESIS_EMERGED
                if emerged
                else HYPOTHESIS_CHANGED
            )
            previous_confidence = float(previous.top_confidence)
            current_confidence = float(current.top_confidence)

            events.append(
                _event(
                    run_id=run_id,
                    experiment_id=experiment_id,
                    generated_at=generated_at,
                    event_type=event_type,
                    row=current,
                    previous_class=previous.top_class,
                    current_class=current.top_class,
                    previous_confidence=previous_confidence,
                    current_confidence=current_confidence,
                    confidence_delta=(
                        current_confidence - previous_confidence
                    ),
                    details={
                        "source": "adjacent_replay_top_class_transition",
                        "incidentConfidenceThreshold": (
                            EVENT_INCIDENT_CONFIDENCE
                        ),
                    },
                )
            )

        # Rolling confidence/stability state crossings.
        #
        # Phase 6.8.1 anti-chatter policy:
        # - Phase 6.7 thresholds remain unchanged.
        # - A candidate state must persist across EVENT_CONFIRMATION_WINDOWS
        #   consecutive rolling windows before it becomes confirmed.
        # - Confidence-family and stability-family events each observe an
        #   EVENT_COOLDOWN_ANCHORS spacing after an emitted event.
        # - The first confirmed state establishes baseline and emits nothing.
        #
        # This records durable state transitions rather than every recrossing
        # around a threshold boundary.
        trend_history: list[str] = []
        stability_history: list[str] = []
        confirmed_trend_state: str | None = None
        confirmed_stability_state: str | None = None
        last_confidence_event_index: int | None = None
        last_stability_event_index: int | None = None

        def confirmed_candidate(history: list[str]) -> str | None:
            if len(history) < EVENT_CONFIRMATION_WINDOWS:
                return None
            tail = history[-EVENT_CONFIRMATION_WINDOWS:]
            if len(set(tail)) != 1:
                return None
            return tail[-1]

        def cooldown_ready(
            current_index: int,
            last_event_index: int | None,
        ) -> bool:
            return (
                last_event_index is None
                or current_index - last_event_index
                >= EVENT_COOLDOWN_ANCHORS
            )

        for index in range(EVENT_RECENT_POINTS - 1, len(rows)):
            recent = rows[
                index - EVENT_RECENT_POINTS + 1:
                index + 1
            ]
            current = recent[-1]
            current_class = current.top_class

            start_confidence = _hypothesis_confidence(
                recent[0],
                current_class,
            )
            current_confidence = _hypothesis_confidence(
                current,
                current_class,
            )
            confidence_delta = current_confidence - start_confidence
            mileage_delta = max(
                0.0,
                float(current.anchor_mileage)
                - float(recent[0].anchor_mileage),
            )
            slope_per_1k = (
                confidence_delta / mileage_delta * 1000.0
                if mileage_delta > 0.0
                else 0.0
            )

            recent_stability = (
                sum(
                    1
                    for item in recent
                    if item.top_class == current_class
                )
                / len(recent)
            )

            if (
                current_class != "healthy"
                and float(current.top_confidence)
                >= EVENT_INCIDENT_CONFIDENCE
                and slope_per_1k
                >= EVENT_ESCALATION_PER_1K_MILES
            ):
                trend_state = "escalating"
            elif (
                current_class != "healthy"
                and slope_per_1k
                <= -EVENT_ESCALATION_PER_1K_MILES
            ):
                trend_state = "deescalating"
            else:
                trend_state = "neutral"

            if (
                current_class != "healthy"
                and float(current.top_confidence)
                >= EVENT_INCIDENT_CONFIDENCE
                and recent_stability >= EVENT_STABLE_FRACTION
            ):
                stability_state = "stable"
            elif recent_stability < EVENT_VOLATILE_FRACTION:
                stability_state = "unstable"
            else:
                stability_state = "neutral"

            trend_history.append(trend_state)
            stability_history.append(stability_state)

            next_confirmed_trend = confirmed_candidate(trend_history)
            next_confirmed_stability = confirmed_candidate(
                stability_history
            )

            if (
                next_confirmed_trend is not None
                and next_confirmed_trend != confirmed_trend_state
            ):
                prior_confirmed_trend = confirmed_trend_state

                if prior_confirmed_trend is not None:
                    trend_event_type = None
                    if next_confirmed_trend == "escalating":
                        trend_event_type = CONFIDENCE_ESCALATED
                    elif next_confirmed_trend == "deescalating":
                        trend_event_type = CONFIDENCE_DEESCALATED

                    if (
                        trend_event_type is not None
                        and cooldown_ready(
                            index,
                            last_confidence_event_index,
                        )
                    ):
                        events.append(
                            _event(
                                run_id=run_id,
                                experiment_id=experiment_id,
                                generated_at=generated_at,
                                event_type=trend_event_type,
                                row=current,
                                previous_class=current_class,
                                current_class=current_class,
                                previous_confidence=start_confidence,
                                current_confidence=current_confidence,
                                confidence_delta=confidence_delta,
                                slope_per_1k_miles=slope_per_1k,
                                details={
                                    "source": (
                                        "confirmed_rolling_confidence_"
                                        "state_crossing"
                                    ),
                                    "recentWindowPoints": (
                                        EVENT_RECENT_POINTS
                                    ),
                                    "confirmationWindows": (
                                        EVENT_CONFIRMATION_WINDOWS
                                    ),
                                    "cooldownAnchors": (
                                        EVENT_COOLDOWN_ANCHORS
                                    ),
                                    "previousConfirmedState": (
                                        prior_confirmed_trend
                                    ),
                                    "confirmedState": (
                                        next_confirmed_trend
                                    ),
                                    "escalationPer1kMilesThreshold": (
                                        EVENT_ESCALATION_PER_1K_MILES
                                    ),
                                },
                            )
                        )
                        last_confidence_event_index = index

                confirmed_trend_state = next_confirmed_trend

            if (
                next_confirmed_stability is not None
                and next_confirmed_stability
                != confirmed_stability_state
            ):
                prior_confirmed_stability = confirmed_stability_state

                if prior_confirmed_stability is not None:
                    stability_event_type = None
                    if next_confirmed_stability == "stable":
                        stability_event_type = HYPOTHESIS_STABILIZED
                    elif next_confirmed_stability == "unstable":
                        stability_event_type = HYPOTHESIS_DESTABILIZED

                    if (
                        stability_event_type is not None
                        and cooldown_ready(
                            index,
                            last_stability_event_index,
                        )
                    ):
                        events.append(
                            _event(
                                run_id=run_id,
                                experiment_id=experiment_id,
                                generated_at=generated_at,
                                event_type=stability_event_type,
                                row=current,
                                previous_class=current_class,
                                current_class=current_class,
                                previous_confidence=start_confidence,
                                current_confidence=current_confidence,
                                confidence_delta=confidence_delta,
                                slope_per_1k_miles=slope_per_1k,
                                details={
                                    "source": (
                                        "confirmed_rolling_stability_"
                                        "state_crossing"
                                    ),
                                    "recentWindowPoints": (
                                        EVENT_RECENT_POINTS
                                    ),
                                    "confirmationWindows": (
                                        EVENT_CONFIRMATION_WINDOWS
                                    ),
                                    "cooldownAnchors": (
                                        EVENT_COOLDOWN_ANCHORS
                                    ),
                                    "previousConfirmedState": (
                                        prior_confirmed_stability
                                    ),
                                    "confirmedState": (
                                        next_confirmed_stability
                                    ),
                                    "recentStability": recent_stability,
                                    "stableFractionThreshold": (
                                        EVENT_STABLE_FRACTION
                                    ),
                                    "volatileFractionThreshold": (
                                        EVENT_VOLATILE_FRACTION
                                    ),
                                },
                            )
                        )
                        last_stability_event_index = index

                confirmed_stability_state = (
                    next_confirmed_stability
                )

    events.sort(
        key=lambda item: (
            item.anchor_timestamp,
            item.vehicle_id,
            item.event_type,
        )
    )
    return events


def materialize_run(
    run_id: int,
    *,
    replace_existing: bool,
) -> dict:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        run = db.get(DiagnosticModelRun, run_id)
        if run is None:
            return {
                "status": "not_found",
                "runId": run_id,
                "reason": "diagnostic run does not exist",
            }

        if run.status != "trained" or not run.champion:
            return {
                "status": "waiting",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "reason": "diagnostic run is not a trained champion run",
            }

        existing_count = int(
            db.scalar(
                select(func.count(DiagnosticEvent.id)).where(
                    DiagnosticEvent.run_id == run.id
                )
            )
            or 0
        )

        if existing_count > 0 and not replace_existing:
            return {
                "status": "already_populated",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "rulesVersion": EVENT_RULES_VERSION,
                "events": existing_count,
            }

        mismatched = int(
            db.scalar(
                select(func.count(DiagnosticReplayPoint.id)).where(
                    DiagnosticReplayPoint.run_id == run.id,
                    DiagnosticReplayPoint.experiment_id
                    != run.experiment_id,
                )
            )
            or 0
        )
        if mismatched:
            raise ValueError(
                "Diagnostic replay contains rows from another experiment"
            )

        replay_rows = db.execute(
            select(DiagnosticReplayPoint)
            .where(
                DiagnosticReplayPoint.run_id == run.id,
                DiagnosticReplayPoint.experiment_id
                == run.experiment_id,
            )
            .order_by(
                DiagnosticReplayPoint.vehicle_id,
                DiagnosticReplayPoint.anchor_timestamp,
                DiagnosticReplayPoint.id,
            )
        ).scalars().all()

        experiment_id = run.experiment_id
        lineage = run.lineage
        champion = run.champion

    if not replay_rows:
        return {
            "status": "waiting",
            "runId": run_id,
            "experimentId": experiment_id,
            "reason": "no persisted diagnostic replay is available",
        }

    events = build_diagnostic_events(
        list(replay_rows),
        run_id=run_id,
        experiment_id=experiment_id,
    )

    with SessionLocal() as db:
        if replace_existing:
            db.execute(
                delete(DiagnosticEvent).where(
                    DiagnosticEvent.run_id == run_id
                )
            )
        db.add_all(events)
        db.commit()

    counts = Counter(event.event_type for event in events)

    return {
        "status": (
            "replaced"
            if replace_existing and existing_count > 0
            else "populated"
        ),
        "runId": run_id,
        "experimentId": experiment_id,
        "lineage": lineage,
        "champion": champion,
        "rulesVersion": EVENT_RULES_VERSION,
        "events": len(events),
        "vehicles": len({event.vehicle_id for event in events}),
        "byType": {
            event_type: int(counts.get(event_type, 0))
            for event_type in DIAGNOSTIC_EVENT_TYPES
        },
        "policy": {
            "runPinned": True,
            "exactExperimentOnly": True,
            "replayDerivedOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
            "usesPostRunTelemetry": False,
            "benchmarkModified": False,
            "modelRetrained": False,
        },
    }


def main() -> None:
    args = _parse_args()
    print(
        json.dumps(
            materialize_run(
                args.run_id,
                replace_existing=args.replace_existing,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
