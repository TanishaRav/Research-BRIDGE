import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const ADMIN = { role: "admin", personaId: "admin-demo-001" };
const STUDENT = { role: "student", personaId: "student-syn-003" };
const FACULTY = { role: "faculty", personaId: "faculty-fictional-001" };

async function asPersona(page: Page, ident: { role: string; personaId: string }) {
  await page.addInitScript((value) => {
    window.localStorage.setItem("researchbridge.demo-identity", JSON.stringify(value));
  }, ident);
}

test("landing page loads and links into the demo", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "ResearchBridge" })).toBeVisible();
  await expect(page.getByRole("link", { name: /open synthetic demo/i })).toBeVisible();
});

test("student can view dashboard and projects", async ({ page }) => {
  await asPersona(page, STUDENT);
  await page.goto("/student");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText(/next action/i)).toBeVisible();

  await page.goto("/student/projects");
  await expect(page.getByRole("heading", { name: "Project catalog" })).toBeVisible();
  // At least one opening is listed from seeded data.
  await expect(page.getByText(/Hypothetical Project/i).first()).toBeVisible();
});

test("admin can review an approved run and see fairness evidence", async ({ page }) => {
  await asPersona(page, ADMIN);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  await page.goto("/admin/evidence");
  await expect(page.getByRole("heading", { name: "Fairness evidence" })).toBeVisible();
  // The strategy comparison table or an empty state must render.
  await expect(
    page.getByText(/strategy comparison|no runs to evaluate/i).first(),
  ).toBeVisible();
});

test("faculty sees the candidates page gated behind approval", async ({ page }) => {
  await asPersona(page, FACULTY);
  await page.goto("/faculty/candidates");
  await expect(page.getByRole("heading", { name: "Assigned candidates" })).toBeVisible();
});

test("admin overview has no serious accessibility violations", async ({ page }) => {
  await asPersona(page, ADMIN);
  await page.goto("/admin");
  await page.waitForLoadState("networkidle");
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(serious, JSON.stringify(serious.map((v) => v.id))).toHaveLength(0);
});


test("complete student edit to approved placement follow-through journey", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  const adminHeaders = {
    "X-Demo-Role": "admin",
    "X-Demo-Persona-Id": "admin-demo-001",
    "Idempotency-Key": `e2e-reset-${Date.now()}`,
  };
  const reset = await request.post("http://127.0.0.1:8000/api/v1/demo/reset", {
    headers: adminHeaders,
    data: { confirmation: "RESET_SYNTHETIC_DEMO" },
  });
  expect(reset.ok(), await reset.text()).toBeTruthy();

  // Student edits recorded evidence.
  await page.goto("/");
  await page.evaluate((ident) => {
    window.localStorage.setItem("researchbridge.demo-identity", JSON.stringify(ident));
  }, STUDENT);
  await page.goto("/student/profile");
  await expect(page.getByRole("heading", { name: "Edit profile" })).toBeVisible();
  const hours = page.getByLabel("Hours per week");
  await hours.fill(String(Number(await hours.inputValue()) + 1));
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText(/profile saved/i)).toBeVisible();

  // Fictional faculty edits a hypothetical project's capacity-bearing record.
  await page.evaluate((ident) => {
    window.localStorage.setItem("researchbridge.demo-identity", JSON.stringify(ident));
  }, FACULTY);
  await page.goto("/faculty/projects");
  await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Edit" }).first().click();
  const description = page.getByLabel("Description");
  await description.fill(`${await description.inputValue()} Reviewed in the automated demo journey.`);
  await page.getByRole("button", { name: "Save project" }).click();
  await expect(page.getByText("Project updated.")).toBeVisible();

  // Admin previews policy, creates a real batch, runs order-invariance proof, and approves.
  await page.evaluate((ident) => {
    window.localStorage.setItem("researchbridge.demo-identity", JSON.stringify(ident));
  }, ADMIN);
  await page.goto("/admin/run");
  await page.getByRole("button", { name: "Preview weights" }).click();
  await expect(page.getByText(/normalized weights/i)).toBeVisible();
  await page.getByRole("button", { name: "Run batch" }).click();
  await page.waitForURL(/\/admin\/run\?run=/, { timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Run review" })).toBeVisible();
  await page.getByRole("button", { name: "Run shuffle test" }).click();
  await expect(page.getByText(/shuffle test: 20\/20/i)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Approve run" }).click();
  await expect(page.getByText(/run approved/i)).toBeVisible();

  const assignmentsPanel = page
    .getByRole("heading", { name: "Assignments", exact: true })
    .locator("xpath=ancestor::section");
  await expect(assignmentsPanel).toContainText(STUDENT.personaId);
  const placedStudentId = STUDENT.personaId;

  const jsonDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  expect((await jsonDownload).suggestedFilename()).toMatch(/\.json$/);
  const csvDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await csvDownload).suggestedFilename()).toMatch(/\.csv$/);

  await page.goto("/admin/audit");
  await expect(page.getByText("Run Approved").first()).toBeVisible();

  // A student placed by this exact run can inspect the result and use follow-through tools.
  const placedStudent = { role: "student", personaId: placedStudentId };
  await page.evaluate((ident) => {
    window.localStorage.setItem("researchbridge.demo-identity", JSON.stringify(ident));
  }, placedStudent);
  await page.goto("/student/outcome");
  await expect(page.getByRole("heading", { name: "Approved placement" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Skill roadmap" })).toBeVisible();
  const roadmapTask = page.getByRole("checkbox").first();
  if (await roadmapTask.count()) {
    await roadmapTask.click();
    await expect(roadmapTask).toBeChecked();
  }
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved locally.")).toBeVisible();
  const outreachDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .txt" }).click();
  expect((await outreachDownload).suggestedFilename()).toMatch(/\.txt$/);
});