"""Isolated command-deck styling and scripted SARA-style interaction preview.

Run: python sara_style_preview.py
Reuses the tested mock session and buttons, not the live HUD or Brain module.
Start/Stop control this preview only. Voice, telemetry, and model conversation
are not connected; this cannot certify compatibility with the live HUD.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from app_tree_desktop_preview import DesktopPreview, PreviewSession, SCENARIOS
from app_tree_prototype import ResultStatus


BG = "#05090e"
PANEL = "#0b1822"
CYAN = "#75e9ed"
WHITE = "#edf7f5"
MUTED = "#78939e"
LINE = "#1a3a46"
AMBER = "#efb56a"


def interaction_text(session: PreviewSession) -> str:
    result = session.result
    if result is None:
        return "Good day. Select a test scenario when you are ready."
    messages = {
        ResultStatus.AWAITING_APPROVAL: (
            "I can simulate a reminder for tomorrow at 9 AM to call Alex. "
            "May I proceed? This will not create a real reminder."
        ),
        ResultStatus.AWAITING_CONFIRMATION: (
            ("The mock reminder has returned a successful result. No real reminder was created. "
             if result.capability_id == "reminders.create"
             else "The mock forecast is sunny and 20 C. This is test data, not live weather. ")
            + "Did that work as expected? I will learn this route only if you confirm that it did."
        ),
        ResultStatus.SUCCESS_CONFIRMED: (
            "Thank you. I have recorded this route as successful in this test session. "
            "That does not grant permission for future actions."
        ),
        ResultStatus.NOT_CONFIRMED: (
            "Understood. I will not learn from this result. "
            "Any earlier confirmed workflows remain unchanged."
        ),
        ResultStatus.FORGE_PROPOSAL: (
            "There is no file-organising app in this test registry. "
            "I have recorded a proposal for review in this session. "
            "Forge has not run, and your Downloads have not been accessed."
        ),
    }
    if result.status is ResultStatus.REJECTED:
        if result.capability_id:
            return "The mock weather service could not complete the request. Nothing was learned."
        return "Very well. The proposed action has been discarded; nothing ran or was learned."
    return messages.get(result.status, result.message)


class SaraStylePreview(DesktopPreview):
    def __init__(self, root: tk.Tk) -> None:
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=WHITE, font=("Segoe UI", 10))
        style.configure("TButton", background=PANEL, foreground=CYAN, padding=8)
        style.map("TButton", foreground=[("disabled", MUTED)], background=[("active", LINE)])
        style.configure("TCombobox", fieldbackground=PANEL, foreground=WHITE)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", WHITE)])
        style.configure("TLabelframe", background=BG, bordercolor=LINE)
        style.configure("TLabelframe.Label", foreground=CYAN)
        super().__init__(root)
        root.title("SARA // ISOLATED STYLE PREVIEW")
        root.configure(bg=BG)
        root.geometry("1000x850")
        root.minsize(900, 780)
        self.running = True
        self.phase = 0.0
        self.timer_id: str | None = None
        self.history.configure(bg=PANEL, fg=WHITE, insertbackground=CYAN, relief="flat")

        frame = self.start_button.master.master
        if not isinstance(frame, ttk.Frame):
            raise TypeError("Expected the isolated desktop preview frame.")
        banner = ttk.Frame(frame)
        banner.pack(fill="x", before=frame.winfo_children()[0], pady=(0, 10))
        ttk.Label(banner, text="SARA // PERSONAL INTELLIGENCE", font=("Segoe UI", 20, "bold"),
                  foreground=CYAN).pack(side="left")
        self.resume_button = ttk.Button(banner, text="Start preview", command=self.resume)
        self.resume_button.pack(side="right", padx=(8, 0))
        self.stop_button = ttk.Button(banner, text="Stop preview", command=self.stop)
        self.stop_button.pack(side="right")
        self.core = tk.Canvas(frame, height=120, bg=BG, highlightthickness=0)
        self.core.pack(fill="x", before=self.history)
        ttk.Label(
            frame,
            text="STYLE REFERENCE ONLY | Scripted wording | No voice, live telemetry, or Ollama conversation",
            foreground=AMBER,
        ).pack(fill="x", before=self.core)
        self.core.bind("<Configure>", lambda event: self.draw_core())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.log(interaction_text(self.session))
        self.refresh()
        self.animate()

    def refresh(self) -> None:
        super().refresh()
        if not hasattr(self, "running"):
            return
        if not self.running:
            for button in (
                self.start_button, self.approve_button, self.reject_button,
                self.yes_button, self.no_button, self.unsure_button,
            ):
                button.configure(state="disabled")
            self.scenario_box.configure(state="disabled")
        self.resume_button.configure(state="disabled" if self.running else "normal")
        self.stop_button.configure(state="normal" if self.running else "disabled")
        self.draw_core()

    def draw_core(self) -> None:
        if not hasattr(self, "core"):
            return
        canvas = self.core
        canvas.delete("all")
        center = max(canvas.winfo_width(), 800) // 2
        pulse = math.sin(self.phase) * 3 if self.running else 0
        for radius in (32 + pulse, 43, 52):
            canvas.create_oval(center - radius, 60 - radius, center + radius, 60 + radius,
                               outline=CYAN if self.running else MUTED, width=2)
        canvas.create_text(center, 60, text="S", fill=WHITE, font=("Segoe UI", 24, "bold"))
        state = "STANDBY"
        if self.running:
            state = "READY"
            if self.session.awaiting_approval:
                state = "AWAITING APPROVAL"
            elif self.session.awaiting_confirmation:
                state = "AWAITING YOUR CONFIRMATION"
        canvas.create_text(center + 80, 55, text=state, fill=CYAN, anchor="w",
                           font=("Consolas", 10, "bold"))
        canvas.create_text(center + 80, 78, text="SIMULATED CORE / NO LIVE DATA", fill=MUTED,
                           anchor="w", font=("Consolas", 8))

    def animate(self) -> None:
        if self.running:
            self.phase += 0.08
        self.draw_core()
        self.timer_id = self.root.after(60, self.animate)

    def stop(self) -> None:
        self.running = False
        self.status.set("Preview stopped. Pending decisions are preserved; nothing is automatically approved or learned.")
        self.refresh()

    def resume(self) -> None:
        self.running = True
        self.status.set("Preview resumed. Any pending decision still needs your response.")
        self.refresh()

    def start(self) -> None:
        if not self.running:
            return
        result = self.session.start(self.scenario.get())
        self.log(f"You: {SCENARIOS[self.scenario.get()][0]}\nSARA-style preview: {interaction_text(self.session)}")
        if result.suggested_capability:
            self.log(f"Previously confirmed route: {result.suggested_capability}")
        self.status.set(result.status.value.replace("_", " "))
        self.refresh()

    def approve(self, approved: bool) -> None:
        if not self.running:
            return
        result = self.session.approve(approved)
        self.log(f"You: {'Approve' if approved else 'Reject'}\nSARA-style preview: {interaction_text(self.session)}")
        self.status.set(result.status.value.replace("_", " "))
        self.refresh()

    def confirm(self, worked: bool | None) -> None:
        if not self.running:
            return
        self.session.confirm(worked)
        message = (
            "Quite all right. I will leave this result unconfirmed and learn nothing from it. "
            "You can decide later, or reset the test session."
            if worked is None else interaction_text(self.session)
        )
        self.log(f"SARA-style preview: {message}")
        self.status.set(message)
        self.refresh()

    def close(self) -> None:
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    SaraStylePreview(root)
    root.update()
    print("Isolated SARA-style preview ready; live HUD and personality are not connected.", flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
