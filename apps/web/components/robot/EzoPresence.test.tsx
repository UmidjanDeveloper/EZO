import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EZO_STATES } from "@/lib/ezo-state";
import { EzoPresence, EzoStatus } from "./EzoPresence";

describe("EzoPresence", () => {
  it.each(EZO_STATES)("renders the %s state with its own motion layer", (state) => {
    const html = renderToStaticMarkup(<EzoPresence state={state} label={`label-${state}`} />);
    expect(html).toContain(`data-state="${state}"`);
    expect(html).toContain(`label-${state}`);
    expect(html).toContain('data-testid="ezo-robot"');
    if (state === "idle") expect(html).not.toContain("data-layer=");
    else expect(html).toContain(`data-layer="${state}"`);
  });

  it("marks busy states for assistive technology", () => {
    expect(renderToStaticMarkup(<EzoPresence state="searching" />)).toContain('aria-busy="true"');
    expect(renderToStaticMarkup(<EzoPresence state="idle" />)).toContain('aria-busy="false"');
  });

  it("tints errors and completion", () => {
    expect(renderToStaticMarkup(<EzoPresence state="error" />)).toContain("var(--danger)");
    expect(renderToStaticMarkup(<EzoPresence state="completed" />)).toContain("var(--success)");
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
