import re
from collections.abc import Sequence


def plan_gestures(text: str, duration: float, levels: Sequence[float] | None = None) -> list[dict]:
    """Estimate phrase accents, optionally refined by the 40 ms audio envelope."""
    words = list(re.finditer(r"\b[\w']+\b", text))
    if not words or duration < 1 or (levels is not None and not any(level > 0.08 for level in levels)):
        return []
    weights = []
    for index, word in enumerate(words):
        following = words[index + 1].start() if index + 1 < len(words) else len(text)
        pause = 1.4 if re.search(r"[.!?;:]", text[word.end():following]) else 0.0
        weights.append(1 + min(len(word.group()), 10) * 0.08 + pause)
    total = sum(weights)
    positions = []
    position = 0
    for weight in weights:
        positions.append((position + min(weight, 1.5) * 0.35) / total * duration)
        position += weight

    rules = (
        ("uncertainty", r"\b(?:sorry|perhaps|maybe|unsure|uncertain|cannot|can't|not sure)\b"),
        ("greeting", r"\b(?:hello|welcome|good morning|good evening|hi)\b"),
        ("emphasis", r"\b(?:important|remember|must|always|never|key point)\b"),
        ("explanation", r"\b(?:because|first|next|for example|you can|here are|this means)\b"),
    )
    cues = []
    for kind, pattern in rules:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            index = sum(word.start() < match.start() for word in words)
            cues.append((positions[index], kind, index))
    candidates = list(cues)
    phrase_start = 0
    for index, word in enumerate(words):
        following = words[index + 1].start() if index + 1 < len(words) else len(text)
        boundary = bool(re.search(r"[,;:.!?]", text[word.end():following]))
        if index - phrase_start >= 7 or boundary or index == len(words) - 1:
            accent_index = min(index, phrase_start + max(1, (index - phrase_start) // 2))
            accent = positions[accent_index]
            if all(abs(accent - cue[0]) >= 2.4 for cue in cues):
                candidates.append((accent, "beat", accent_index))
            phrase_start = index + 1

    events = []
    for accent, kind, index in sorted(candidates):
        if levels:
            low = max(0, int((accent - 0.24) / 0.04))
            high = min(len(levels), int((accent + 0.24) / 0.04) + 1)
            if low >= high:
                continue
            frame = max(range(low, high), key=lambda i: (
                sum(levels[max(0, i - 1):min(len(levels), i + 2)]) / 3 + levels[i] * 0.5
                - abs(i * 0.04 - accent) * 0.3))
            if levels[frame] <= 0.08:
                continue
            accent = frame * 0.04
        variant = len(events) % 3
        prepare = (0.68, 0.76, 0.62)[variant]
        stroke = 0.28 if kind in {"beat", "emphasis"} else 0.34
        hold = (0.16, 0.24, 0.2)[variant]
        recover = (0.86, 0.96, 0.8)[variant]
        start = max(0.0, accent - prepare - stroke / 2)
        length = prepare + stroke + hold + recover
        if start == 0 and length > duration:
            scale = duration / length
            prepare, stroke, hold, recover = (phase * scale for phase in (prepare, stroke, hold, recover))
            length = duration
        if start + length > duration:
            recover -= start + length - duration
            length = duration - start
        if recover < 0.3 or (events and start < events[-1]["start"] + events[-1]["duration"] + 0.12):
            continue
        # Keep a dominant hand across a phrase pair, rather than metronomic alternation.
        side = -1 if (len(events) // 2) % 2 == 0 else 1
        support = 0.45 if kind == "uncertainty" else 0.28 if kind == "explanation" and variant == 1 else 0
        strength = (0.9, 1.0, 0.82)[variant]
        if levels:
            strength *= 0.8 + min(1.0, levels[frame]) * 0.2
        events.append({
            "kind": kind, "start": round(start, 3), "duration": round(length, 3),
            "prepare": round(prepare, 3), "stroke": round(stroke, 3),
            "hold": round(hold, 3), "recover": round(recover, 3),
            "side": side, "support": support, "strength": round(strength, 3), "variant": variant,
        })
    if len(events) > 12:
        meaningful = [event for event in events if event["kind"] != "beat"]
        if len(meaningful) > 12:
            events = [meaningful[round(slot * (len(meaningful) - 1) / 11)] for slot in range(12)]
        else:
            selected = list(meaningful)
            while len(selected) < 12:
                remaining = [event for event in events if event not in selected]
                selected.append(max(remaining, key=lambda event: min(
                    (abs(event["start"] - chosen["start"]) for chosen in selected),
                    default=-event["start"])))
            events = sorted(selected, key=lambda event: event["start"])
    for index, event in enumerate(events):
        event["side"] = -1 if (index // 2) % 2 == 0 else 1
    for first, second in zip(events, events[1:]):
        gap = second["start"] - first["start"] - first["duration"]
        if first["side"] == second["side"] and first["kind"] == second["kind"] and gap < 1.2:
            first["link_next"] = second["start"]
            second["linked"] = True
    return events
