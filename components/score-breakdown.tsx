import type { PairScore } from "@/lib/types";
import { bpToIndex, factorLabel, reasonLabel } from "@/lib/format";
import { Badge, ScoreBar, StatusCallout } from "./ui";

const FACTOR_ORDER = ["interest", "technical_skill", "availability", "preference", "learning_goal"];

export function ScoreBreakdown({ pair }: { pair: PairScore }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="tnum text-3xl font-semibold text-ink">
          {bpToIndex(pair.total_bp)}
        </span>
        <span className="text-sm text-ink-muted">compatibility index (0–100)</span>
        {pair.eligible ? (
          <Badge tone="success">Eligible</Badge>
        ) : (
          <Badge tone="warning">Not eligible</Badge>
        )}
      </div>
      <p className="text-xs text-ink-muted">
        A compatibility index, not a probability of acceptance. Score version {pair.score_version}.
      </p>

      <div className="space-y-2.5">
        {FACTOR_ORDER.filter((key) => key in pair.factor_scores_bp).map((key) => (
          <ScoreBar
            key={key}
            label={factorLabel(key)}
            valueBp={pair.factor_scores_bp[key] ?? 0}
            weightPercent={
              pair.normalized_weights[key] !== undefined
                ? (Number(pair.normalized_weights[key]) * 100).toFixed(0)
                : undefined
            }
          />
        ))}
      </div>

      {pair.eligibility_reasons.length > 0 ? (
        <StatusCallout tone="warning" title="Eligibility notes">
          <ul className="list-disc space-y-1 pl-4">
            {pair.eligibility_reasons.map((reason, index) => (
              <li key={index}>
                {reason.detail}{" "}
                <span className="text-xs text-ink-muted">({reason.resolution})</span>
              </li>
            ))}
          </ul>
        </StatusCallout>
      ) : null}

      {pair.gaps.length > 0 ? (
        <div>
          <h3 className="text-sm font-semibold text-ink">Skill gaps</h3>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-ink-secondary">
            {pair.gaps.map((gap, index) => (
              <li key={index}>{describeGap(gap)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {pair.missing_fields.length > 0 ? (
        <p className="text-sm text-ink-secondary">
          Missing fields affecting the score: {pair.missing_fields.map(reasonLabel).join(", ")}.
        </p>
      ) : null}
    </div>
  );
}

function describeGap(gap: Record<string, unknown>): string {
  const skill = typeof gap.skill_id === "string" ? gap.skill_id : "skill";
  const current = gap.current_proficiency ?? gap.current ?? 0;
  const target =
    gap.target_proficiency ?? gap.required_proficiency ?? gap.target ?? 0;
  const kind = typeof gap.kind === "string" ? ` (${gap.kind})` : "";
  return `${skill}: current ${current} → target ${target}${kind}`;
}
