"""Standalone button-based preview, not SARA's HUD or persona.

Run with the experiment venv: python app_tree_desktop_preview.py.
Uses scripted scenarios and the real prototype approval/confirmation rules.
No Ollama, Forge, live apps, file storage, or SARA modules are used.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_tree_prototype import (
    AppTree,
    Capability,
    DispatchResult,
    Intent,
    MockExecutor,
    MockOutcome,
    ResultStatus,
    RouteKind,
)


SCENARIOS = {
    "Weather (mock)": (
        "Check the weather forecast for Boston.",
        Intent(RouteKind.CAPABILITY, "weather", capability_id="weather.lookup"),
    ),
    "Reminder (approval)": (
        "Remind me tomorrow at 9 AM to call Alex.",
        Intent(RouteKind.CAPABILITY, "reminder", capability_id="reminders.create"),
    ),
    "Failed weather (mock)": (
        "Try the unavailable weather service.",
        Intent(RouteKind.CAPABILITY, "weather", capability_id="weather.failed"),
    ),
    "Missing app (proposal only)": (
        "Sort my Downloads by file type.",
        Intent(
            RouteKind.NEEDS_CAPABILITY,
            "file organization",
            capability_request="Propose a file organization app for review.",
        ),
    ),
}


class PreviewSession:
    def __init__(self) -> None:
        self.app = AppTree([
            Capability("weather.lookup", "Mock Boston weather lookup.", False,
                       MockExecutor(MockOutcome(True, "Mock forecast: sunny, 20 C. Not live weather."))),
            Capability("reminders.create", "Mock reminder: tomorrow at 9 AM, call Alex.", True,
                       MockExecutor(MockOutcome(True, "Mock reminder returned success. No real reminder was created."))),
            Capability("weather.failed", "Mock unavailable weather service.", False,
                       MockExecutor(MockOutcome(False, "Mock weather service failed. Nothing was learned."))),
        ])
        self.result: DispatchResult | None = None

    @property
    def awaiting_approval(self) -> bool:
        return self.result is not None and self.result.status is ResultStatus.AWAITING_APPROVAL

    @property
    def awaiting_confirmation(self) -> bool:
        return self.result is not None and self.result.status is ResultStatus.AWAITING_CONFIRMATION

    def start(self, scenario: str) -> DispatchResult:
        if self.awaiting_approval or self.awaiting_confirmation:
            raise ValueError("Resolve the current interaction or reset the test session first.")
        request, intent = SCENARIOS[scenario]
        self.result = self.app.route(request, intent)
        return self.result

    def approve(self, approved: bool) -> DispatchResult:
        if not self.awaiting_approval or self.result is None:
            raise ValueError("There is no action awaiting approval.")
        self.result = (
            self.app.approve(self.result.approval_id)
            if approved else self.app.reject(self.result.approval_id)
        )
        return self.result

    def confirm(self, worked: bool | None) -> str:
        if not self.awaiting_confirmation or self.result is None:
            raise ValueError("There is no result awaiting success confirmation.")
        if worked is None:
            return "No problem. Nothing was learned; confirmation is still pending. You can decide later or reset."
        self.result = self.app.confirm_success(self.result.confirmation_id, worked)
        return self.result.message

    def memory_text(self) -> str:
        routes = self.app.memory.successful_routes
        if not routes:
            return "Learned workflows: none."
        return "Learned workflows (this session only):\n" + "\n".join(
            f"{task} -> {capability} | confirmed {count} time(s)"
            for (task, capability), count in sorted(routes.items())
        )


class DesktopPreview:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.session = PreviewSession()
        root.title("SARA - ISOLATED app-tree preview")
        root.geometry("850x680")
        root.minsize(700, 600)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="SARA app-tree interaction preview", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="ISOLATED TEST | Scripted mock apps | No changes to SARA or her HUD",
            wraplength=750,
        ).pack(anchor="w", pady=(6, 12))
        ttk.Label(
            frame,
            text="1. Choose a scenario.  2. Review any action.  3. Confirm only if the result worked.\n"
                 "This previews interaction wording, not SARA's actual voice or personality.",
            wraplength=750,
        ).pack(anchor="w", pady=(0, 12))

        selection = ttk.Frame(frame)
        selection.pack(fill="x")
        self.scenario = tk.StringVar(value="Weather (mock)")
        self.scenario_box = ttk.Combobox(
            selection, textvariable=self.scenario, values=list(SCENARIOS),
            state="readonly", width=34,
        )
        self.scenario_box.pack(side="left", padx=(0, 10))
        self.start_button = ttk.Button(selection, text="Start scenario", command=self.start)
        self.start_button.pack(side="left")
        ttk.Button(selection, text="Reset test session", command=self.reset).pack(side="right")

        self.history = tk.Text(frame, height=12, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.history.pack(fill="both", expand=True, pady=12)
        self.status = tk.StringVar(value="Ready. Nothing has run or been learned.")
        ttk.Label(frame, textvariable=self.status, wraplength=750).pack(anchor="w", pady=(0, 8))

        actions = ttk.LabelFrame(frame, text="Before running the mock action", padding=8)
        actions.pack(fill="x", pady=(0, 8))
        self.approve_button = ttk.Button(actions, text="Approve mock action", command=lambda: self.approve(True))
        self.approve_button.pack(side="left", padx=(0, 8))
        self.reject_button = ttk.Button(actions, text="Reject action", command=lambda: self.approve(False))
        self.reject_button.pack(side="left")

        feedback = ttk.LabelFrame(frame, text="After the mock app reports success: did it work?", padding=8)
        feedback.pack(fill="x", pady=(0, 8))
        self.yes_button = ttk.Button(feedback, text="It worked - learn this route", command=lambda: self.confirm(True))
        self.yes_button.pack(side="left", padx=(0, 8))
        self.no_button = ttk.Button(feedback, text="It didn't work", command=lambda: self.confirm(False))
        self.no_button.pack(side="left", padx=(0, 8))
        self.unsure_button = ttk.Button(feedback, text="Not sure / decide later", command=lambda: self.confirm(None))
        self.unsure_button.pack(side="left")

        self.memory = tk.StringVar(value=self.session.memory_text())
        ttk.Label(frame, textvariable=self.memory, wraplength=750).pack(anchor="w", pady=(4, 8))
        ttk.Label(
            frame,
            text="Reset or close discards all test memory, pending decisions, and proposals. Nothing is saved to disk.",
            wraplength=750,
        ).pack(anchor="w")
        self.refresh()

    def log(self, text: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", text + "\n\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    def refresh(self) -> None:
        busy = self.session.awaiting_approval or self.session.awaiting_confirmation
        self.start_button.configure(state="disabled" if busy else "normal")
        self.scenario_box.configure(state="disabled" if busy else "readonly")
        for button in (self.approve_button, self.reject_button):
            button.configure(state="normal" if self.session.awaiting_approval else "disabled")
        for button in (self.yes_button, self.no_button, self.unsure_button):
            button.configure(state="normal" if self.session.awaiting_confirmation else "disabled")
        self.memory.set(self.session.memory_text())

    def start(self) -> None:
        scenario = self.scenario.get()
        result = self.session.start(scenario)
        self.log(f"Test request: {SCENARIOS[scenario][0]}\nPreview: {result.message}")
        if result.suggested_capability:
            self.log(f"Previously user-confirmed route suggested: {result.suggested_capability}")
        self.status.set(result.status.value.replace("_", " "))
        self.refresh()

    def approve(self, approved: bool) -> None:
        result = self.session.approve(approved)
        self.log(f"You: {'Approve' if approved else 'Reject'}\nPreview: {result.message}")
        self.status.set(result.status.value.replace("_", " "))
        self.refresh()

    def confirm(self, worked: bool | None) -> None:
        message = self.session.confirm(worked)
        response = "Not sure" if worked is None else ("It worked" if worked else "It didn't work")
        self.log(f"You: {response}\nPreview: {message}")
        self.status.set("Still awaiting confirmation; nothing learned from this result." if worked is None else message)
        self.refresh()

    def reset(self) -> None:
        self.session = PreviewSession()
        self.log("Test session reset. All test memory and pending decisions were discarded.")
        self.status.set("Ready for a fresh test.")
        self.refresh()


def main() -> None:
    root = tk.Tk()
    DesktopPreview(root)
    root.update()
    print("Isolated desktop preview ready. No live integrations enabled.", flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
