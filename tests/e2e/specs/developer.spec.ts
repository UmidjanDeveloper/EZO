import { expect, test } from "@playwright/test";

// The e2e API runs without an AI provider, so the built project is served from fixtures:
// this checks what the owner sees — the file list and a preview that cannot run scripts.
const ID = "7d1f8f3e-2c55-4e6b-9a51-1f0c2b7d3a10";
const NOW = "2026-11-18T10:00:00Z";
const SITE = `<!doctype html><html><head><style>h1{color:rgb(200,150,20)}</style></head>
<body><h1 id="title">Oqtepa Kafe</h1><script>document.getElementById("title").textContent="HACKED"</script></body></html>`;

const version = {
  id: "0b6b3a8e-9a7d-4f3e-8f0e-5d2c1b0a9e01",
  version_number: 1,
  filename: "oqtepa-kafe.zip",
  mime_type: "application/zip",
  file_size: 2048,
  content_hash: "x".repeat(64),
  provider: "anthropic",
  model: "fixture",
  created_by: "agent:developer",
  change_summary: "Created",
  parent_version_id: null,
  generation_metadata: {
    kind: "website",
    files: [{ path: "index.html" }, { path: "style.css" }, { path: "script.js" }, { path: "README.md" }],
    executed: false,
  },
  source_references: [],
  created_at: NOW,
  current: true,
  is_text: false,
  exports: [{ name: "site", filename: "oqtepa-kafe.html", mime_type: "text/html; charset=utf-8", size: SITE.length }],
};
const artifact = {
  id: ID,
  title: "Oqtepa Kafe sayti",
  type: "code",
  status: "ready",
  project_id: null,
  conversation_id: null,
  created_by_agent: "developer",
  provider: "anthropic",
  model: "fixture",
  metadata: { action: "code_project", kind: "website" },
  source_references: [],
  current_version: version,
  version_count: 1,
  created_at: NOW,
  updated_at: NOW,
};

test("developer: a built website shows its files and a script-free preview", async ({ page }) => {
  await page.route("**/api/artifacts?*", (route) => route.fulfill({ json: [artifact] }));
  await page.route("**/api/artifacts", (route) => route.fulfill({ json: [artifact] }));
  await page.route(`**/api/artifacts/${ID}`, (route) => route.fulfill({ json: { ...artifact, versions: [version] } }));
  await page.route(`**/api/artifacts/${ID}/versions/1/exports/site`, (route) =>
    route.fulfill({ body: SITE, contentType: "text/html; charset=utf-8", headers: { "Content-Disposition": "attachment" } }),
  );

  await page.goto(`/artifacts?open=${ID}`);
  const row = page.getByTestId("artifact-row");
  await expect(row).toContainText("Oqtepa Kafe sayti");
  const files = row.getByTestId("project-files");
  await expect(files).toContainText("Loyiha fayllari (4)");
  await files.locator("summary").click();
  await expect(files).toContainText("style.css");
  await expect(files).toContainText("EZO bu kodni ishga tushirmagan");
  await expect(row.getByTestId("export-site")).toContainText("Sayt (bitta HTML fayl)");

  const frame = row.getByTestId("site-preview");
  await expect(frame).toHaveAttribute("sandbox", "");
  const heading = page.frameLocator('[data-testid="site-preview"]').locator("h1");
  await expect(heading).toHaveText("Oqtepa Kafe"); // the page's script did not run
  await expect(heading).toHaveCSS("color", "rgb(200, 150, 20)"); // its styles did
});
