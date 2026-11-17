from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from backend.app.domain.models import (
    Faculty,
    HYPOTHETICAL_LABEL,
    ImportSnapshot,
    Project,
    ProjectSkill,
    ProvenanceType,
    Skill,
    SkillKind,
    Student,
    StudentPreference,
    StudentSkill,
    SYNTHETIC_LABEL,
    TimeWindow,
    WindowPurpose,
)
from backend.app.services.scoring import profile_missing_fields

SEED = 731
FIXED_TIME = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

PROJECT_TEMPLATES: list[tuple[str, str, list[str], str, str]] = [
    ("Computer Science", "Responsible data systems", ["python", "database"], "data-visualization", "offline data quality"),
    ("Statistics", "Survey uncertainty", ["statistics", "r"], "writing", "uncertainty communication"),
    ("Ecology", "Prairie sensor patterns", ["ecology", "statistics"], "gis", "synthetic habitat sensing"),
    ("Mechanical Engineering", "Accessible device prototyping", ["cad"], "electronics", "inclusive prototyping"),
    ("Bioinformatics", "Synthetic genome workflow", ["python", "bioinformatics"], "statistics", "reproducible biology"),
    ("Sociology", "Community narrative methods", ["interviewing"], "qualitative-analysis", "ethical qualitative methods"),
    ("Geography", "Heat-map validation", ["gis", "statistics"], "python", "geospatial validation"),
    ("English", "Digital archive description", ["writing", "literature-review"], "web-development", "accessible archives"),
    ("Electrical Engineering", "Low-power sensor bench", ["electronics"], "python", "sensor calibration"),
    ("Psychology", "Open behavioral protocol", ["statistics", "ethics"], "r", "transparent analysis"),
    ("Agronomy", "Crop image annotation", ["ecology"], "machine-learning", "responsible image models"),
    ("Industrial Design", "Lab tool usability", ["cad", "interviewing"], "qualitative-analysis", "usability evidence"),
    ("Computer Science", "Explainable model cards", ["python", "machine-learning"], "writing", "model documentation"),
    ("Public Health", "Resource access mapping", ["gis"], "statistics", "equitable mapping methods"),
    ("Chemistry", "Reproducible sample log", ["laboratory", "ethics"], "database", "laboratory data practice"),
    ("Education", "Mentoring feedback study", ["literature-review", "interviewing"], "qualitative-analysis", "mentoring feedback"),
    ("Architecture", "Daylight simulation study", ["cad"], "data-visualization", "environmental design"),
    ("Computer Engineering", "Edge-device telemetry", ["electronics", "python"], "database", "reliable telemetry"),
    ("Statistics", "Inactive historical demo", ["statistics"], "r", "inactive fixture"),
    ("Ecology", "Zero-capacity watershed demo", ["ecology", "gis"], "writing", "capacity fixture"),
]

MAJORS = [
    "Computer Science",
    "Statistics",
    "Biology",
    "Mechanical Engineering",
    "Sociology",
    "Design",
    "Environmental Science",
    "English",
]
YEARS = ["First year", "Second year", "Third year", "Fourth year"]


