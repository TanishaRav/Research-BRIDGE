PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE faculty (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    display_name TEXT NOT NULL,
    department TEXT NOT NULL,
    research_interests_json TEXT NOT NULL,
    provenance_type TEXT NOT NULL CHECK (provenance_type IN ('public', 'fictional')),
    provenance_label TEXT NOT NULL,
    source_url TEXT,
    source_retrieved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE skills (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    label TEXT NOT NULL,
    category TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE students (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    synthetic_label TEXT NOT NULL,
    display_name TEXT NOT NULL,
    major TEXT NOT NULL,
    academic_year TEXT NOT NULL,
    interests_json TEXT NOT NULL,
    hours_per_week NUMERIC,
    learning_goals_json TEXT NOT NULL,
    first_time_researcher INTEGER NOT NULL CHECK (first_time_researcher IN (0, 1)),
    accepts_suggestions INTEGER NOT NULL CHECK (accepts_suggestions IN (0, 1)),
    profile_complete INTEGER NOT NULL CHECK (profile_complete IN (0, 1)),
    submitted INTEGER NOT NULL CHECK (submitted IN (0, 1)),
    synthetic_submission_order INTEGER NOT NULL CHECK (synthetic_submission_order > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    faculty_id TEXT NOT NULL REFERENCES faculty(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    department TEXT NOT NULL,
    interests_json TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity >= 0),
    prerequisites_json TEXT NOT NULL,
    mentoring_available INTEGER NOT NULL CHECK (mentoring_available IN (0, 1)),
    commitment_hours NUMERIC NOT NULL CHECK (commitment_hours > 0),
    term TEXT NOT NULL,
    modality TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    provenance_type TEXT NOT NULL CHECK (provenance_type = 'hypothetical'),
    provenance_label TEXT NOT NULL,
    source_url TEXT,
    source_note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE student_skills (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    proficiency INTEGER NOT NULL CHECK (proficiency BETWEEN 0 AND 4),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(student_id, skill_id)
);

CREATE TABLE project_skills (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    required_proficiency INTEGER NOT NULL CHECK (required_proficiency BETWEEN 1 AND 4),
    kind TEXT NOT NULL CHECK (kind IN ('mandatory', 'trainable')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, skill_id)
);

CREATE TABLE student_preferences (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id),
    rank INTEGER NOT NULL CHECK (rank > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(student_id, project_id),
    UNIQUE(student_id, rank)
);

CREATE TABLE availability_windows (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('student', 'project')),
    owner_id TEXT NOT NULL,
    day INTEGER NOT NULL CHECK (day BETWEEN 0 AND 6),
    start_minute INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 1439),
    end_minute INTEGER NOT NULL CHECK (end_minute BETWEEN 1 AND 1440),
    fixed INTEGER NOT NULL CHECK (fixed IN (0, 1)),
    purpose TEXT NOT NULL CHECK (purpose IN ('availability', 'required', 'mentoring')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (end_minute > start_minute)
);
CREATE INDEX idx_availability_owner ON availability_windows(owner_type, owner_id);

CREATE TABLE match_config (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    schema_version TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    threshold_bp INTEGER NOT NULL CHECK (threshold_bp BETWEEN 0 AND 10000),
    score_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    solver_seed INTEGER NOT NULL,
    worker_count INTEGER NOT NULL CHECK (worker_count = 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE match_runs (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
    stale_reasons_json TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    input_snapshot_hash TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    result_snapshot_json TEXT NOT NULL,
    stage_evidence_json TEXT NOT NULL,
    benchmark_evidence_json TEXT,
    shuffle_evidence_json TEXT,
    runtime_ms NUMERIC NOT NULL,
    placement_count INTEGER NOT NULL,
    total_score_bp INTEGER NOT NULL,
    minimum_score_bp INTEGER,
    solver_seed INTEGER NOT NULL,
    worker_count INTEGER NOT NULL,
    score_version TEXT NOT NULL,
    optimality_limitation TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_match_runs_status ON match_runs(status, stale);

CREATE TABLE pair_scores (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES match_runs(id) ON DELETE CASCADE,
    student_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    eligibility_reasons_json TEXT NOT NULL,
    factor_scores_json TEXT NOT NULL,
    raw_weights_json TEXT NOT NULL,
    normalized_weights_json TEXT NOT NULL,
    contributions_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    gaps_json TEXT NOT NULL,
    missing_fields_json TEXT NOT NULL,
    total_bp INTEGER NOT NULL CHECK (total_bp BETWEEN 0 AND 10000),
    compatibility_index NUMERIC NOT NULL,
    score_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, student_id, project_id)
);
CREATE INDEX idx_pair_scores_run_student ON pair_scores(run_id, student_id);

CREATE TABLE assignments (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES match_runs(id) ON DELETE CASCADE,
    student_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    score_bp INTEGER NOT NULL CHECK (score_bp BETWEEN 0 AND 10000),
    compatibility_index NUMERIC NOT NULL,
    canonical_tie_order INTEGER NOT NULL,
    global_rationale TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, student_id),
    UNIQUE(run_id, project_id, student_id)
);
CREATE INDEX idx_assignments_run_project ON assignments(run_id, project_id);

CREATE TABLE decision_audit (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    actor_role TEXT NOT NULL CHECK (actor_role IN ('student', 'faculty', 'admin')),
    actor_persona_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    run_id TEXT,
    reason TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_audit_created ON decision_audit(created_at, id);

CREATE TABLE roadmaps (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    student_id TEXT NOT NULL REFERENCES students(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    run_id TEXT REFERENCES match_runs(id),
    relationship TEXT NOT NULL CHECK (relationship IN ('approved_placement', 'not_a_placement')),
    weeks INTEGER NOT NULL CHECK (weeks BETWEEN 2 AND 4),
    tasks_json TEXT NOT NULL,
    notice TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(student_id, project_id, run_id)
);

CREATE TABLE outreach_drafts (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    student_id TEXT NOT NULL REFERENCES students(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    run_id TEXT REFERENCES match_runs(id),
    deterministic_source TEXT NOT NULL CHECK (deterministic_source = 'offline-template'),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    edited_body TEXT NOT NULL,
    notice TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(student_id, project_id, run_id)
);

CREATE TABLE idempotency_records (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(scope, idempotency_key)
);

CREATE TRIGGER decision_audit_no_update
BEFORE UPDATE ON decision_audit BEGIN
    SELECT RAISE(ABORT, 'decision audit is append-only');
END;
CREATE TRIGGER decision_audit_no_delete
BEFORE DELETE ON decision_audit BEGIN
    SELECT RAISE(ABORT, 'decision audit is append-only');
END;
CREATE TRIGGER pair_scores_no_update
BEFORE UPDATE ON pair_scores BEGIN
    SELECT RAISE(ABORT, 'pair score snapshots are immutable');
END;
CREATE TRIGGER pair_scores_no_delete
BEFORE DELETE ON pair_scores BEGIN
    SELECT RAISE(ABORT, 'pair score snapshots are immutable');
END;
CREATE TRIGGER assignments_no_update
BEFORE UPDATE ON assignments BEGIN
    SELECT RAISE(ABORT, 'assignment snapshots are immutable');
END;
CREATE TRIGGER assignments_no_delete
BEFORE DELETE ON assignments BEGIN
    SELECT RAISE(ABORT, 'assignment snapshots are immutable');
END;
CREATE TRIGGER match_runs_snapshot_immutable
BEFORE UPDATE ON match_runs
WHEN OLD.config_snapshot_json <> NEW.config_snapshot_json
  OR OLD.input_snapshot_hash <> NEW.input_snapshot_hash
  OR OLD.input_snapshot_json <> NEW.input_snapshot_json
  OR OLD.result_snapshot_json <> NEW.result_snapshot_json
  OR OLD.stage_evidence_json <> NEW.stage_evidence_json
  OR COALESCE(OLD.benchmark_evidence_json, '') <> COALESCE(NEW.benchmark_evidence_json, '')
  OR OLD.runtime_ms <> NEW.runtime_ms
  OR OLD.placement_count <> NEW.placement_count
  OR OLD.total_score_bp <> NEW.total_score_bp
  OR COALESCE(OLD.minimum_score_bp, -1) <> COALESCE(NEW.minimum_score_bp, -1)
  OR OLD.solver_seed <> NEW.solver_seed
  OR OLD.worker_count <> NEW.worker_count
  OR OLD.score_version <> NEW.score_version
BEGIN
    SELECT RAISE(ABORT, 'run input/config/result snapshots are immutable');
END;
