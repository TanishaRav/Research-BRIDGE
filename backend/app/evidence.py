from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.app.config import Settings
from backend.app.db import create_database
from backend.app.repositories.sqlite import SQLiteRepository
from backend.app.seed.seed_data import seed_database
from backend.app.services.evaluation import run_shuffle_test
from backend.app.services.runs import create_match_run

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "evidence"


def generate_evidence() -> tuple[Path, Path, dict]:
    settings = Settings(database_url="sqlite:///:memory:", solver_timeout_seconds=10)
    database = create_database(settings.database_url)
    counts = seed_database(database)
    repository = SQLiteRepository(database)
    run = create_match_run(repository, settings)
    students = repository.list_students(submitted_only=True)
    projects = repository.list_projects()
    pair_scores = repository.list_pair_scores(run.id)
    assignments = repository.list_assignments(run.id)
    config = repository.get_config()
    shuffle = run_shuffle_test(
        students,
        projects,
        pair_scores,
        config.threshold_bp,
        assignments,
        timeout_seconds=settings.solver_timeout_seconds,
    )
    repository.save_shuffle_evidence(run.id, shuffle)
    run = repository.get_run(run.id)
    assert run is not None and run.benchmark_evidence is not None

    payload = {
        "schema_version": "1.0",
        "synthetic_only": True,
        "independent_prototype": True,
        "seed": 731,
        "counts": counts,
        "run_id": run.id,
        "input_snapshot_hash": run.input_snapshot_hash,
        "status": run.status.value,
        "placement_count": run.placement_count,
        "total_score_bp": run.total_score_bp,
        "minimum_score_bp": run.minimum_score_bp,
        "runtime_ms": str(run.runtime_ms),
        "solver_seed": run.solver_seed,
        "worker_count": run.worker_count,
        "score_version": run.score_version,
        "optimality_limitation": run.optimality_limitation,
        "benchmark": run.benchmark_evidence.model_dump(mode="json"),
        "shuffle": shuffle.model_dump(mode="json"),
        "limitation": (
            "Synthetic evaluation cannot establish actual rematching reduction or demographic "
            "fairness. A pilot must measure acceptance, withdrawal, rematching rounds, and "
            "time-to-placement."
        ),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "seeded-benchmark.json"
    csv_path = OUTPUT_DIR / "seeded-benchmark.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "strategy",
                "label",
                "placement_count",
                "submitted_count",
                "eligible_count",
                "placement_rate_submitted",
                "placement_rate_eligible",
                "mean_score",
                "median_score",
                "bottom_decile_score",
                "minimum_score",
                "top_choice_rate",
                "first_time_placement_rate",
                "constraint_violations",
                "runtime_ms",
                "synthetic_limitation",
            ],
        )
        writer.writeheader()
        for strategy, metrics in run.benchmark_evidence.strategies.items():
            writer.writerow(
                {
                    "strategy": strategy,
                    "label": metrics.label,
                    "placement_count": metrics.placement_count,
                    "submitted_count": metrics.submitted_count,
                    "eligible_count": metrics.eligible_count,
                    "placement_rate_submitted": metrics.placement_rate_submitted,
                    "placement_rate_eligible": metrics.placement_rate_eligible,
                    "mean_score": metrics.mean_score,
                    "median_score": metrics.median_score,
                    "bottom_decile_score": metrics.bottom_decile_score,
                    "minimum_score": metrics.minimum_score,
                    "top_choice_rate": metrics.top_choice_rate,
                    "first_time_placement_rate": metrics.first_time_placement_rate,
                    "constraint_violations": metrics.constraint_violations["total"],
                    "runtime_ms": metrics.runtime_ms,
                    "synthetic_limitation": payload["limitation"],
                }
            )
    return json_path, csv_path, payload


def main() -> None:
    json_path, csv_path, payload = generate_evidence()
    strategies = payload["benchmark"]["strategies"]
    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "global_placements": strategies["global"]["placement_count"],
                "greedy_placements": strategies["greedy"]["placement_count"],
                "fcfs_placements": strategies["fcfs"]["placement_count"],
                "shuffle_pass_count": payload["shuffle"]["identical_assignment_pass_count"],
                "synthetic_only": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
