# Sara - Desktop AI Assistant

[![LinkedIn][linkedin-shield]][linkedin-url]
[![Instagram][instagram-shield]][instagram-url]
[![Twitter][twitter-shield]][twitter-url]
[![YouTube][youtube-shield]][youtube-url]
[![Telegram][telegram-shield]][telegram-url]

**Welcome to Sara!**  
Sara is a desktop AI assistant designed to assist with various tasks, from navigating websites to controlling your PC with natural language commands.

### Version 2.0.2
- Custom indigo-and-teal SARA monogram for the Windows app and desktop shortcuts.
- Manage local saved preferences and personal notes in the HUD; relevant notes can inform local AI replies.
- Review and approve supported computer-changing commands before execution, inspect the local action log, and undo recent volume or brightness changes.
- Interrupt spoken replies with a stop command or a new wake-word command to redirect SARA.
- WhatsApp message sending shows the recipient and exact text and requires a separate spoken confirmation before sending.
- Ambient black-to-midnight-blue background with a soft glow behind SARA.
- The background is rendered separately from the avatar, preserving natural
  skin tones and suit contrast without a blue overlay.
- Muted charcoal telemetry cards complement the new background.

### Version 2.0.1
- The animated HUD is now the main native desktop window, using embedded WebView2
  instead of opening a browser tab or the legacy Tk panel.
- Opening SARA starts the assistant automatically; closing the window stops its
  owned assistant process tree and local server. Start/Stop controls are in the SARA card.
- Setup installs WebView2 if missing using Microsoft's signed bootstrapper.

### Version 2.0.0
- Full-body SARA avatar with blinking, voice-driven mouth motion, conversational
  hand gestures, subtle weight shifts, and an invisible shadow-receiving floor.
- Live assistant, computer, and Ollama telemetry in the browser HUD.
- Automatic startup update/dependency checks with compact controls shown only
  when a newer release or missing component needs attention.
- Offline Piper voice included in the installer, with optional Chrome, Ollama,
  AI-model, and Forge setup; skipped choices remain installable in Dependencies.
- Improved microphone startup, speech formatting, and Forge configuration handling.

![image](https://github.com/user-attachments/assets/59727c15-d85a-41bc-b27d-bea08b3b3a41)


## Installation ⚙️
### Windows installer
Download the latest `JARVIS-Setup-*.exe` from the repository's GitHub Releases page and run it. The installer creates a desktop shortcut and installs the HUD as the main app.

To update Sara, run the newer installer over the existing installation. It replaces the app executable while preserving your conversation log, schedules, input state, and preferences.

Chrome for speech recognition and Ollama/model downloads for local AI are optional
setup choices, not bundled applications. Skipped choices remain available in the
Dependencies panel. Python, libraries, the avatar renderer, and voice files are included.

SARA stores saved preferences and personal notes locally. Use “remember note …” by voice,
or open **Manage Memory** in the HUD to review, edit, or delete saved entries. Relevant
personal notes can be added to local Ollama prompts.

After a clearly stated detail (for example, your name, city, job, or current project) comes
up in separate interactions, SARA may ask whether to save it. She saves nothing from this
learning prompt unless you say “remember it”; say “don't remember it” to decline. Detection
is limited to explicit, supported phrases, and precise street-address details are not proposed.
Profile preferences and learned knowledge are stored in `%LOCALAPPDATA%\\Sara` and loaded
into the local AI context when relevant. Existing project-folder memory files are copied into
that persistent location on first use.

Supported app launches, closes, file creation/renaming, system volume/brightness changes, reminders,
image generation, and WhatsApp flows show a review step before SARA dispatches them. Say
“approve action” or “cancel action”; use **Review Action Log** or “show action history” to
see approved commands. Volume and brightness changes can be undone with “undo last action.”
Supported file renames can also be undone when the original name is still available.
Say “stop talking” or interrupt a spoken reply with “SARA, …” to redirect the conversation.

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

To open SARA's desktop app, run:
```powershell
py -3.12 launcher.py
```

### Staged mock app-tree integration (off by default)

The app tree is **not enabled for ordinary requests**. This first integration stage
uses scripted mock scenarios and optional local Ollama routing, never real apps or
Forge. SARA's existing persona, profile, notes, preferences, knowledge, and HUD
remain on their existing paths. Mock replies use the existing speech and conversation
feed; no new HUD controls are added.

To opt in for a source-run test, launch from a PowerShell terminal:

```powershell
$env:SARA_APP_TREE_MOCK_ENABLED = "1"
.\.venv312\Scripts\python.exe launcher.py
```

Say "SARA, app tree test help" for commands. Try "app tree test weather",
"app tree test reminder", "app tree test failure", or "app tree test missing app".
Exact prefix spellings `apptree test` and `app-tree test` are also accepted.
For natural-language routing, say "app tree test ask check the weather in Boston",
"app tree test ask remind me to call Alex tomorrow", or
"app tree test ask explain photosynthesis". The local routing model defaults to
`qwen3:8b` (override with `SARA_APP_TREE_OLLAMA_MODEL`) and needs a running Ollama
instance and an installed model. Only loopback HTTP endpoints are permitted.
It selects a fixed mock weather app, an approval-gated mock reminder, a proposal,
or an answer through SARA's existing conversation handler (and its existing model,
persona, and saved-memory context). Planner answer text is not spoken instead of
SARA's own answer. Invalid decisions get one validated repair; failures are
reported without falling through to real app execution. A repair cannot detect
every semantically wrong choice, so model accuracy remains under test.
Requests are routed independently; pronoun-based task follow-ups are not yet supported.
Routing can take up to two 120-second model requests; it does not alter the HUD.

