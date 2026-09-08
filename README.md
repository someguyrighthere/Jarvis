# J.A.R.V.I.S - Just A Rather Very Intelligent System 🤖

[![LinkedIn][linkedin-shield]][linkedin-url]
[![Instagram][instagram-shield]][instagram-url]
[![Twitter][twitter-shield]][twitter-url]
[![YouTube][youtube-shield]][youtube-url]
[![Telegram][telegram-shield]][telegram-url]

**Welcome to J.A.R.V.I.S!**  
J.A.R.V.I.S (Just A Rather Very Intelligent System) is an advanced AI assistant inspired by Iron Man's Jarvis, designed to assist with various tasks, from navigating websites to controlling your PC with natural language commands.

![image](https://github.com/user-attachments/assets/59727c15-d85a-41bc-b27d-bea08b3b3a41)


## Installation ⚙️
### Windows installer
Download the latest `JARVIS-Setup-*.exe` from the repository's GitHub Releases page and run it. The installer creates a desktop shortcut and installs the HUD as the main app.

To update JARVIS, run the newer installer over the existing installation. It replaces the app executable while preserving your conversation log, schedules, input state, and preferences.

The installed app still requires Google Chrome for speech recognition and Ollama for local LLM answers. These are external dependencies and are not bundled into the installer.

### Developer installation
1. Clone the repository:
    ```bash
    git clone https://github.com/AnubhavChaturvedi-GitHub/J.A.R.V.I.S.git
    ```
2. Navigate to the project directory:
    ```bash
    cd J.A.R.V.I.S
    ```
3. Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage 🚀
To start the assistant, run:
```bash
python jarvis.py
```

To open the visual control panel, run:
```powershell
py -3.12 ui.py
```

### Build an installer
On Windows, install Inno Setup, then run:
```powershell
.\build.ps1
iscc .\installer.iss
```

The installer is also built automatically by `.github/workflows/release.yml` whenever a `v*` tag is pushed.

Use **Start Jarvis** and **Stop** in the panel to control the assistant. The panel shows the current Ollama model, voice, and recent conversation log.

### Local AI answers with Ollama
Jarvis uses Ollama locally for general questions. Install Ollama from `https://ollama.com/download/windows`, then run these commands:

PowerShell:
```powershell
ollama pull llama3.2
$env:OLLAMA_MODEL = "llama3.2"
py -3.12 jarvis.py
```

Ollama runs on your computer and does not require an API key or subscription. Local commands such as weather and opening applications continue to use Jarvis's local handlers.

Jarvis uses the Microsoft `en-GB-SoniaNeural` British female voice for more natural speech when internet access is available, and falls back to the installed Windows voice when it is not.

### Controlled learning
Jarvis can remember preferences without changing its source code:

```text
Jarvis, remember that my preferred temperature unit is Fahrenheit
Jarvis, what do you remember about me?
Jarvis, forget what you remember
```

To request a code improvement, say:

```text
Jarvis, improve yourself by using Fahrenheit in weather responses
```

Jarvis saves the request in `improvement_request.json` for review. It does not edit or execute source-code changes automatically.

## Contribution 🤝
Feel free to fork the repository, submit issues, or create pull requests. Your contributions are welcome!

## License 📄
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
<!-- Linkedin -->

[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=0B5FBB
[linkedin-url]: https://www.linkedin.com/in/anubhav-chaturvedi-/

<!-- Instagram -->

[instagram-shield]: https://img.shields.io/badge/Instagram-%23E4405F.svg?style=for-the-badge&logo=Instagram&logoColor=white
[instagram-url]: https://www.instagram.com/_anubhav__chaturvedi_/

<!-- Twitter -->

[twitter-shield]: https://img.shields.io/badge/Twitter-%231DA1F2.svg?style=for-the-badge&logo=Twitter&logoColor=white
[twitter-url]: https://x.com/AnubhavChatu


<!-- YouTube -->
[youtube-shield]: https://img.shields.io/badge/YouTube-%23FF0000.svg?style=for-the-badge&logo=YouTube&logoColor=white
[youtube-url]: https://www.youtube.com/@NetHyTech

<!-- Telegram -->
[telegram-shield]: https://img.shields.io/badge/Telegram-%231DA1F2.svg?style=for-the-badge&logo=Telegram&logoColor=white
[telegram-url]: https://t.me/YourTelegramUsername


