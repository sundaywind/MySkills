---
name: windows-computer-use
description: Control Microsoft Windows desktop applications using SendInput, UI Automation (UIA), and screen capturing. Use when asked to operate Windows desktop apps, click UI elements, send keystrokes, inspect active windows, or automate GUI workflows.
---

# Windows Computer Use Skill (CUA Enhanced)

Use this skill to automate Microsoft Windows desktop applications via SendInput hardware-level input, UI Automation (UIA) control tree navigation, screen capturing, and batch execution pipelines.

## Driver Engine Location
The driver engine script is located at:
`C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py`

Execute driver commands using `run_command`:
`python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py <subcommand> [options]`

---

## Core Philosophy: Accessibility First

Follow this action hierarchy for maximum speed, accuracy, and background non-intrusiveness:
1. **Semantic / Accessibility Inspection (`uia-tree`)**: Inspect the UI tree to identify target controls with their assigned `index`, `name`, and bounding boxes.
2. **Index-based & Semantic Interaction**: Prefer clicking via `--index <N>` or setting values via `set-value` over blind coordinate guessing.
3. **Batch Pipelines (`batch`)**: Combine multi-step workflows (e.g. Focus -> Click -> Type -> Enter -> Screenshot) into a single batch execution to avoid multi-turn roundtrip delays.
4. **Visual & Coordinate Fallback**: Use relative/absolute coordinates or screenshots only when controls lack accessible representations (e.g., custom game canvas, proprietary graphics).

---

## Workflow & Guidelines

### 1. Window Discovery & Focus
Before interacting with any application, discover open windows and bring the target application to the foreground:

```bash
# List all visible top-level windows or search for a specific title
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py list-windows --search "WeChat"

# Bring a window to foreground by HWND or Title
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py focus --title "微信"
```

### 2. Screen Capturing & UI Inspection
Understand the current visual state and UIA element tree before clicking or typing:

```bash
# Take a screenshot of full screen or a target window
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py screenshot --title "微信"

# Inspect the UI Automation (UIA) Control Tree (auto-generates element index cache)
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py uia-tree --title "微信" --max-depth 3
```

### 3. Executing Input Actions

#### Clicking (Index, Coordinates, or UIA Name)
```bash
# Recommended: Click by cached element index from the latest uia-tree
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py click --index 2

# Click using relative coordinates within a window (auto-adds window left/top)
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py click --title "微信" --rel-x 500 --rel-y 1150

# Click by UIA element name
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py click --title "Notepad" --uia-name "File"

# Double click / Right click
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py click -x 500 -y 300 --double
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py click -x 500 -y 300 --button right
```

#### Typing Text & Semantic Setting
```bash
# Semantic set-value (tries UIA ValuePattern background write, fallback to click+paste)
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py set-value "Hello World" --index 5

# Type via clipboard paste (Ctrl+V) for Chinese characters or special formatting
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py type "测试消息" --clipboard

# Send Key Combinations (e.g., Ctrl+S, Alt+F4, Enter, Win+R)
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py key "enter"
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py key "ctrl+s"
```

#### Scrolling & Dragging
```bash
# Mouse Wheel Scroll (direction: up, down, left, right; amount: wheel clicks)
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py scroll --direction down --amount 3 --title "微信"

# Mouse Drag from (x1, y1) to (x2, y2)
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py drag --from-x 200 --from-y 300 --to-x 600 --to-y 300 --modifiers "shift"
```

---

### 4. High-Performance Batch Execution Pipeline

Combine multiple steps into a single atomic run to eliminate LLM turn delays:

```bash
# Execute a sequence of actions in one call
python C:\Users\Wind\.gemini\config\skills\windows-computer-use\scripts\computer_use_win.py batch --steps "[{'action': 'focus', 'title': '微信'}, {'action': 'click', 'rel_x': 500, 'rel_y': 1150}, {'action': 'type', 'text': '你好！', 'clipboard': true}, {'action': 'key', 'combo': 'enter'}, {'action': 'wait', 'duration': 0.2}, {'action': 'screenshot', 'title': '微信'}]"
```

---

## Safety & Confirmation Guidelines

> ⚠️ **IMPORTANT**:
> Always seek explicit user confirmation before performing destructive actions, such as:
> - Closing unsaved documents or applications (`alt+f4`)
> - Overwriting files or modifying system configurations
> - Executing potentially unsafe system shortcuts (`win+r` commands)