def _load_json(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def generate_skills() -> list[Skill]:
    taxonomy = _load_json("taxonomy.v1.json")
    return [
        Skill(
            id=item["id"],
            label=item["label"],
            category=item["category"],
            aliases=item["aliases"],
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
        for item in taxonomy["skills"]
    ]


def generate_faculty() -> list[Faculty]:
    departments = [template[0] for template in PROJECT_TEMPLATES]
    return [
        Faculty(
            id=f"faculty-fictional-{index:03d}",
            display_name=f"Fictional Faculty Mentor {index:02d} (demo)",
            department=departments[(index - 1) * 2],
            research_interests=[
                PROJECT_TEMPLATES[(index - 1) * 2][1],
                PROJECT_TEMPLATES[(index - 1) * 2 + 1][1],
            ],
            provenance_type=ProvenanceType.FICTIONAL,
            provenance_label="Fictional faculty identity created for the synthetic demo",
            source_url=None,
            source_retrieved_at="2026-11-17",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
        for index in range(1, 11)
    ]


def _student_day_windows() -> list[TimeWindow]:
    return [
        TimeWindow(
            day=day,
            start_minute=8 * 60,
            end_minute=17 * 60,
            fixed=False,
            purpose=WindowPurpose.AVAILABILITY,
        )
        for day in range(5)
    ]


def generate_projects() -> list[Project]:
    projects: list[Project] = []
    for index, (department, interest, mandatory, trainable, description_topic) in enumerate(
        PROJECT_TEMPLATES, start=1
    ):
        required_windows: list[TimeWindow] = []
        if index in {3, 7, 11, 15}:
            required_windows.append(
                TimeWindow(
                    day=1,
                    start_minute=13 * 60,
                    end_minute=14 * 60,
                    fixed=True,
                    purpose=WindowPurpose.REQUIRED,
                )
            )
        mentoring_windows = [
            TimeWindow(
                day=(index + 1) % 5,
                start_minute=14 * 60,
                end_minute=16 * 60,
                fixed=False,
                purpose=WindowPurpose.MENTORING,
            )
        ]
        capacity = 2 if index == 1 else (1 + index % 3)
        if index == 20:
            capacity = 0
        project_skills = [
            ProjectSkill(
                skill_id=skill_id,
                required_proficiency=2 if skill_id not in {"ethics", "literature-review"} else 1,
                kind=SkillKind.MANDATORY,
            )
            for skill_id in mandatory
        ]
        project_skills.append(
            ProjectSkill(
                skill_id=trainable,
                required_proficiency=2,
                kind=SkillKind.TRAINABLE,
            )
        )
        projects.append(
            Project(
                id=f"project-hyp-{index:03d}",
                faculty_id=f"faculty-fictional-{((index - 1) // 2) + 1:03d}",
                title=f"Hypothetical Project {index:02d}: {interest}",
                description=(
                    f"A fictional, synthetic-data project opening about {description_topic}. "
                    "The title, availability, capacity, schedule, and prerequisites are hypothetical."
                ),
                department=department,
                interests=[interest, mandatory[0]],
                capacity=capacity,
                prerequisites=[mandatory[0]],
                mentoring_available=True,
                commitment_hours=Decimal(6 + index % 4),
                term="Synthetic Fall Term",
                modality=["In person", "Hybrid", "Remote demo"][(index - 1) % 3],
                active=index != 19,
                provenance_type=ProvenanceType.HYPOTHETICAL,
                provenance_label=HYPOTHETICAL_LABEL,
                source_url=None,
                source_note=(
                    "All opening details are fictional and are not an advertised Iowa State position."
                ),
                skills=project_skills,
                required_windows=required_windows,
                mentoring_windows=mentoring_windows,
                created_at=FIXED_TIME,
                updated_at=FIXED_TIME,
            )
        )
    return projects


def generate_students(projects: list[Project]) -> list[Student]:
    rng = random.Random(SEED)
    submission_orders = list(range(1, 61))
    rng.shuffle(submission_orders)
    by_id = {project.id: project for project in projects}
    students: list[Student] = []
    for index in range(1, 61):
        primary_number = 1 if index <= 20 else ((index - 1) % 18) + 1
        if index == 12:
            primary_number = 3
        primary_id = f"project-hyp-{primary_number:03d}"
        secondary_number = (primary_number % 18) + 1
        tertiary_number = ((primary_number + 5) % 18) + 1
        preference_ids = list(dict.fromkeys(
            [primary_id, f"project-hyp-{secondary_number:03d}", f"project-hyp-{tertiary_number:03d}"]
        ))
        if index == 15:
            preference_ids = ["project-hyp-020"]
        primary = by_id[primary_id]
        levels: dict[str, int] = {}
        for requirement in primary.skills:
            if requirement.kind == SkillKind.MANDATORY:
                levels[requirement.skill_id] = requirement.required_proficiency
            else:
                levels[requirement.skill_id] = max(0, requirement.required_proficiency - 1)
        if index >= 51:
            levels = {skill_id: 0 for skill_id in levels}
        skills = [
            StudentSkill(skill_id=skill_id, proficiency=proficiency)
            for skill_id, proficiency in sorted(levels.items())
        ]
        interests = list(primary.interests)
        if index == 7:
            interests.extend(["qualitative methods", "accessible design", "ecology"])
        availability = _student_day_windows()
        if index == 12:
            availability = [
                TimeWindow(
                    day=5,
                    start_minute=9 * 60,
                    end_minute=12 * 60,
                    purpose=WindowPurpose.AVAILABILITY,
                )
            ]
        if index == 14:
            availability = []
        hours: Decimal | None = Decimal(12 + index % 5)
        if index == 13:
            hours = None
        display_name = f"Synthetic Learner {index:02d}"
        if index in {5, 6}:
            display_name = "Synthetic Learner Duplicate"
        learning_goals = [
            f"Build guided practice in {next((s.skill_id for s in primary.skills if s.kind == SkillKind.TRAINABLE), 'writing')}",
            "Practice research ethics and feedback",
        ]
        if index == 14:
            learning_goals = []
        student = Student(
            id=f"student-syn-{index:03d}",
            synthetic=True,
            synthetic_label=SYNTHETIC_LABEL,
            display_name=display_name,
            major=MAJORS[(index - 1) % len(MAJORS)],
            academic_year=YEARS[(index - 1) % len(YEARS)],
            interests=interests,
            hours_per_week=hours,
            learning_goals=learning_goals,
            first_time_researcher=index % 3 != 0,
            accepts_suggestions=index % 10 == 0,
            profile_complete=False,
            submitted=True,
            synthetic_submission_order=submission_orders[index - 1],
            skills=skills,
            preferences=[
                StudentPreference(project_id=project_id, rank=rank)
                for rank, project_id in enumerate(preference_ids, start=1)
            ],
            availability=availability,
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
        # The two tie fixtures differ only in stable ID/presentation fields, neither of which scores.
        if index == 11:
            reference = students[9]
            student.interests = list(reference.interests)
            student.hours_per_week = reference.hours_per_week
            student.learning_goals = list(reference.learning_goals)
            student.accepts_suggestions = reference.accepts_suggestions
            student.skills = [item.model_copy() for item in reference.skills]
            student.preferences = [item.model_copy() for item in reference.preferences]
            student.availability = [item.model_copy() for item in reference.availability]
        student.profile_complete = not profile_missing_fields(student)
        students.append(student)
    return students


def generate_snapshot() -> ImportSnapshot:
    projects = generate_projects()
    return ImportSnapshot(
        schema_version="1.0",
        students=generate_students(projects),
        faculty=generate_faculty(),
        projects=projects,
        skills=generate_skills(),
        source_manifest=_load_json("source_manifest.json"),
    )
