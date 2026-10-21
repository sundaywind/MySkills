param(
  [string]$State = "",
  [string]$Mode = "hook",
  [string]$Token = "",
  [string]$InputJson = "",
  [int]$WatchPid = 0,
  [switch]$DryRun
)

$ErrorActionPreference = "SilentlyContinue"
$ProgressPreference = "SilentlyContinue"
try {
  $Utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
  [Console]::InputEncoding = $Utf8NoBom
  [Console]::OutputEncoding = $Utf8NoBom
} catch {}

$ScriptPath = if (-not [string]::IsNullOrWhiteSpace($PSCommandPath)) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
$ScriptDir = Split-Path -Parent $ScriptPath
$StateFile = Join-Path $ScriptDir ".clawd-mochi-state.json"
$LogFile = Join-Path $ScriptDir ".clawd-mochi.log"
$UrlFile = Join-Path $ScriptDir "clawd-mochi.url"
$IpFile = Join-Path $ScriptDir ".clawd-mochi-ip"
$LegacyIpFile = Join-Path $env:USERPROFILE ".clawd_mochi_ip"
$DefaultHost = "clawd-mochi.local"
$DefaultSleepState = "sleep"
$DuplicateWindowMs = 300
$PostStopSuppressMs = 7000
$DoneHoldMs = 5200
$IdleSleepMs = 180000
$PipelineInputText = ""
$script:HadHookInput = $false
$script:HookInputInvalid = $false

$ValidStates = @(
  "idle",
  "thinking",
  "reading",
  "coding",
  "running",
  "delegating",
  "planning",
  "waiting",
  "compacting",
  "notify",
  "done",
  "error",
  "sleep"
)

function Write-HookLog {
  param([string]$Message)
  if ($env:CLAWD_MOCHI_DEBUG -ne "1") { return }
  Add-Content -LiteralPath $LogFile -Encoding UTF8 -Value "$(Get-Date -Format o) $Message"
}

# Lifecycle log (session start / watcher / sleep / per-event trace). Silent unless
# CLAWD_MOCHI_DEBUG=1, so a shipped device writes nothing to disk in normal use.
function Write-LifeLog {
  param([string]$Message)
  if ($env:CLAWD_MOCHI_DEBUG -ne "1") { return }
  try { Add-Content -LiteralPath $LogFile -Encoding UTF8 -Value "$(Get-Date -Format o) $Message" } catch {}
}

