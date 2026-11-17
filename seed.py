"""Seed the SPARK demo database with synthetic, idempotent data.

Populates:
  - org units (University -> Biology dept, Materials Engineering dept),
  - departments, majors/minors, and related_majors links (biology ~
    biomedical engineering, bioinformatics, computational biology; R5.2),
  - synthetic faculty + undergraduate accounts (PBKDF2-hashed passwords),
  - two match_sessions:
      1. mutual-preference Biology session, mid-lifecycle (preferencing) with
         projects, eligible majors, student profiles, and ranked preferences,
      2. student-preference Materials Engineering session with projects.

Run:  python seed.py
It recreates spark.db so repeated runs are idempotent, then prints the demo
login credentials.
"""

from app import db
from app.server import hash_password

DEMO_PASSWORD = "sparkdemo123"


def _user(conn, email, display_name, given, family, role, org_unit_id=None, blocked=0):
    pw_hash, salt, iters = hash_password(DEMO_PASSWORD)
    return db.insert(
        conn, "users",
        email=email, display_name=display_name, given_name=given,
        family_name=family, role=role, org_unit_id=org_unit_id,
        password_hash=pw_hash, password_salt=salt, password_iter=iters,
        is_blocked=blocked, updated_at=db.utcnow(),
    )


def _relate(conn, a, b, weight=1.0):
    # Symmetric relatedness: store both directions.
    db.insert(conn, "related_majors", major_id=a, related_major_id=b, weight=weight)
    db.insert(conn, "related_majors", major_id=b, related_major_id=a, weight=weight)


