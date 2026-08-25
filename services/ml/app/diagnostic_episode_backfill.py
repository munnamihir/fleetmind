from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.diagnostic_episode_rules import (
    EPISODE_DESTABILIZED,
    EPISODE_CONTINUITY_MAX_HEALTHY_GAP_MILES,
    EPISODE_CONTINUITY_MAX_INTERVENING_HEALTHY_EVENTS,
    EPISODE_EMERGING,
    EPISODE_EVOLVING,
    EPISODE_RESOLVED,
    EPISODE_RULES_VERSION,
    EPISODE_SOURCE_EVENT_RULES_VERSION,
    EPISODE_STABILIZED,
    EPISODE_START_CLASS_CHANGED,
    EPISODE_START_EMERGED,
    EPISODE_START_OBSERVED_IN_PROGRESS,
    EPISODE_SUPERSEDED,
)
from fleetmind_common.diagnostic_event_rules import (
    CONFIDENCE_DEESCALATED,
    CONFIDENCE_ESCALATED,
    HYPOTHESIS_CHANGED,
    HYPOTHESIS_DESTABILIZED,
    HYPOTHESIS_EMERGED,
    HYPOTHESIS_STABILIZED,
)
from fleetmind_common.diagnostic_store import (
    DiagnosticEpisode,
    DiagnosticEvent,
    DiagnosticModelRun,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize deterministic diagnostic episodes from the "
            "persisted diagnostic event stream for one explicit run."
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
        help="Replace episodes only for this explicit run id.",
    )
    return parser.parse_args()


def _event_confidence(event: DiagnosticEvent) -> float | None:
    if event.current_confidence is not None:
        return float(event.current_confidence)
    if event.previous_confidence is not None:
        return float(event.previous_confidence)
    return None


def _state_for_event(event_type: str) -> str:
    if event_type == HYPOTHESIS_EMERGED:
        return EPISODE_EMERGING
    if event_type == HYPOTHESIS_STABILIZED:
        return EPISODE_STABILIZED
    if event_type == HYPOTHESIS_DESTABILIZED:
        return EPISODE_DESTABILIZED
    return EPISODE_EVOLVING


def _new_episode(
    event: DiagnosticEvent,
    *,
    start_reason: str,
    left_censored: bool,
) -> dict:
    confidence = _event_confidence(event)
    return {
        "vehicle_id": event.vehicle_id,
        "hypothesis_class": event.current_class,
        "state": _state_for_event(event.event_type),
        "start_reason": start_reason,
        "start_timestamp": event.anchor_timestamp,
        "start_mileage": float(event.anchor_mileage),
        "end_timestamp": event.anchor_timestamp,
        "end_mileage": float(event.anchor_mileage),
        "is_open": True,
        "left_censored": left_censored,
        "event_count": 0,
        "escalation_count": 0,
        "deescalation_count": 0,
        "class_change_count": 0,
        "stabilized_count": 0,
        "destabilized_count": 0,
        "peak_confidence": confidence,
        "latest_confidence": confidence,
        "event_ids": [],
        "details": {
            "source": "diagnostic_events",
            "startEventId": event.id,
            "closedByEventId": None,
            "closeReason": None,
        },
    }


def _append_event(episode: dict, event: DiagnosticEvent) -> None:
    episode["end_timestamp"] = event.anchor_timestamp
    episode["end_mileage"] = float(event.anchor_mileage)
    episode["event_count"] += 1
    episode["event_ids"].append(event.id)

    confidence = _event_confidence(event)
    if confidence is not None:
        episode["latest_confidence"] = confidence
        peak = episode["peak_confidence"]
        episode["peak_confidence"] = (
            confidence if peak is None else max(float(peak), confidence)
        )

    if event.event_type == CONFIDENCE_ESCALATED:
        episode["escalation_count"] += 1
    elif event.event_type == CONFIDENCE_DEESCALATED:
        episode["deescalation_count"] += 1
    elif event.event_type == HYPOTHESIS_CHANGED:
        episode["class_change_count"] += 1
    elif event.event_type == HYPOTHESIS_STABILIZED:
        episode["stabilized_count"] += 1
    elif event.event_type == HYPOTHESIS_DESTABILIZED:
        episode["destabilized_count"] += 1

    episode["state"] = _state_for_event(event.event_type)