function Read-JsonFile {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return $null }
  try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-NowMs {
  return [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
}

function Save-StateRecord {
  param(
    [string]$NewState,
    [string]$SessionToken,
    [int64]$SuppressUntilMs = 0,
    [int64]$IdleSleepDueMs = 0
  )
  $record = [ordered]@{
    state = $NewState
    updatedAt = (Get-Date).ToUniversalTime().ToString("o")
    updatedAtMs = Get-NowMs
    sessionToken = $SessionToken
    watchPid = $WatchPid
    suppressUntilMs = $SuppressUntilMs
    idleSleepDueMs = $IdleSleepDueMs
  }
  Set-Content -LiteralPath $StateFile -Encoding UTF8 -Value ($record | ConvertTo-Json -Compress)
}

function Get-Prop {
  param($Object, [string[]]$Names)
  if ($null -eq $Object) { return $null }
  foreach ($name in $Names) {
    if ($Object.PSObject.Properties.Name -contains $name) { return $Object.$name }
  }
  return $null
}

function Read-RedirectedInputUtf8 {
  try {
    if (-not [Console]::IsInputRedirected) { return "" }
    $stream = [Console]::OpenStandardInput()
    $buffer = New-Object byte[] 4096
    $memory = New-Object System.IO.MemoryStream
    while ($true) {
      $read = $stream.Read($buffer, 0, $buffer.Length)
      if ($read -le 0) { break }
      $memory.Write($buffer, 0, $read)
    }
    $bytes = $memory.ToArray()
    if ($bytes.Length -eq 0) { return "" }
    return ([System.Text.Encoding]::UTF8.GetString($bytes))
  } catch {
    try { return [Console]::In.ReadToEnd() } catch { return "" }
  }
}

function Read-HookInput {
  $stdin = ""
  if (-not [string]::IsNullOrWhiteSpace($InputJson)) {
    $stdin = $InputJson
  }
  if ([string]::IsNullOrWhiteSpace($stdin)) {
    # Guard against a blocking read when stdin is the console (e.g. SessionStart at
    # TUI launch). Only read when Codex actually redirected/piped a payload.
    $stdin = Read-RedirectedInputUtf8
  }
  if ([string]::IsNullOrWhiteSpace($stdin) -and -not [string]::IsNullOrWhiteSpace($script:PipelineInputText)) {
    $stdin = $script:PipelineInputText
  }
  if ([string]::IsNullOrWhiteSpace($stdin)) { return $null }
  $script:HadHookInput = $true
  try { return $stdin | ConvertFrom-Json } catch {
    $script:HookInputInvalid = $true
    Write-HookLog "invalid-json $($_.Exception.Message)"
    return $null
  }
}

function Normalize-BaseUrl {
  param([string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) { return "" }
  $v = $Value.Trim().TrimEnd("/")
  if ($v -notmatch "^https?://") { $v = "http://$v" }
  return $v
}

function Get-TextFileValue {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return "" }
  try { return (Get-Content -LiteralPath $Path -Raw).Trim() } catch { return "" }
}

function Resolve-MochiLocalIp {
  $curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
  if ([string]::IsNullOrWhiteSpace($curl)) { return "" }
  try {
    $ip = & $curl -s -m 5 -o NUL -w "%{remote_ip}" "http://$DefaultHost/state" 2>$null
    $ip = ([string]$ip).Trim()
    if ($ip -match "^\d{1,3}(\.\d{1,3}){3}$") {
      Set-Content -LiteralPath $IpFile -Encoding ASCII -Value $ip
      return $ip
    }
  } catch {}
  return ""
}

function Get-KnownBaseUrls {
  # Known targets only — NO mDNS resolve. This is the hot path, so every event
  # stays ~70ms instead of paying a ~2.7s blocking clawd-mochi.local lookup.
  $seen = @{}
  $values = New-Object System.Collections.Generic.List[string]

  foreach ($raw in @(
    $env:CLAWD_MOCHI_URL,
    (Get-TextFileValue $UrlFile),
    (Get-TextFileValue $IpFile),
    (Get-TextFileValue $LegacyIpFile)
  )) {
    $url = Normalize-BaseUrl $raw
    if ($url -and -not $seen.ContainsKey($url)) {
      $seen[$url] = $true
      [void]$values.Add($url)
    }
  }
  return $values
}

function Test-RecentDuplicate {
  param([string]$NewState, [switch]$Force)
  if ($Force) { return $false }
  $record = Read-JsonFile $StateFile
  if ($null -eq $record -or $record.state -ne $NewState) { return $false }
  try {
    $age = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [int64]$record.updatedAtMs
    return ($age -lt $DuplicateWindowMs)
  } catch { return $false }
}

function Send-MochiState {
  param(
    [string]$NewState,
    [string]$SessionToken = "",
    [int64]$SuppressUntilMs = 0,
    [switch]$Force
  )
  if ($ValidStates -notcontains $NewState) { $NewState = "idle" }
  $idleSleepDueMs = 0
  if ($NewState -eq "idle") {
    $idleSleepDueMs = (Get-NowMs) + $IdleSleepMs
  }
  if (Test-RecentDuplicate -NewState $NewState -Force:$Force) {
    Write-HookLog "skip-duplicate state=$NewState"
    return
  }

  if ($DryRun) {
    Write-HookLog "dry-run state=$NewState"
    Write-Output $NewState
    return
  }

  $trySend = {
    param([string]$base)
    $uri = "$base/event?s=$([uri]::EscapeDataString($NewState))"
    try {
      Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 -Uri $uri | Out-Null
      if ($base -match "^http://\d{1,3}(\.\d{1,3}){3}$") {
        Set-Content -LiteralPath $IpFile -Encoding ASCII -Value ($base -replace "^https?://", "")
      }
      Write-HookLog "sent state=$NewState url=$uri"
      return $true
    } catch {
      Write-HookLog "send-failed state=$NewState url=$uri error=$($_.Exception.Message)"
      return $false
    }
  }

  # Hot path: cached IP / known targets first — no mDNS lookup, ~70ms.
  foreach ($base in (Get-KnownBaseUrls)) {
    if (& $trySend $base) { Save-StateRecord -NewState $NewState -SessionToken $SessionToken -SuppressUntilMs $SuppressUntilMs -IdleSleepDueMs $idleSleepDueMs; Write-LifeLog "send-ok state=$NewState via=$base"; return }
  }

  # Cold path: known targets all failed (device IP drifted?) — resolve mDNS once,
  # re-cache, and retry. This ~2.7s cost is now paid only when the IP actually changed.
  $resolved = Resolve-MochiLocalIp
  if ($resolved -and (& $trySend (Normalize-BaseUrl $resolved))) {
    Save-StateRecord -NewState $NewState -SessionToken $SessionToken -SuppressUntilMs $SuppressUntilMs -IdleSleepDueMs $idleSleepDueMs; Write-LifeLog "send-ok state=$NewState via=resolved:$resolved"; return
  }
  if (& $trySend (Normalize-BaseUrl $DefaultHost)) {
    Save-StateRecord -NewState $NewState -SessionToken $SessionToken -SuppressUntilMs $SuppressUntilMs -IdleSleepDueMs $idleSleepDueMs; Write-LifeLog "send-ok state=$NewState via=mdns"; return
  }

  Save-StateRecord -NewState $NewState -SessionToken $SessionToken -SuppressUntilMs $SuppressUntilMs -IdleSleepDueMs $idleSleepDueMs
  Write-LifeLog "send-FAIL state=$NewState (device unreachable on all targets)"
}

function Get-ToolName {
  param($Payload)
  $name = Get-Prop $Payload @("tool_name", "toolName", "name")
  if ($null -eq $name) { return "" }
  return [string]$name
}

function Get-CommandText {
  param($Payload)
  $input = Get-Prop $Payload @("tool_input", "toolInput", "input")
  if ($null -eq $input) { return "" }
  $command = Get-Prop $input @("command", "cmd", "script")
  if ($null -eq $command) { return "" }
  return [string]$command
}

function Test-UserInputTool {
  param($Payload)
  $tool = Get-ToolName $Payload
  return ($tool -match "(?i)(AskUserQuestion|request_user_input|request-user-input|user_input|select_option|choose_option)")
}

function Test-ReadOnlyCommand {
  param([string]$Command)
  $c = $Command.Trim()
  if ($c.Length -eq 0) { return $false }
  if ($c -match "(?i)\b(Set-Content|Add-Content|Out-File|New-Item|Remove-Item|Move-Item|Rename-Item|Copy-Item|Start-Process|Invoke-WebRequest|curl|iwr|irm|npm\s+install|pnpm\s+install|yarn\s+install|git\s+(apply|commit|push|pull|checkout|reset|merge|rebase|add|restore|clean)|docker\s+(run|compose|build|exec)|mvn\s+(test|package|install)|cargo\s+(test|build|run)|npm\s+(run|test)|pnpm\s+(run|test)|yarn\s+(run|test)|pytest|playwright|python|node)\b") { return $false }
  return ($c -match "(?i)^\s*(&\s*)?(Get-Content|gc|type|cat|rg|ripgrep|Select-String|Get-ChildItem|gci|dir|ls|Get-Location|pwd|Test-Path|Resolve-Path|Get-Command|where(\.exe)?|Get-Process|Get-Service|git\s+(status|show|diff|log|grep|branch|rev-parse)|docker\s+ps|docker\s+logs)\b")
}

function Test-EditingCommand {
  param([string]$Command)
  return ($Command -match "(?i)\b(apply_patch|Set-Content|Add-Content|Out-File|New-Item|Remove-Item|Move-Item|Rename-Item|Copy-Item|git\s+(apply|add|commit|checkout|restore|reset|clean))\b")
}

function Get-ToolState {
  param($Payload)
  $tool = Get-ToolName $Payload
  $command = Get-CommandText $Payload

  if (Test-UserInputTool $Payload) { return "waiting" }
  if ($tool -match "(?i)(ExitPlanMode|update_plan|planning|plan_mode|plan-mode)") { return "planning" }
  if ($tool -match "(?i)(Subagent|Task|multi_agent|handoff_thread|send_message_to_thread|create_thread|fork_thread)") { return "delegating" }
  if ($tool -match "(?i)^(apply_patch|Edit|Write|MultiEdit|NotebookEdit)$|apply_patch|edit|write|patch|file_write") { return "coding" }
  if ($tool -match "(?i)^(Bash|Shell|Command)$|shell_command|terminal|exec") {
    if (Test-EditingCommand $command) { return "coding" }
    if (Test-ReadOnlyCommand $command) { return "reading" }
    return "running"
  }
  if ($tool -match "(?i)(compact|summari[sz]e_context)") { return "compacting" }
  if ($tool -match "(?i)(mcp__|automation|reminder|monitor|notification|notify|linear|jira|slack)") { return "notify" }
  if ($tool -match "(?i)node_repl|computer|browser|chrome") { return "running" }
  if ($tool -match "(?i)read|search|fetch|open|find|list|get|resolve|context7|everything|web|finance|weather|sports|time") { return "reading" }
  if ($tool -match "(?i)create|update|move|delete|write|edit|patch|apply") { return "coding" }
  return "running"
}

function Test-FailedValue {
  param($Value, [int]$Depth = 0)
  if ($Depth -gt 6 -or $null -eq $Value) { return $false }
  if ($Value -is [System.Array]) {
    foreach ($item in $Value) { if (Test-FailedValue -Value $item -Depth ($Depth + 1)) { return $true } }
    return $false
  }
  if ($Value -isnot [psobject]) { return $false }
  foreach ($prop in $Value.PSObject.Properties) {
    $name = $prop.Name
    $v = $prop.Value
    if ($name -match "(?i)^(isError|error|failed|failure)$" -and $v -eq $true) { return $true }
    # NOTE: a non-zero exit code is NOT treated as an error. Normal commands exit
    # non-zero all the time (ripgrep/grep with no match -> 1, failing tests, type
    # checks), and flashing the X_X face on every one of those is what made the
    # mascot look broken. Codex hooks should not map every non-zero exit code to
    # error either, so this matches that behaviour. Only explicit error flags count.
    if ($name -match "(?i)^(status|result)$" -and ($v -is [string]) -and $v -match "(?i)^(failed|failure|error)$") { return $true }
    if (Test-FailedValue -Value $v -Depth ($Depth + 1)) { return $true }
  }
  return $false
}

function Test-ToolFailed {
  param($Payload)
  $response = Get-Prop $Payload @("tool_response", "toolResponse", "response", "result")
  if ($null -eq $response) { return $false }
  return Test-FailedValue -Value $response
}

function Get-PayloadText {
  param($Payload)
  if ($null -eq $Payload) { return "" }
  try { return ($Payload | ConvertTo-Json -Depth 32 -Compress) } catch { return "" }
}

function Test-NeedsUser {
  param($Payload)
  $text = Get-PayloadText $Payload
  if ([string]::IsNullOrWhiteSpace($text)) { return $false }
  return ($text -match "(?i)(permission|approval|approve|allow|deny|escalat|sandbox|request_permissions|approval request|confirm|choose|choice|select|submit|apply these changes|apply changes|yes/no|\by/n\b|askuserquestion|request_user_input|\u662f\u5426|\u9009\u62e9|\u8f93\u5165|\u786e\u8ba4|\u63d0\u4ea4|\u5e94\u7528|\u5141\u8bb8|\u6279\u51c6|\u540c\u610f|\u6388\u6743)")
}

function Test-UserChoiceText {
  param([string]$Text)
  if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
  $trimmed = $Text.Trim()
  if ($trimmed.Length -gt 160) { return $false }
  $hasMeaningfulText = ($trimmed -match "(?i)[a-z0-9]" -or $trimmed -match "[\u4E00-\u9FFF]")
  if (-not $hasMeaningfulText) { return $false }
  $choicePrefix = "(?i)^(confirm|choose|select|submit|apply these changes|apply changes|yes/no|\by/n\b|should i|do you want|would you like|\u662f\u5426|\u8bf7\u9009\u62e9|\u9009\u62e9|\u8f93\u5165|\u786e\u8ba4|\u63d0\u4ea4|\u5e94\u7528|\u8981\u4e0d\u8981|\u9700\u4e0d\u9700\u8981|\u662f\u5426\u9700\u8981|\u9700\u8981.*(\u786e\u8ba4|\u9009\u62e9|\u7ee7\u7eed)|\u8bf7\u786e\u8ba4|\u8bf7\u95ee)"
  if ($trimmed -match $choicePrefix) { return $true }
  if ($trimmed -match "\?\?" -and $trimmed -notmatch "[\u4E00-\u9FFF]") { return $false }
  return ($trimmed -match "[?\uFF1F]\s*$")
}

function Test-AssistantQuestion {
  param($Payload)
  $message = Get-Prop $Payload @("last_assistant_message", "lastAssistantMessage", "message", "notification", "text")
  if ([string]::IsNullOrWhiteSpace($message)) { return $false }
  $text = ([string]$message).Trim()
  return (Test-UserChoiceText $text)
}

function Test-Interrupted {
  param($Payload)
  $text = Get-PayloadText $Payload
  if ([string]::IsNullOrWhiteSpace($text)) { return $false }
  return ($text -match "(?i)(interrupted|interrupt|cancelled|canceled|aborted|paused|pause|escape|esc|user_cancel|user-abort|\u4e2d\u65ad|\u53d6\u6d88|\u6682\u505c)")
}

function Test-AssistantReportsError {
  param($Payload)
  $message = Get-Prop $Payload @("last_assistant_message", "lastAssistantMessage")
  if ([string]::IsNullOrWhiteSpace($message)) { return $false }
  $text = ([string]$message).Trim()
  return ($text -match "(?i)(failed|failure|error|exception|crash|timed out|unable to|could not|was not able|not able to|blocked|denied|\u5931\u8d25|\u62a5\u9519|\u9519\u8bef|\u5f02\u5e38|\u672a\u80fd|\u65e0\u6cd5|\u88ab\u62d2\u7edd|\u88ab\u963b\u6b62)")
}

function Test-InternalAppSession {
  # The Codex DESKTOP APP spawns its own background helper sessions after each turn
  # (prompt suggestions, the "exclude" list, title/summary) on a -mini model, running
  # inside the app's own install directory. Those fire the SAME global hooks as your
  # real chat, so without this guard the mascot flickers thinking/reading/done right
  # after a turn "ends". Identify them by cwd (inside the WindowsApps app folder) and
  # ignore them so the device stays on your real session's state.
  param($Payload)
  $cwd = [string](Get-Prop $Payload @("cwd", "workingDirectory", "working_dir"))
  if ($cwd -match "(?i)WindowsApps[\\/]+OpenAI\.Codex") { return $true }
  $message = [string](Get-Prop $Payload @("last_assistant_message", "lastAssistantMessage"))
  if ($message -match '(?i)\\?"suggestions\\?"\s*:\s*\[') { return $true }
  if ($message -match "(?i)suggestions" -and $message -match '(?i)\\?"(appId|description|prompt|title)\\?"\s*:') { return $true }
  $text = Get-PayloadText $Payload
  if ($text -match '(?i)\\?"suggestions\\?"\s*:\s*\[') { return $true }
  if ($text -match "(?i)ambient[-_ ]?suggestions|followUpQueue") { return $true }
  return $false
}

function Test-PostStopSuppressed {
  param($Payload)
  $event = [string](Get-Prop $Payload @("hook_event_name", "hookEventName"))
  if ([string]::IsNullOrWhiteSpace($event)) { return $false }
  if ($event -match "^(SessionStart|UserPromptSubmit|PermissionRequest|Notification|Stop)$") { return $false }
  $record = Read-JsonFile $StateFile
  if ($null -eq $record) { return $false }
  try {
    return (([int64]$record.suppressUntilMs) -gt (Get-NowMs))
  } catch { return $false }
}

function Get-StateFromPayload {
  param($Payload)
  $event = Get-Prop $Payload @("hook_event_name", "hookEventName")
  if ($null -eq $event) { return "idle" }

  switch ([string]$event) {
    "SessionStart" { return "idle" }
    "UserPromptSubmit" { return "thinking" }
    "PermissionRequest" { return "waiting" }
    "PreToolUse" { return Get-ToolState $Payload }
    "PostToolUse" {
      if (Test-ToolFailed $Payload) { return "error" }
      if (Test-UserInputTool $Payload) { return "thinking" }
      return Get-ToolState $Payload
    }
    "PreCompact" { return "compacting" }
    "PostCompact" { return "thinking" }
    "SubagentStart" { return "delegating" }
    "SubagentStop" {
      if (Test-AssistantReportsError $Payload) { return "error" }
      return "thinking"
    }
    "Notification" {
      if (Test-Interrupted $Payload) { return "idle" }
      if (Test-NeedsUser $Payload) { return "waiting" }
      return "notify"
    }
    "Stop" {
      if (Test-Interrupted $Payload) { return "idle" }
      if (Test-AssistantQuestion $Payload) { return "waiting" }
      return "done"
    }
    "SessionEnd" { return $DefaultSleepState }
    default { return "idle" }
  }
}

function Get-CodexAncestorPid {
  # Walk up the process tree to find the Codex session process to watch. Match any
  # ancestor whose image name or path contains "codex" (codex.exe, Codex.exe, a
  # desktop host, etc.) so the watcher still arms across Codex build variants.
  $current = $PID
  for ($i = 0; $i -lt 16; $i++) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$current"
    if ($null -eq $proc) { return 0 }
    $parent = [int]$proc.ParentProcessId
    if ($parent -le 0) { return 0 }
    $parentProc = Get-CimInstance Win32_Process -Filter "ProcessId=$parent"
    if ($null -eq $parentProc) { return 0 }
    if ($parentProc.Name -match "(?i)codex" -or $parentProc.ExecutablePath -match "(?i)codex") { return $parent }
    $current = $parent
  }
  return 0
}

