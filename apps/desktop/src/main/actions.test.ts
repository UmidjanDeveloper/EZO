import { describe, expect, it } from "vitest";
import { createActions, UnsupportedAction, type ActionDeps } from "./actions";

function fakeDeps(platform: NodeJS.Platform = "win32") {
  const runs: { file: string; args: readonly string[] }[] = [];
  let clipboard = "oldingi";
  const clipboardWrites: string[] = [];
  const deps: ActionDeps = {
    platform,
    run: async (file, args) => {
      runs.push({ file, args });
    },
    clipboard: {
      readText: () => clipboard,
      writeText: (text) => {
        clipboard = text;
        clipboardWrites.push(text);
      },
    },
    openPath: async () => "",
    sleep: async () => undefined,
  };
  return { deps, runs, clipboardWrites, current: () => clipboard };
}

describe("createActions", () => {
  it("opens registered apps by fixed executable, with no arguments", async () => {
    const { deps, runs } = fakeDeps();
    await createActions(deps).openApp("calculator");
    expect(runs).toEqual([{ file: "calc.exe", args: [] }]);
  });

  it("dictation goes through the clipboard; the command line never contains user text", async () => {
    const { deps, runs, clipboardWrites, current } = fakeDeps();
    const hostile = "'; Remove-Item C:\\ -Recurse; '";
    await createActions(deps).typeText(hostile);
    expect(clipboardWrites).toEqual([hostile, "oldingi"]);
    expect(current()).toBe("oldingi");
    expect(runs).toHaveLength(1);
    expect(runs[0]!.args.join(" ")).not.toContain("Remove-Item");
    expect(runs[0]!.args.at(-1)).toBe("$s=New-Object -ComObject WScript.Shell; $s.SendKeys('^v')");
  });

  it("restores the clipboard even when pasting fails", async () => {
    const { deps, current } = fakeDeps();
    deps.run = async () => {
      throw new Error("powershell missing");
    };
    await expect(createActions(deps).typeText("Salom")).rejects.toThrow("powershell missing");
    expect(current()).toBe("oldingi");
  });

  it("volume uses fixed media-key presses", async () => {
    const { deps, runs } = fakeDeps();
    await createActions(deps).changeVolume("mute");
    expect(runs[0]!.args.at(-1)).toContain("[char]173");
  });

  it("refuses Windows actions on other systems instead of pretending", async () => {
    const { deps } = fakeDeps("linux");
    await expect(createActions(deps).openApp("notepad")).rejects.toBeInstanceOf(UnsupportedAction);
  });

  it("reports a file that could not be opened", async () => {
    const { deps } = fakeDeps();
    deps.openPath = async () => "No application is associated";
    await expect(createActions(deps).openFile("C:/x.abc")).rejects.toThrow("No application");
  });
});
