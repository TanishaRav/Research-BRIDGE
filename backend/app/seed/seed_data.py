from __future__ import annotations

import argparse
import json

from backend.app.db import Database, create_database
from backend.app.repositories.sqlite import SQLiteRepository
from backend.app.seed.generator import generate_snapshot

RESET_CONFIRMATION = "RESET_SYNTHETIC_DEMO"


def seed_database(database: Database, *, reset: bool = False) -> dict[str, int]:
    if reset:
        database.recreate()
    snapshot = generate_snapshot()
    repository = SQLiteRepository(database)
    repository.load_snapshot(snapshot, event_type="reset" if reset else "seed_completed")
    counts = {
        "students": len(repository.list_students()),
        "faculty": len(repository.list_faculty()),
        "projects": len(repository.list_projects()),
        "skills": len(repository.list_skills()),
    }
    if counts["students"] != 60 or counts["projects"] != 20:
        raise RuntimeError(f"seed count invariant failed: {counts}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the local synthetic ResearchBridge demo")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if args.reset and args.confirm != RESET_CONFIRMATION:
        parser.error(f"--reset requires --confirm {RESET_CONFIRMATION}")
    database = create_database()
    counts = seed_database(database, reset=args.reset)
    print(
        json.dumps(
            {
                "seed": 731,
                "synthetic_only": True,
                "reset": args.reset,
                "counts": counts,
                "notice": (
                    "Every student is synthetic, every faculty identity is fictional, and "
                    "every opening is hypothetical."
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
