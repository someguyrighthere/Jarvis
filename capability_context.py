"""Host-verified capability facts and read-only diagnostic request aliases."""

import re


CAPABILITY_FACTS = (
    "SARA runs as a local Windows desktop assistant, not a cloud-hosted chatbot. "
    "Her configured conversation and routing models run through local Ollama. "
    "Existing local integrations can inspect CPU, memory, free disk space, network interfaces "
    "and Microsoft Defender status; open applications/websites; use supported browser/media controls; "
    "manage tasks, reminders, working-folder files and saved personal memory; and propose Forge tools. "
    "Weather and optional web research use external services. Access is limited to implemented handlers "
    "and current Windows permissions, not unrestricted access to every file or account. "
    "Actions may require explicit approval; generated tools have no user-file or network access "
    "inside the WSL sandbox. A capability description is not proof an action has executed. "
    "Personal memory is explicit local storage, not automatic learning of every conversation."
)

SELF_QUERIES = {
    "do you have access to my computer", "can you access my computer",
    "do you have access to my pc", "can you access my pc",
    "what can you do on my computer", "what can you do", "what are your capabilities",
    "how do you work", "how does your long-term memory work", "how does your long term memory work",
    "i thought you had the ability to check your own systems",
}

SYSTEM_QUERIES = {
    "system status", "check system health", "hardware status", "monitor hardware",
    "system check", "systems check", "check my system", "check my systems",
    "check your system", "check your systems", "run a system check", "run a systems check",
    "run a diagnostic check", "run a diagnostic check on yourself",
    "can you run a diagnostic check on yourself", "can you run a system check",
    "can you run a systems check", "check your own systems",
}
NETWORK_QUERIES = {"network status", "check my network", "monitor my network"}
SECURITY_QUERIES = {"security status", "check security"}


def normalize_request(request: str) -> str:
    return re.sub(r"\s+", " ", request.casefold().strip()).rstrip(".?!")


def diagnostic_capability(request: str) -> str:
    query = normalize_request(request)
    for phrases, identifier in (
        (SYSTEM_QUERIES, "system.status"),
        (NETWORK_QUERIES, "network.status"),
        (SECURITY_QUERIES, "security.status"),
    ):
        if query in phrases:
            return identifier
    return ""


def describe_capabilities(request: str) -> str | None:
    if normalize_request(request) not in SELF_QUERIES:
        return None
    return (
        "I run locally on your Windows computer, with local Ollama models. I can use my implemented "
        "tools to check system health, network and Defender status, open applications and websites, "
        "and manage tasks, reminders, supported files and saved memory. I do not have unrestricted "
        "access to every file or account, and protected actions still need approval. "
        "Generated apps are sandboxed. Say 'check system health' for a real CPU, memory and disk report. "
        "My saved personal memory is explicit local storage; I don't automatically save every conversation."
    )
