---
name: tabbit
description:  Use in Web Browser related task such as web navigation, inspection, interaction, or visual verification. Control the user's Tabbit Browser through its installed CLI and browser-owned Playwright runtime.
---

# Tabbit Browser

Tabbit is the user's Chromium browser. Use this skill for web tasks that need
its real browser state; stay on this backend for the whole task.

## Connect and discover
Use the installed stable launcher: `"$HOME/.local/bin/tabbit-cli"` on MacOS or
`& "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"` on Windows. Call
it `<launcher>` below. Never invoke a CLI inside an application bundle or a
versioned runtime directory.

There is no separate connect command: the stable launcher routes to the
selected Browser instance, launching it when necessary. On macOS:

```bash
tabbit_cli="$HOME/.local/bin/tabbit-cli"
"$tabbit_cli" diagnose
"$tabbit_cli" tabs --task review-checkout --state available
"$tabbit_cli" nodejs --task review-checkout --request-id read-title \
  --read-only <<'JS'
return {title: await page.title(), url: page.url()};
JS
```

On Windows PowerShell, inspect capabilities directly, then use a UTF-8
temporary file and CMD redirection for JavaScript stdin so PowerShell does not
rewrite the program:

```powershell
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
& $tabbitCli diagnose
& $tabbitCli tabs --task review-checkout --state available
$program = [IO.Path]::GetTempFileName()
try {
  [IO.File]::WriteAllText($program,
    'return {title: await page.title(), url: page.url()};',
    [Text.UTF8Encoding]::new($false))
  cmd.exe /d /c "`"$tabbitCli`" nodejs --task review-checkout --request-id read-title --read-only < `"$program`""
} finally {
  Remove-Item $program -ErrorAction SilentlyContinue
}
```

Choose one short `NAME` for the user goal and reuse it exactly. `NAME` is also
the visible title of the task's single tab group. Every tab the task owns joins
that group. A task is created by the first command that needs one; there is no
separate start step. Within the same agent session, prefer `resume` of a
relevant retained group before opening duplicate tabs.

## Own the right tabs

Inventory does not attach to tabs:

```text
<launcher> diagnose [--task NAME]
<launcher> tabs --task NAME [--state available|owned|claimed] [--limit 50]
<launcher> claim --task NAME --tab ID...
<launcher> resume --task NAME --group ID
```

Only claimed, resumed, or task-created tabs appear in `context.pages()` and
`pages()`. Inventory IDs are not Playwright Page objects. When the first program
starts an empty task, reuse its provided `page` for the first target; the runtime
creates that owned page automatically. Use `context.newPage()` only for
additional tabs.

## Submit coherent programs

Submit JavaScript through stdin and give every submission a path-safe request
ID. `--read-only` classifies a program that cannot navigate, focus, type,
click, or otherwise change browser or application state; it does not change
the JavaScript API.

```text
<launcher> nodejs --task NAME --request-id ID [--read-only] [--timeout-ms MS]
```

Each program has a 60-second executor deadline by default. Extend it only for
a known longer program with `--timeout-ms`, up to the 180-second maximum.
Upstream Playwright retains its native 30-second per-operation default, and
native timeout options such as `locator.click({timeout: 60_000})` are honored.
Set the executor deadline longer than the longest operation timeout. A
Playwright `timeout: 0` disables only that operation's timeout, never the
executor deadline.

Each submission runs in a fresh async wrapper with top-level `await` and
`return`. Lexical variables do not survive submissions. Re-resolve pages, or
store intentional task-local state on `globalThis`. Return bounded JSON-safe
values, never Page, Locator, Frame, JSHandle, DOM, or unbounded page text.

Programs receive `assert`, `expect`, `browser`, `context`, the current `page`,
`pages()`, `usePage(page)`, `artifactPath(name)`, `reportIssue(code)`, and the
`tabbit` helper object. Run `<launcher> diagnose` without `--task` when you need
capabilities, runtime limits, or the compact live-task inventory with current
`ownedPageCount` and `groupId`. Run `<launcher> diagnose --task NAME` for that
task's effective Playwright version, executor deadlines, result limits, and
foreground policy, plus its live ownership summary. Use `tabs` for
authoritative ownership state when you need the individual tab descriptors.

Keep navigation, extraction, and verification in one program when the next
step is already determined by browser state. Return only when new evidence
requires model judgment. Avoid repeated one-field probes and repeated reads of
unchanged page state.

For independent sources, open only the scratch tabs needed, navigate and
extract with `Promise.allSettled()`, and close every scratch tab in `finally`.
Keep mutations to one business object sequential. Stop before an unauthorized
final confirmation, publish, send, purchase, or delete action.

Prefer a JavaScript-heavy operation graph over one CLI round per page or fact.
For example, search independent known URLs concurrently and return one bounded
candidate table:

```js
const urls = inputUrls.slice(0, 6);
const scratch = await Promise.all(urls.map(() => context.newPage()));
try {
  const settled = await Promise.allSettled(scratch.map(async (tab, index) => {
    await tab.goto(urls[index], {waitUntil: "domcontentloaded"});
    return await tab.locator("main").evaluate((main) => ({
      title: document.title,
      url: location.href,
      text: (main.innerText || "").slice(0, 4000),
    }));
  }));
  return settled.flatMap((item) =>
    item.status === "fulfilled" ? [item.value] : []);
} finally {
  await Promise.allSettled(scratch.map((tab) => tab.close()));
}
```

## Observe and act

Use the narrowest reliable surface:

1. Known target: semantic locators and native Playwright actions.
2. Unknown accessible structure: a bounded
   `page.ariaSnapshot({mode: "ai", depth: 20})`, then a semantic locator or a
   fresh ref for an immediate action.
3. Known data or aggregation: one bounded `page.evaluate()` or
   `locator.evaluateAll()` program that filters, normalizes, deduplicates, and
   aggregates before returning.
4. Cross-frame structure: `tabbit.observe({maxChars: 6000})`.
5. Visual layout or canvas:
   ```js
   return await page.screenshot({fullPage: false});
   ```
   `artifactPath()` is a naming hint. Load `result.nextAction.path`; never reuse
   the requested path or scan the artifact directory.

When later steps may replace the observed DOM node, normalize its fresh ref
immediately, before another snapshot or the first material change:

```js
const target = await page.locator("aria-ref=e2").normalize();
await target.click();
```

The normalized locator re-resolves the element using Playwright's preferred
test-id, role, and user-facing attributes instead of the snapshot-only ref. It
is more resilient, not permanent. Re-snapshot after navigation or when its
identifying attributes change. If the locator must survive another submission
in the same task, store it intentionally on `globalThis`; never return a
Locator.

Native `click`, `fill`, `press`, `dragTo`, event waiters, and assertions retain
Playwright actionability and input semantics. Use `tabbit.pasteText` inside the
program for task-local synthetic paste into an already focused editable.
Use `tabbit.triggerAndWait` for one known event and
`tabbit.triggerAndObserve` when several transitions are possible.

`tabbit.pasteText(text, options)` accepts `format: "text"` or `"tsv"` and the
optional `requireEditableFocus` guard.
`tabbit.triggerAndWait(event, trigger, options)` installs a waiter for
`"popup"`, `"page"`, `"download"`, `"dialog"`, `"navigation"`, or `"url"`
before invoking the trigger; options include `timeoutMs`, plus `url` and
`waitUntil` where applicable.
`tabbit.triggerAndObserve(trigger, options)` observes the first page, URL,
navigation, frame, or render transition; options include `timeoutMs`,
`settleMs`, `pollMs`, and `activatePage`.

For example, reduce a native popup result before returning it:

```js
const popup = await tabbit.triggerAndWait("popup", () =>
  page.getByRole("link", {name: "Open details"}).click());
