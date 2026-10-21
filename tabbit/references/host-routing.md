# Host routing

Use this reference only for explicit product or instance selection, Windows
multiline transport trouble, or launcher, installation, permission, or routing
failure. Keep using the installed stable launcher; never invoke a CLI from an
application bundle, read `endpoint.json`, or start the Browser-owned Runtime
Service directly.

## Stable launchers and multiline input

- POSIX: `"$HOME/.local/bin/tabbit-cli"`
- Windows PowerShell: `& "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"`
- Windows CMD: `"%LOCALAPPDATA%\Tabbit\LocalAgent\bin\tabbit-cli.exe"`

On Windows, send multiline code through pipe-backed stdin. If the host cannot
close the pipe, write the code to a task-scoped temporary `.js` file, invoke the
stable launcher from CMD with `<` redirection, and remove the file after its
receipt. Do not use a PowerShell pipeline, here-string, `echo`, or console PTY;
they can alter newlines, encoding, or long input.

## Explicit product or instance selection

Without an explicit user request, do not inspect the registry or set an
override. The stable launcher selects the instance for each command.

For an explicit request, inspect only the current user's registry with
read-only OS commands. Normalize only case and surrounding space, then match
exactly one canonical product: `Tabbit Browser`, `Tabbit Browser Dev`, `Tabbit`,
or `Tabbit Dev`. These are not aliases. If multiple valid records match, show
their instance IDs and ask the user.

Set the selected uppercase 16-hex ID before the first command and keep it fixed
for the task:

```bash
export TABBIT_PLAYWRIGHT_INSTANCE='0123456789ABCDEF'
"$HOME/.local/bin/tabbit-cli" tabs --task NAME
unset TABBIT_PLAYWRIGHT_INSTANCE
```

```powershell
$env:TABBIT_PLAYWRIGHT_INSTANCE = '0123456789ABCDEF'
& "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe" tabs --task NAME
Remove-Item Env:TABBIT_PLAYWRIGHT_INSTANCE
```

Do not probe with an unpinned launcher or change the ID during the task.

## Validate records without repairing them

On POSIX, inspect only `$HOME/.local/share/tabbit-playwright/instances`. The
directory must be owned by the current user, mode 0700, and not a symlink. Each
record must be a regular non-symlink owned by that user with mode 0600, an
uppercase 16-hex filename ID, exact managed marker and line count, absolute
managed paths, and a canonical product sidecar.

On Windows, inspect only
`%LOCALAPPDATA%\Tabbit\LocalAgent\instances` using `Get-ChildItem`, `Get-Item`,
`Get-Acl`, and bounded `Get-Content -Raw`. A record must be a regular file below
that protected root, have no reparse component, and have the protected DACL for
the current user and `SYSTEM`. Require the documented version and exact fields,
a matching uppercase 16-hex ID, canonical product, accepted absolute paths, and
an endpoint path below the record's user-data directory.

Ignore invalid records. Never repair the registry, broaden permissions or ACLs,
require administrator access, disable security controls, or relocate binaries.

## Failure boundaries

- **Agent sandbox denial:** request approval for the stable launcher and, only
  for explicit selection, read-only registry access.
- **OS ownership, mode, ACL, endpoint access, quarantine, or signing policy:**
  verify Agent and Browser share an OS user, then relaunch Browser once so it can
  repair its managed integration. Report any remaining denial unchanged.
- **Missing or malformed launcher or registry:** invalid installation.
- **Exit 69:** routing is unavailable or ambiguous; pin a valid instance.
- **Runtime unavailable:** relaunch Browser once with permission; do not launch
  the service yourself or switch browser backends.
