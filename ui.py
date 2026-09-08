import math
import os
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path

import psutil
import requests


PROJECT_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
LOG_PATH = PROJECT_DIR / "log.txt"
VOICE_STATE_PATH = PROJECT_DIR / "voice_state.txt"
BG = "#05090e"
CYAN = "#75e9ed"
CYAN_DIM = "#2d6975"
WHITE = "#edf7f5"
MUTED = "#78939e"
AMBER = "#efb56a"
RED = "#ef7078"
PANEL = "#0b1822"
PANEL_ALT = "#0e202b"
LINE = "#1a3a46"
BLUE = "#4fb9d1"


class JarvisPanel:
    def __init__(self, root):
        self.root = root
        self.process = None
        self.active = False
        self.phase = 0.0
        self.last_log = ""
        self.weather = "UPDATING"
        self.weather_detail = "LIVE DATA LINK"
        self.cpu = 0.0
        self.memory = 0.0
        self.gpu = None
        self.ollama_online = False
        self.voice_state = "STANDBY"
        self.buttons = {}

        root.title("JARVIS // INTERACTIVE COMMAND DECK")
        root.geometry("1280x760")
        root.minsize(980, 620)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            root.state("zoomed")
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self.render())
        self.canvas.bind("<Button-1>", self.handle_click)
        self.render()
        self.refresh_log()
        self.animate()
        self.update_telemetry()

    def render(self):
        width = max(self.canvas.winfo_width(), 980)
        height = max(self.canvas.winfo_height(), 620)
        self.canvas.delete("all")
        self.buttons = {}
        self.draw_background(width, height)
        self.draw_header(width)
        self.draw_left_panel(width, height)
        self.draw_core(width, height)
        self.draw_right_panel(width, height)
        self.draw_bottom_controls(width, height)

    def draw_background(self, width, height):
        self.canvas.create_rectangle(0, 0, width, height, fill=BG, outline="")
        for y in range(94, height, 32):
            self.canvas.create_line(28, y, width - 28, y, fill="#08131b")
        self.rounded_box(28, 22, width - 28, height - 22, radius=18, outline=LINE)
        self.rounded_box(28, 22, 32, height - 22, radius=2, fill=CYAN_DIM)
        self.rounded_box(width - 32, 22, width - 28, height - 22, radius=2, fill=CYAN_DIM)
        self.canvas.create_line(44, 92, width - 44, 92, fill=LINE)
        self.canvas.create_line(44, height - 92, width - 44, height - 92, fill=LINE)

    def corner(self, x, y, horizontal, vertical):
        self.canvas.create_line(x, y, x + horizontal * 30, y, fill=CYAN_DIM, width=2)
        self.canvas.create_line(x, y, x, y + vertical * 30, fill=CYAN_DIM, width=2)

    def rounded_box(self, left, top, right, bottom, radius=12, fill="", outline="", width=1):
        radius = min(radius, (right - left) / 2, (bottom - top) / 2)
        if fill:
            self.canvas.create_rectangle(left + radius, top, right - radius, bottom, fill=fill, outline="")
            self.canvas.create_rectangle(left, top + radius, right, bottom - radius, fill=fill, outline="")
            for x1, y1, x2, y2 in (
                (left, top, left + radius * 2, top + radius * 2),
                (right - radius * 2, top, right, top + radius * 2),
                (left, bottom - radius * 2, left + radius * 2, bottom),
                (right - radius * 2, bottom - radius * 2, right, bottom),
            ):
                self.canvas.create_oval(x1, y1, x2, y2, fill=fill, outline="")
        if outline:
            self.canvas.create_line(left + radius, top, right - radius, top, fill=outline, width=width)
            self.canvas.create_line(left + radius, bottom, right - radius, bottom, fill=outline, width=width)
            self.canvas.create_line(left, top + radius, left, bottom - radius, fill=outline, width=width)
            self.canvas.create_line(right, top + radius, right, bottom - radius, fill=outline, width=width)
            for start, x1, y1, x2, y2 in (
                (90, left, top, left + radius * 2, top + radius * 2),
                (0, right - radius * 2, top, right, top + radius * 2),
                (180, left, bottom - radius * 2, left + radius * 2, bottom),
                (270, right - radius * 2, bottom - radius * 2, right, bottom),
            ):
                self.canvas.create_arc(x1, y1, x2, y2, start=start, extent=90, outline=outline, width=width, style="arc")

    def draw_header(self, width):
        self.canvas.create_text(52, 47, text="JARVIS", fill=WHITE, font=("Segoe UI", 24, "bold"), anchor="w")
        self.canvas.create_text(163, 47, text="PERSONAL INTELLIGENCE", fill=BLUE, font=("Consolas", 9, "bold"), anchor="w")
        self.canvas.create_text(163, 63, text="COMMAND DECK / LOCAL INSTANCE", fill=MUTED, font=("Consolas", 7), anchor="w")
        status_color = CYAN if self.ollama_online else AMBER
        link = "OLLAMA / LLAMA3.2 / ONLINE" if self.ollama_online else "OLLAMA / CHECKING"
        status_left = width - 330
        status_right = width - 52
        self.rounded_box(status_left, 30, status_right, 70, radius=12, fill=PANEL_ALT, outline=LINE)
        self.canvas.create_oval(status_left + 14, 44, status_left + 22, 52, fill=status_color, outline="")
        self.canvas.create_text((status_left + status_right) / 2 + 10, 50, text=link, fill=status_color, font=("Consolas", 8, "bold"), anchor="center")
        controls_center = width * 0.49
        self.button("start", controls_center - 126, 30, controls_center - 8, 70, "LISTENING" if self.active else "START", CYAN)
        self.button("stop", controls_center + 8, 30, controls_center + 126, 70, "STOP", RED)

    def draw_left_panel(self, width, height):
        x = 54
        center = 165
        self.rounded_box(44, 112, 286, height - 118, radius=16, fill=PANEL, outline=LINE)
        self.canvas.create_text(center, 130, text="PERSONAL CONSOLE", fill=BLUE, font=("Consolas", 8, "bold"), anchor="center")
        now = datetime.now()
        self.canvas.create_text(center - 18, 174, text=now.strftime("%I:%M"), fill=WHITE, font=("Segoe UI", 40), anchor="center")
        self.canvas.create_text(center + 88, 183, text=now.strftime("%p"), fill=AMBER, font=("Consolas", 10, "bold"), anchor="center")
        self.canvas.create_text(center, 216, text=now.strftime("%A"), fill=CYAN, font=("Segoe UI", 17), anchor="center")
        self.canvas.create_text(center, 240, text=now.strftime("%B %d, %Y"), fill=MUTED, font=("Segoe UI", 10), anchor="center")
        self.canvas.create_line(68, 260, 262, 260, fill=CYAN_DIM)
        self.canvas.create_text(center, 278, text="CURRENT SESSION", fill=MUTED, font=("Consolas", 8, "bold"), anchor="center")
        self.canvas.create_text(center, 305, text="JARVIS SYSTEMS", fill=WHITE, font=("Segoe UI", 15), anchor="center")
        self.canvas.create_text(center, 328, text="LOCAL INTELLIGENCE", fill=CYAN_DIM, font=("Consolas", 8), anchor="center")
        self.canvas.create_text(center, 374, text="VOICE INTERFACE", fill=MUTED, font=("Consolas", 8, "bold"), anchor="center")
        self.canvas.create_text(center, 397, text="ACTIVE" if self.active else "STANDBY", fill=CYAN if self.active else AMBER, font=("Consolas", 11, "bold"), anchor="center")

    def draw_core(self, width, height):
        cx = width * 0.49
        cy = height * 0.48
        self.core_center = (cx, cy)
        state_colors = {
            "LISTENING": CYAN,
            "SPEAKING": AMBER,
            "PROCESSING": WHITE,
            "IDLE": CYAN_DIM,
            "STANDBY": AMBER,
        }
        core_color = state_colors.get(self.voice_state, CYAN_DIM)
        self.canvas.create_text(cx, 110, text="COGNITIVE CORE", fill=CYAN, font=("Consolas", 10, "bold"))
        radius = 202
        self.canvas.create_oval(cx - radius - 10, cy - radius - 10, cx + radius + 10, cy + radius + 10, fill="#010305", outline="")
        phase = self.phase * 0.8
        particle_colors = ["#1a2528", "#354144", "#687477", "#aeb8b9", "#e6eeee"]
        spacing = 6
        for row in range(-radius, radius + 1, spacing):
            for column in range(-radius, radius + 1, spacing):
                normalized_x = column / radius
                normalized_y = row / (radius * 0.91)
                distance = normalized_x * normalized_x + normalized_y * normalized_y
                if distance > 1:
                    continue
                depth = math.sqrt(max(0, 1 - distance))
                jitter_x = math.sin(row * 0.31 + column * 0.17) * 2.1
                jitter_y = math.cos(row * 0.23 - column * 0.19) * 2.1
                wave = (math.sin(column * 0.08 + row * 0.13 + phase) + 1) / 2
                edge = min(1, max(0, (distance - 0.58) / 0.42))
                brightness = edge * 0.82 + depth * 0.12 + wave * 0.16
                if distance < 0.3 and wave < 0.82:
                    continue
                if depth < 0.18 and wave < 0.55:
                    continue
                color_index = min(4, max(0, int(brightness * 5)))
                dot_size = 2 if brightness < 0.72 else 3
                left = cx + column + jitter_x - dot_size / 2
                top = cy + row + jitter_y - dot_size / 2
                self.canvas.create_oval(left, top, left + dot_size, top + dot_size, fill=particle_colors[color_index], outline="")
        for point in range(260):
            angle = point / 260 * math.tau + phase * 0.15
            noise = (math.sin(point * 4.73 + phase * 3) + math.sin(point * 1.91 - phase)) / 2
            ring_radius = radius + noise * 18 + math.sin(point * 0.71) * 5
            x = cx + math.cos(angle) * ring_radius
            y = cy + math.sin(angle) * ring_radius * 0.91
            brightness = (math.sin(point * 6.1 + phase * 2) + 1) / 2
            dot_size = 2 if brightness < 0.7 else 3
            self.canvas.create_oval(x, y, x + dot_size, y + dot_size, fill=particle_colors[2 + int(brightness * 3) % 3], outline="")
        for band in (-0.55, -0.18, 0.24, 0.57):
            band_width = math.sqrt(1 - band * band) * radius
            for point in range(80):
                if (point + int(phase * 4)) % 3:
                    continue
                angle = point / 80 * math.tau + phase * 0.12
                x = cx + math.cos(angle) * band_width
                y = cy + band * radius * 0.91 + math.sin(angle) * 3
                self.canvas.create_oval(x, y, x + 2, y + 2, fill="#465255", outline="")
        for orbit in range(3):
            orbit_radius = 54 + orbit * 28
            orbit_tilt = 0.34 + orbit * 0.13
            orbit_phase = phase * (1.4 - orbit * 0.18) + orbit * 1.7
            for point in range(42):
                angle = point / 42 * math.tau + orbit_phase
                depth = math.sin(angle)
                if depth < -0.35 and (point + int(phase * 6)) % 2:
                    continue
                x = cx + math.cos(angle) * orbit_radius
                y = cy + depth * orbit_radius * orbit_tilt
                dot_size = (2 if orbit else 3) + (1 if depth > 0.35 else 0)
                dot_color = "#aeb8b9" if depth > 0 else "#465255"
                self.canvas.create_oval(x - dot_size / 2, y - dot_size / 2, x + dot_size / 2, y + dot_size / 2, fill=dot_color, outline="")
        self.canvas.create_text(cx, cy + 255, text=self.voice_state if self.active else "STANDBY", fill=core_color, font=("Consolas", 11, "bold"))
        self.canvas.create_text(cx, cy + 276, text="CLICK CORE TO START / STOP", fill=MUTED, font=("Consolas", 8))
        self.buttons["core"] = (cx - 235, cy - 235, cx + 235, cy + 235)

    def draw_right_panel(self, width, height):
        x = width * 0.77
        panel_right = width - 48
        center = (x + panel_right) / 2
        self.rounded_box(x - 22, 102, panel_right, height - 112, radius=16, fill="#08141d", outline="#1d4b57")
        self.canvas.create_line(x - 22, 102, panel_right, 102, fill=CYAN_DIM, width=2)
        self.canvas.create_text(x, 128, text="SYSTEM TELEMETRY", fill=CYAN, font=("Consolas", 10, "bold"), anchor="w")
        self.canvas.create_text(panel_right - 18, 128, text="LIVE", fill=CYAN_DIM, font=("Consolas", 8, "bold"), anchor="e")
        self.canvas.create_text(center, 158, text="ENVIRONMENT", fill=MUTED, font=("Consolas", 8, "bold"), anchor="center")
        self.canvas.create_text(center, 181, text=self.weather, fill=WHITE, font=("Consolas", 13, "bold"), anchor="center")
        self.canvas.create_text(center, 202, text=self.weather_detail, fill=CYAN_DIM, font=("Consolas", 8), anchor="center")
        self.canvas.create_line(x, 232, panel_right - 18, 232, fill="#17343f")
        self.canvas.create_text(center, 258, text="RESOURCE LOAD", fill=MUTED, font=("Consolas", 8, "bold"), anchor="center")
        self.telemetry_row(x, 290, "CPU", self.cpu, CYAN, panel_right - 18)
        self.telemetry_row(x, 346, "RAM", self.memory, AMBER, panel_right - 18)
        self.telemetry_row(x, 402, "GPU", self.gpu, WHITE, panel_right - 18)
        self.canvas.create_line(x, 454, panel_right - 18, 454, fill="#17343f")
        self.canvas.create_text(center, 480, text="CORE STATUS", fill=MUTED, font=("Consolas", 8, "bold"), anchor="center")
        self.canvas.create_text(center, 506, text=self.voice_state, fill=CYAN if self.active else AMBER, font=("Consolas", 12, "bold"), anchor="center")
        self.canvas.create_text(center, 528, text="VOICE LINK / LOCAL PROCESS", fill=CYAN_DIM, font=("Consolas", 8), anchor="center")

    def telemetry_row(self, x, y, label, value, color, right):
        value_text = "N/A" if value is None else f"{value:.0f}%"
        numeric_value = 0 if value is None else max(0, min(100, value))
        bar_left = x + 58
        bar_right = right - 58
        self.canvas.create_text(x, y, text=label, fill=WHITE, font=("Consolas", 10, "bold"), anchor="w")
        self.canvas.create_text(right, y, text=value_text, fill=color if value is not None else MUTED, font=("Consolas", 10, "bold"), anchor="e")
        self.rounded_box(bar_left, y + 13, bar_right, y + 19, radius=3, fill="#132832")
        if numeric_value:
            self.rounded_box(bar_left, y + 13, bar_left + (bar_right - bar_left) * numeric_value / 100, y + 19, radius=3, fill=color)

    def draw_bottom_controls(self, width, height):
        return

    def button(self, name, left, top, right, bottom, label, color):
        self.rounded_box(left, top, right, bottom, radius=10, fill="#102b37", outline=color)
        self.rounded_box(left, top, left + 3, bottom, radius=2, fill=color)
        self.canvas.create_text((left + right) / 2, (top + bottom) / 2, text=label, fill=WHITE, font=("Consolas", 8, "bold"))
        self.buttons[name] = (left, top, right, bottom)

    def animate(self):
        self.phase = (self.phase + 0.06) % (math.pi * 2)
        self.voice_state = self.read_voice_state() if self.active else "STANDBY"
        self.render()
        self.root.after(120, self.animate)

    @staticmethod
    def read_voice_state():
        try:
            state = VOICE_STATE_PATH.read_text(encoding="utf-8").strip().upper()
            return state if state in {"IDLE", "LISTENING", "PROCESSING", "SPEAKING"} else "IDLE"
        except (OSError, UnicodeError):
            return "IDLE"

    def handle_click(self, event):
        for name, bounds in self.buttons.items():
            if self.inside(event, bounds):
                actions = {"start": self.start, "core": lambda: self.stop() if self.active else self.start(), "stop": self.stop}
                actions[name]()
                return

    @staticmethod
    def inside(event, bounds):
        left, top, right, bottom = bounds
        return left <= event.x <= right and top <= event.y <= bottom

    def start(self):
        if self.process and self.process.poll() is None:
            return
        if getattr(sys, "frozen", False):
            assistant_command = [sys.executable, "--assistant"]
        else:
            assistant_command = [sys.executable, str(PROJECT_DIR / "jarvis.py")]
        self.process = subprocess.Popen(assistant_command, cwd=PROJECT_DIR, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        self.active = True
        self.render()

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.process = None
        self.active = False
        self.render()

    def update_telemetry(self):
        self.cpu = psutil.cpu_percent(interval=None)
        self.memory = psutil.virtual_memory().percent
        self.gpu = self.get_gpu_usage()
        threading.Thread(target=self.fetch_weather, daemon=True).start()
        threading.Thread(target=self.check_ollama, daemon=True).start()
        self.root.after(10000, self.update_telemetry)

    @staticmethod
    def get_gpu_usage():
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            values = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
            return max(values) if values else None
        except (FileNotFoundError, subprocess.SubprocessError, ValueError):
            return None

    def fetch_weather(self):
        try:
            response = requests.get("https://wttr.in/?format=j1", headers={"User-Agent": "Jarvis/1.0"}, timeout=8)
            current = response.json()["current_condition"][0]
            weather = f"{current['temp_F']}F / {current['weatherDesc'][0]['value'].upper()}"
            detail = "LIVE DATA / CLICK TO REFRESH"
        except (requests.RequestException, KeyError, IndexError, ValueError):
            weather = "OFFLINE"
            detail = "WEATHER LINK UNAVAILABLE"
        self.root.after(0, self.set_weather, weather, detail)

    def set_weather(self, weather, detail):
        self.weather = weather
        self.weather_detail = detail
        self.render()

    def check_ollama(self):
        try:
            requests.get("http://localhost:11434/api/tags", timeout=3).raise_for_status()
            online = True
        except requests.RequestException:
            online = False
        self.root.after(0, self.set_ollama, online)

    def set_ollama(self, online):
        self.ollama_online = online
        self.render()

    def refresh_log(self):
        try:
            content = LOG_PATH.read_text(encoding="utf-8")
            if content != self.last_log:
                self.last_log = content
                recent = content[-220:].strip().replace("\n", " ") or "Awaiting transmission"
                self.canvas.create_text(self.canvas.winfo_width() * 0.42, self.canvas.winfo_height() - 28, text=recent[:120], fill=WHITE, font=("Consolas", 8), anchor="w", tags="transcript")
        except (OSError, UnicodeError):
            pass
        self.root.after(700, self.refresh_log)

    def close(self):
        self.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    JarvisPanel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
