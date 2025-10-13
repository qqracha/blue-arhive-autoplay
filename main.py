import time
import threading
from pathlib import Path
import cv2
import numpy as np
import pyautogui
import customtkinter as ctk
from pynput import keyboard
import mss
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1" # delete pygame trash in console
import pygame

# ----------------------------- sound -------------------------------------
pygame.mixer.init()
SOUND_PATH = "resources/whistle.wav"
if Path(SOUND_PATH).exists():
    start_sound = pygame.mixer.Sound(SOUND_PATH)
else:
    start_sound = None
    print(f"[Warning] Звуковой файл {SOUND_PATH} не найден, звук отключен.")

# ----------------------------- configuration -----------------------------

TEMPLATES = [
    {
        "name": "confirm_button",
        "path": "templates/confirm.png",
        "zone": (0.77, 0.84, 0.99, 0.99),
        "threshold": 0.85
    },
    {
        "name": "yellow_confirm_button",
        "path": "templates/confirm2.png",
        "zone": (0.35, 0.82, 0.62, 0.99),
        "threshold": 0.85
    },
    {
        "name": "watch_button",
        "path": "templates/watch.png",
        "zone": (0.48, 0.65, 0.73, 0.80),
        "threshold": 0.85
    },
    {
        "name": "enter_button",
        "path": "templates/enter.png",
        "zone": (0.26, 0.70, 0.73, 0.89),
        "threshold": 0.85
    },
    {
        "name": "mobilize_button",
        "path": "templates/mobilize.png",
        "zone": (0.80, 0.80, 0.99, 0.99),
        "threshold": 0.85
    },
    {
        "name": "enter_episode",
        "path": "templates/enter_episode.png",
        "zone": (0.36, 0.63, 0.63, 0.78),
        "threshold": 0.85
    }    
]


# [NEW] automenu detection
AUTOMENU_TEMPLATE = {
    "name": "automenu",
    "path": "templates/automenu.png",
    "zone": (0.68, 0.01, 0.99, 0.14),
    "threshold": 0.85
}

REWARD_TEMPLATE = {
        "name": "reward",
        "path": "templates/reward.png",
        "zone": (0.23, 0.14, 0.72, 0.28),
        "threshold": 0.85,
}

DEFAULT_DELAY = 1.0  # seconds

# ----------------------------- utilities -----------------------------

def load_template(path):
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Template not found or unreadable: {path}")
    return img

def region_from_percent(zone):
    screen_w, screen_h = pyautogui.size()
    x1 = int(screen_w * zone[0])
    y1 = int(screen_h * zone[1])
    x2 = int(screen_w * zone[2])
    y2 = int(screen_h * zone[3])
    return (x1, y1, x2 - x1, y2 - y1)

def screenshot_region(region):
    """Universal screenshot for X11 and Windows only"""
    x, y, w, h = region
    with mss.mss() as sct:
        monitor = {"top": y, "left": x, "width": w, "height": h}
        img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img[..., :3], cv2.COLOR_RGB2BGR)