def seed():
    db.reset_db()
    conn = db.connect()
    try:
        now = db.utcnow()

        # --- Org units -----------------------------------------------------
        university = db.insert(conn, "org_units", name="State University", kind="university", updated_at=now)
        bio_unit = db.insert(conn, "org_units", name="Department of Biology", kind="department", parent_id=university, updated_at=now)
        mse_unit = db.insert(conn, "org_units", name="Materials Engineering", kind="department", parent_id=university, updated_at=now)

        # --- Departments ---------------------------------------------------
        bio_dept = db.insert(conn, "departments", name="Biology", org_unit_id=bio_unit, updated_at=now)
        mse_dept = db.insert(conn, "departments", name="Materials Engineering", org_unit_id=mse_unit, updated_at=now)

        # --- Majors / minors + relatedness (R5.2) --------------------------
        biology = db.insert(conn, "majors", name="Biology", kind="major", department_id=bio_dept, updated_at=now)
        biomed_eng = db.insert(conn, "majors", name="Biomedical Engineering", kind="major", department_id=bio_dept, updated_at=now)
        bioinformatics = db.insert(conn, "majors", name="Bioinformatics", kind="major", department_id=bio_dept, updated_at=now)
        comp_bio = db.insert(conn, "majors", name="Computational Biology", kind="major", department_id=bio_dept, updated_at=now)
        mat_eng = db.insert(conn, "majors", name="Materials Engineering", kind="major", department_id=mse_dept, updated_at=now)
        chem = db.insert(conn, "majors", name="Chemistry", kind="major", department_id=mse_dept, updated_at=now)
        db.insert(conn, "majors", name="Data Science", kind="minor", department_id=bio_dept, updated_at=now)

        _relate(conn, biology, biomed_eng, 0.8)
        _relate(conn, biology, bioinformatics, 0.9)
        _relate(conn, biology, comp_bio, 0.9)
        _relate(conn, mat_eng, chem, 0.7)

        # --- Users ---------------------------------------------------------
        admin = _user(conn, "admin@spark.edu", "Site Admin", "Sam", "Admin", "admin", university)
        manager = _user(conn, "manager@spark.edu", "Session Manager", "Morgan", "Lee", "manager", bio_unit)

        # Faculty
        prof_bio1 = _user(conn, "rivera@spark.edu", "Dr. Rivera", "Elena", "Rivera", "faculty", bio_unit)
        prof_bio2 = _user(conn, "okafor@spark.edu", "Dr. Okafor", "Chidi", "Okafor", "faculty", bio_unit)
        prof_mse1 = _user(conn, "nakamura@spark.edu", "Dr. Nakamura", "Kenji", "Nakamura", "faculty", mse_unit)

        # Undergraduates (one blocked for the auth demo)
        students = []
        student_specs = [
            ("ava@spark.edu", "Ava Chen", "Ava", "Chen", [biology, bioinformatics]),
            ("ben@spark.edu", "Ben Flores", "Ben", "Flores", [biology]),
            ("cara@spark.edu", "Cara Singh", "Cara", "Singh", [comp_bio, biology]),
            ("dev@spark.edu", "Dev Patel", "Dev", "Patel", [biomed_eng]),
            ("eli@spark.edu", "Eli Novak", "Eli", "Novak", [mat_eng]),
            ("fay@spark.edu", "Fay Osei", "Fay", "Osei", [mat_eng, chem]),
        ]
        for email, dn, gn, fn, majors in student_specs:
            uid = _user(conn, email, dn, gn, fn, "student")
            students.append((uid, majors))

        blocked_student = _user(conn, "blocked@spark.edu", "Blocked Student", "Bea", "Locke", "student", blocked=1)

        # --- Session 1: Biology, mutual-preference, mid-lifecycle ----------
        bio_session = db.insert(
            conn, "match_sessions",
            name="Biology Research Match (Spring)", org_unit_id=bio_unit,
            mode="mutual", matching_method="mutual", weighting="equal",
            status="preferencing", timezone="America/Chicago",
            favorite_invites=1, show_ratings=1,
            description="Mutual-preference matching for the Biology department.",
            updated_at=now,
        )
        db.insert(conn, "session_managers", session_id=bio_session, user_id=manager)

        bio_projects = []
        bio_project_specs = [
            (prof_bio1, "CRISPR gene regulation in zebrafish", 2, [biology, bioinformatics, comp_bio]),
            (prof_bio2, "Microbiome diversity in soil samples", 1, [biology, comp_bio]),
            (prof_bio1, "Protein folding simulation pipeline", 2, [bioinformatics, comp_bio, biomed_eng]),
        ]
        for mentor, title, cap, elig in bio_project_specs:
            pid = db.insert(
                conn, "projects", session_id=bio_session, title=title,
                description="A hands-on undergraduate research project.",
                positions=cap, capacity=cap, major_policy="prefer",
                primary_department_id=bio_dept, status="published", updated_at=now,
            )
            db.insert(conn, "project_mentors", project_id=pid, user_id=mentor,
                      role="faculty", is_pi=1, permission="editor")
            for mid in elig:
                db.insert(conn, "project_eligible_majors", project_id=pid, major_id=mid)
            bio_projects.append(pid)

        # Student profiles + student->project preferences (mid-lifecycle).
        bio_students = students[:4]
        for idx, (uid, majors) in enumerate(bio_students):
            profile_id = db.insert(
                conn, "student_profiles", user_id=uid, session_id=bio_session,
                year="junior", gpa=3.4 + idx * 0.1,
                bio="Interested in molecular biology research.",
                interests="Molecular biology, genetics, and lab techniques.",
                time_kind="credit", credit_option="2",
                submitted=1, updated_at=now,
            )
            for mpos, mid in enumerate(majors):
                db.insert(conn, "profile_majors", profile_id=profile_id,
                          major_id=mid, kind="major" if mpos == 0 else "secondary")
            # Ranked student preferences across the three projects.
            ordering = bio_projects[idx % len(bio_projects):] + bio_projects[:idx % len(bio_projects)]
            for rank, pid in enumerate(ordering, start=1):
                db.insert(
                    conn, "preferences", session_id=bio_session, actor_role="student",
                    student_id=uid, project_id=pid, rank=rank, updated_at=now,
                )

        # Faculty/project->student preferences (mutual mode).
        for p_idx, pid in enumerate(bio_projects):
            ordering = bio_students[p_idx % len(bio_students):] + bio_students[:p_idx % len(bio_students)]
            for rank, (uid, _m) in enumerate(ordering, start=1):
                db.insert(
                    conn, "preferences", session_id=bio_session, actor_role="project",
                    student_id=uid, project_id=pid, rank=rank, updated_at=now,
                )

        # --- Session 2: Materials Engineering, student-preference ----------
        mse_session = db.insert(
            conn, "match_sessions",
            name="Materials Engineering Match (Spring)", org_unit_id=mse_unit,
            mode="student", matching_method="student", weighting="equal",
            status="open", timezone="America/Chicago",
            description="Student-preference matching for Materials Engineering.",
            updated_at=now,
        )
        db.insert(conn, "session_managers", session_id=mse_session, user_id=manager)

        mse_project_specs = [
            (prof_mse1, "Fatigue testing of 3D-printed alloys", 2, [mat_eng, chem]),
            (prof_mse1, "Polymer composites for aerospace", 1, [mat_eng]),
        ]
        for mentor, title, cap, elig in mse_project_specs:
            pid = db.insert(
                conn, "projects", session_id=mse_session, title=title,
                description="A hands-on undergraduate research project.",
                positions=cap, capacity=cap, major_policy="prefer",
                primary_department_id=mse_dept, status="published", updated_at=now,
            )
            db.insert(conn, "project_mentors", project_id=pid, user_id=mentor,
                      role="faculty", is_pi=1, permission="editor")
            for mid in elig:
                db.insert(conn, "project_eligible_majors", project_id=pid, major_id=mid)

        # --- Ratings (R12.1) ----------------------------------------------
        # The Biology session has show_ratings on. Give Dr. Rivera >= 5 distinct
        # raters so an average surfaces; give Dr. Okafor only a few so the
        # >=5-rater threshold visibly suppresses their average.
        rater_ids = [uid for uid, _m in students] + [manager]
        rivera_stars = [5, 4, 5, 4, 5, 3]  # 6 distinct raters
        for rid, stars in zip(rater_ids, rivera_stars):
            db.insert(conn, "ratings", session_id=bio_session, rater_id=rid,
                      subject_id=prof_bio1, stars=stars,
                      comment="Great mentor.", updated_at=now)
        for rid, stars in zip(rater_ids[:3], [5, 4, 4]):  # only 3 raters
            db.insert(conn, "ratings", session_id=bio_session, rater_id=rid,
                      subject_id=prof_bio2, stars=stars,
                      comment="Helpful.", updated_at=now)

        conn.commit()
    finally:
        conn.close()

    _print_credentials()


def _print_credentials():
    print("")
    print("SPARK demo database seeded (spark.db).")
    print("All accounts use password: %s" % DEMO_PASSWORD)
    print("")
    print("Demo logins:")
    print("  admin@spark.edu      admin    (site administrator)")
    print("  manager@spark.edu    manager  (manages both sessions)")
    print("  rivera@spark.edu     faculty  (Biology projects)")
    print("  nakamura@spark.edu   faculty  (Materials Engineering projects)")
    print("  ava@spark.edu        student  (Biology, has ranked preferences)")
    print("  eli@spark.edu        student  (Materials Engineering)")
    print("  blocked@spark.edu    student  (BLOCKED - cannot log in, R1.6 demo)")
    print("")
    print("Sessions:")
    print("  1. Biology Research Match (Spring)   mode=mutual   status=preferencing (mid-lifecycle)")
    print("  2. Materials Engineering Match       mode=student  status=open")
    print("")


if __name__ == "__main__":
    seed()
