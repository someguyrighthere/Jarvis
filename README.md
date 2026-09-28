# Sara - Desktop AI Assistant

[![LinkedIn][linkedin-shield]][linkedin-url]
[![Instagram][instagram-shield]][instagram-url]
[![Twitter][twitter-shield]][twitter-url]
[![YouTube][youtube-shield]][youtube-url]
[![Telegram][telegram-shield]][telegram-url]

**Welcome to Sara!**  
Sara is a desktop AI assistant designed to assist with various tasks, from navigating websites to controlling your PC with natural language commands.

![image](https://github.com/user-attachments/assets/59727c15-d85a-41bc-b27d-bea08b3b3a41)


## Installation ⚙️
### Windows installer
Download the latest `JARVIS-Setup-*.exe` from the repository's GitHub Releases page and run it. The installer creates a desktop shortcut and installs the HUD as the main app.

To update Sara, run the newer installer over the existing installation. It replaces the app executable while preserving your conversation log, schedules, input state, and preferences.

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
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" .\installer.iss
```

The installer is also built automatically by `.github/workflows/release.yml` whenever a `v*` tag is pushed.

Use **Start** and **Stop** in the panel to control Sara. The panel shows the current Ollama model, voice, and recent conversation log. Say “Sara” before a command to address the assistant.

### Local AI answers with Ollama
Sara uses Ollama locally for general questions. Install Ollama from `https://ollama.com/download/windows`, then run these commands:

PowerShell:
```powershell
ollama pull llama3.2
$env:OLLAMA_MODEL = "llama3.2"
py -3.12 jarvis.py
```

Ollama runs on your computer and does not require an API key or subscription. Local commands such as weather and opening applications continue to use Sara's local handlers.

Sara uses Piper's local British English `en_GB-alba-medium` voice. The voice is downloaded on first use and then works offline. If Piper cannot load the model, Windows SAPI is used as a fallback.

Piper's runtime is GPL-3.0-or-later. The Alba voice model is CC-BY 4.0 and is based on the Edinburgh speech dataset. See the [voice model card](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alba/medium) for attribution and details.

### Web research
For general questions, Sara searches the web through DuckDuckGo and gives the local Ollama model the result snippets as reference material. This lets it answer questions about newer information without changing or retraining the model. Web results are treated as untrusted text and are not executed. To permanently save a personal preference, use the `remember` command.

Sara also has a local retrieval-augmented knowledge base. After researching a topic, explicitly save a fact with commands such as `Sara, learn this: Python uses indentation to define code blocks`. Relevant saved facts are automatically retrieved for later questions. Say `Sara, clear learned knowledge` to remove that knowledge without removing personal preferences.

### System monitoring and updates
Sara can report local hardware usage, active network interfaces, and Microsoft Defender status on request:

```text
Sara, check system health
Sara, check my network
Sara, check security
Sara, scan for threats
Sara, check for updates
Sara, update drivers and software
```

These checks are on demand and limited to this computer. A quick scan uses Microsoft Defender. The update command installs available Windows driver updates and upgrades packages managed by `winget`; it accepts package agreements and may require Windows elevation or a restart. Sara does not run these updates in the background, and an unavailable update source is reported rather than treated as a successful check.

### Sara extensions
Sara can propose reusable extensions from her currently approved read-only tools. Review a proposal before enabling it:

```text
Sara, create a tool for a network and security brief
Sara, show extension proposal
Sara, approve extension
Sara, reject extension
Sara, list extensions
```

Enabled extensions can be invoked by their trigger phrases. This initial extension system only combines local system, network, and Defender status reports. It does not execute model-generated code, install software, run scans, or create arbitrary applications. Requests needing capabilities outside that allowlist are declined rather than granted new permissions automatically.

### Project generation
Sara can draft a small multi-file app or project, show the proposed file list, and write it into `Documents/SaraProjects` only after approval:

```text
Sara, build a simple website for tracking reading goals
Sara, show project proposal
Sara, approve project
Sara, reject project
```

The full draft is stored in `%LOCALAPPDATA%\Sara\project_proposal.json` for review before approval. Sara validates relative paths, file types, size limits, and Python/JSON syntax. Generated code is never run during project creation.

To run a saved Python CLI project, inspect its files first and request a run:

```text
Sara, run project reading-tracker
Sara, show run request
Sara, approve run
Sara, reject run
```

Only projects with a root `main.py` or `app.py` can run. Sara checks that the source has not changed since the request. Approved runs use Ubuntu/WSL with Bubblewrap: project source is read-only, networking and Windows/home-directory mounts are unavailable, temporary output is discarded, and runtime, memory, process, file, and output limits are enforced. Sara does not install dependencies.

To make a reusable Sara tool, ask for a tool project, approve its source as a project, then propose and separately approve it as a tool:

```text
Sara, create a Sara tool to convert temperatures
Sara, approve project
Sara, propose project temperature-helper as a Sara tool
Sara, show tool proposal
Sara, approve tool
Sara, list my tools
```

Tools must provide `tool.py` and `sara_tool.json`, declare no extra permissions, and use specific trigger phrases. Each invocation receives only the current request text, runs in the same WSL sandbox, and must return bounded JSON text. Editing an enabled project's source disables the tool until it is reviewed and approved again.

### Controlled learning
Sara can remember preferences without changing its source code:

```text
Sara, remember that my preferred temperature unit is Fahrenheit
Sara, remember not to say the word asterisk when speaking to me
Sara, what do you remember about me?
Sara, forget what you remember
```

To request a code improvement, say:

```text
Sara, improve yourself by using Fahrenheit in weather responses
```

### Tasks and plans
Sara can keep a local task list and draft a checklist for a goal. Proposed plan steps are only added to the task list after approval:

```text
Sara, add task to review the project budget
Sara, show my tasks
Sara, complete task 1
Sara, plan a website launch
Sara, approve plan
```

Say `Sara, cancel plan` to discard a proposed checklist. Plans organize work; Sara does not execute the listed actions automatically.

Sara creates a proposed change using the local Ollama model and does not edit source code yet. Review the proposal, then say:

```text
Sara, approve this improvement
```

Approved changes are limited to one Python source file, syntax-checked, and backed up in `self_update_backups` before they are applied. If Ollama is unavailable, Sara saves the request for manual review instead.

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


