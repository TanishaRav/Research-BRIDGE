import { chromium } from "@playwright/test";
import { writeFileSync } from "node:fs";

const BASE = "http://127.0.0.1:3000";
const ADMIN = { role: "admin", personaId: "admin-demo-001" };
const browser = await chromium.launch();

// Automated keyboard-only smoke check. This does not replace a human screen-reader review.
const keyboardContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
const keyboardPage = await keyboardContext.newPage();
await keyboardPage.addInitScript((identity) => {
  localStorage.setItem("researchbridge.demo-identity", JSON.stringify(identity));
}, ADMIN);
await keyboardPage.goto(`${BASE}/admin`, { waitUntil: "networkidle" });
await keyboardPage.keyboard.press("Tab");
const firstFocus = await keyboardPage.evaluate(() => ({
  text: document.activeElement?.textContent?.trim(),
  href: document.activeElement?.getAttribute("href"),
}));
await keyboardPage.keyboard.press("Enter");
const afterSkip = await keyboardPage.evaluate(() => document.activeElement?.id ?? "");

// Start a fresh keyboard sequence: skip link, then mobile-menu button, then Enter.
await keyboardPage.goto(`${BASE}/admin`, { waitUntil: "networkidle" });
await keyboardPage.evaluate(() => {
  history.replaceState(null, "", "/admin");
  document.body.focus();
});
await keyboardPage.keyboard.press("Tab");
await keyboardPage.keyboard.press("Tab");
const menuFocus = await keyboardPage.evaluate(() => ({
  tag: document.activeElement?.tagName,
  name: document.activeElement?.getAttribute("aria-controls"),
}));
await keyboardPage.keyboard.press("Enter");
const mobileExpanded = await keyboardPage
  .getByRole("button", { name: "Toggle navigation" })
  .getAttribute("aria-expanded");
const focusSequence = [];
for (let i = 0; i < 12; i += 1) {
  await keyboardPage.keyboard.press("Tab");
  focusSequence.push(
    await keyboardPage.evaluate(() => ({
      tag: document.activeElement?.tagName,
      text: document.activeElement?.textContent?.trim().slice(0, 60),
    })),
  );
}
await keyboardContext.close();

// Local lab timing only. These are not field or p75 Core Web Vitals.
const timings = [];
for (let i = 0; i < 5; i += 1) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.addInitScript((identity) => {
    localStorage.setItem("researchbridge.demo-identity", JSON.stringify(identity));
  }, ADMIN);
  const started = Date.now();
  await page.goto(`${BASE}/admin`, { waitUntil: "networkidle" });
  const wallMs = Date.now() - started;
  const data = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    const paint = performance.getEntriesByName("first-contentful-paint")[0];
    return {
      domContentLoadedMs: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
      loadEventMs: nav ? Math.round(nav.loadEventEnd) : null,
      firstContentfulPaintMs: paint ? Math.round(paint.startTime) : null,
    };
  });
  timings.push({ wallMs, ...data });
  await context.close();
}
await browser.close();

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
};
const report = {
  generated_at: new Date().toISOString(),
  caveat: "Local production-build lab timings on one machine; not field or p75 Core Web Vitals.",
  keyboard: {
    firstFocus,
    afterSkip,
    menuFocus,
    mobileExpanded,
    focusSequence,
    passed:
      firstFocus.href === "#main-content" &&
      afterSkip === "main-content" &&
      menuFocus.name === "mobile-nav" &&
      mobileExpanded === "true",
  },
  timing_runs: timings,
  medians: {
    wallMs: median(timings.map((item) => item.wallMs)),
    domContentLoadedMs: median(timings.map((item) => item.domContentLoadedMs).filter(Number.isFinite)),
    loadEventMs: median(timings.map((item) => item.loadEventMs).filter(Number.isFinite)),
    firstContentfulPaintMs: median(
      timings.map((item) => item.firstContentfulPaintMs).filter(Number.isFinite),
    ),
  },
};
writeFileSync("evidence/quality-report.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
