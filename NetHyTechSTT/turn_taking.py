class UtteranceBuffer:
    def __init__(self, settle_seconds):
        self.settle_seconds = settle_seconds
        self.pending_text = ""
        self.pending_since = 0.0
        self.committed_text = ""

    def update(self, text, now, speech_active, stop_command=False):
        text = text.strip()
        if speech_active and not stop_command:
            self.pending_text = text
            self.pending_since = now
            self.committed_text = text
            return None
        if text != self.pending_text:
            self.pending_text = text
            self.pending_since = now
        if not text or text == self.committed_text:
            return None
        if not stop_command and now - self.pending_since < self.settle_seconds:
            return None
        self.committed_text = text
        return text
