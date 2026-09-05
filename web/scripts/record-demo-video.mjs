import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const BASE_URL = process.env.DEMO_BASE_URL ?? "http://localhost:3000";
const OUT_DIR = path.resolve(process.cwd(), "videos");
const TARGET_NAME = process.env.DEMO_VIDEO_NAME ?? "cadence-track03-5min.webm";

function nowStamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
}

async function setCue(page, title, body) {
  await page.evaluate(({ titleText, bodyText }) => {
    let box = document.getElementById("demo-cue-box");
    if (!box) {
      box = document.createElement("div");
      box.id = "demo-cue-box";
      box.style.position = "fixed";
      box.style.right = "20px";
      box.style.bottom = "20px";
      box.style.width = "460px";
      box.style.maxWidth = "42vw";
      box.style.background = "rgba(0, 0, 0, 0.72)";
      box.style.border = "1px solid rgba(255,255,255,0.22)";
      box.style.backdropFilter = "blur(8px)";
      box.style.borderRadius = "12px";
      box.style.padding = "14px 16px";
      box.style.zIndex = "2147483647";
      box.style.color = "#fff";
      box.style.fontFamily = "Inter, system-ui, sans-serif";
      box.style.pointerEvents = "none";
      box.innerHTML = '<div id="demo-cue-title" style="font-size:16px;font-weight:700;margin-bottom:6px"></div><div id="demo-cue-body" style="font-size:13px;line-height:1.5;color:#D5D6DC"></div>';
      document.body.appendChild(box);
    }
    const t = document.getElementById("demo-cue-title");
    const b = document.getElementById("demo-cue-body");
    if (t) t.textContent = titleText;
    if (b) b.textContent = bodyText;
  }, { titleText: title, bodyText: body });
}

async function hold(page, ms) {
  await page.waitForTimeout(ms);
}

async function safeClick(page, selector) {
  const el = page.locator(selector).first();
  if (await el.count()) {
    await el.click({ timeout: 8000 });
    return true;
  }
  return false;
}

async function scrollBy(page, y) {
  await page.evaluate((delta) => window.scrollBy({ top: delta, behavior: "smooth" }), y);
}

async function run() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: {
      dir: OUT_DIR,
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: "networkidle" });

  await setCue(
    page,
    "Track 03 — AI Revenue Recovery",
    "Cadence detects revenue at risk, picks the right intervention, and executes bounded recovery with compliance and audit trail."
  );
  await hold(page, 14000);

  await setCue(
    page,
    "Problem Context",
    "Revenue leakage happens across payment degradation, failed subscriptions, and receivables delays. The agent closes this loop end-to-end."
  );
  await hold(page, 12000);

  await scrollBy(page, 640);
  await hold(page, 7000);
  await scrollBy(page, 520);
  await setCue(
    page,
    "Six-Stage Decision Loop",
    "Ingest -> Classify -> Predict -> Policy -> Compliance Gate -> Execute. Every stage is explicit and testable."
  );
  await hold(page, 24000);

  await scrollBy(page, 640);
  await setCue(
    page,
    "Compliance and Explainability",
    "No action bypasses the gate. Blocked outcomes are logged, and each decision has a plain-language rationale."
  );
  await hold(page, 22000);

  await scrollBy(page, 700);
  await setCue(
    page,
    "Measured Batch Recovery",
    "The score is not detection only. We compare recovered money and efficiency against baseline and oracle in the same world."
  );
  await hold(page, 23000);

  await page.goto(`${BASE_URL}/app`, { waitUntil: "networkidle" });
  await setCue(
    page,
    "Portfolio Operations View",
    "Finance ops sees at-risk value, in-recovery queue, recovered amount, escalation count, and upcoming work."
  );
  await hold(page, 24000);

  await safeClick(page, 'a[href="/app/compare"]');
  await page.waitForLoadState("networkidle");
  await setCue(
    page,
    "Run Comparison",
    "Baseline vs Cadence vs Oracle. Month-strip shows timing intelligence and why retries should happen on likely funding days."
  );
  await hold(page, 32000);

  await scrollBy(page, 520);
  await setCue(
    page,
    "Track 03 Bar Coverage",
    "Recovered money is reported across a batch, with compliant escalation, stopping rules, and independent-audit visibility."
  );
  await hold(page, 26000);

  await safeClick(page, 'a[href="/app/cycles"]');
  await page.waitForLoadState("networkidle");
  await setCue(
    page,
    "Cycle Drill-Down",
    "Open any cycle to inspect diagnosis, prediction basis, event timeline, and next action explainability."
  );
  await hold(page, 17000);

  const openedCycle = await safeClick(page, 'a[href^="/app/cycles/"]');
  if (openedCycle) {
    await page.waitForLoadState("networkidle");
    await setCue(
      page,
      "Single-Cycle Explainability",
      "This is where support can answer: what happened, why that decision fired, and when recovery succeeded or stopped."
    );
    await hold(page, 30000);
  }

  await page.goto(`${BASE_URL}/app/ledger`, { waitUntil: "networkidle" });
  await setCue(
    page,
    "Ledger Audit Trail",
    "Filter by run and event type, inspect blocked actions, and export CSV. This is the compliance and audit backbone."
  );
  await hold(page, 30000);

  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle" });
  await setCue(
    page,
    "Close",
    "Cadence satisfies Track 03 with measured revenue recovery, bounded workflow execution, compliance gating, and full auditability."
  );
  await hold(page, 16000);

  const video = page.video();
  await context.close();
  await browser.close();

  const recordedPath = await video.path();
  const finalPath = path.join(OUT_DIR, `${nowStamp()}-${TARGET_NAME}`);
  fs.copyFileSync(recordedPath, finalPath);
  console.log(`Video saved: ${finalPath}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
