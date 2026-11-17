from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from backend.app.domain.models import (
    ImportSnapshot,
    ImportValidationReport,
    ValidationIssue,
)


class LocalSnapshotAdapter:
    source_name = "researchbridge-local-synthetic-json"
    schema_version = "1.0"

    def validate(self, payload: bytes, media_type: str = "application/json") -> ImportValidationReport:
        if media_type.split(";", 1)[0].strip() not in {"application/json", "text/json"}:
            return ImportValidationReport(
                valid=False,
                issues=[
                    ValidationIssue(
                        path="$",
                        code="unsupported_media_type",
                        message="The local adapter accepts JSON snapshots only.",
                    )
                ],
                counts={},
            )
        try:
            raw = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return ImportValidationReport(
                valid=False,
                issues=[
                    ValidationIssue(path="$", code="invalid_json", message=str(exc))
                ],
                counts={},
            )
        return validate_import_data(raw)

    def load_snapshot(
        self, payload: bytes, media_type: str = "application/json"
    ) -> ImportSnapshot:
        report = self.validate(payload, media_type)
        if not report.valid:
            raise ValueError("snapshot did not pass validation")
        return ImportSnapshot.model_validate_json(payload)


class MockWorkdayAdapter:
    """Hypothetical contract only. It performs no network or institutional-system calls."""

    source_name = "mock-workday-contract-no-network"
    schema_version = "1.0"
    approved_fields = (
        "opaque_external_person_id",
        "opaque_external_project_id",
        "effective_term",
        "affiliation_status",
        "change_cursor",
    )

    def validate(self, payload: bytes, media_type: str) -> ImportValidationReport:
        return ImportValidationReport(
            valid=False,
            issues=[
                ValidationIssue(
                    path="$",
                    code="mock_adapter_only",
                    message=(
                        "The mock Workday adapter documents a hypothetical contract and never "
                        "loads or sends institutional data."
                    ),
                )
            ],
            counts={},
            schema_version=self.schema_version,
        )

    def load_snapshot(self, payload: bytes, media_type: str) -> ImportSnapshot:
        raise RuntimeError("MockWorkdayAdapter has no live data-loading implementation")


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def validate_import_data(raw: Any) -> ImportValidationReport:
    if not isinstance(raw, dict):
        return ImportValidationReport(
            valid=False,
            issues=[
                ValidationIssue(
                    path="$", code="invalid_root", message="Snapshot root must be an object."
                )
            ],
            counts={},
        )
    counts = {
        key: len(raw.get(key, [])) if isinstance(raw.get(key), list) else 0
        for key in ("students", "faculty", "projects", "skills")
    }
    issues: list[ValidationIssue] = []
    try:
        snapshot = ImportSnapshot.model_validate(raw)
    except ValidationError as exc:
        for error in exc.errors(include_url=False, include_input=False):
            path = ".".join(str(part) for part in error["loc"])
            issues.append(
                ValidationIssue(
                    path=path or "$",
                    code=str(error["type"]),
                    message=str(error["msg"]),
                )
            )
        return ImportValidationReport(
            valid=False,
            issues=issues,
            counts=counts,
            schema_version=str(raw.get("schema_version")) if raw.get("schema_version") else None,
        )

    for collection_name, entities in (
        ("students", snapshot.students),
        ("faculty", snapshot.faculty),
        ("projects", snapshot.projects),
        ("skills", snapshot.skills),
    ):
        for duplicate in _duplicates([entity.id for entity in entities]):
            issues.append(
                ValidationIssue(
                    path=collection_name,
                    code="duplicate_identifier",
                    message=f"Duplicate stable identifier: {duplicate}",
                )
            )

    faculty_ids = {faculty.id for faculty in snapshot.faculty}
    project_ids = {project.id for project in snapshot.projects}
    skill_ids = {skill.id for skill in snapshot.skills}
    for index, project in enumerate(snapshot.projects):
        if project.faculty_id not in faculty_ids:
            issues.append(
                ValidationIssue(
                    path=f"projects.{index}.faculty_id",
                    code="unknown_reference",
                    message=f"Unknown faculty identifier: {project.faculty_id}",
                )
            )
        for skill_index, relation in enumerate(project.skills):
            if relation.skill_id not in skill_ids:
                issues.append(
                    ValidationIssue(
                        path=f"projects.{index}.skills.{skill_index}.skill_id",
                        code="unknown_reference",
                        message=f"Unknown skill identifier: {relation.skill_id}",
                    )
                )
        for prerequisite_index, skill_id in enumerate(project.prerequisites):
            if skill_id not in skill_ids:
                issues.append(
                    ValidationIssue(
                        path=f"projects.{index}.prerequisites.{prerequisite_index}",
                        code="unknown_reference",
                        message=f"Unknown prerequisite skill identifier: {skill_id}",
                    )
                )

    for index, student in enumerate(snapshot.students):
        for skill_index, relation in enumerate(student.skills):
            if relation.skill_id not in skill_ids:
                issues.append(
                    ValidationIssue(
                        path=f"students.{index}.skills.{skill_index}.skill_id",
                        code="unknown_reference",
                        message=f"Unknown skill identifier: {relation.skill_id}",
                    )
                )
        for preference_index, preference in enumerate(student.preferences):
            if preference.project_id not in project_ids:
                issues.append(
                    ValidationIssue(
                        path=f"students.{index}.preferences.{preference_index}.project_id",
                        code="unknown_reference",
                        message=f"Unknown project identifier: {preference.project_id}",
                    )
                )

    if snapshot.source_manifest.get("synthetic_only") is not True:
        issues.append(
            ValidationIssue(
                path="source_manifest.synthetic_only",
                code="synthetic_boundary_required",
                message="The local demo imports only snapshots explicitly marked synthetic_only=true.",
            )
        )
    return ImportValidationReport(
        valid=not issues,
        issues=issues,
        counts=counts,
        schema_version=snapshot.schema_version,
    )
