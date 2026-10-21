#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  Clawd Mochi —— Codex 适配器 · WiFi 版  (macOS / Linux, 零依赖)
#
#  作用：Codex 每次触发 hook 时把一段 JSON 从 stdin 喂给本脚本；脚本判断
#        这是什么事件(读代码/写文件/跑命令/等待/完成…)，映射成一个状态字，
#        再通过 HTTP 发给同一局域网里的 Clawd Mochi 设备：
#              GET http://<设备IP>/event?s=<state>
#
#  为什么用 bash：macOS 自带 bash + curl + perl，开箱即用，无需安装 Python、
#        PowerShell 或任何依赖。行为对齐 Windows 版 .ps1(状态映射 + done 回落 +
#        空闲转 sleep + 关闭 Codex 转 sleep)。
#
#  设备地址来源(按优先级)：
#     1) 与本脚本同目录的 clawd-mochi.url   (内容如 http://192.168.1.23)
#     2) ~/.clawd_mochi_ip                  (缓存的纯 IP)
#     3) 解析 clawd-mochi.local             (mDNS，macOS 原生秒解析)
#
#  调试：CLAWD_MOCHI_DEBUG=1 把每步写到 ~/.clawd_mochi_codex.log。
#        CLAWD_MOCHI_DRYRUN=1 只打印判定出的状态、不真正发送(便于自测)。
# ╚══════════════════════════════════════════════════════════════╝
set +e

# ── 参数：默认从 stdin 读 JSON；SessionStart 与内部定时器用 --state / --mode ──
STATE=""; MODE="hook"; TOKEN=""; WATCH_PID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --state) STATE="$2"; shift 2 ;;
    --mode)  MODE="$2";  shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --watchpid) WATCH_PID="$2"; shift 2 ;;
    *) shift ;;
  esac
done

SELF="$0"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" 2>/dev/null && pwd)"
URL_FILE="$SCRIPT_DIR/clawd-mochi.url"
IP_FILE="$HOME/.clawd_mochi_ip"
STATE_FILE="$HOME/.clawd_mochi_codex.state"   # state<TAB>updatedAtMs<TAB>token<TAB>suppressUntilMs<TAB>idleSleepDueMs
LOG_FILE="$HOME/.clawd_mochi_codex.log"
DEFAULT_HOST="clawd-mochi.local"

DUP_WINDOW_MS=300
POST_STOP_SUPPRESS_MS=7000
DONE_HOLD_MS=5200
IDLE_SLEEP_MS=180000

VALID="idle thinking reading coding running delegating planning waiting compacting notify done error sleep"

log()      { [ "$CLAWD_MOCHI_DEBUG" = "1" ] && printf '%s %s\n' "$(date +%FT%T)" "$*" >> "$LOG_FILE" 2>/dev/null; return 0; }
now_ms()   { perl -MTime::HiRes=time -e 'printf "%.0f", time()*1000' 2>/dev/null || echo 0; }
sleep_ms() { perl -e 'select(undef,undef,undef,$ARGV[0]/1000)' "$1" 2>/dev/null || sleep $(( ${1%.*} / 1000 )); }
is_valid() { case " $VALID " in *" $1 "*) return 0;; *) return 1;; esac; }
spawn()    { nohup bash "$@" >/dev/null 2>&1 & disown 2>/dev/null; return 0; }   # 完全脱离，hook 立即返回

