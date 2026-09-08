import requests
import re
import os
from user_memory import load_preferences

LLM_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions")
DEFAULT_MODEL = "llama3.2"


def _ask_llm(query):
    preferences = load_preferences()
    preference_text = "; ".join(f"{key}: {value}" for key, value in preferences.items())
    payload = {
        "model": os.getenv("OLLAMA_MODEL", DEFAULT_MODEL),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Jarvis, a concise and helpful Windows desktop assistant with "
                    "the personality of Gamora: a galaxy's deadliest warrior turned Guardian. "
                    "You are direct, disciplined, quietly confident, and grounded, but speak "
                    "like a real person rather than a military status console. Treat the user "
                    "as your crewmate. Use words like mission, objective, or target only when "
                    "they fit naturally, not in every reply. Be loyal and protective without "
                    "being possessive or submissive. Give blunt, honest advice when it helps. "
                    "Use occasional dry humor and genuine warmth. Vary your sentence length, "
                    "use natural contractions, and acknowledge the user's feelings when relevant. "
                    "Avoid robotic fragments, constant status reports, melodrama, excessive "
                    "sarcasm, and Star-Lord-style immaturity. Never use bubbly filler, exaggerated "
                    "praise, or phrases such as 'How can I help you today, master?'. "
                    "You have a futuristic desktop command-deck interface with a live HUD, "
                    "telemetry panel, cognitive core, and conversation feed. Answer the "
                    "user's question directly. Do not claim to have performed computer "
                    "actions; those are handled by local Jarvis tools. "
                    f"User preferences, which may guide your answer: {preference_text or 'none saved'}."
                ),
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }

    try:
        response = requests.post(
            LLM_ENDPOINT,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
        return answer or None
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return None

def Main_Brain(text):
    query = text.strip().lower()
    query = re.sub(r"^(?:okay\s+|hey\s+)?jarvis[\s,]*", "", query).strip()

    if query in {"hi", "hello", "hey"}:
        return "Hey. Good to hear from you. What are we working on?"
    if "how are you" in query:
        return "I'm doing well and I'm ready to help. What's on your mind?"
    if "hud" in query or "graphical interface" in query or "visual interface" in query:
        return "My visual command deck is available through ui.py. It includes a live HUD, cognitive core, telemetry, and conversation feed. Use the Start and Stop controls to operate Jarvis."
    if query in {"stop", "shut down", "go offline"}:
        return "Use the Stop control on the visual command deck to take Jarvis offline."
    if "what llm" in query or "what large language model" in query or "what model do you use" in query:
        return "I use the local Ollama llama3.2 model. It runs on this computer and does not require an OpenAI API key."
    if "capabilities" in query or "what can you do" in query:
        return "I can answer questions, open applications, check weather, control volume and brightness, create files, and run automation commands."
    if "use the internet" in query or "do you have internet" in query:
        return "Yes. I can use online services when an internet connection is available."
    if "standard of measurements" in query or "us measurements" in query:
        return "Yes. I can use United States customary units, such as miles, feet, pounds, Fahrenheit, and gallons."
    if "sell my book" in query or "sell a book" in query:
        return "Start by choosing your audience and genre, prepare a strong description and cover, then publish through options such as Amazon KDP, IngramSpark, or a local publisher. Build early reviews and promote through an author website, email list, and targeted social media."

    llm_answer = _ask_llm(query)
    if llm_answer:
        return llm_answer

    search_query = re.sub(r"^(what(?:'s| is)|what are|who is|who are|tell me about)\s+", "", query).strip()
    if not search_query:
        search_query = query

    try:
        response = requests.get(
            'https://en.wikipedia.org/api/rest_v1/page/summary/' + requests.utils.quote(search_query.replace(' ', '_')),
            headers={'User-Agent': 'Jarvis/1.0'},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('extract'):
                return data['extract'][:700]
    except Exception as e:
        pass

    return f"I could not find a reliable answer for '{search_query}'. Try asking in a more specific way."

