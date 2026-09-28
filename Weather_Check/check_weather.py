import requests
from urllib.parse import quote

def get_weather_by_address(address):
    location = address.strip()
    endpoint = "https://wttr.in/"
    if location:
        endpoint += quote(location)
    endpoint += "?format=j1"

    try:
        response = requests.get(
            endpoint,
            headers={"User-Agent": "Jarvis/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        current = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        resolved_location = area.get("areaName", [{}])[0].get("value", location or "your location")
        description = current["weatherDesc"][0]["value"]
        temperature = current["temp_C"]
        feels_like = current["FeelsLikeC"]
        return (
            f"Current weather in {resolved_location}: {description}, "
            f"{temperature} degrees Celsius, feels like {feels_like}."
        )
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return "I could not retrieve the weather right now."