function Start-CliWatcher {
  param([string]$SessionToken)
  if ([string]::IsNullOrWhiteSpace($SessionToken)) { return }
  $ancestorPid = Get-CodexAncestorPid
  if ($ancestorPid -le 0) {
    Write-LifeLog "watch-skip no-codex-ancestor (sleep-on-close disabled this session)"
    return
  }
  $ps = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
  if ([string]::IsNullOrWhiteSpace($ps)) { return }
  $args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$ScriptPath`"",
    "-Mode", "watch-cli",
    "-Token", "`"$SessionToken`"",
    "-WatchPid", "$ancestorPid"
  )
  try {
    Start-Process -FilePath $ps -ArgumentList $args -WindowStyle Hidden | Out-Null
    Write-LifeLog "watch-start pid=$ancestorPid token=$SessionToken"
  } catch {
    Write-LifeLog "watch-start-failed $($_.Exception.Message)"
  }
}

function Start-DoneReturn {
  param([string]$SessionToken)
  $ps = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
  if ([string]::IsNullOrWhiteSpace($ps)) { return }
  $args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$ScriptPath`"",
    "-Mode", "done-return",
    "-Token", "`"$SessionToken`""
  )
  try {
    Start-Process -FilePath $ps -ArgumentList $args -WindowStyle Hidden | Out-Null
    Write-LifeLog "done-return-start token=$SessionToken"
  } catch {
    Write-LifeLog "done-return-start-failed $($_.Exception.Message)"
  }
}

