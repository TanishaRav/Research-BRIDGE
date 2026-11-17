import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
await page.addInitScript(() => {
  window.localStorage.setItem(
    "researchbridge.demo-identity",
    JSON.stringify({ role: "student", personaId: "student-syn-003" }),
  );
});
await page.goto("http://127.0.0.1:3000/student/projects", { waitUntil: "networkidle" });
await page.waitForTimeout(800);

const axe = await new AxeBuilder({ page })
  .withTags(["wcag2aa", "wcag21aa", "wcag22aa"])
  .analyze();

for (const v of axe.violations) {
  console.log(`\n== ${v.id} (${v.impact}) ==`);
  for (const node of v.nodes) {
    console.log("TARGET:", node.target.join(" "));
    console.log("HTML:", node.html.slice(0, 200));
    console.log("MSG:", node.failureSummary?.replace(/\n/g, " | "));
  }
}
await browser.close();
