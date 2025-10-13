import time
import threading
import cv2
import numpy as np
import pyautogui
from pathlib import Path
import customtkinter as ctk
from PIL import Image
from pynput import keyboard

# ----------------------------- configuration -----------------------------

# define templates: image path, search area (%), similarity threshold
TEMPLATES = [
    {
        "name": "confirm_button",
        "path": "templates/confirm.png",
        "zone": (0.77, 0.84, 0.99, 0.99),  # x1, y1, x2, y2 (as % of screen)
        "threshold": 0.85
    },
    #{
    #     "name": "ok_button",
    #     "path": "templates/ok.png",
    #     "zone": (0.45, 0.40, 0.55, 0.50),
    #     "threshold": 0.85
    # },
    # {
    #     "name": "reward_button",
    #     "path": "templates/reward.png",
    #     "zone": (0.75, 0.15, 0.90, 0.25),
    #     "threshold": 0.85
    # },
]

# delay between scans
DEFAULT_DELAY = 1.0

# ----------------------------- utils -----------------------------

def load_template(path):
    """load image as cv2 bgr array"""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"template not found or unreadable: {path}")
    return img

def region_from_percent(zone):
    """convert zone in % to absolute screen region (x, y, w, h)"""
    screen_w, screen_h = pyautogui.size()
    x1 = int(screen_w * zone[0])
    y1 = int(screen_h * zone[1])
    x2 = int(screen_w * zone[2])
    y2 = int(screen_h * zone[3])
    return (x1, y1, x2 - x1, y2 - y1)

def screenshot_region(region):
    """take screenshot of region and return cv2 bgr image"""
    x, y, w, h = region
    img = pyautogui.screenshot(region=(x, y, w, h))
    img = img.convert('RGB')
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def match_template(image, template, threshold):
    """return center (x,y) of match if found above threshold, else None"""
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

        # preload template images
        for t in self.templates:
            t["image"] = load_template(Path(t["path"]).resolve())
            t["region_abs"] = region_from_percent(t["zone"])

    def run(self):
        self.start_time = time.time()
        while not self.stop_flag.is_set():
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

# ----------------------------- gui -----------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Image AutoClicker")
        self.geometry("420x400")
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.delay_var = ctk.DoubleVar(value=DEFAULT_DELAY)
        self.time_var = ctk.StringVar(value="0.0 s")
        self.count_vars = {t["name"]: ctk.StringVar(value="0") for t in TEMPLATES}

        # for mouse position display
        self.mouse_pos_var = ctk.StringVar(value="x: 0, y: 0 (0.0%, 0.0%)")

        self.worker = None

        self._build_ui()

        # start mouse position updater
        self.update_mouse_position()

    def _build_ui(self):
        # delay
        ctk.CTkLabel(self, text="delay between scans (s):").pack(pady=(10,0))
        ctk.CTkEntry(self, textvariable=self.delay_var).pack()

        # click counts
        ctk.CTkLabel(self, text="click counts:").pack(pady=(10,0))
        for name, var in self.count_vars.items():
            frame = ctk.CTkFrame(self)
            frame.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(frame, text=name).pack(side="left", padx=5)
            ctk.CTkLabel(frame, textvariable=var).pack(side="right", padx=5)

        # elapsed time
        ctk.CTkLabel(self, text="elapsed time:").pack(pady=(10,0))
        ctk.CTkLabel(self, textvariable=self.time_var).pack()

        # buttons
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Start", command=self.start_clicker).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Restart", command=self.restart_clicker).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Stop", command=self.stop_clicker).pack(side="left", padx=5)

        # mouse position debug
        ctk.CTkLabel(self, text="cursor position (debug):").pack(pady=(10,0))
        ctk.CTkLabel(self, textvariable=self.mouse_pos_var).pack()

    def start_clicker(self):
        if self.worker and self.worker.is_alive():
            return
        self.worker = AutoClicker(TEMPLATES, self.delay_var.get(), on_update=self.update_status)
        self.worker.start()

    def restart_clicker(self):
        self.stop_clicker()
        for var in self.count_vars.values():
            var.set("0")
        self.time_var.set("0.0 s")
        self.start_clicker()

    def stop_clicker(self):
        if self.worker and self.worker.is_alive():
            self.worker.stop()
            self.worker.join()

    def update_status(self, counts, elapsed):
        for name, count in counts.items():
            self.count_vars[name].set(str(count))
        self.time_var.set(f"{elapsed:.1f} s")

    def update_mouse_position(self):
        """update mouse position label every 0.5 sec"""
        x, y = pyautogui.position()
        sw, sh = pyautogui.size()
        px = (x / sw) * 100
        py = (y / sh) * 100
        self.mouse_pos_var.set(f"x: {x}, y: {y}  ({px:.1f}%, {py:.1f}%)")
        self.after(100, self.update_mouse_position)  # update every 0.1s

    def on_close(self):
        self.stop_clicker()
        self.destroy()

    def on_activate_start():
        app.start_clicker()

    def on_activate_stop():
        app.stop_clicker()

    # define hotkeys
    hotkeys = keyboard.GlobalHotKeys({
        '<ctrl>+<f1>': on_activate_start,
        '<ctrl>+<f2>': on_activate_stop
    })
    hotkeys.start()

# ----------------------------- main -----------------------------

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