For speech-independent testing, open a **separate typed test window** from the
project root:

```powershell
$env:SARA_APP_TREE_MOCK_ENABLED = "1"
$env:SARA_APP_TREE_OLLAMA_MODEL = "qwen3:8b"
.\.venv312\Scripts\python.exe -m experiments.typed_app_tree_test
```

Type a natural request without a prefix, then use the approval/feedback buttons.
Simple local-time questions (including the observed typo "waht time is it") use
the computer's clock directly, not a model-generated time. This read-only answer
does not learn a workflow or override a pending approval/confirmation.
It uses the same staged adapter, but has its own session and temporary history;
it does not write requests to the running assistant or its conversation log.
Conversation answers use local Ollama with SARA's existing persona and saved-memory
context, without web-search fallback or Forge offers. Reset discards pending test decisions,
not persisted mock workflows.
Existing saved profile/notes/knowledge are not changed.

The conversation-only answer path now checks common first-person action-completion
claims and promises of notifications, replacing unverified claims with an explicit
warning. This is a conservative phrase guard, not a proof of factual correctness
or a complete detector of every paraphrase. Real tool execution reports remain
on their existing paths.
Incomplete commands such as "app tree help" receive correction rather than a
model-generated explanation. Action words are not guessed: "whether failed"
does not start a weather test or confirm its result.
Only "app tree test approve" approves a mock action. Only "app tree test worked"
learns its successful route; "app tree test failed" declines learning, and
"app tree test not sure" leaves confirmation pending. Ordinary "yes", "approve action",
and profile-learning confirmations do not confirm a mock result. Each decision
is one-time. "app tree test memory" describes confirmed mock workflows and
labels whether they are temporary or persisted. Existing real-app commands are
unchanged even while testing: only the explicit test namespace is mocked.

#### Persistent mock workflow memory (separate opt-in)

Set `SARA_APP_TREE_MEMORY_ENABLED=1` before launching the source app or typed
window to retain **explicitly user-confirmed mock successes** across restarts:

```powershell
Set-Location "C:\Users\xarcy\OneDrive\Desktop\Jarvis\jarvis-ai-assistant"
$env:SARA_APP_TREE_MOCK_ENABLED = "1"
$env:SARA_APP_TREE_MEMORY_ENABLED = "1"
$env:SARA_APP_TREE_OLLAMA_MODEL = "qwen3:8b"
.\.venv312\Scripts\python.exe -m experiments.typed_app_tree_test
```

