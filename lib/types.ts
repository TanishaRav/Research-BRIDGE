// Typed contracts mirroring the ResearchBridge FastAPI models the UI consumes.
// Decimal fields are serialized by the API as JSON strings; keep them typed as string.

export type DemoRole = "student" | "faculty" | "admin";
export type SkillKind = "mandatory" | "trainable";
export type ProvenanceType = "public" | "fictional" | "hypothetical";
export type WindowPurpose = "availability" | "required" | "mentoring";

export type RunStatus =
  | "validating"
  | "scoring"
  | "optimizing_coverage"
  | "optimizing_quality"
  | "optimizing_floor"
  | "resolving_ties"
  | "evaluating"
  | "proposed"
  | "approved"
  | "feasible_not_proven"
  | "failed";

export interface Persona {
  role: DemoRole;
  persona_id: string;
  label: string;
  synthetic: boolean;
}

export interface PersonaList {
  demo_only_notice: string;
  personas: Persona[];
}

export interface TimeWindow {
  id?: string | null;
  day: number;
  start_minute: number;
  end_minute: number;
  fixed: boolean;
  purpose: WindowPurpose;
}

export interface StudentSkill {
  skill_id: string;
  proficiency: number;
}

export interface ProjectSkill {
  skill_id: string;
  required_proficiency: number;
  kind: SkillKind;
}

export interface StudentPreference {
  project_id: string;
  rank: number;
}

export interface Student {
  id: string;
  schema_version: string;
  created_at: string;
  updated_at: string;
  synthetic: true;
  synthetic_label: string;
  display_name: string;
  major: string;
  academic_year: string;
  interests: string[];
  hours_per_week: string | null;
  learning_goals: string[];
  first_time_researcher: boolean;
  accepts_suggestions: boolean;
  profile_complete: boolean;
  submitted: boolean;
  synthetic_submission_order: number;
  skills: StudentSkill[];
  preferences: StudentPreference[];
  availability: TimeWindow[];
}

export interface Faculty {
  id: string;
  display_name: string;
  department: string;
  research_interests: string[];
  provenance_type: ProvenanceType;
  provenance_label: string;
  source_url: string | null;
  source_retrieved_at: string | null;
}

export interface Skill {
  id: string;
  label: string;
  category: string;
  aliases: string[];
}

export interface Project {
  id: string;
  faculty_id: string;
  title: string;
  description: string;
  department: string;
  interests: string[];
  capacity: number;
  prerequisites: string[];
  mentoring_available: boolean;
  commitment_hours: string;
  term: string;
  modality: string;
  active: boolean;
  provenance_type: "hypothetical";
  provenance_label: string;
  source_url: string | null;
  source_note: string;
  skills: ProjectSkill[];
  required_windows: TimeWindow[];
  mentoring_windows: TimeWindow[];
}

export interface ProjectList {
  items: Project[];
  count: number;
  active_filters: Record<string, unknown>;
}

export interface StudentProfileResponse {
  student: Student;
  missing_required_fields: string[];
  batch_status: "draft" | "submitted" | "approved_placement" | "approved_unplaced";
  next_action: string;
  notice: string;
}

export interface EligibilityReason {
  code: string;
  detail: string;
  field?: string | null;
  resolution: "failed" | "unresolved";
}

export interface PairScore {
  run_id?: string | null;
  student_id: string;
  project_id: string;
  eligible: boolean;
  eligibility_reasons: EligibilityReason[];
  factor_scores_bp: Record<string, number>;
  raw_weights: Record<string, string>;
  normalized_weights: Record<string, string>;
  contributions_bp: Record<string, number>;
  evidence: Record<string, unknown>;
  gaps: Array<Record<string, unknown>>;
  missing_fields: string[];
  total_bp: number;
  compatibility_index: string;
  score_version: string;
  taxonomy_version: string;
  config_snapshot: Record<string, unknown>;
}

export interface Assignment {
  run_id?: string | null;
  student_id: string;
  project_id: string;
  score_bp: number;
  compatibility_index: string;
  canonical_tie_order: number;
  state: "proposed" | "approved";
  global_rationale: string;
}

export interface Recommendation {
  project: Project;
  pair_score: PairScore;
  label: string;
}

export interface StudentOutcome {
  student_id: string;
  run_id: string | null;
  status: "pending" | "placed" | "unplaced";
  assignment: Assignment | null;
  reasons: string[];
  notice: string;
}