read_state_field() { [ -f "$STATE_FILE" ] && cut -f"$1" "$STATE_FILE" 2>/dev/null; }
save_state() { printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$(now_ms)" "$2" "${3:-0}" "${4:-0}" > "$STATE_FILE" 2>/dev/null; }

# ╭───────────────────────────────────────────────────────────────╮
# │  发送实现 —— 只有这一段随传输方式不同(WiFi / 有线 / 蓝牙)          │
# │  WiFi：curl 打设备 /event?s=<state>，-m 1 永不阻塞 Codex          │
# ╰───────────────────────────────────────────────────────────────╯
device_bases() {
  [ -f "$URL_FILE" ] && sed -e 's#/*$##' "$URL_FILE" 2>/dev/null | grep -E '^https?://'
  [ -f "$IP_FILE" ]  && { ip=$(tr -d ' \r\n' < "$IP_FILE"); [ -n "$ip" ] && echo "http://$ip"; }
}
resolve_local_ip() {
  ip=$(curl -s -m 6 -o /dev/null -w '%{remote_ip}' "http://$DEFAULT_HOST/state" 2>/dev/null)
  case "$ip" in
    [0-9]*.[0-9]*.[0-9]*.[0-9]*) printf '%s' "$ip" > "$IP_FILE" 2>/dev/null; echo "http://$ip" ;;
    *) echo "" ;;
  esac
}
send_state() { # $1=state
  local s="$1" base
  while IFS= read -r base; do
    [ -n "$base" ] || continue
    curl -s -m 1 -o /dev/null "$base/event?s=$s" 2>/dev/null && { log "send-ok $s via=$base"; return 0; }
  done <<EOF
$(device_bases)
EOF
  base="$(resolve_local_ip)"
  [ -n "$base" ] && curl -s -m 1 -o /dev/null "$base/event?s=$s" 2>/dev/null && { log "send-ok $s via=$base"; return 0; }
  curl -s -m 1 -o /dev/null "http://$DEFAULT_HOST/event?s=$s" 2>/dev/null && { log "send-ok $s via=mdns"; return 0; }
  log "send-FAIL $s (device unreachable)"; return 1
}
# ╰───────────────────────────────────────────────────────────────╯

# 统一出口：去重 + 落盘 + 发送(dry-run 只打印)
emit() { # $1=state $2=force(1/0) $3=token $4=suppressUntilMs
  local s="$1" force="${2:-0}" token="${3:-$TOKEN}" suppress="${4:-0}" idleDue=0
  is_valid "$s" || s="idle"
  [ "$s" = "idle" ] && idleDue=$(( $(now_ms) + IDLE_SLEEP_MS ))
  if [ "$force" != "1" ]; then
    local prev prevTs age; prev="$(read_state_field 1)"; prevTs="$(read_state_field 2)"
    if [ "$prev" = "$s" ] && [ -n "$prevTs" ]; then
      age=$(( $(now_ms) - prevTs ))
      [ "$age" -ge 0 ] && [ "$age" -lt "$DUP_WINDOW_MS" ] && { log "skip-dup $s"; return 0; }
    fi
  fi
  if [ "$CLAWD_MOCHI_DRYRUN" = "1" ]; then echo "$s"; save_state "$s" "$token" "$suppress" "$idleDue"; return 0; fi
  send_state "$s"; save_state "$s" "$token" "$suppress" "$idleDue"
}

# ── 生命周期定时器(内部 --mode 再入本脚本，逻辑集中、可测) ──
start_done_return()   { spawn "$SELF" --mode done-return --token "$1"; }
start_idle_sleep()    { spawn "$SELF" --mode idle-sleep  --token "$1"; }
find_codex_pid() {
  local pid=$PPID i=0 comm ppid
  while [ "$i" -lt 16 ] && [ -n "$pid" ] && [ "$pid" -gt 1 ]; do
    comm=$(ps -o comm= -p "$pid" 2>/dev/null)
    case "$comm" in *codex*|*Codex*) echo "$pid"; return;; esac
    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' '); [ -n "$ppid" ] || break
    pid=$ppid; i=$((i+1))
  done
  echo ""
}
start_close_watcher() {
  local wp; wp="$(find_codex_pid)"
  [ -n "$wp" ] || { log "watch-skip no-codex-ancestor"; return; }
  spawn "$SELF" --mode watch-cli --token "$1" --watchpid "$wp"
}

# ── 内部定时器模式：先于一切执行，跑完即退 ──
case "$MODE" in
  done-return)
    sleep_ms "$DONE_HOLD_MS"
    [ "$(read_state_field 1)" = "done" ] || exit 0
    emit idle 1 "$TOKEN" 0; start_idle_sleep "$TOKEN"; exit 0 ;;
  idle-sleep)
    sleep_ms "$IDLE_SLEEP_MS"
    [ "$(read_state_field 1)" = "idle" ] || exit 0
    due="$(read_state_field 5)"
    { [ -n "$due" ] && [ "$due" -gt 0 ] 2>/dev/null && [ "$(now_ms)" -lt "$due" ]; } && exit 0
    emit sleep 1 "$TOKEN" 0; exit 0 ;;
  watch-cli)
    [ -n "$WATCH_PID" ] || exit 0
    while kill -0 "$WATCH_PID" 2>/dev/null; do sleep 0.5; done
    sleep 0.3
    if command -v pgrep >/dev/null 2>&1; then pgrep -i codex >/dev/null 2>&1 && exit 0
    else ps ax 2>/dev/null | grep -iq "[c]odex" && exit 0; fi
    emit sleep 1 "$TOKEN" 0; exit 0 ;;
