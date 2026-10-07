"""Run from the project root: .\\.venv312\\Scripts\\python.exe -m experiments.typed_app_tree_test

Separate typed window using the staged adapter. It never submits real commands to
SARA, dispatches apps, or launches Forge. History is in-memory; saving confirmed
mock workflows requires SARA_APP_TREE_MEMORY_ENABLED=1.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app_tree_stage import MockAppTreeStage


def conversation_answer(request: str) -> str:
    from Brain.brain import _ask_llm, _guard_conversation_answer, _record_turn

    answer = _ask_llm(request)
    if not answer:
        raise RuntimeError("SARA's local conversation model did not return an answer.")
    return _record_turn(request, _guard_conversation_answer(answer))


class TypedTestWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.stage = MockAppTreeStage()
        self.busy = False
        self.closed = False
        self.results: queue.Queue[str] = queue.Queue()
        root.title("SARA - typed mock routing test")
        root.geometry("1100x650")
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Typed local-model routing | MOCK APPS ONLY", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame, wraplength=880,
            text="Type a natural request below; no spoken prefix is required. "
                 "This separate session does not control SARA, create real reminders, access Downloads, "
                 "or launch Forge. Answers use her local persona and saved-memory context. "
                 "Closing discards history and unanswered decisions. "
                 "Confirmed mock workflows persist only when the separate memory opt-in is enabled.",
        ).pack(anchor="w", pady=8)
        self.history = tk.Text(frame, wrap="word", state="disabled")
        self.history.pack(fill="both", expand=True)
        self.entry = ttk.Entry(frame)
        self.entry.pack(fill="x", pady=8)
        self.entry.bind("<Return>", lambda event: self.submit())
        self.buttons: list[ttk.Button] = []
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        for label, action in (
            ("Send request", None), ("Approve mock", "approve"), ("Reject mock", "reject"),
            ("It worked", "worked"), ("It failed", "failed"), ("Not sure", "not sure"),
            ("Memory", "memory"), ("Reset", "reset"), ("Clear workflows", "clear workflows"),
        ):
            button = ttk.Button(controls, text=label, command=lambda value=action: self.submit(value))
            button.pack(side="left", padx=2)
            self.buttons.append(button)
        memory_mode = "persistent MOCK-TEST-ONLY" if os.environ.get("SARA_APP_TREE_MEMORY_ENABLED") == "1" else "temporary"
        self.status = tk.StringVar(value=f"Workflow memory: {memory_mode}. Enable SARA_APP_TREE_MOCK_ENABLED=1 to test.")
        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=8)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.timer = root.after(100, self.poll)

    def log(self, text: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", text + "\n\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    def submit(self, action: str | None = None) -> None:
        if self.busy or self.closed:
            return
        request = self.entry.get().strip() if action is None else action
        if not request:
            self.status.set("Please type a request.")
            return
        if action == "clear workflows" and not messagebox.askyesno(
            "Clear mock workflows?",
            "Delete all confirmed mock workflow successes and discard pending mock decisions? "
            "Personal memory will not be changed.",
            parent=self.root,
        ):
            return
        command = "app tree test " + ("ask " + request if action is None else request)
        self.log("You: " + request)
        self.entry.delete(0, "end")
        self.busy = True
        self.entry.configure(state="disabled")
        for button in self.buttons:
            button.configure(state="disabled")
        self.status.set("Waiting for local model or test result; no real action will execute.")
        threading.Thread(target=self.process, args=(command,), daemon=True).start()

    def process(self, command: str) -> None:
        try:
            answer = self.stage.handle(command, answerer=conversation_answer)
            if answer is None:
                raise RuntimeError("The typed test command was not handled.")
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            answer = f"Test failed: {error}. No real action was dispatched."
        self.results.put(answer)

    def poll(self) -> None:
        if self.closed:
            return
        try:
            answer = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.log("SARA test: " + answer)
            self.busy = False
            self.entry.configure(state="normal")
            for button in self.buttons:
                button.configure(state="normal")
            self.status.set("Ready. Memory shows whether mock workflows are persisted; history and pending decisions are session-only.")
        self.timer = self.root.after(100, self.poll)

    def close(self) -> None:
        if self.busy:
            self.status.set("Please wait for this operation to finish before closing; a save may be in progress.")
            return
        self.closed = True
        self.root.after_cancel(self.timer)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    TypedTestWindow(root)
    root.update()
    print("Typed mock test ready; enabled=" + str(os.environ.get("SARA_APP_TREE_MOCK_ENABLED") == "1"), flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
