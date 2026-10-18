import { describe, expect, it } from "vitest";
import { imageInfo } from "./VersionExports";

describe("imageInfo", () => {
  it("names the provider of a generated image", () => {
    expect(imageInfo({ provider: "openai", model: "gpt-image-2", placeholder: false })).toEqual({
      placeholder: false,
      madeBy: "openai · gpt-image-2",
    });
  });

  it("never credits a provider for a placeholder picture", () => {
    expect(imageInfo({ kind: "social", provider: "openai", placeholder: true })).toEqual({
      placeholder: true,
      madeBy: null,
    });
  });

  it("credits EZO for diagrams and knows nothing about plain uploads", () => {
    expect(imageInfo({ kind: "diagram", provider: "ezo" })).toEqual({ placeholder: false, madeBy: "EZO" });
    expect(imageInfo({})).toEqual({ placeholder: false, madeBy: null });
  });
});
