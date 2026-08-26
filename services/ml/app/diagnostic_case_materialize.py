from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, select

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.diagnostic_case_rules import (
    CASE_ACTIVITY_CREATED,
    CASE_OPEN,
    CASE_RULES_VERSION,
    CASE_SOURCE_EPISODE_RULES_VERSION,
    derive_case_review_priority,
)
from fleetmind_common.diagnostic_store import (
    DiagnosticCase,
    DiagnosticCaseActivity,
    DiagnosticEpisode,
    DiagnosticModelRun,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize run-pinned operational diagnostic cases from "
            "persisted DiagnosticEpisode rows."
        )
    )
    parser.add_argument(
        "--run-id",
        type=int,
        required=True,
        help="Persisted diagnostic_model_runs.id to materialize.",
    )
    return parser.parse_args()


def _json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _title(hypothesis_class: str, vehicle_id: str) -> str:
    label = hypothesis_class.replace("_", " ").title()
    return f"{label} hypothesis · {vehicle_id}"


def materialize_cases(run_id: int) -> dict:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        run = db.get(DiagnosticModelRun, run_id)
        if run is None:
            raise ValueError(f"Diagnostic run {run_id} does not exist")
        if not run.champion:
            raise ValueError(
                "Diagnostic run has no persisted champion; "
                "cases require a completed diagnostic model run"
            )

        episodes = db.execute(
            select(DiagnosticEpisode)
            .where(
                DiagnosticEpisode.run_id == run.id,
                DiagnosticEpisode.experiment_id == run.experiment_id,
                DiagnosticEpisode.is_open.is_(True),
            )
            .order_by(
                DiagnosticEpisode.vehicle_id,
                DiagnosticEpisode.start_timestamp,
                DiagnosticEpisode.id,
            )
        ).scalars().all()

        if not episodes:
            return {
                "status": "no_eligible_episodes",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "rulesVersion": CASE_RULES_VERSION,
                "sourceEpisodeRulesVersion": (
                    CASE_SOURCE_EPISODE_RULES_VERSION
                ),
                "eligibleEpisodes": 0,
                "createdCases": 0,
                "existingCases": 0,
                "policy": _policy(),
            }

        mismatched = [
            row.id
            for row in episodes
            if row.rules_version != CASE_SOURCE_EPISODE_RULES_VERSION
        ]
        if mismatched:
            raise ValueError(
                "Episode rules version does not match the case source "
                f"contract; mismatched episode ids: {mismatched[:10]}"
            )

        episode_ids = [row.id for row in episodes]
        existing_rows = db.execute(
            select(DiagnosticCase).where(
                DiagnosticCase.run_id == run.id,
                DiagnosticCase.episode_id.in_(episode_ids),
            )
        ).scalars().all()
        existing_episode_ids = {row.episode_id for row in existing_rows}

        generated_at = datetime.now(timezone.utc)
        created: list[DiagnosticCase] = []

        for episode in episodes:
            if episode.id in existing_episode_ids:
                continue

            episode_details = _json_object(episode.details_json)
            priority = derive_case_review_priority(
                episode_state=episode.state,
                latest_confidence=episode.latest_confidence,
                escalation_count=int(episode.escalation_count),
                destabilized_count=int(episode.destabilized_count),
            )

            case = DiagnosticCase(
                run_id=run.id,
                experiment_id=run.experiment_id,
                episode_id=episode.id,
                created_at=generated_at,
                updated_at=generated_at,
                last_activity_at=generated_at,
                vehicle_id=episode.vehicle_id,
                hypothesis_class=episode.hypothesis_class,
                rules_version=CASE_RULES_VERSION,
                source_episode_rules_version=episode.rules_version,
                source_event_rules_version=episode.source_event_rules_version,
                episode_state_at_creation=episode.state,
                status=CASE_OPEN,
                review_priority=priority,
                assigned_to=None,
                title=_title(
                    episode.hypothesis_class,
                    episode.vehicle_id,
                ),
                start_timestamp=episode.start_timestamp,
                start_mileage=float(episode.start_mileage),
                latest_timestamp=episode.end_timestamp,
                latest_mileage=float(episode.end_mileage),
                latest_confidence=episode.latest_confidence,
                peak_confidence=episode.peak_confidence,
                event_count=int(episode.event_count),
                left_censored=bool(episode.left_censored),
                note_count=0,
                details_json=json.dumps(
                    {
                        "source": "diagnostic_episodes",
                        "sourceEpisodeId": episode.id,
                        "sourceEpisodeState": episode.state,
                        "sourceEpisodeStartReason": episode.start_reason,
                        "continuationCount": int(
                            episode_details.get("continuationCount", 0) or 0
                        ),
                        "casePriorityPolicy": (
                            "review heuristic only; not calibrated "
                            "failure risk"
                        ),
                    },
                    sort_keys=True,
                ),
            )
            db.add(case)
            db.flush()

            db.add(
                DiagnosticCaseActivity(
                    case_id=case.id,
                    run_id=run.id,
                    experiment_id=run.experiment_id,
                    vehicle_id=episode.vehicle_id,
                    created_at=generated_at,
                    activity_type=CASE_ACTIVITY_CREATED,
                    actor="system",
                    from_value=None,
                    to_value=CASE_OPEN,
                    note_text=None,
                    details_json=json.dumps(
                        {
                            "sourceEpisodeId": episode.id,
                            "initialPriority": priority,
                            "episodeState": episode.state,
                        },
                        sort_keys=True,
                    ),
                )
            )
            created.append(case)

        db.commit()

        by_priority = Counter(row.review_priority for row in created)
        by_class = Counter(row.hypothesis_class for row in created)

        total_for_run = int(
            db.scalar(
                select(func.count(DiagnosticCase.id)).where(
                    DiagnosticCase.run_id == run.id,
                    DiagnosticCase.experiment_id == run.experiment_id,
                )
            )
            or 0
        )

        if created:
            status = (
                "populated"
                if not existing_rows
                else "synchronized"
            )
        else:
            status = "already_populated"

        return {
            "status": status,
            "runId": run.id,
            "experimentId": run.experiment_id,
            "lineage": run.lineage,
            "champion": run.champion,
            "rulesVersion": CASE_RULES_VERSION,
            "sourceEpisodeRulesVersion": (
                CASE_SOURCE_EPISODE_RULES_VERSION
            ),
            "eligibleEpisodes": len(episodes),
            "createdCases": len(created),
            "existingCases": len(existing_rows),
            "totalCases": total_for_run,
            "byPriorityCreated": dict(sorted(by_priority.items())),
            "byClassCreated": dict(sorted(by_class.items())),
            "policy": _policy(),
        }


def _policy() -> dict:
    return {
        "runPinned": True,
        "exactExperimentOnly": True,
        "episodeDerivedOnly": True,
        "sourceEpisodeRulesPinned": True,
        "existingWorkflowPreserved": True,
        "usesDiagnosticEvents": False,
        "usesDiagnosticReplay": False,
        "usesPredictions": False,
        "usesTelemetry": False,
        "usesPostRunTelemetry": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "benchmarkModified": False,
        "modelRetrained": False,
    }


def main() -> None:
    args = _parse_args()
    print(json.dumps(materialize_cases(args.run_id), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