These entries are stored separately in
`%LOCALAPPDATA%\Sara\app_tree_mock_workflows.json`, with scope `mock_test_only`.
Only normalized task categories, mock capability IDs, and explicit confirmation
counts are stored, not conversation transcripts or raw task requests.
They do not establish that a real app works, affect personal-memory retrieval,
or grant any future approval. The voice test and typed window share this mock
store when opted in; concurrent updates are locked and writes are atomic.
Invalid files and storage failures are reported rather than silently reset.
If a save fails, success confirmation remains pending for an explicit retry.

Use **Memory** or "app tree test memory" to inspect; **Clear workflows** or
"app tree test clear workflows" deletes mock successes and pending mock decisions
without touching personal memory. **Reset** or "app tree test reset" resets only
the active session; saved mock successes remain. Pending approvals, unanswered
confirmations, proposals, and test history do not persist. Closing or Stop/Start
never automatically approves or confirms a task.
The typed window confirms deletion before clearing workflows and waits for the
current operation to finish before allowing you to close, avoiding an unseen
save after normal window closure. If the store is corrupt, the explicit clear
command can discard it; otherwise the invalid data is left untouched.

Without the separate memory opt-in, workflows remain temporary and disappear
when the process exits. Disabling persistence does not delete the existing mock
store. The older isolated scripted previews still use temporary memory only.

Remove the opt-in before launching normally:

```powershell
Remove-Item Env:\SARA_APP_TREE_MOCK_ENABLED
```

Version 2.0.3 packages the staged adapter and the typed test window. These remain
disabled by default, including after an installer upgrade. To use the typed test
without the source tree or Python, set the opt-in variables above and run:

```powershell
& "$env:LOCALAPPDATA\JARVIS\Jarvis.exe" --app-tree-test
```

The normal desktop shortcut opens the existing HUD. The isolated previews and
local-model tests remain available in `experiments`.

### Real app tree (2.1.0)

The normal assistant now routes conversational requests through local Ollama
(`qwen3:8b` by default) to an answer, a registered real capability, or an
approval-gated Forge build proposal. Answers still use SARA's existing personality,
conversation context, and saved personal memory. Model text never executes a
command or grants approval. Existing specialized commands remain available.
Common reminders, tasks, weather, and working-folder file commands from a
wake-word/follow-up request use the real routing path directly.

For typed access, select **SARA App Tree** in the Start menu, or run:

```powershell
& "$env:LOCALAPPDATA\JARVIS\Jarvis.exe" --app-tree
```

There is no mock opt-in required for this real window. It can create actual
reminders, tasks, and files **only after approval**. The older `--app-tree-test`
window and `app tree test` commands remain mock-only and separate.

