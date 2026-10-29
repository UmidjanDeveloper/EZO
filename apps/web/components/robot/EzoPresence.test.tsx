import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EZO_STATES } from "@/lib/ezo-state";
import { EzoPresence, EzoStatus } from "./EzoPresence";
import { I18nProvider } from "@/lib/i18n/context";

describe("EzoPresence", () => {
  const render = (node: React.ReactElement) => renderToStaticMarkup(<I18nProvider>{node}</I18nProvider>);
  it.each(EZO_STATES)("renders the %s state with its own motion layer", (state) => {
    const html = render(<EzoPresence state={state} label={`label-${state}`} />);
    expect(html).toContain(`data-state="${state}"`);
    expect(html).toContain(`label-${state}`);
    expect(html).toContain('data-testid="ezo-humanoid"');
    expect(html).toContain('data-style="energy"');
  });

  it("marks busy states for assistive technology", () => {
    expect(render(<EzoPresence state="searching" />)).toContain('aria-busy="true"');
    expect(render(<EzoPresence state="idle" />)).toContain('aria-busy="false"');
  });

  it("keeps error and completion states accessible", () => {
    expect(render(<EzoPresence state="error" />)).toContain('data-state="error"');
    expect(render(<EzoPresence state="completed" />)).toContain('data-state="completed"');
  });
});

describe("EzoStatus", () => {
  it("is hidden while idle and shows the label otherwise", () => {
    expect(renderToStaticMarkup(<EzoStatus state="idle" label="Ready" />)).toBe("");
    const html = renderToStaticMarkup(<EzoStatus state="reading" label="Reading sources…" />);
    expect(html).toContain('data-state="reading"');
    expect(html).toContain("Reading sources…");
  });
});