export interface ScoreWeights {
  interest: string;
  technical_skill: string;
  availability: string;
  preference: string;
  learning_goal: string;
}

export interface MatchConfig {
  weights: ScoreWeights;
  threshold: string;
  score_version: string;
  taxonomy_version: string;
  solver_seed: number;
  worker_count: 1;
}

export interface NormalizedConfig {
  config: MatchConfig;
  normalized_weights_percent: Record<string, string>;
}

export interface SolverStage {
  name: string;
  status: string;
  runtime_ms: string;
  objective: number | null;
  detail: string | null;
}

export interface StrategyMetrics {
  strategy: string;
  label: string;
  placement_count: number;
  submitted_count: number;
  eligible_count: number;
  placement_rate_submitted: string;
  placement_rate_eligible: string | null;
  mean_score: string | null;
  median_score: string | null;
  bottom_decile_score: string | null;
  minimum_score: string | null;
  top_choice_count: number;
  top_choice_denominator: number;
  top_choice_rate: string | null;
  first_time_placed: number;
  first_time_denominator: number;
  first_time_placement_rate: string | null;
  major_rates: Record<string, { placed: number; denominator: number; rate: string | null; small_group_warning: boolean }>;
  unplaced_count: number;
  unplaced_reasons: Record<string, string[]>;
  constraint_violations: Record<string, number>;
  runtime_ms: string;
}

export interface BenchmarkEvidence {
  strategies: Record<string, StrategyMetrics>;
  counterexample: {
    description: string;
    greedy_assignments: Array<[string, string]>;
    greedy_placement_count: number;
    global_assignments: Array<[string, string]>;
    global_placement_count: number;
    global_proven_optimal: boolean;
  };
  limitation: string;
}

export interface ShuffleEvidence {
  requested_runs: 20;
  identical_assignment_pass_count: number;
  seeds: number[];
  failing_seeds: number[];
  reference_assignments: Array<[string, string]>;
  statement: string;
}

export interface MatchRun {
  id: string;
  schema_version: string;
  created_at: string;
  updated_at: string;
  status: RunStatus;
  stale: boolean;
  stale_reasons: string[];
  config_snapshot: Record<string, unknown>;
  input_snapshot_hash: string;
  input_snapshot: Record<string, unknown>;
  result_snapshot: Record<string, unknown>;
  stage_evidence: SolverStage[];
  benchmark_evidence: BenchmarkEvidence | null;
  shuffle_evidence: ShuffleEvidence | null;
  runtime_ms: string;
  placement_count: number;
  total_score_bp: number;
  minimum_score_bp: number | null;
  solver_seed: number;
  worker_count: number;
  score_version: string;
  optimality_limitation: string | null;
  approved_at: string | null;
}

export interface RunReview {
  run: MatchRun;
  assignments: Assignment[];
  pair_scores: PairScore[];
  unplaced: Record<string, string[]>;
  project_utilization: Record<string, { assigned: number; capacity: number }>;
}

export interface RunEvidenceResponse {
  run_id: string;
  input_snapshot_hash: string;
  score_version: string;
  solver_seed: number;
  worker_count: number;
  benchmark: BenchmarkEvidence | null;
  shuffle: ShuffleEvidence | null;
  limitation: string;
}

export interface DecisionAudit {
  id: string;
  created_at: string;
  actor_role: DemoRole;
  actor_persona_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  run_id: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
}

export interface RoadmapTask {
  id: string;
  week: number;
  skill_id: string;
  category: string;
  priority: "mandatory" | "trainable";
  current_proficiency: number;
  target_proficiency: number;
  concrete_task: string;
  estimated_hours: string;
  resource_label: string;
  resource_url: string | null;
  deliverable: string;
  success_check: string;
  complete: boolean;
  completion_notice: string;
}

export interface Roadmap {
  id: string;
  student_id: string;
  project_id: string;
  run_id: string | null;
  relationship: "approved_placement" | "not_a_placement";
  weeks: number;
  tasks: RoadmapTask[];
  notice: string;
}

export interface OutreachDraft {
  id: string;
  student_id: string;
  project_id: string;
  run_id: string | null;
  deterministic_source: "offline-template";
  subject: string;
  body: string;
  edited_body: string;
  notice: string;
}

export interface FacultyAssignment {
  run_id: string;
  project_id: string;
  student_id: string;
  student_display_name: string;
  synthetic_label: string;
  compatibility_index: string;
  explanation: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  field_errors?: Record<string, string[]>;
  request_id: string;
}