function Start-IdleSleepTimer {
  param([string]$SessionToken)
  $ps = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
  if ([string]::IsNullOrWhiteSpace($ps)) { return }
  $args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$ScriptPath`"",
    "-Mode", "idle-sleep",
    "-Token", "`"$SessionToken`""
  )
  try {
    Start-Process -FilePath $ps -ArgumentList $args -WindowStyle Hidden | Out-Null
    Write-LifeLog "idle-sleep-start token=$SessionToken"
  } catch {
    Write-LifeLog "idle-sleep-start-failed $($_.Exception.Message)"
  }
}

function Test-AnyCodexAlive {
  # True if any Codex CLI process is still running. Used to decide whether closing
  # THIS session should sleep the mascot (only when no other session is active).
  try {
    $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "(?i)codex" }
    return ($null -ne $procs -and @($procs).Count -gt 0)
  } catch { return $false }
}

function Wait-And-SleepOnExit {
  if ($WatchPid -le 0) { exit 0 }
  while ($true) {
    Start-Sleep -Milliseconds 350
    $proc = Get-Process -Id $WatchPid -ErrorAction SilentlyContinue
    if ($null -eq $proc) { break }
  }
  # The watched Codex session process has exited. Sleep the mascot UNLESS another
  # Codex session is still alive (then that session owns the screen). This replaces
  # the old token-equality guard, which broke because turn events wiped the token.
  Start-Sleep -Milliseconds 250
  if (Test-AnyCodexAlive) {
    Write-LifeLog "watch-skip-active pid=$WatchPid token=$Token (another codex session alive; no sleep)"
  } else {
    Send-MochiState -NewState $DefaultSleepState -SessionToken $Token -Force
    Write-LifeLog "watch-sleep pid=$WatchPid token=$Token"
  }
  exit 0
}

