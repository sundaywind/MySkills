import sys
import os
import time
import json
import argparse
import ctypes
from ctypes import wintypes

# 1. Declare Per-Monitor DPI Awareness V2 BEFORE any GUI/win32 modules load
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# 2. Attach thread to user's interactive 'default' desktop
try:
    user32 = ctypes.windll.user32
    hDesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
    if hDesk:
        user32.SetThreadDesktop(hDesk)
except Exception:
    pass

import win32api
import win32gui
import win32con
import win32process
import win32clipboard
from PIL import ImageGrab, Image

try:
    import pywinauto
    from pywinauto import Desktop
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

CACHE_DIR = r"C:\Users\Wind\.gemini\antigravity\scratch\computer_use"
TREE_CACHE_FILE = os.path.join(CACHE_DIR, "tree_cache.json")

# SendInput C structures
PUL = ctypes.POINTER(ctypes.c_ulong)

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", PUL)
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", PUL)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION)
    ]

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120

VK_MAP = {
    'ctrl': win32con.VK_CONTROL,
    'control': win32con.VK_CONTROL,
    'alt': win32con.VK_MENU,
    'shift': win32con.VK_SHIFT,
    'win': win32con.VK_LWIN,
    'enter': win32con.VK_RETURN,
    'return': win32con.VK_RETURN,
    'tab': win32con.VK_TAB,
    'space': win32con.VK_SPACE,
    'backspace': win32con.VK_BACK,
    'delete': win32con.VK_DELETE,
    'esc': win32con.VK_ESCAPE,
    'escape': win32con.VK_ESCAPE,
    'up': win32con.VK_UP,
    'down': win32con.VK_DOWN,
    'left': win32con.VK_LEFT,
    'right': win32con.VK_RIGHT,
    'home': win32con.VK_HOME,
    'end': win32con.VK_END,
    'pageup': win32con.VK_PRIOR,
    'pagedown': win32con.VK_NEXT,
    'f1': win32con.VK_F1, 'f2': win32con.VK_F2, 'f3': win32con.VK_F3, 'f4': win32con.VK_F4,
    'f5': win32con.VK_F5, 'f6': win32con.VK_F6, 'f7': win32con.VK_F7, 'f8': win32con.VK_F8,
    'f9': win32con.VK_F9, 'f10': win32con.VK_F10, 'f11': win32con.VK_F11, 'f12': win32con.VK_F12,
}