return {url: popup.url(), title: await popup.title()};
```

For synthetic paste, focus the editable with native Playwright first and
return the helper receipt:

```js
await page.getByRole("textbox", {name: "Items"}).focus();
return await tabbit.pasteText("alpha\tbeta", {
  format: "tsv", requireEditableFocus: true,
});
```

For a known, reasonably sized file URL, skip download UI: fetch with
`context.request` to reuse BrowserContext cookies, validate the file, and save
it under `artifactPath()`. Return metadata, not the buffer:

```js
const href = await page.getByRole("link", {name: /view pdf/i}).getAttribute("href");
assert(href);
const url = new URL(href, page.url()).href;
const response = await context.request.get(url, {timeout: 15_000});
assert(response.ok(), `HTTP ${response.status()}`);
const body = await response.body();
assert.equal(body.subarray(0, 5).toString(), "%PDF-");
const path = artifactPath("paper.pdf");
await (await import("node:fs/promises")).writeFile(path, body, {flag: "wx"});
return {path, bytes: body.length, url};
```

Use `tabbit.focusInfo`, `tabbit.hitTest`, or `tabbit.actionability` only when
focus, coordinate targeting, or a failed native action is ambiguous. Keep
locator and `expect` waits when semantic visibility or rerender diagnostics
matter. For a cheap deterministic DOM predicate, use
`page.waitForFunction(predicate, argument, {polling: "raf"})`.

After each meaningful mutation, verify application-visible state. Login,
CAPTCHA, payment, sensitive values, and irreversible actions remain with the
user or an authorized protected flow.

## Extract complete evidence

Before finalizing a list, count, minimum, maximum, or ranking, state the
candidate set and inclusion predicate in the extraction program. Establish
which pages, filters, result types, and stop signal make the set complete
enough. Verify each included item, bound pagination and scrolling, deduplicate
on a stable key, and report truncation or uncertainty explicitly.

The submitted program runs in the Browser-owned Node realm; `document` and
`window` exist only inside `page.evaluate`. Pass values through the argument
channel because page callbacks do not capture Node variables.

## Results, recovery, and finish

`nodejs` returns a compact response. `result` and `status` are always present;
the remaining fields are sparse:

| Field | Present when | Contract |
| --- | --- | --- |
| `result` | Always | Contains `requestId` and the inline value, resource handle, or failure details that exist for this submission. |
| `status` | Always | `queued`, `running`, `succeeded`, `failed`, or `interrupted`. |
| `task` | A task is new, or the response is non-success | Identifies the task and whether it was reused; it can also carry `groupId`. |
| `transition` | Optional page or document transition evidence exists | Reports changed URLs/pages and runtime revision tokens; treat `targetEpoch` and `documentGeneration` as staleness evidence, not durable identifiers. |
| `result.mutationState` | The compact response is failed or interrupted | The submission's declared side-effect class used to decide whether retry needs visible-state verification. |
| `result.elapsedMs` | Timing is available | Elapsed submission time in milliseconds. |

The `receipt` command returns the durable receipt directly, so its `status` and
`mutationState` are top-level rather than nested under `result`.

Successful small results are inline. Results over 16 KiB return a resource
handle instead of truncating; read only the required slice:

```text
<launcher> resource --task NAME --resource ID --offset 0 --max-bytes 65536
```

Resource offsets and `nextOffset` are UTF-8 byte offsets, not JavaScript
character indexes. Start at zero and use each returned `nextOffset` unchanged;
arbitrary offsets inside a multibyte character are rejected. `max-bytes` is a
hard page limit and must be large enough for the next UTF-8 character.

The launcher writes the JSON response to stdout and exits 0 for `succeeded`,
70 for `failed` or `interrupted`, and 75 for `queued` or `running`. A nonzero
exit does not erase the receipt; inspect its status, error fields,
`mutationState`, and `nextAction`.

Do not request receipts routinely. If a request is queued, running,
interrupted, or uncertain, keep the same task name and request ID and read
[recovery](references/recovery.md) before acting. Read
[host routing](references/host-routing.md) only when launcher, installation,
permission, product selection, multiline transport, or instance routing fails.

Before finishing, close scratch tabs and task-created empty tabs that are no
longer useful. Do this in the same program that created them or only after
verifying ownership; never close a claimed or resumed user tab merely because
its URL is `about:blank`. Then run `<launcher> finish --task NAME` exactly once.
Normal finish also closes the still-empty implicit page created for an empty task;
a modified `about:blank` page is retained. It releases ownership and retains the
other useful live tabs as a resumable group. Use
`<launcher> finish --task NAME --discard` only when cleanup was requested; it
closes every tab owned by the task, including tabs that were claimed or resumed.
