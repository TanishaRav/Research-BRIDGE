"use client";

import { useRouter } from "next/navigation";
import { useDemo, personasForRole } from "@/lib/demo-context";
import type { DemoRole } from "@/lib/types";
import { Select } from "./ui";

const ROLE_ORDER: { role: DemoRole; label: string; home: string }[] = [
  { role: "student", label: "Student", home: "/student" },
  { role: "faculty", label: "Faculty", home: "/faculty" },
  { role: "admin", label: "EUReCA Admin", home: "/admin" },
];

export function RoleSwitcher() {
  const { identity, personas, setIdentity } = useDemo();
  const router = useRouter();

  const role = identity?.role ?? "student";
  const rolePersonas = personasForRole(personas, role);

  function selectRole(nextRole: DemoRole) {
    const first = personasForRole(personas, nextRole)[0];
    if (!first) return;
    setIdentity({ role: nextRole, personaId: first.persona_id });
    const home = ROLE_ORDER.find((entry) => entry.role === nextRole)?.home ?? "/";
    router.push(home);
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        role="group"
        aria-label="Demo role"
        className="grid grid-cols-3 gap-1 rounded-md border border-divider bg-subtle p-1"
      >
        {ROLE_ORDER.map((entry) => (
          <button
            key={entry.role}
            type="button"
            aria-pressed={role === entry.role}
            onClick={() => selectRole(entry.role)}
            className={
              role === entry.role
                ? "rounded-sm bg-surface px-2 py-1.5 text-xs font-semibold text-accent-pressed shadow-sm"
                : "rounded-sm px-2 py-1.5 text-xs font-medium text-ink-secondary hover:text-ink"
            }
          >
            {entry.label}
          </button>
        ))}
      </div>
      {rolePersonas.length > 1 ? (
        <Select
          aria-label="Demo persona"
          value={identity?.personaId ?? ""}
          onChange={(event) => setIdentity({ role, personaId: event.target.value })}
        >
          {rolePersonas.map((persona) => (
            <option key={persona.persona_id} value={persona.persona_id}>
              {persona.label}
            </option>
          ))}
        </Select>
      ) : null}
    </div>
  );
}