def send_input_keyboard_unicode(char):
    utf16_val = ord(char)
    inp_down = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(wVk=0, wScan=utf16_val, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None)))
    inp_up = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(wVk=0, wScan=utf16_val, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

def send_key_code(vk_code, is_up=False):
    flags = KEYEVENTF_KEYUP if is_up else 0
    inp = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def get_dpi_info():
    try:
        user32 = ctypes.windll.user32
        hdc = user32.GetDC(0)
        gdi32 = ctypes.windll.gdi32
        log_pixels = gdi32.GetDeviceCaps(hdc, 88)
        user32.ReleaseDC(0, hdc)
        scale = round(log_pixels / 96.0, 2)
        screen_w = win32api.GetSystemMetrics(0)
        screen_h = win32api.GetSystemMetrics(1)
        return {'scale': scale, 'scale_percent': f"{int(scale * 100)}%", 'screen_width': screen_w, 'screen_height': screen_h}
    except Exception:
        return {'scale': 1.0, 'scale_percent': "100%", 'screen_width': 0, 'screen_height': 0}

def list_windows(search_title=None, include_hidden=False):
    results = []
    def enum_windows_callback(hwnd, extra):
        try:
            is_vis = win32gui.IsWindowVisible(hwnd)
            if is_vis or include_hidden:
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    if search_title and search_title.lower() not in title.lower():
                        return True
                    rect = win32gui.GetWindowRect(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    class_name = win32gui.GetClassName(hwnd)
                    results.append({
                        'hwnd': hwnd,
                        'title': title,
                        'class_name': class_name,
                        'pid': pid,
                        'is_visible': bool(is_vis),
                        'rect': {'left': rect[0], 'top': rect[1], 'right': rect[2], 'bottom': rect[3],
                                 'width': rect[2] - rect[0], 'height': rect[3] - rect[1]}
                    })
        except Exception:
            pass
        return True
    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception:
        pass
    return results

def release_stuck_modifiers():
    """Ensure no modifier keys or Windows menu states remain stuck after execution."""
    try:
        user32 = ctypes.windll.user32
        # Release Mouse buttons
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        # Release Alt, Ctrl, Shift
        user32.keybd_event(win32con.VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(win32con.VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(win32con.VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        # Dismiss any accidentally activated Windows menu loop
        user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(win32con.VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
    except Exception:
        pass

def focus_window(hwnd=None, title=None):
    target_hwnd = hwnd
    if not target_hwnd and title:
        wins = list_windows(title, include_hidden=False)
        if wins:
            target_hwnd = wins[0]['hwnd']
        else:
            # Fallback: search hidden/tray windows and unhide/restore them
            hidden_wins = list_windows(title, include_hidden=True)
            if hidden_wins:
                target_hwnd = hidden_wins[0]['hwnd']
    
    if not target_hwnd or not win32gui.IsWindow(target_hwnd):
        return {'status': 'error', 'message': f'Window not found: hwnd={hwnd}, title={title}'}
    
    try:
        # Restore if hidden or minimized
        ctypes.windll.user32.ShowWindow(target_hwnd, win32con.SW_RESTORE)
        ctypes.windll.user32.ShowWindow(target_hwnd, win32con.SW_SHOW)
        win32gui.BringWindowToTop(target_hwnd)
        
        # Clean focus without sending Alt key (prevents menu bar freeze)
        ctypes.windll.user32.SwitchToThisWindow(target_hwnd, True)
        ctypes.windll.user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.1)
        
        fore = win32gui.GetForegroundWindow()
        rect = win32gui.GetWindowRect(target_hwnd)
        is_foreground = (fore == target_hwnd)
        
        return {'status': 'success' if is_foreground else 'warning',
                'is_foreground': is_foreground,
                'fore_hwnd': fore,
                'target_hwnd': target_hwnd,
                'title': win32gui.GetWindowText(target_hwnd),
                'rect': {'left': rect[0], 'top': rect[1], 'right': rect[2], 'bottom': rect[3]}}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def take_screenshot(hwnd=None, title=None, output_path=None):
    target_hwnd = hwnd
    if not target_hwnd and title:
        wins = list_windows(title)
        if wins:
            target_hwnd = wins[0]['hwnd']

    if target_hwnd and win32gui.IsWindow(target_hwnd):
        rect = win32gui.GetWindowRect(target_hwnd)
        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
        if width > 0 and height > 0:
            image = ImageGrab.grab(bbox=(left, top, right, bottom))
        else:
            image = ImageGrab.grab()
            left, top = 0, 0
    else:
        image = ImageGrab.grab()
        left, top = 0, 0

    if not output_path:
        out_dir = r"C:\Users\Wind\.gemini\antigravity\scratch"
        os.makedirs(out_dir, exist_ok=True)
        timestamp = int(time.time() * 1000)
        output_path = os.path.join(out_dir, f"screenshot_{timestamp}.png")
    else:
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    image.save(output_path, format="PNG")
    return {
        'status': 'success',
        'path': output_path,
        'width': image.width,
        'height': image.height,
        'bbox': {'left': left, 'top': top, 'right': left + image.width, 'bottom': top + image.height},
        'dpi_info': get_dpi_info()
    }

def get_uia_tree(hwnd=None, title=None, max_depth=3, save_cache=True):
    if not PYWINAUTO_AVAILABLE:
        return {'status': 'error', 'message': 'pywinauto is not installed'}
    
    target_hwnd = hwnd
    if not target_hwnd and title:
        wins = list_windows(title)
        if wins:
            target_hwnd = wins[0]['hwnd']

    try:
        desktop = Desktop(backend="uia")
        if target_hwnd:
            win_obj = desktop.window(handle=target_hwnd)
        else:
            win_obj = desktop.active_window()
            target_hwnd = win_obj.handle

        elements = []
        counter = [0]

        def traverse(wrapper, depth=0):
            if depth > max_depth:
                return
            try:
                elem_info = wrapper.element_info
                rect = elem_info.rectangle
                name = elem_info.name
                control_type = elem_info.control_type
                auto_id = elem_info.automation_id
                w = rect.width()
                h = rect.height()
                
                # Include reasonable visible elements
                if (name or auto_id or depth <= 1) and w > 0 and h > 0:
                    idx = counter[0]
                    counter[0] += 1
                    center_x = rect.left + w // 2
                    center_y = rect.top + h // 2
                    elements.append({
                        'index': idx,
                        'depth': depth,
                        'name': name or '',
                        'control_type': control_type or '',
                        'auto_id': auto_id or '',
                        'rect': {'left': rect.left, 'top': rect.top, 'right': rect.right, 'bottom': rect.bottom,
                                 'width': w, 'height': h},
                        'center': [center_x, center_y],
                        'hwnd': target_hwnd
                    })
                
                for child in wrapper.children():
                    traverse(child, depth + 1)
            except Exception:
                pass

        traverse(win_obj, 0)

        # Save cache for index-based click/set_value
        if save_cache:
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(TREE_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({'hwnd': target_hwnd, 'count': len(elements), 'elements': elements}, f, ensure_ascii=False)
            except Exception:
                pass

        return {'status': 'success', 'hwnd': target_hwnd, 'count': len(elements), 'elements': elements[:150]}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def _get_cached_element(index):
    if not os.path.exists(TREE_CACHE_FILE):
        return None
    try:
        with open(TREE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for el in data.get('elements', []):
                if el.get('index') == index:
                    return el
    except Exception:
        pass
    return None

def click_action(x=None, y=None, rel_x=None, rel_y=None, hwnd=None, title=None,
                 uia_name=None, uia_id=None, index=None, button='left', double=False):
    target_x, target_y = x, y
    action_sent = False

    # 1. Address by Index from cache
    if index is not None:
        cached = _get_cached_element(index)
        if cached:
            target_x, target_y = cached['center'][0], cached['center'][1]
            hwnd = hwnd or cached.get('hwnd')
        else:
            # Re-fetch tree if not found in cache
            tree = get_uia_tree(hwnd=hwnd, title=title, max_depth=4)
            if tree.get('status') == 'success':
                for el in tree.get('elements', []):
                    if el.get('index') == index:
                        target_x, target_y = el['center'][0], el['center'][1]
                        break

    # 2. Window relative offset (--rel-x, --rel-y)
    if target_x is None and rel_x is not None and rel_y is not None:
        target_hwnd = hwnd
        if not target_hwnd and title:
            wins = list_windows(title)
            if wins:
                target_hwnd = wins[0]['hwnd']
        if target_hwnd and win32gui.IsWindow(target_hwnd):
            rect = win32gui.GetWindowRect(target_hwnd)
            target_x = rect[0] + rel_x
            target_y = rect[1] + rel_y
        else:
            return {'status': 'error', 'action_sent': False, 'message': f'Relative click requires a valid window: hwnd={hwnd}, title={title}'}

    # 3. Match by UIA name or auto_id
    if target_x is None and (uia_name or uia_id) and PYWINAUTO_AVAILABLE:
        tree = get_uia_tree(hwnd=hwnd, title=title, max_depth=4)
        if tree.get('status') == 'success':
            for elem in tree.get('elements', []):
                match_name = uia_name and uia_name.lower() in elem['name'].lower()
                match_id = uia_id and uia_id.lower() == elem['auto_id'].lower()
                if match_name or match_id:
                    target_x, target_y = elem['center'][0], elem['center'][1]
                    break

    if target_x is None or target_y is None:
        return {'status': 'error', 'action_sent': False, 'message': 'Target coordinates could not be determined.'}

    try:
        if hwnd or title:
            focus_window(hwnd=hwnd, title=title)

        win32api.SetCursorPos((target_x, target_y))
        time.sleep(0.02)
        # Hardware mouse move jitter to guarantee Qt/WPF/DirectUI registers hover & mouse-down
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 1, 0, 0, 0)
        time.sleep(0.02)
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, -1, 0, 0, 0)
        time.sleep(0.04)

        btn_down = MOUSEEVENTF_LEFTDOWN if button == 'left' else MOUSEEVENTF_RIGHTDOWN
        btn_up = MOUSEEVENTF_LEFTUP if button == 'left' else MOUSEEVENTF_RIGHTUP

        clicks = 2 if double else 1
        for i in range(clicks):
            win32api.mouse_event(btn_down, 0, 0, 0, 0)
            time.sleep(0.03)
            win32api.mouse_event(btn_up, 0, 0, 0, 0)
            if double and i == 0:
                time.sleep(0.08)
        action_sent = True
        return {'status': 'success', 'action_sent': action_sent, 'x': target_x, 'y': target_y, 'button': button, 'double': double}
    except Exception as e:
        return {'status': 'error', 'action_sent': action_sent, 'message': str(e)}

def scroll_action(direction='down', amount=3, x=None, y=None, hwnd=None, title=None):
    action_sent = False
    try:
        # Move cursor if target coordinates or window provided
        if x is not None and y is not None:
            win32api.SetCursorPos((x, y))
            time.sleep(0.03)
        elif hwnd or title:
            wins = list_windows(title) if title else [{'hwnd': hwnd}]
            if wins and win32gui.IsWindow(wins[0]['hwnd']):
                rect = win32gui.GetWindowRect(wins[0]['hwnd'])
                center_x = rect[0] + (rect[2] - rect[0]) // 2
                center_y = rect[1] + (rect[3] - rect[1]) // 2
                win32api.SetCursorPos((center_x, center_y))
                time.sleep(0.03)

        delta = WHEEL_DELTA * int(amount)
        direction = direction.lower()

        if direction in ['down', 'd']:
            win32api.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -delta, 0)
        elif direction in ['up', 'u']:
            win32api.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
        elif direction in ['right', 'r']:
            win32api.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, delta, 0)
        elif direction in ['left', 'l']:
            win32api.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, -delta, 0)
        else:
            return {'status': 'error', 'action_sent': False, 'message': f'Unknown scroll direction: {direction}'}

        action_sent = True
        return {'status': 'success', 'action_sent': action_sent, 'direction': direction, 'amount': amount}
    except Exception as e:
        return {'status': 'error', 'action_sent': action_sent, 'message': str(e)}

def drag_action(from_x, from_y, to_x, to_y, modifiers=None, duration=0.25, steps=10):
    action_sent = False
    try:
        # Handle modifier keys (e.g. shift, ctrl)
        mod_vk = None
        if modifiers:
            m = modifiers.lower().strip()
            if m in VK_MAP:
                mod_vk = VK_MAP[m]
                send_key_code(mod_vk, False)

        win32api.SetCursorPos((from_x, from_y))
        time.sleep(0.05)
        win32api.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)

        # Smooth drag steps
        step_sleep = duration / max(steps, 1)
        for i in range(1, steps + 1):
            curr_x = int(from_x + (to_x - from_x) * (i / steps))
            curr_y = int(from_y + (to_y - from_y) * (i / steps))
            win32api.SetCursorPos((curr_x, curr_y))
            time.sleep(step_sleep)

        win32api.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        action_sent = True

        if mod_vk:
            send_key_code(mod_vk, True)

        return {'status': 'success', 'action_sent': action_sent, 'from': [from_x, from_y], 'to': [to_x, to_y]}
    except Exception as e:
        win32api.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return {'status': 'error', 'action_sent': action_sent, 'message': str(e)}

def type_action(text, use_clipboard=False):
    if not text:
        return {'status': 'error', 'action_sent': False, 'message': 'No text provided'}

    if use_clipboard:
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            time.sleep(0.02)
            send_key_code(win32con.VK_CONTROL, False)
            send_key_code(ord('V'), False)
            time.sleep(0.02)
            send_key_code(ord('V'), True)
            send_key_code(win32con.VK_CONTROL, True)
            return {'status': 'success', 'action_sent': True, 'mode': 'clipboard', 'len': len(text)}
        except Exception as e:
            return {'status': 'error', 'action_sent': False, 'message': f'Clipboard error: {e}'}
    else:
        try:
            for char in text:
                send_input_keyboard_unicode(char)
                time.sleep(0.005)
            return {'status': 'success', 'action_sent': True, 'mode': 'unicode_input', 'len': len(text)}
        except Exception as e:
            return {'status': 'error', 'action_sent': True, 'message': str(e)}

def set_value_action(text, index=None, uia_name=None, hwnd=None, title=None):
    """Set value via UIA ValuePattern (semantic/background) or fallback to click+paste."""
    target_x, target_y = None, None
    if index is not None:
        cached = _get_cached_element(index)
        if cached:
            target_x, target_y = cached['center'][0], cached['center'][1]
            hwnd = hwnd or cached.get('hwnd')

    # Try UIA ValuePattern
    if PYWINAUTO_AVAILABLE and hwnd:
        try:
            desktop = Desktop(backend="uia")
            win_obj = desktop.window(handle=hwnd)
            target_el = None
            if uia_name:
                target_el = win_obj.child_window(title_re=uia_name)
            elif index is not None and cached:
                # Find matching child
                for c in win_obj.descendants():
                    r = c.rectangle()
                    if r.left == cached['rect']['left'] and r.top == cached['rect']['top']:
                        target_el = c
                        break
            if target_el:
                try:
                    target_el.set_text(text)
                    return {'status': 'success', 'action_sent': True, 'mode': 'uia_value_pattern', 'len': len(text)}
                except Exception:
                    pass
        except Exception:
            pass

    # Fallback to click and paste
    if target_x is not None and target_y is not None:
        click_action(x=target_x, y=target_y)
        time.sleep(0.05)
        # Select all first
        key_combo_action("ctrl+a")
        time.sleep(0.02)
        res = type_action(text, use_clipboard=True)
        res['fallback'] = 'click_and_paste'
        return res

    return {'status': 'error', 'action_sent': False, 'message': 'Target element not found for set-value'}

def key_combo_action(key_str):
    parts = [k.strip().lower() for k in key_str.split('+')]
    codes = []
    for p in parts:
        if p in VK_MAP:
            codes.append(VK_MAP[p])
        elif len(p) == 1:
            codes.append(ord(p.upper()))
        else:
            return {'status': 'error', 'action_sent': False, 'message': f'Unknown key: {p}'}

    try:
        for code in codes:
            send_key_code(code, False)
            time.sleep(0.02)

        for code in reversed(codes):
            send_key_code(code, True)
            time.sleep(0.02)

        return {'status': 'success', 'action_sent': True, 'combo': key_str, 'vk_codes': codes}
    except Exception as e:
        return {'status': 'error', 'action_sent': True, 'message': str(e)}

def batch_pipeline_action(steps):
    """Execute a list of steps in a single execution pipeline."""
    results = []
    for idx, step in enumerate(steps):
        action = step.get('action', '').lower()
        res = {'step': idx, 'action': action}
        if action == 'focus':
            res.update(focus_window(step.get('hwnd'), step.get('title')))
        elif action == 'click':
            res.update(click_action(
                x=step.get('x'), y=step.get('y'),
                rel_x=step.get('rel_x'), rel_y=step.get('rel_y'),
                hwnd=step.get('hwnd'), title=step.get('title'),
                uia_name=step.get('uia_name'), uia_id=step.get('uia_id'),
                index=step.get('index'), button=step.get('button', 'left'),
                double=step.get('double', False)
            ))
        elif action == 'type':
            res.update(type_action(step.get('text', ''), step.get('clipboard', False)))
        elif action == 'set_value':
            res.update(set_value_action(
                step.get('text', ''), index=step.get('index'),
                uia_name=step.get('uia_name'), hwnd=step.get('hwnd'), title=step.get('title')
            ))
        elif action == 'key':
            res.update(key_combo_action(step.get('combo', 'enter')))
        elif action == 'scroll':
            res.update(scroll_action(
                direction=step.get('direction', 'down'), amount=step.get('amount', 3),
                x=step.get('x'), y=step.get('y'), hwnd=step.get('hwnd'), title=step.get('title')
            ))
        elif action == 'drag':
            res.update(drag_action(
                step.get('from_x'), step.get('from_y'), step.get('to_x'), step.get('to_y'),
                modifiers=step.get('modifiers')
            ))
        elif action == 'wait' or action == 'sleep':
            duration = step.get('duration', 0.5)
            time.sleep(duration)
            res.update({'status': 'success', 'waited': duration})
        elif action == 'screenshot':
            res.update(take_screenshot(step.get('hwnd'), step.get('title'), step.get('out')))
        elif action == 'uia_tree':
            res.update(get_uia_tree(step.get('hwnd'), step.get('title'), step.get('max_depth', 3)))
        else:
            res.update({'status': 'error', 'message': f'Unknown pipeline action: {action}'})

        results.append(res)
        delay = step.get('post_delay', 0.05)
        if delay > 0:
            time.sleep(delay)

        # Halt if step failed and stop_on_error is true
        if res.get('status') == 'error' and step.get('stop_on_error', True):
            break

    return {'status': 'success', 'total_steps': len(steps), 'executed_steps': len(results), 'pipeline': results}

def main():
    parser = argparse.ArgumentParser(description="Windows Computer Use Driver CLI - CUA Enhanced")
    subparsers = parser.add_subparsers(dest="command")

    # list-windows
    p_list = subparsers.add_parser("list-windows")
    p_list.add_argument("--search", help="Filter by title substring", default=None)

    # focus
    p_focus = subparsers.add_parser("focus")
    p_focus.add_argument("--hwnd", type=int, default=None)
    p_focus.add_argument("--title", default=None)

    # screenshot
    p_shot = subparsers.add_parser("screenshot")
    p_shot.add_argument("--hwnd", type=int, default=None)
    p_shot.add_argument("--title", default=None)
    p_shot.add_argument("--out", default=None)

    # uia-tree
    p_tree = subparsers.add_parser("uia-tree")
    p_tree.add_argument("--hwnd", type=int, default=None)
    p_tree.add_argument("--title", default=None)
    p_tree.add_argument("--max-depth", type=int, default=3)

    # click
    p_click = subparsers.add_parser("click")
    p_click.add_argument("-x", type=int, default=None, help="Absolute X coordinate")
    p_click.add_argument("-y", type=int, default=None, help="Absolute Y coordinate")
    p_click.add_argument("--rel-x", type=int, default=None, help="Relative X offset")
    p_click.add_argument("--rel-y", type=int, default=None, help="Relative Y offset")
    p_click.add_argument("--hwnd", type=int, default=None)
    p_click.add_argument("--title", default=None)
    p_click.add_argument("--uia-name", default=None)
    p_click.add_argument("--uia-id", default=None)
    p_click.add_argument("--index", type=int, default=None, help="Element index from last uia-tree")
    p_click.add_argument("--button", choices=['left', 'right'], default='left')
    p_click.add_argument("--double", action='store_true')

    # scroll
    p_scroll = subparsers.add_parser("scroll")
    p_scroll.add_argument("--direction", choices=['up', 'down', 'left', 'right', 'u', 'd', 'l', 'r'], default='down')
    p_scroll.add_argument("--amount", type=int, default=3, help="Scroll wheels count")
    p_scroll.add_argument("-x", type=int, default=None)
    p_scroll.add_argument("-y", type=int, default=None)
    p_scroll.add_argument("--hwnd", type=int, default=None)
    p_scroll.add_argument("--title", default=None)

    # drag
    p_drag = subparsers.add_parser("drag")
    p_drag.add_argument("--from-x", type=int, required=True)
    p_drag.add_argument("--from-y", type=int, required=True)
    p_drag.add_argument("--to-x", type=int, required=True)
    p_drag.add_argument("--to-y", type=int, required=True)
    p_drag.add_argument("--modifiers", default=None, help="Optional modifiers e.g. ctrl, shift")

    # type
    p_type = subparsers.add_parser("type")
    p_type.add_argument("text", help="Text to type")
    p_type.add_argument("--clipboard", action='store_true', help="Use clipboard paste (Ctrl+V)")

    # set-value
    p_setval = subparsers.add_parser("set-value")
    p_setval.add_argument("text", help="Value to set")
    p_setval.add_argument("--index", type=int, default=None)
    p_setval.add_argument("--uia-name", default=None)
    p_setval.add_argument("--hwnd", type=int, default=None)
    p_setval.add_argument("--title", default=None)

    # key
    p_key = subparsers.add_parser("key")
    p_key.add_argument("combo", help="Key combo e.g. ctrl+s, alt+f4, enter")

    # batch
    p_batch = subparsers.add_parser("batch")
    p_batch.add_argument("--steps", required=True, help="JSON string or path to JSON file containing step array")

    args = parser.parse_args()

    if args.command == "list-windows":
        res = list_windows(args.search)
    elif args.command == "focus":
        res = focus_window(args.hwnd, args.title)
    elif args.command == "screenshot":
        res = take_screenshot(args.hwnd, args.title, args.out)
    elif args.command == "uia-tree":
        res = get_uia_tree(args.hwnd, args.title, args.max_depth)
    elif args.command == "click":
        res = click_action(args.x, args.y, args.rel_x, args.rel_y, args.hwnd, args.title,
                           args.uia_name, args.uia_id, args.index, args.button, args.double)
    elif args.command == "scroll":
        res = scroll_action(args.direction, args.amount, args.x, args.y, args.hwnd, args.title)
    elif args.command == "drag":
        res = drag_action(args.from_x, args.from_y, args.to_x, args.to_y, args.modifiers)
    elif args.command == "type":
        res = type_action(args.text, args.clipboard)
    elif args.command == "set-value":
        res = set_value_action(args.text, args.index, args.uia_name, args.hwnd, args.title)
    elif args.command == "key":
        res = key_combo_action(args.combo)
    elif args.command == "batch":
        steps_val = args.steps
        if os.path.isfile(steps_val):
            with open(steps_val, "r", encoding="utf-8") as f:
                steps_data = json.load(f)
        else:
            try:
                steps_data = json.loads(steps_val)
            except Exception:
                # Fallback for Windows PowerShell quote-stripping: try single quote replacement
                normalized = steps_val.replace("'", '"')
                steps_data = json.loads(normalized)
        res = batch_pipeline_action(steps_data)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(res, ensure_ascii=False, indent=2))
    release_stuck_modifiers()

if __name__ == "__main__":
    main()
