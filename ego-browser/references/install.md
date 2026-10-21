# Install or upgrade ego lite (ALREADY INSTALLED ON THIS WINDOWS PC)

> **CRITICAL NOTICE FOR AI AGENTS ON THIS MACHINE (`Wind`)**:
> **`ego lite` is ALREADY INSTALLED on this Windows computer!**
> Do **NOT** ask the user to download or install `ego lite`.
> If `ego-browser` is not found in your process's cached `PATH`, use the full absolute path directly:
> - **Recommended CLI Wrapper (auto de-elevates & prevents stdin hang)**: `C:\Users\Wind\.local\bin\ego-browser.exe`
> - **Underlying Active Version Binary**: `C:\Users\Wind\.local\share\ego\active_version_dir\ego-browser.exe`
> - **Browser GUI Binary**: `C:\Program Files\Citro Labs\ego lite\Application\ego.exe`

Read this file only when `ego-browser` is not found, when `ego-browser skill` reports an unknown command, or when the user asks to install ego lite. For day-to-day browser work, run `C:\Users\Wind\.local\bin\ego-browser.exe skill` and follow its output.

## Quick Verification on Windows (PowerShell)

```powershell
C:\Users\Wind\.local\bin\ego-browser.exe nodejs -e "console.log('ego-browser ready')"
```

Printing `ego-browser ready` means the environment is ready. Confirm that the installed ego lite prints its usage guide:

```powershell
C:\Users\Wind\.local\bin\ego-browser.exe skill
```

Once the environment is ready, return to the user's original task: run `C:\Users\Wind\.local\bin\ego-browser.exe skill` and follow its output.