esac

# ── JSON 抽取(perl，一次一个顶层字符串字段) ──
PAYLOAD=""
field() { # $1=字段名(可用 | 分隔多个)，取第一个匹配的字符串值
  [ -n "$PAYLOAD" ] || { echo ""; return; }
  printf '%s' "$PAYLOAD" | perl -0777 -ne 'BEGIN{$f=shift}
    for my $k (split/\|/,$f){ if(/"\Q$k\E"\s*:\s*"((?:[^"\\]|\\.)*)"/){ my $v=$1; $v=~s/\\(["\\\/])/$1/g; print $v; exit } }' "$1"
}
pmatch() { printf '%s' "$PAYLOAD" | grep -iqE "$1"; }   # 在整段 payload 上做正则(与 .ps1 同思路)

tool_state() {  # 工具事件 → 状态(对齐 .ps1 Get-ToolState)
  local tool cmd; tool="$(field 'tool_name|toolName|name')"; cmd="$(field 'command|cmd|script')"
  case "$tool" in *AskUserQuestion*|*request_user_input*|*request-user-input*|*user_input*|*select_option*|*choose_option*) echo waiting; return;; esac
  echo "$tool" | grep -iqE 'ExitPlanMode|update_plan|plan_mode|plan-mode|planning' && { echo planning; return; }
  echo "$tool" | grep -iqE 'Subagent|Task|multi_agent|handoff_thread|send_message_to_thread|create_thread|fork_thread' && { echo delegating; return; }
  echo "$tool" | grep -iqE 'apply_patch|^(Edit|Write|MultiEdit|NotebookEdit)$|edit|write|patch|file_write' && { echo coding; return; }
  if echo "$tool" | grep -iqE '^(Bash|Shell|Command)$|shell_command|terminal|exec'; then
    echo "$cmd" | grep -iqE '\b(apply_patch|git[[:space:]]+(apply|add|commit|checkout|restore|reset|clean)|rm|mv|cp|tee|sed[[:space:]]+-i)\b|>[>]?' && { echo coding; return; }
    echo "$cmd" | grep -iqE '^[[:space:]]*(cat|less|head|tail|rg|grep|ls|find|pwd|stat|file|git[[:space:]]+(status|show|diff|log|branch|rev-parse)|docker[[:space:]]+ps|docker[[:space:]]+logs)\b' && { echo reading; return; }
    echo running; return
  fi
  echo "$tool" | grep -iqE 'compact|summari[sz]e_context' && { echo compacting; return; }
  echo "$tool" | grep -iqE 'mcp__|automation|reminder|monitor|notification|notify|linear|jira|slack' && { echo notify; return; }
  echo "$tool" | grep -iqE 'node_repl|computer|browser|chrome' && { echo running; return; }
  echo "$tool" | grep -iqE 'read|search|fetch|open|find|list|get|resolve|context7|everything|web|finance|weather|sports|time' && { echo reading; return; }
  echo "$tool" | grep -iqE 'create|update|move|delete|write|edit|patch|apply' && { echo coding; return; }
  echo running
}

is_internal_app_session() {  # 过滤 Codex 桌面 App 的后台小会话(建议/标题/摘要)，避免收尾闪烁
  # suggestions 常以「转义的 JSON 字符串」嵌在 last_assistant_message 里 → 引号前允许一个反斜杠
  pmatch '\\?"suggestions\\?"[[:space:]]*:[[:space:]]*\[' && return 0
  pmatch 'ambient[-_ ]?suggestions|followUpQueue' && return 0
  return 1
}