function Wait-And-IdleAfterDone {
  Start-Sleep -Milliseconds $DoneHoldMs
  $record = Read-JsonFile $StateFile
  if ($null -eq $record -or $record.state -ne "done") { exit 0 }
  $suppressUntilMs = 0
  try { $suppressUntilMs = [int64]$record.suppressUntilMs } catch {}
  Send-MochiState -NewState "idle" -SessionToken $Token -SuppressUntilMs $suppressUntilMs -Force
  Start-IdleSleepTimer -SessionToken $Token
  Write-LifeLog "done-return-idle token=$Token"
  exit 0
}

function Wait-And-SleepAfterIdle {
  Start-Sleep -Milliseconds $IdleSleepMs
  $record = Read-JsonFile $StateFile
  if ($null -eq $record -or $record.state -ne "idle") { exit 0 }
  try {
    $due = [int64]$record.idleSleepDueMs
    if ($due -le 0 -or $due -gt (Get-NowMs)) { exit 0 }
  } catch { exit 0 }
  Send-MochiState -NewState $DefaultSleepState -SessionToken $Token -Force
  Write-LifeLog "idle-sleep-fired token=$Token"
  exit 0
}

if ($Mode -eq "watch-cli") {
  Wait-And-SleepOnExit
}

if ($Mode -eq "done-return") {
  Wait-And-IdleAfterDone
}

