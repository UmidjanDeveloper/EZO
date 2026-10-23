/**
 * `EZO.exe --self-test=<report.json> --self-test-folder=<dir>` runs the registered actions
 * for real on this Windows machine and writes what actually happened. CI runs it on a
 * GitHub Windows runner; the report is evidence of real OS behaviour, not of voice
 * quality or of a physical owner device.
 */
import { execFile } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Actions } from "./actions";
import { findFiles } from "./files";
import { parseIntent } from "./intents";

export interface CheckResult {
  name: string;
  ok: boolean;
  skipped?: boolean;
  detail: string;
}

interface SelfTestDeps {
  actions: Actions;
  captureScreen(): Promise<Uint8Array>;
  folder?: string;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function powershell(script: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", `[Console]::OutputEncoding=[Text.Encoding]::UTF8; ${script}`],
      { windowsHide: true, timeout: 30_000 },
      (error, stdout) => (error ? reject(error) : resolve(stdout.trim())),
    );
  });
}

const READ_NOTEPAD = `
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$p = Get-Process notepad -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object StartTime -Descending | Select-Object -First 1
$root = [Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
foreach ($type in @([Windows.Automation.ControlType]::Document, [Windows.Automation.ControlType]::Edit)) {
  $cond = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty, $type)
  $el = $root.FindFirst([Windows.Automation.TreeScope]::Descendants, $cond)
  if ($el) {
    $vp = $null
    if ($el.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) { $vp.Current.Value; exit 0 }
    $tp = $null
    if ($el.TryGetCurrentPattern([Windows.Automation.TextPattern]::Pattern, [ref]$tp)) { $tp.DocumentRange.GetText(-1); exit 0 }
  }
}
exit 3`;

async function check(name: string, body: () => Promise<string>): Promise<CheckResult> {
  try {
    return { name, ok: true, detail: await body() };
  } catch (error) {
    return { name, ok: false, detail: String((error as Error).message ?? error) };
  }
}

export async function runSelfTest(deps: SelfTestDeps): Promise<CheckResult[]> {
  const results: CheckResult[] = [];
  results.push(
    await check("intent: Uzbek command maps to a registered action", async () => {
      const intent = parseIntent("Kalkulyatorni och");
      if (intent.kind !== "open_app" || intent.app !== "calculator") throw new Error(JSON.stringify(intent));
      return JSON.stringify(intent);
    }),
  );

  const folder = deps.folder ?? path.join(process.cwd(), "ezo-selftest");
  results.push(
    await check("files: find a real file in an allowed folder", async () => {
      mkdirSync(path.join(folder, "2026"), { recursive: true });
      writeFileSync(path.join(folder, "2026", "Hisobot oktyabr 2026.txt"), "EZO self-test");
      writeFileSync(path.join(folder, "boshqa.txt"), "x");
      const hits = await findFiles("hisobot 2026", [folder]);
      if (hits.length !== 1) throw new Error(`expected 1 hit, got ${hits.length}`);
      return hits[0]!.path;
    }),
  );

  if (process.platform !== "win32") {
    for (const name of ["calculator", "dictation", "volume", "screenshot"]) {
      results.push({ name, ok: false, skipped: true, detail: `not Windows (${process.platform})` });
    }
    return results;
  }

  results.push(
    await check("calculator: open the real app", async () => {
      await deps.actions.openApp("calculator");
      await sleep(4000);
      const list = await powershell(
        "Get-Process | Where-Object { $_.ProcessName -match '^(calc|CalculatorApp|win32calc|Calculator)$' } | ForEach-Object { $_.ProcessName }",
      );
      if (!list) throw new Error("no calculator process found after launch");
      return `running: ${list.replace(/\s+/g, ", ")}`;
    }),
  );

  results.push(
    await check("dictation: type Uzbek text into Notepad", async () => {
      await deps.actions.openApp("notepad");
      await sleep(3000);
      const expected = "Salom EZO! O‘zbekcha matn 2026.";
      await deps.actions.typeText(expected);
      await sleep(1000);
      const actual = await powershell(READ_NOTEPAD);
      if (!actual.includes(expected)) throw new Error(`Notepad contains: ${JSON.stringify(actual.slice(0, 200))}`);
      return `Notepad text: ${JSON.stringify(actual)}`;
    }),
  );

  results.push(
    await check("volume: media keys accepted", async () => {
      await deps.actions.changeVolume("up");
      await deps.actions.changeVolume("down");
      return "SendKeys volume up/down completed (no audio device check)";
    }),
  );

  results.push(
    await check("screenshot: capture the primary screen as PNG", async () => {
      const png = await deps.captureScreen();
      const signature = Buffer.from(png.slice(0, 8)).toString("hex");
      if (signature !== "89504e470d0a1a0a" || png.length < 1000) throw new Error(`bad PNG (${png.length} bytes)`);
      writeFileSync(path.join(folder, "screen.png"), png);
      return `${png.length} bytes`;
    }),
  );

  await powershell("Stop-Process -Name notepad, calc, CalculatorApp, win32calc -Force -ErrorAction SilentlyContinue").catch(
    () => undefined,
  );
  return results;
}
