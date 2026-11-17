from __future__ import annotations

from decimal import Decimal

from backend.app.domain.models import (
    OutreachDraft,
    Project,
    Roadmap,
    RoadmapTask,
    SkillKind,
    Student,
    utc_now,
)
from backend.app.repositories.sqlite import RepositoryNotFound, SQLiteRepository


def _target_for_student(
    repository: SQLiteRepository, student: Student
) -> tuple[Project, str, str | None]:
    run = repository.latest_approved_run()
    if run is None:
        raise RepositoryNotFound("no approved synthetic run is available")
    assignment = next(
        (item for item in repository.list_assignments(run.id) if item.student_id == student.id),
        None,
    )
    if assignment is not None:
        project = repository.get_project(assignment.project_id)
        relationship = "approved_placement"
    else:
        preferred_id = (
            min(student.preferences, key=lambda item: item.rank).project_id
            if student.preferences
            else None
        )
        project = repository.get_project(preferred_id) if preferred_id else None
        relationship = "not_a_placement"
    if project is None:
        raise RepositoryNotFound("no recorded placement or preferred project is available")
    return project, relationship, run.id


def build_roadmap(repository: SQLiteRepository, student: Student) -> Roadmap:
    project, relationship, run_id = _target_for_student(repository, student)
    skills = {skill.id: skill for skill in repository.list_skills()}
    levels = {item.skill_id: item.proficiency for item in student.skills}
    available = student.hours_per_week or Decimal(4)
    weeks = 4 if available <= 6 else (3 if available <= 10 else 2)
    tasks: list[RoadmapTask] = []
    requirements = sorted(
        project.skills,
        key=lambda item: (item.kind != SkillKind.MANDATORY, item.skill_id),
    )
    gaps = [
        requirement
        for requirement in requirements
        if levels.get(requirement.skill_id, 0) < requirement.required_proficiency
    ]
    total_budget = Decimal(weeks) * available
    for index, requirement in enumerate(gaps, start=1):
        current = levels.get(requirement.skill_id, 0)
        raw_hours = Decimal(max(2, (requirement.required_proficiency - current) * 2))
        remaining_budget = max(Decimal(1), total_budget - sum(task.estimated_hours for task in tasks))
        estimated = min(raw_hours, remaining_budget)
        skill = skills.get(requirement.skill_id)
        label = skill.label if skill else requirement.skill_id
        tasks.append(
            RoadmapTask(
                id=f"roadmap-task-{student.id}-{project.id}-{requirement.skill_id}",
                week=((index - 1) % weeks) + 1,
                skill_id=requirement.skill_id,
                category=skill.category if skill else "research",
                priority=requirement.kind.value,
                current_proficiency=current,
                target_proficiency=requirement.required_proficiency,
                concrete_task=(
                    f"Complete a small synthetic practice exercise in {label} at level "
                    f"{requirement.required_proficiency}."
                ),
                estimated_hours=estimated,
                deliverable=f"A short {label} practice artifact using synthetic inputs.",
                success_check=(
                    "Self-check the artifact against the stated project requirement and record "
                    "questions for a mentor; this does not verify mastery."
                ),
            )
        )
    now = utc_now()
    roadmap = Roadmap(
        id=f"roadmap-{run_id}-{student.id}",
        student_id=student.id,
        project_id=project.id,
        run_id=run_id,
        relationship=relationship,
        weeks=weeks,
        tasks=tasks,
        created_at=now,
        updated_at=now,
    )
    return repository.save_roadmap(roadmap)


def build_outreach(repository: SQLiteRepository, student: Student) -> OutreachDraft:
    project, _relationship, run_id = _target_for_student(repository, student)
    faculty = repository.get_faculty(project.faculty_id)
    if faculty is None:
        raise RepositoryNotFound(f"faculty {project.faculty_id} was not found")
    levels = {item.skill_id: item.proficiency for item in student.skills}
    demonstrated = [item.skill_id for item in student.skills if item.proficiency > 0]
    gaps = [
        item.skill_id
        for item in project.skills
        if levels.get(item.skill_id, 0) < item.required_proficiency
    ]
    interest_text = ", ".join(student.interests[:3]) or "the project's recorded topics"
    skill_text = ", ".join(demonstrated[:4]) or "beginner-level research practice"
    gap_sentence = (
        f" I also want to be transparent that I am still developing {', '.join(gaps[:3])}."
        if gaps
        else ""
    )
    availability = (
        f"I have recorded {student.hours_per_week} hours per week of availability."
        if student.hours_per_week is not None
        else "I would like to clarify my weekly availability in a discussion."
    )
    subject = f"Discussion request: {project.title}"
    body = (
        f"Hello {faculty.display_name},\n\n"
        f"I am a synthetic demo student interested in {interest_text}. I am writing about "
        f"{project.title}. My recorded skills include {skill_text}.{gap_sentence} {availability}\n\n"
        "Would you be willing to discuss the project requirements and whether my interests and "
        "learning plan could be a fit? This draft does not state or imply acceptance.\n\n"
        f"Sincerely,\n{student.display_name}\nSynthetic ResearchBridge demo persona"
    )
    now = utc_now()
    draft = OutreachDraft(
        id=f"outreach-{run_id}-{student.id}",
        student_id=student.id,
        project_id=project.id,
        run_id=run_id,
        subject=subject,
        body=body,
        edited_body=body,
        created_at=now,
        updated_at=now,
    )
    return repository.save_outreach(draft)