if ($Mode -eq "idle-sleep") {
  Wait-And-SleepAfterIdle
}

$PipelineInputText = ""
$payload = Read-HookInput
if ($null -eq $payload -and -not $script:HookInputInvalid) {
  try { $PipelineInputText = (@($input) -join [Environment]::NewLine).Trim() } catch {}
  if (-not [string]::IsNullOrWhiteSpace($script:PipelineInputText)) {
    $payload = Read-HookInput
  }
}

if ([string]::IsNullOrWhiteSpace($State) -and $null -eq $payload) {
  Write-LifeLog "skip-empty-or-invalid-payload invalid=$script:HookInputInvalid"
  exit 0
}

# Ignore the Codex desktop app's internal background helper sessions (suggestions,
# "exclude", title/summary on a -mini model in the app install dir). They fire the
# same global hooks and would otherwise make the mascot flicker after every turn.
if (-not $DryRun -and (Test-InternalAppSession $payload)) {
  $evt = [string](Get-Prop $payload @("hook_event_name", "hookEventName"))
  Write-LifeLog "skip-internal-app-session event=$evt"
  exit 0
}

$eventName = Get-Prop $payload @("hook_event_name", "hookEventName")
$sessionId = Get-Prop $payload @("session_id", "sessionId")
$sessionToken = ""
$isSessionStart = ($eventName -eq "SessionStart" -or $Mode -eq "session-start")
if ($isSessionStart) {
  $sessionToken = if ([string]::IsNullOrWhiteSpace($sessionId)) { [guid]::NewGuid().ToString("N") } else { [string]$sessionId }
}