def _close_episode(
    episode: dict,
    *,
    state: str,
    boundary_event: DiagnosticEvent,
    close_reason: str,
) -> None:
    episode["is_open"] = False
    episode["state"] = state
    episode["end_timestamp"] = boundary_event.anchor_timestamp
    episode["end_mileage"] = float(boundary_event.anchor_mileage)
    episode["details"]["closedByEventId"] = boundary_event.id
    episode["details"]["closeReason"] = close_reason

    if boundary_event.previous_confidence is not None:
        episode["latest_confidence"] = float(
            boundary_event.previous_confidence
        )


def _continuation_gap_miles(
    pending_resolution: dict,
    event: DiagnosticEvent,
) -> float:
    return max(
        0.0,
        float(event.anchor_mileage)
        - float(pending_resolution["anchor_mileage"]),
    )


def _can_continue_same_class(
    active: dict,
    pending_resolution: dict,
    event: DiagnosticEvent,
) -> bool:
    if event.current_class != active["hypothesis_class"]:
        return False

    gap_miles = _continuation_gap_miles(
        pending_resolution,
        event,
    )
    return (
        gap_miles
        <= EPISODE_CONTINUITY_MAX_HEALTHY_GAP_MILES
        and pending_resolution["intervening_healthy_events"]
        <= EPISODE_CONTINUITY_MAX_INTERVENING_HEALTHY_EVENTS
    )


def _record_continuation(
    active: dict,
    pending_resolution: dict,
    event: DiagnosticEvent,
) -> None:
    gap_miles = _continuation_gap_miles(
        pending_resolution,
        event,
    )
    continuations = active["details"].setdefault(
        "continuations",
        [],
    )
    continuations.append(
        {
            "exitEventId": pending_resolution["event"].id,
            "returnEventId": event.id,
            "healthyGapMiles": round(gap_miles, 3),
            "interveningHealthyEvents": (
                pending_resolution[
                    "intervening_healthy_events"
                ]
            ),
        }
    )
    active["details"]["continuationCount"] = len(
        continuations
    )
    active["details"]["maxObservedHealthyGapMiles"] = max(
        float(
            active["details"].get(
                "maxObservedHealthyGapMiles",
                0.0,
            )
        ),
        gap_miles,
    )


