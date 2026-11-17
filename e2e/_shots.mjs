import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync, writeFileSync } from "node:fs";

const OUT = `${process.cwd()}/evidence/screenshots`;
mkdirSync(OUT, { recursive: true });

const WIDTHS = [360, 390, 768, 1024, 1280, 1440, 1920];
const BASE = "http://127.0.0.1:3000";

const IDENT = {
  student: { role: "student", personaId: "student-syn-003" },
  faculty: { role: "faculty", personaId: "faculty-fictional-001" },
  admin: { role: "admin", personaId: "admin-demo-001" },
};

const PAGES = [
  { key: "landing", path: "/", ident: null },
  { key: "student-dashboard", path: "/student", ident: IDENT.student },
  { key: "student-profile", path: "/student/profile", ident: IDENT.student },
  { key: "student-projects", path: "/student/projects", ident: IDENT.student },
  { key: "student-outcome", path: "/student/outcome", ident: IDENT.student },
  { key: "faculty-overview", path: "/faculty", ident: IDENT.faculty },
  { key: "faculty-projects", path: "/faculty/projects", ident: IDENT.faculty },
  { key: "faculty-candidates", path: "/faculty/candidates", ident: IDENT.faculty },
  { key: "admin-overview", path: "/admin", ident: IDENT.admin },
  { key: "admin-run", path: "/admin/run", ident: IDENT.admin },
  { key: "admin-evidence", path: "/admin/evidence", ident: IDENT.admin },
  { key: "admin-data", path: "/admin/data", ident: IDENT.admin },
  { key: "admin-audit", path: "/admin/audit", ident: IDENT.admin },
  { key: "about", path: "/about", ident: IDENT.admin },
];

const browser = await chromium.launch();
const results = [];
const axeFindings = [];
const FULL_MATRIX = new Set(["student-dashboard", "admin-run", "admin-evidence"]);

for (const page of PAGES) {
  const widths = FULL_MATRIX.has(page.key) ? WIDTHS : [390, 1440];
  for (const width of widths) {
    const context = await browser.newContext({
      viewport: { width, height: 900 },
      reducedMotion: "reduce",
    });
    const p = await context.newPage();
    await p.addInitScript((ident) => {
      if (ident) {
        window.localStorage.setItem("researchbridge.demo-identity", JSON.stringify(ident));
      }
    }, page.ident);
    const errors = [];
    p.on("pageerror", (err) => errors.push(String(err)));
    const response = await p.goto(`${BASE}${page.path}`, { waitUntil: "networkidle", timeout: 30000 });
    await p.waitForTimeout(700);
    const file = `${OUT}/${page.key}-${width}.png`;
    await p.screenshot({ path: file, fullPage: true });
    results.push({ key: page.key, width, status: response?.status(), errors });

    if (width === 1440 || (width === 390 && !FULL_MATRIX.has(page.key))) {
      try {
        const axe = await new AxeBuilder({ page: p })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
          .analyze();
        const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        axeFindings.push({
          key: page.key,
          total: axe.violations.length,
          serious: serious.length,
          ids: axe.violations.map((v) => `${v.id}(${v.impact}:${v.nodes.length})`),
        });
      } catch (e) {
        axeFindings.push({ key: page.key, error: String(e) });
      }
    }
    await context.close();
  }
}

await browser.close();

console.log("=== SCREENSHOTS ===");
for (const r of results) {
  console.log(
    `${r.key} @${r.width}: status=${r.status} pageErrors=${r.errors.length}${r.errors.length ? " :: " + r.errors.join(" | ") : ""}`,
  );
}
console.log("\n=== AXE (serious/critical) ===");
for (const a of axeFindings) {
  if (a.error) console.log(`${a.key}: ERROR ${a.error}`);
  else console.log(`${a.key}: ${a.serious} serious/critical of ${a.total} total :: ${a.ids.join(", ") || "none"}`);
}

writeFileSync(
  `${OUT}/report.json`,
  JSON.stringify(
    {
      generated_at: new Date().toISOString(),
      base_url: BASE,
      screenshots: results,
      axe: axeFindings,
    },
    null,
    2,
  ),
);