Examples (spoken with SARA's wake word, or typed without it):

```text
app tree ask remind me to call Alex tomorrow at 9 AM
app tree approve
app tree worked
app tree ask weather in Boston
app tree approve
app tree worked
```

Registered built-ins: local time, weather for an explicitly named city, local
reminder creation/listing, task creation/listing, and safe file creation/renaming
in SARA's working folder. Time is read-only and immediate; the other real routes
require explicit `app tree approve` (or the Approve button). Weather review
discloses the city and external service. Missing/invalid arguments prompt for
details; the model cannot invent arguments, paths, or a notification destination.
The file handlers retain their no-overwrite and working-folder restrictions.

Reminders require an exact local time and support today, tomorrow, or
`YYYY-MM-DD`; omitted dates use the next occurrence. A time without AM/PM must
be a 24-hour `HH:MM` time. Ambiguous requests such as "tomorrow" without a time
do not schedule anything. Reminders persist separately in
`%LOCALAPPDATA%\Sara\reminders.sqlite3`; SARA must be running to announce them.
Overdue reminders are delivered when the assistant or real typed window next
runs. These are local spoken reminders, not phone notifications or an
always-running Windows background service.

#### Missing capabilities and Forge

1. Request an unsupported capability. SARA proposes a Forge tool but does not
   start a build. Approve with `app tree approve build`.
2. Forge 1.4.1+ builds in its existing restricted, private workspace and asks
   before edits. Its shell, code execution, and web tools remain disabled.
3. When it finishes, use `app tree review build`, inspect the full proposed
   source, then `app tree approve project` to save it.
4. Use the **separate** `app tree approve run` command for the first execution.
   A generic approval does not satisfy this first-run gate.
5. Valid sandbox output enables the tool for future routing. Only your later
   `app tree worked` confirmation records the successful workflow.

Generated tools must provide `tool.py` and a validated `sara_tool.json` manifest.
They read a JSON request from stdin and return a JSON `text` response. They run
only in the existing Ubuntu/WSL Bubblewrap sandbox: no network, user files,
Windows drives, installed dependencies, or persistent output; execution is
bounded to 15 seconds. Thus a generated helper can perform computations but
cannot organize Downloads or send messages by bypassing these restrictions.
Failures, malformed output, modified source, or conflicting triggers do not
enable or learn an app. Approved tools are discoverable immediately and on
restart, with a fresh approval required for each app-tree invocation.

Confirmed real routes are stored in
`%LOCALAPPDATA%\Sara\confirmed_workflows.sqlite3`, never the mock store or personal
memory. Categories, capability IDs, source fingerprints, and counts help future
model routing; they do not store raw requests or grant permissions. Generated
source must still match its reviewed fingerprint. `app tree memory` inspects
these records; `app tree clear workflows` clears only real workflow history.
`app tree failed` does not learn, and `app tree not sure` leaves the result
unconfirmed. Failed saves remain retryable without rerunning the action.
Pending operation approvals and success confirmations stay session-only.
`app tree reset` discards pending decisions, but does not undo completed actions
or stop a running Forge build. Existing Forge/project commands can inspect
persisted builds after an app-tree session ends.

### Selected 3D avatar
The selected avatar is Microsoft Rocketbox **Business Female 01**, stored in
`assets/avatars/business-female-01/`. The facial FBX and all seven TGA textures
come from [Microsoft Rocketbox](https://github.com/microsoft/Microsoft-Rocketbox/tree/0943055db6ec570bcef9f2c8b41c9e5467c808f9/Assets/Avatars/Professions/Business_Female_01)
at revision `0943055db6ec570bcef9f2c8b41c9e5467c808f9`.
The original MIT license is included in the asset folder and must accompany
redistributed copies.

Inspection found 80 skeleton bones and 175 shape geometries, including the
15 `AA_VI` speech visemes and left/right eye-blink shapes. The character wears
a black jacket, white shirt, and trousers. The FBX references texture paths
from its author's computer; importers must resolve those filenames against
the supplied `Textures` folder.

The installed app opens the avatar in its own desktop window, with no browser
tab or address bar. The legacy panel is available only by running `ui.py` explicitly.
Install its local renderer once with `npm ci` inside `avatar_web`.
No avatar or speech data is sent to a cloud rendering service.
SARA stands on an invisible floor that only receives a subtle, soft-edged shadow;
there is no visible platform or pedestal.

The avatar rests with her arms down, blinks, breathes, and gently sways her
upper body. Waiting includes subtle posture adjustments with upper-spine/head
counterbalance rather than a repeated sideways bend, and an occasional
wrist glance after 12 seconds, then roughly every 36 seconds, with the arm
lowering smoothly when interaction resumes, followed by a small six-second
settling sway once her arm lowers.
The wrist glance mimics checking
the time; the character does not currently wear a modeled watch. Listening adds
a slight attentive head tilt. Piper speech selects greeting, palm-up explanation,
emphasis, uncertainty, and small conversational beat gestures. Punctuation and
word-length estimates locate phrase accents; nearby peaks in the 40 ms audio
envelope refine stroke timing and scale gesture strength. This is an energy-based
timing heuristic, not pitch analysis or forced word alignment.
Each gesture has a preparation, a moving expressive stroke, a short hold, and
a slower recovery. Smooth minimum-jerk curves drive reachable wrist paths,
not a repeated blend into a static arm pose. A dominant hand can continue across
two gestures; nearby same-kind strokes retain a low ready position between them.
Some uncertainty/explanation gestures add a smaller, delayed supporting hand.
Wrist rotation and finger opening lag the arm slightly, and small head nods and
upper-torso turns accompany the stroke. Speaking also adds a slow, subtle
side-to-side upper-body sway with a smaller forward/back component and head
counterbalance. It fades in/out smoothly.
Standing and speaking now include slow hip weight shifts (roughly 2 cm),
a small pelvis roll, and knee flexion solved with two-bone leg IK.
World-space ankle targets and foot orientations preserve contact instead of
dragging the feet with the hips. After about 12 seconds, then roughly every
32 seconds, alternating feet can make a small outward/forward adjustment:
lift about 2.5 cm, place about 3.5 cm outward and 1.8 cm forward, hold,
then lift and return. The supporting leg stays in contact, and the body shifts
toward it during the adjustment. An in-progress adjustment finishes before
lower-body motion fades out on a state change; this is in-place stance
animation, not walking or physics-based balance.
Path, duration, and strength vary without
random jitter. Gestures stay in a compact conversational space and are capped
at twelve per response, distributed across long replies rather than exhausted
at the beginning. Text-cued gestures take priority over filler beats.
Silent audio does not trigger a gesture.
Idle behavior also includes occasional alternating side glances, a small
shoulder/arm stretch, and a relaxed upper-body posture adjustment, spaced
between wrist checks. A 72-second idle sequence includes hands held together
in front of her waist (around 31 seconds) and behind her back (around 57 seconds).
Two-bone arm positioning keeps these poses within reach. Wrist orientation
follows the pose with a roughly 25-degree bend limit; all 30 finger joints
receive a relaxed curl that deepens during hand-folding. During wrist checks,
the watch-side fingers close into a loose fist with a tucked thumb, then
relax again as the arm lowers.
Folded hands are staggered rather than placed at the same point; precise
finger interlocking/contact is not simulated. These fade out when processing
or speech begins. A lighter blue-gray backdrop and additional fill/rim
lighting separate the character's dark clothing from the background.
These are procedural poses with rule-based intent selection, not motion-captured
animation or full semantic understanding. Speech interruption clears the gesture plan and smoothly
returns the arms to rest. SAPI fallback has no timed gesture plan.
The phase/grouping and asymmetric-handedness design follows the
[MIT Speech Communication Group gesture coding manual](https://speechcommunicationgroup.mit.edu/gesture/coding-manual.html).
Anticipatory preparation is informed by
[ter Bekke, Drijvers, and Holler (2024)](https://doi.org/10.1111/cogs.13407);
the specific timings and path dimensions above are implementation choices,
not measured human motion data.
Run gesture regressions with `python -B -m unittest test_speech_gestures test_avatar_bridge`
and `node --test avatar_web/speech_motion.test.mjs`.
The embedded VS Code viewer can report hidden-page visibility; a throttled
timer keeps animation running there when browser animation frames are paused.
During Piper playback, a
40 ms audio-volume envelope drives the `aa` mouth shape; this is audio-reactive
animation, not phoneme-aligned viseme lip-sync. Windows SAPI fallback has no
audio envelope and therefore does not animate the mouth. Speech interruption
and playback completion close the mouth. The desktop window owns assistant
startup/shutdown and the local avatar server. Missing Chrome and process failures
are shown in the SARA card; use Dependencies, then Start, to retry.

The avatar's right-side cards show live Ollama/model availability, SARA's
activity, voice, avatar/connection status, assistant-process CPU/RAM/uptime,
and computer CPU/RAM/GPU readings. Hardware telemetry refreshes every three
seconds independently of speech synchronization. Process CPU is normalized
to total system capacity; it excludes Ollama and the browser. GPU readings
require NVIDIA's `nvidia-smi`; unavailable readings are explicitly labeled
rather than shown as zero. The viewer reports standby when the assistant
process is not running.

The browser HUD has compact, vertically stacked controls in its bottom-left
corner: **Dependencies** above **Update Available**, leaving the avatar unobstructed.
The HUD checks for updates in the background on startup using the original HUD's
GitHub release/version matching. The update button only appears when a newer
release is available and opens the official release page; it does not install automatically.
Update-check errors remain visible in the status text.
Dependencies opens a separate checklist for Chrome, Ollama, SARA/Forge models,
Python and declared packages, Piper voice files, WebView2, Node/npm, the pinned avatar
renderer, Forge 1.4.1+, and optional Pyright/Playwright and WSL/Ubuntu/Bubblewrap
tools. Select **Refresh Status**, then confirm each desired **Install** separately.
The checklist separates core components from optional installs. Chrome, Ollama,
and SARA's AI model remain available here even if declined in the installer.
Choosing not to install Chrome disables the current voice-recognition path;
local AI responses require Ollama and a model. They are optional *installation
choices*, not replacements for those features.
Dependencies are checked automatically on HUD startup. The Dependencies button
only appears when at least one component (including optional tools) is missing,
and disappears after all components are installed or bundled. Check failures
remain visible in the HUD status instead of being treated as missing or installed.
Nothing installs automatically. Installations run in a background worker;
errors and verification failures are displayed instead of assumed successful.
Windows software uses exact winget package IDs. Forge installers must be from
the official release, at least 1.4.1, and match the release's SHA-256 digest.
An older public installer is rejected even when it is labeled the latest release.
Models may take several GB. Optional WSL setup can require elevation, a restart,
and Ubuntu initialization. Source Python package changes require restarting
SARA. Source-launched Forge inherits SARA's Python environment for its Python
extras unless `FORGE_PYTHON` is explicitly set. For standalone/packaged Forge,
set `FORGE_PYTHON` to the environment shown by the dependency checker.
Packaged Python and renderer dependencies are bundled rather than
modified by pip/npm inside the executable. The Dependencies panel never downloads
a SARA application-update installer. The original Tk HUD retains its confirmed
download-and-install app update workflow.

Microphone startup uses Selenium's built-in driver manager to match the
installed Chrome version. The activity indicator shows `STARTING` while the
recognition browser initializes, and `MIC_ERROR` if startup/listening fails;
the terminal reports the underlying error.

Conversational requests such as "Sara, tell me about your basic functions"
receive a normal spoken answer. The "tell me" reminder route only applies
when the request includes a time such as `11:30 PM`.
Speech removes asterisk emphasis and bullet markers before Piper or SAPI
playback, so formatting is not read aloud. Written responses remain unchanged.

For a standalone viewer, run `py -3.12 avatar_bridge.py` and open the printed
localhost URL. Asset and connection errors appear in the viewer. This viewer
does not start the assistant; start SARA through the HUD separately.

### Build an installer
On Windows, install Inno Setup, then run:
```powershell
.\build.ps1
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" .\installer.iss
```

For an already prepared build environment, `.\build.ps1 -SkipDependencyInstall`
reuses installed dependencies instead of upgrading Python packages or reinstalling
the avatar renderer. Missing build dependencies still fail explicitly.

The installer is also built automatically by `.github/workflows/release.yml` whenever a `v*` tag is pushed.
It provisions the Microsoft Edge WebView2 Runtime if absent (an internet
connection is required). The bootstrapper's Microsoft signature is checked during
the build. Chrome remains optional and is only needed for speech recognition,
not for displaying the app. External release links open in the default browser;
the avatar and app controls remain in the native SARA window.

The build stages the Alba model/configuration and attribution notice alongside
the executable. The installer includes those files, the packaged Python runtime
and libraries, and the avatar/Three.js assets, so end users do not need Python or
Node.js to run SARA. Building requires Node/npm and internet access for uncached assets.
Release packages use empty initial conversation/input/schedule files, never the
developer's local runtime data. Existing user files are preserved by installer upgrades.

Setup offers independently selectable, initially unchecked choices for **Chrome**,
**Ollama**, and **SARA's AI model**, plus **Enable coding features** (Forge 1.4.1+
and its model). Only selected, missing components are installed. Models require
Ollama: select Ollama too if it is not already installed. Skipped software stays
available under **Dependencies / Optional installs** later. Forge Python, Node/npm,
Pyright, Playwright, and WSL/sandbox extras can also be installed there individually.
Selected downloads may take several GB, accept the listed package licenses, or
require Windows approval/restart. Setup failures are reported and logged to
`dependency-setup.log` in the install directory; SARA itself remains installed.
An incompatible public Forge installer is rejected rather than silently used.

Use **Start** and **Stop** in the SARA telemetry card to control the assistant.
The app starts it when the HUD loads, and stops it when the window closes.
Startup/exit problems appear in that card. Detailed diagnostic logs are
`desktop-runtime.log` and `assistant-runtime.log` in the app directory.
Say “Sara” before a command to address the assistant.

Sara ignores ordinary microphone transcripts while speaking and for one second afterward to avoid responding to her own voice. Wait until she finishes before replying; spoken stop commands still interrupt playback. Conversational replies are accepted without the wake word for 25 seconds after her answer finishes.

### Local AI answers with Ollama
Sara uses Ollama locally for general questions. Install Ollama from `https://ollama.com/download/windows`, then run these commands:

PowerShell:
```powershell
ollama pull llama3.2
$env:OLLAMA_MODEL = "llama3.2"
py -3.12 jarvis.py
```

Ollama runs on your computer and does not require an API key or subscription. Local commands such as weather and opening applications continue to use Sara's local handlers.

Sara uses Piper's local British English `en_GB-alba-medium` voice. The installer
includes the voice for offline use. Source runs download it on first use if
missing. If Piper cannot load the model, Windows SAPI is used as a fallback.

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

For a more involved task, Sara can hand the request to Forge, the separate local coding agent. Install Forge 1.4.1 or newer with its command-line option enabled (or set `FORGE_EXECUTABLE` to the full path of `forge.exe`), then say:

```text
Sara, use Forge to build a reading tracker
```

When Sara offers to ask Forge after an out-of-scope request, say `yes` to open Forge in ask-before-edits mode. Forge works in a private workspace under `%LOCALAPPDATA%\Sara\forge_workspaces`; the Sara-launched session has file tools confined to that workspace, while shell commands, code execution, browser/web tools, GitHub, and sub-agents are unavailable. Review and approve each edit in the Forge window. After Forge finishes, say `Sara, review Forge project`. Sara validates the files and presents them through the existing `show project proposal` / `approve project` flow. Imported apps are saved to `Documents/SaraProjects` only after that approval, and are never run automatically. To run an eligible Python CLI project, use the separate `run project <name>` / `approve run` sandbox flow above.

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

### Proactive tool offers
When Sara can't find a reliable answer, the model admits it can't help, or a spoken command doesn't match a known action, she offers to ask Forge to build a small app or helper:

```text
You: Sara, what's the tide schedule for Cape May tomorrow?
Sara: I couldn't find a reliable answer for that. Would you like me to ask Forge to build a small app or helper for this task?
You: yes
Sara: Forge is working in its own workspace...
```

A plain "yes"/"sure"/"go ahead" or "no"/"not now" answers the offer directly, without needing the wake word. Forge asks before each edit, and its Sara-launched session has no shell, code-execution, or web tools. After it finishes, say `Sara, review Forge project`; Sara validates the files and requires the normal project approval before copying them to `Documents/SaraProjects`. Creating a reusable Sara tool from that project remains a separate, reviewed approval flow.

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