def build_diagnostic_episodes(
    events: list[DiagnosticEvent],
    *,
    run_id: int,
    experiment_id: str,
) -> list[dict]:
    """
    Group persisted diagnostic events into non-healthy hypothesis episodes.

    This function consumes DiagnosticEvent rows only. It does not inspect
    telemetry, diagnostic replay, predictions, failure-event truth, simulator
    markers, benchmark labels, or any post-run source.

    Phase 6.9.1 prevents same-class episode fragmentation by treating a
    short temporary healthy gap as continuity when:
      * the returning non-healthy class is the same class,
      * no other non-healthy hypothesis intervened,
      * the healthy gap is within the fixed mileage window, and
      * at most the fixed number of healthy context events intervened.

    Raw Phase 6.8.1 diagnostic events remain unchanged and auditable.
    """

    grouped: dict[str, list[DiagnosticEvent]] = defaultdict(list)

    for event in events:
        if event.run_id != run_id:
            raise ValueError(
                "Diagnostic event belongs to another diagnostic run"
            )
        if event.experiment_id != experiment_id:
            raise ValueError(
                "Diagnostic event belongs to another experiment"
            )
        if event.rules_version != EPISODE_SOURCE_EVENT_RULES_VERSION:
            raise ValueError(
                "Diagnostic event rules version does not match the "
                "episode source contract"
            )
        grouped[event.vehicle_id].append(event)

    completed: list[dict] = []

    for vehicle_id in sorted(grouped):
        vehicle_events = sorted(
            grouped[vehicle_id],
            key=lambda item: (
                item.anchor_timestamp,
                item.id,
            ),
        )
        active: dict | None = None
        pending_resolution: dict | None = None

        for event in vehicle_events:
            current_class = event.current_class

            # If the active episode temporarily returned to healthy, first
            # decide whether this event continues the same-class episode or
            # makes the earlier healthy boundary durable.
            if active is not None and pending_resolution is not None:
                if current_class == "healthy" or not current_class:
                    pending_resolution[
                        "intervening_healthy_events"
                    ] += 1

                    gap_miles = _continuation_gap_miles(
                        pending_resolution,
                        event,
                    )
                    if (
                        gap_miles
                        > EPISODE_CONTINUITY_MAX_HEALTHY_GAP_MILES
                        or pending_resolution[
                            "intervening_healthy_events"
                        ]
                        > EPISODE_CONTINUITY_MAX_INTERVENING_HEALTHY_EVENTS
                    ):
                        _close_episode(
                            active,
                            state=EPISODE_RESOLVED,
                            boundary_event=pending_resolution["event"],
                            close_reason="durable_return_to_healthy",
                        )
                        completed.append(active)
                        active = None
                        pending_resolution = None
                    continue

                if _can_continue_same_class(
                    active,
                    pending_resolution,
                    event,
                ):
                    _record_continuation(
                        active,
                        pending_resolution,
                        event,
                    )
                    pending_resolution = None
                    _append_event(active, event)

                    # A re-entry is continuation, not a brand-new emergence.
                    if event.event_type in (
                        HYPOTHESIS_EMERGED,
                        HYPOTHESIS_CHANGED,
                    ):
                        active["state"] = EPISODE_EVOLVING
                    continue

                # The healthy boundary is now durable. Finalize the prior
                # episode before processing this new non-healthy hypothesis.
                _close_episode(
                    active,
                    state=EPISODE_RESOLVED,
                    boundary_event=pending_resolution["event"],
                    close_reason="durable_return_to_healthy",
                )
                completed.append(active)
                active = None
                pending_resolution = None

            if event.event_type == HYPOTHESIS_EMERGED:
                if not current_class or current_class == "healthy":
                    continue

                if (
                    active is not None
                    and active["hypothesis_class"] != current_class
                ):
                    _close_episode(
                        active,
                        state=EPISODE_SUPERSEDED,
                        boundary_event=event,
                        close_reason="hypothesis_replaced",
                    )
                    completed.append(active)
                    active = None

                if active is None:
                    active = _new_episode(
                        event,
                        start_reason=EPISODE_START_EMERGED,
                        left_censored=False,
                    )

                _append_event(active, event)
                continue

            if event.event_type == HYPOTHESIS_CHANGED:
                if current_class == "healthy":
                    if active is not None:
                        _append_event(active, event)
                        pending_resolution = {
                            "event": event,
                            "anchor_mileage": float(
                                event.anchor_mileage
                            ),
                            "intervening_healthy_events": 0,
                        }
                    continue

                if not current_class:
                    continue

                if (
                    active is not None
                    and active["hypothesis_class"] == current_class
                ):
                    _append_event(active, event)
                    continue

                if active is not None:
                    _close_episode(
                        active,
                        state=EPISODE_SUPERSEDED,
                        boundary_event=event,
                        close_reason="hypothesis_replaced",
                    )
                    completed.append(active)

                active = _new_episode(
                    event,
                    start_reason=EPISODE_START_CLASS_CHANGED,
                    left_censored=False,
                )
                _append_event(active, event)
                continue

            if not current_class or current_class == "healthy":
                continue

            if (
                active is not None
                and active["hypothesis_class"] != current_class
            ):
                _close_episode(
                    active,
                    state=EPISODE_SUPERSEDED,
                    boundary_event=event,
                    close_reason="event_stream_class_boundary",
                )
                completed.append(active)
                active = None

            if active is None:
                active = _new_episode(
                    event,
                    start_reason=EPISODE_START_OBSERVED_IN_PROGRESS,
                    left_censored=True,
                )

            _append_event(active, event)

        if active is not None:
            if pending_resolution is not None:
                _close_episode(
                    active,
                    state=EPISODE_RESOLVED,
                    boundary_event=pending_resolution["event"],
                    close_reason="end_of_event_stream_after_healthy",
                )
            completed.append(active)

    completed.sort(
        key=lambda episode: (
            episode["start_timestamp"],
            episode["vehicle_id"],
            episode["hypothesis_class"] or "",
        )
    )
    return completed