state_from_payload() {
  local ev; ev="$(field 'hook_event_name|hookEventName')"
  case "$ev" in
    SessionStart)      echo idle ;;
    UserPromptSubmit)  echo thinking ;;
    PermissionRequest) echo waiting ;;
    PreToolUse)        tool_state ;;
    PostToolUse)
      pmatch '"(isError|error|failed|failure)"[[:space:]]*:[[:space:]]*true' && { echo error; return; }
      local t; t="$(field 'tool_name|toolName|name')"
      echo "$t" | grep -iqE 'AskUserQuestion|request_user_input|user_input' && { echo thinking; return; }
      tool_state ;;
    PreCompact)        echo compacting ;;
    PostCompact)       echo thinking ;;
    SubagentStart)     echo delegating ;;
    SubagentStop)
      pmatch 'failed|failure|error|exception|crash|timed out|unable to|could not|not able to|blocked|denied|失败|报错|错误|异常|未能|无法|被拒绝|被阻止' && { echo error; return; }
      echo thinking ;;
    Notification)
      pmatch 'interrupted|interrupt|cancelled|canceled|aborted|paused|中断|取消|暂停' && { echo idle; return; }
      pmatch 'permission|approval|approve|allow|deny|confirm|choose|choice|select|submit|askuserquestion|是否|选择|确认|提交|允许|批准|授权' && { echo waiting; return; }
      echo notify ;;
    Stop)
      pmatch 'interrupted|interrupt|cancelled|canceled|aborted|中断|取消' && { echo idle; return; }
      local m; m="$(field 'last_assistant_message|lastAssistantMessage|message')"
      if [ -n "$m" ] && [ "${#m}" -le 160 ] && printf '%s' "$m" | grep -qE '[?？][[:space:]]*$'; then echo waiting; return; fi
      echo done ;;
    SessionEnd)        echo sleep ;;
    *)                 echo idle ;;
  esac
}

# ══════════════════ 主流程 ══════════════════
# 显式状态：SessionStart(--mode session-start) 或手动测试
if [ -n "$STATE" ]; then
  [ -n "$TOKEN" ] || TOKEN="$(now_ms)$$"
  emit "$STATE" 1 "$TOKEN" 0
  if [ "$MODE" = "session-start" ]; then
    start_idle_sleep "$TOKEN"; start_close_watcher "$TOKEN"
  elif [ "$STATE" = "idle" ]; then
    start_idle_sleep "$TOKEN"
  fi
  exit 0
fi

# 正常 hook：从 stdin 读 JSON
[ -t 0 ] || PAYLOAD="$(cat 2>/dev/null)"
[ -n "$PAYLOAD" ] || { log "empty-payload"; exit 0; }
is_internal_app_session && { log "skip-internal-app-session"; exit 0; }

EVENT="$(field 'hook_event_name|hookEventName')"
NEXT="$(state_from_payload)"

IS_START=0; [ "$EVENT" = "SessionStart" ] && IS_START=1
if [ "$IS_START" = "1" ]; then
  TOKEN="$(field 'session_id|sessionId')"; [ -n "$TOKEN" ] || TOKEN="$(now_ms)$$"
else
  TOKEN="$(read_state_field 3)"
fi

# Stop 之后 ~7s 内，抑制拖尾工具事件覆盖 done(生命周期事件不抑制)
case "$EVENT" in
  SessionStart|UserPromptSubmit|PermissionRequest|Notification|Stop|SessionEnd) : ;;
  *)
    su="$(read_state_field 4)"
    { [ -n "$su" ] && [ "$su" -gt 0 ] 2>/dev/null && [ "$(now_ms)" -lt "$su" ]; } && { log "skip-post-stop $EVENT"; exit 0; } ;;
esac

SUPPRESS=0
{ [ "$EVENT" = "Stop" ] || { [ "$EVENT" = "Notification" ] && pmatch 'interrupted|cancelled|canceled|中断|取消'; }; } && SUPPRESS=$(( $(now_ms) + POST_STOP_SUPPRESS_MS ))

FORCE=0
{ [ "$IS_START" = "1" ] || [ "$NEXT" = "sleep" ] || [ "$NEXT" = "idle" ] || [ "$NEXT" = "waiting" ] || [ "$NEXT" = "done" ]; } && FORCE=1

log "evt=$EVENT -> $NEXT token=$TOKEN"
emit "$NEXT" "$FORCE" "$TOKEN" "$SUPPRESS"

[ "$EVENT" = "Stop" ] && [ "$NEXT" = "done" ] && start_done_return "$TOKEN"
[ "$NEXT" = "idle" ] && start_idle_sleep "$TOKEN"
[ "$IS_START" = "1" ] && start_close_watcher "$TOKEN"
exit 0