# Preserve the session token across turn events. Only SessionStart mints a token;
# every other event must KEEP the existing one, otherwise it wipes the state file
# token to "" and the close-watcher can never match it -> sleep never fires.
if (-not $isSessionStart) {
  $existing = Read-JsonFile $StateFile
  $priorToken = Get-Prop $existing @("sessionToken")
  if (-not [string]::IsNullOrWhiteSpace($priorToken)) { $sessionToken = [string]$priorToken }
}

$nextState = if (-not [string]::IsNullOrWhiteSpace($State)) { $State } else { Get-StateFromPayload $payload }
$forceSend = ($isSessionStart -or $nextState -eq "sleep" -or $nextState -eq "idle" -or $nextState -eq "waiting" -or $nextState -eq "done")
$suppressUntilMs = 0

if (-not $DryRun -and (Test-PostStopSuppressed $payload)) {
  $evt = [string](Get-Prop $payload @("hook_event_name", "hookEventName"))
  Write-LifeLog "skip-post-stop event=$evt state=$nextState"
  exit 0
}

if ($eventName -eq "Stop" -or ($eventName -eq "Notification" -and (Test-Interrupted $payload))) {
  $suppressUntilMs = (Get-NowMs) + $PostStopSuppressMs
}

# Per-invocation trace (debug-gated) so launch/interrupt/close behaviour is
# observable when CLAWD_MOCHI_DEBUG=1. eventName is "" for arg-driven calls.
Write-LifeLog "evt event=$eventName mode=$Mode -> state=$nextState token=$sessionToken"

Send-MochiState -NewState $nextState -SessionToken $sessionToken -SuppressUntilMs $suppressUntilMs -Force:$forceSend

if ($eventName -eq "Stop" -and $nextState -eq "done" -and -not $DryRun) {
  Start-DoneReturn -SessionToken $sessionToken
}

if ($nextState -eq "idle" -and -not $DryRun) {
  Start-IdleSleepTimer -SessionToken $sessionToken
}

if ($isSessionStart -and -not $DryRun) {
  Start-CliWatcher -SessionToken $sessionToken
}

exit 0