def _persisted_episode(
    episode: dict,
    *,
    run_id: int,
    experiment_id: str,
    generated_at: datetime,
) -> DiagnosticEpisode:
    return DiagnosticEpisode(
        run_id=run_id,
        generated_at=generated_at,
        experiment_id=experiment_id,
        vehicle_id=episode["vehicle_id"],
        rules_version=EPISODE_RULES_VERSION,
        source_event_rules_version=EPISODE_SOURCE_EVENT_RULES_VERSION,
        hypothesis_class=episode["hypothesis_class"],
        state=episode["state"],
        start_reason=episode["start_reason"],
        start_timestamp=episode["start_timestamp"],
        start_mileage=episode["start_mileage"],
        end_timestamp=episode["end_timestamp"],
        end_mileage=episode["end_mileage"],
        is_open=episode["is_open"],
        left_censored=episode["left_censored"],
        event_count=episode["event_count"],
        escalation_count=episode["escalation_count"],
        deescalation_count=episode["deescalation_count"],
        class_change_count=episode["class_change_count"],
        stabilized_count=episode["stabilized_count"],
        destabilized_count=episode["destabilized_count"],
        peak_confidence=episode["peak_confidence"],
        latest_confidence=episode["latest_confidence"],
        event_ids_json=json.dumps(episode["event_ids"]),
        details_json=json.dumps(episode["details"], sort_keys=True),
    )


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
                select(func.count(DiagnosticEpisode.id)).where(
                    DiagnosticEpisode.run_id == run.id
                )
            )
            or 0
        )

        if existing_count > 0 and not replace_existing:
            return {
                "status": "already_populated",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "rulesVersion": EPISODE_RULES_VERSION,
                "episodes": existing_count,
            }

        event_count = int(
            db.scalar(
                select(func.count(DiagnosticEvent.id)).where(
                    DiagnosticEvent.run_id == run.id,
                    DiagnosticEvent.experiment_id == run.experiment_id,
                )
            )
            or 0
        )
        if event_count == 0:
            return {
                "status": "waiting",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "reason": (
                    "no persisted diagnostic events are available; "
                    "materialize Phase 6.8.1 events first"
                ),
            }

        mismatched_experiment = int(
            db.scalar(
                select(func.count(DiagnosticEvent.id)).where(
                    DiagnosticEvent.run_id == run.id,
                    DiagnosticEvent.experiment_id != run.experiment_id,
                )
            )
            or 0
        )
        if mismatched_experiment:
            raise ValueError(
                "Diagnostic events contain rows from another experiment"
            )

        source_versions = set(
            db.execute(
                select(DiagnosticEvent.rules_version)
                .where(
                    DiagnosticEvent.run_id == run.id,
                    DiagnosticEvent.experiment_id == run.experiment_id,
                )
                .distinct()
            ).scalars().all()
        )

        if source_versions != {EPISODE_SOURCE_EVENT_RULES_VERSION}:
            return {
                "status": "event_rules_mismatch",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "requiredEventRulesVersion": EPISODE_SOURCE_EVENT_RULES_VERSION,
                "foundEventRulesVersions": sorted(source_versions),
                "reason": (
                    "episodes require one exact Phase 6.8.1 event rules "
                    "version; rematerialize events before episodes"
                ),
            }

        events = db.execute(
            select(DiagnosticEvent)
            .where(
                DiagnosticEvent.run_id == run.id,
                DiagnosticEvent.experiment_id == run.experiment_id,
                DiagnosticEvent.rules_version
                == EPISODE_SOURCE_EVENT_RULES_VERSION,
            )
            .order_by(
                DiagnosticEvent.vehicle_id,
                DiagnosticEvent.anchor_timestamp,
                DiagnosticEvent.id,
            )
        ).scalars().all()

        experiment_id = run.experiment_id
        lineage = run.lineage
        champion = run.champion

    episode_dicts = build_diagnostic_episodes(
        list(events),
        run_id=run_id,
        experiment_id=experiment_id,
    )
    generated_at = datetime.now(timezone.utc)
    episodes = [
        _persisted_episode(
            episode,
            run_id=run_id,
            experiment_id=experiment_id,
            generated_at=generated_at,
        )
        for episode in episode_dicts
    ]

    with SessionLocal() as db:
        if replace_existing:
            db.execute(
                delete(DiagnosticEpisode).where(
                    DiagnosticEpisode.run_id == run_id
                )
            )
        db.add_all(episodes)
        db.commit()

    state_counts = Counter(episode.state for episode in episodes)
    class_counts = Counter(
        episode.hypothesis_class for episode in episodes
    )
    open_count = sum(1 for episode in episodes if episode.is_open)
    left_censored_count = sum(
        1 for episode in episodes if episode.left_censored
    )

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
        "rulesVersion": EPISODE_RULES_VERSION,
        "sourceEventRulesVersion": EPISODE_SOURCE_EVENT_RULES_VERSION,
        "sourceEvents": len(events),
        "episodes": len(episodes),
        "vehicles": len({episode.vehicle_id for episode in episodes}),
        "openEpisodes": open_count,
        "closedEpisodes": len(episodes) - open_count,
        "leftCensoredEpisodes": left_censored_count,
        "byState": dict(sorted(state_counts.items())),
        "byClass": dict(sorted(class_counts.items())),
        "policy": {
            "runPinned": True,
            "exactExperimentOnly": True,
            "eventDerivedOnly": True,
            "sourceEventRulesPinned": True,
            "usesDiagnosticReplay": False,
            "usesTelemetry": False,
            "usesPostRunTelemetry": False,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
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