def match_template(image, template, threshold):
    gray_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(gray_img, gray_tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        h, w = gray_tpl.shape
        cx = max_loc[0] + w // 2
        cy = max_loc[1] + h // 2
        return (cx, cy)
    return None

# ----------------------------- worker -----------------------------

class AutoClicker(threading.Thread):
    def __init__(self, templates, delay, on_update=None):
        super().__init__(daemon=True)
        self.templates = templates
        self.delay = delay
        self.stop_flag = threading.Event()
        self.click_counts = {t["name"]: 0 for t in templates}
        self.on_update = on_update
        self.start_time = None

        # preload templates
        for t in self.templates:
            t["image"] = load_template(Path(t["path"]).resolve())
            t["region_abs"] = region_from_percent(t["zone"])

        # [NEW] preload automenu
        self.automenu_img = load_template(Path(AUTOMENU_TEMPLATE["path"]).resolve())
        self.automenu_region = region_from_percent(AUTOMENU_TEMPLATE["zone"])

        # [NEW] reward
        self.reward_img = load_template(Path(REWARD_TEMPLATE["path"]).resolve())
        self.reward_region = region_from_percent(REWARD_TEMPLATE["zone"])

    def run(self):
        self.start_time = time.time()
        while not self.stop_flag.is_set():

            # [NEW] check automenu first
            automenu_screen = screenshot_region(self.automenu_region)
            found_menu = match_template(
                automenu_screen, self.automenu_img, AUTOMENU_TEMPLATE["threshold"]
            )
            if found_menu:
                print("[AutoMenu] Found automenu.png — pressing ESC → wait 2s → ENTER")
                pyautogui.press("esc")
                time.sleep(2)
                pyautogui.press("enter")
                time.sleep(self.delay)
                continue
            
            # [NEW] check reward
            reward_screen = screenshot_region(self.reward_region)
            found_reward = match_template(
                reward_screen, self.reward_img, REWARD_TEMPLATE["threshold"]
            )
            if found_reward:
                print("[Reward] Found reward.png — pressing ENTER")
                pyautogui.press("enter")
                time.sleep(self.delay)
                continue
            # normal templates loop
            for t in self.templates:
                region = t["region_abs"]
                screenshot = screenshot_region(region)
                match = match_template(screenshot, t["image"], t["threshold"])
                if match:
                    abs_x = region[0] + match[0]
                    abs_y = region[1] + match[1]
                    pyautogui.click(abs_x, abs_y)
                    self.click_counts[t["name"]] += 1
                    if self.on_update:
                        self.on_update(self.click_counts, time.time() - self.start_time)
            time.sleep(self.delay)

    def stop(self):
        self.stop_flag.set()

# ----------------------------- GUI -----------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("オートブルーアーカイブ | Auto Blue Archive")
        self.geometry("450x600")
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.delay_var = ctk.DoubleVar(value=DEFAULT_DELAY)
        self.time_var = ctk.StringVar(value="0.0 s")
        self.count_vars = {t["name"]: ctk.StringVar(value="0") for t in TEMPLATES}
        self.mouse_pos_var = ctk.StringVar(value="x: 0, y: 0 (0.0%, 0.0%)")

        self.worker = None

        self._build_ui()
        self.update_mouse_position()

        self.hotkeys = keyboard.GlobalHotKeys({
            '<ctrl>+<f1>': self.start_clicker,
            '<ctrl>+<f2>': self.stop_clicker
        })
        self.hotkeys.start()
        print("[Hotkeys] Start = Ctrl+F1 | Stop = Ctrl+F2")

    def _build_ui(self):
        ctk.CTkLabel(self, text="delay between scans (s):").pack(pady=(10,0))
        ctk.CTkEntry(self, textvariable=self.delay_var).pack()

        ctk.CTkLabel(self, text="click counts:").pack(pady=(10,0))
        for name, var in self.count_vars.items():
            frame = ctk.CTkFrame(self)
            frame.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(frame, text=name).pack(side="left", padx=5)
            ctk.CTkLabel(frame, textvariable=var).pack(side="right", padx=5)

        ctk.CTkLabel(self, text="elapsed time:").pack(pady=(10,0))
        ctk.CTkLabel(self, textvariable=self.time_var).pack()

        ctk.CTkLabel(self, text="cursor position (debug):").pack(pady=(10,0))
        ctk.CTkLabel(self, textvariable=self.mouse_pos_var).pack()

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Start", command=self.start_clicker).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Restart", command=self.restart_clicker).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Stop", command=self.stop_clicker).pack(side="left", padx=5)

        ctk.CTkLabel(self, text="Hotkeys: Ctrl+F1 = Start, Ctrl+F2 = Stop").pack(pady=(10,0))

    def start_clicker(self):
        if self.worker and self.worker.is_alive():
            return
        self.worker = AutoClicker(TEMPLATES, self.delay_var.get(), on_update=self.update_status)
        self.worker.start()
        if start_sound:
            start_sound.play()
        print("> Start button pressed")

    def restart_clicker(self):
        self.stop_clicker()
        for var in self.count_vars.values():
            var.set("0")
        self.time_var.set("0.0 s")
        print("> Restart button pressed")

    def stop_clicker(self):
        if self.worker and self.worker.is_alive():
            self.worker.stop()
            self.worker.join()
            print("> Stop button pressed")

    def update_status(self, counts, elapsed):
        for name, count in counts.items():
            self.count_vars[name].set(str(count))
        self.time_var.set(f"{elapsed:.1f} s")

    def update_mouse_position(self):
        x, y = pyautogui.position()
        sw, sh = pyautogui.size()
        px = (x / sw) * 100
        py_ = (y / sh) * 100
        self.mouse_pos_var.set(f"x: {x}, y: {y}  ({px:.1f}%, {py_:.1f}%)")
        self.after(500, self.update_mouse_position)

    def on_close(self):
        self.stop_clicker()
        self.hotkeys.stop()
        self.destroy()

# ----------------------------- main -----------------------------

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
