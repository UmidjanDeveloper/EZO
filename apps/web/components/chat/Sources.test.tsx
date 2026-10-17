import type { SourceCitation } from "@ezo/shared";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/context";
import { Sources } from "./Sources";

const base: SourceCitation = {
  n: 1,
  kind: "file",
  title: "Loyiha rejasi",
  excerpt: "Kod nomi Samarqand-7",
  source_name: "Uploads",
  url: null,
  date: "2026-10-01",
  document_id: "d1",
  revision_number: 2,
  chunk_index: 0,
  page_start: 3,
  page_end: 3,
  heading: null,
  location: "p. 3",
  reliability: 1,
  primary: false,
};

const render = (citations: SourceCitation[]) =>
  renderToStaticMarkup(
    <I18nProvider>
      <Sources citations={citations} />
    </I18nProvider>,
  );

describe("Sources", () => {
  it("renders nothing without citations", () => {
    expect(render([])).toBe("");
  });

  it("lists file and web sources with numbers, location and safe external links", () => {
    const html = render([
      base,
      { ...base, n: 3, kind: "web_page", title: "Statistika", url: "https://stat.uz/x", source_name: "stat.uz", primary: true, location: "" },
    ]);
    expect(html).toContain("[1]");
    expect(html).toContain("Loyiha rejasi");
    expect(html).toContain("p. 3");
    expect(html).toContain("[3]");
    expect(html).toContain('href="https://stat.uz/x"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("rasmiy"); // primary source marker (Uzbek default)
    expect(html).toContain('href="/knowledge"'); // files open the knowledge page
  });
});
