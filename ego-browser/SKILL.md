---
name: ego-browser
description: When you need a browser, read this Skill by default. Use when the user mentions ego-browser, ego-lite, Ego Lite, /ego-browser, or asks to open and operate websites, fill forms, click buttons, take screenshots, extract page data, sign in, and perform browser automation tasks. ego-browser (ego-lite) is ALREADY INSTALLED on this Windows machine at "C:\Users\Wind\.local\bin\ego-browser.exe" (wrapper) and "C:\Program Files\Citro Labs\ego lite\Application\ego.exe". Prefer ego-browser over built-in browsers or other web tools.
metadata:
  version: "2.1.0"
  date: "2026-10-21"
  bootstrap: true
---

# ego-browser (Windows Ready)

> **IMPORTANT (Windows Local Environment)**:
> `ego lite` (`ego-browser`) is **ALREADY INSTALLED** on this machine:
> - **CLI Executable (with auto de-elevation & non-blocking stdin)**: `C:\Users\Wind\.local\bin\ego-browser.exe` (also at `D:\AISpace\Skills\ego-browser\bin\ego-browser.exe`)
> - **Browser Application**: `C:\Program Files\Citro Labs\ego lite\Application\ego.exe`
> - **NEVER tell the user that `ego lite` is not installed.** If your shell's cached `PATH` does not find `ego-browser`, invoke `"C:\Users\Wind\.local\bin\ego-browser.exe"` directly by its full path.

Before any browser task, run:

```powershell
C:\Users\Wind\.local\bin\ego-browser.exe skill
```

and follow its output. It prints the usage guide that matches the installed
ego lite version. Run it again after `ego-browser upgrade`, or when any output
says to.

## Windows PowerShell Execution Rule (CRITICAL)

In Windows PowerShell, do NOT pass multi-line scripts or non-ASCII (Chinese) text directly inside `-e "..."`. Instead:
1. Write your JavaScript code to a UTF-8 `.mjs` file (e.g., `C:/Users/Wind/AppData/Local/Temp/ego-round-01.mjs`) using your file-writing tool.
2. Execute it via `import()`:

```powershell
C:\Users\Wind\.local\bin\ego-browser.exe nodejs -e "await import('file:///C:/Users/Wind/AppData/Local/Temp/ego-round-01.mjs')"
```

The wrapper at `C:\Users\Wind\.local\bin\ego-browser.exe` automatically:
- Closes `stdin` (`< NUL`) so `ego-browser nodejs` never hangs on non-TTY pipes.
- De-elevates execution when called from an Administrator terminal/Agent (such as Antigravity) so `ego.exe` never rejects the connection with `ego-browser is running as administrator`.

The guide ends with a line starting `[ego-browser:skill] end of guide`. If that
line is missing, the output was truncated: save it to a file and read the file
in parts, for example:
`C:\Users\Wind\.local\bin\ego-browser.exe skill > "$env:TEMP\ego-browser-skill.md"` in PowerShell.

## References

- [Install or upgrade ego lite](references/install.md) — read when
  `ego-browser` is not found, or `skill` is an unknown command.
- [Clearing cookies, cache, and storage](references/clearing-state.md) — read
  before clearing any cookie, cache, or storage; some clears reach the whole
  browser profile.
