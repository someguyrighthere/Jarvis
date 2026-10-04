from Automation.Automation_Brain import Auto_main_brain,clear_file
from Automation.open_App import close_App
from NetHyTechSTT.listen import listen
from TextToSpeech.Fast_DF_TTS import is_stop_command, speak, stop_speaking, set_voice_state
import threading
import time
from Data.DLG_Data import online_dlg,offline_dlg
import random
from Automation.Battery import battery_Alert
from Time_Operations.brain import input_manage,input_manage_Alam
from Brain.brain import Main_Brain, pop_capability_gap, reset_conversation
from Features.create_file import create_file
from Vision.Vbrain import *
from Vision.MVbrain import *
from Weather_Check.check_weather import get_weather_by_address
from Whatsapp_automation.wa import send_msg_wa
from TextToImage.gen_image import generate_image
from Features.mike_health import mike_health
from Features.speaker_health import speaker_health_test
from Features.br_persentage import check_br_persentage
from Features.set_br import set_brightness_windows
from Features.set_get_volume import *
from Features.check_running_app import *
from user_memory import (
    describe_preferences,
    forget_preferences,
    parse_preference_request,
    remember_instruction,
    remember_preference,
)
from assistant_improvement import save_improvement_request
from self_update import apply_pending_improvement, create_improvement_proposal
from knowledge import clear_knowledge, save_knowledge
from task_workflow import handle_task_command
from system_admin import handle_system_command
from extension_workflow import create_extension_proposal, handle_extension_command, should_propose_extension
from forge_workflow import handle_forge_command, start_forge_project
from project_workflow import handle_project_command
from tool_workflow import handle_tool_command, run_registered_tool
from version import APP_NAME, WAKE_WORD_PATTERN
import re

numbers = ["1:","2:","3:","4:","5:","6:","7:","8:","9:"]
spl_numbers = ["11:","12:"]

ran_online_dlg = random.choice(online_dlg)
ran_offline_dlg = random.choice(offline_dlg)

# After Sara speaks a conversational reply, keep listening without the wake word for a
# short window so the user can ask a natural follow-up ("what about tomorrow?") instead
# of repeating "Sara" every time.
FOLLOW_UP_WINDOW_SECONDS = 25
_conversation_deadline = 0.0


def _in_follow_up_window():
    return time.time() < _conversation_deadline


def _extend_follow_up_window():
    global _conversation_deadline
    _conversation_deadline = time.time() + FOLLOW_UP_WINDOW_SECONDS


def _end_follow_up_window():
    global _conversation_deadline
    _conversation_deadline = 0.0
    reset_conversation()


# When Sara can't answer a question or complete a task, she offers to build a
# reusable tool for it. We remember that pending offer so the very next thing the
# user says can be a plain "yes"/"no" instead of a fresh "Sara, create a tool..." command.
_pending_tool_offer = None
_AFFIRMATIVE_PATTERN = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|please do|go ahead|do it|okay|ok|sounds good|please|affirmative)\b"
)
_NEGATIVE_PATTERN = re.compile(
    r"^(?:no|nope|nah|not now|don'?t bother|negative|no thanks|no thank you)\b"
)


def _offer_tool_for(request):
    global _pending_tool_offer
    _pending_tool_offer = request


def _pop_tool_offer():
    global _pending_tool_offer
    request = _pending_tool_offer
    _pending_tool_offer = None
    return request


def check_inputs():
    last_input = ""
    while True:
        with open("input.txt","r", encoding="utf-8-sig") as file:
            input_text = file.read().lower() 
        if input_text != last_input:
            last_input = input_text
            output_text = input_text.strip()
            has_wake_word = bool(re.match(WAKE_WORD_PATTERN, output_text))
            is_follow_up = not has_wake_word and bool(output_text) and _in_follow_up_window()
            output_text = re.sub(WAKE_WORD_PATTERN, "", output_text).strip()
            if not output_text:
                continue
            if output_text and not is_stop_command(output_text):
                set_voice_state("PROCESSING")
            pending_tool_offer = _pop_tool_offer()
            if pending_tool_offer and _AFFIRMATIVE_PATTERN.match(output_text):
                speak(start_forge_project(pending_tool_offer))
                _extend_follow_up_window()
            elif pending_tool_offer and _NEGATIVE_PATTERN.match(output_text):
                speak("Understood. I will not ask Forge to build a helper for that.")
            elif is_stop_command(output_text):
                _end_follow_up_window()
                stop_speaking()
            elif (task_response := handle_task_command(output_text)) is not None:
                speak(task_response)
            elif (system_response := handle_system_command(output_text)) is not None:
                speak(system_response)
            elif (tool_response := handle_tool_command(output_text)) is not None:
                speak(tool_response)
            elif (extension_response := handle_extension_command(output_text)) is not None:
                speak(extension_response)
            elif (registered_tool_response := run_registered_tool(output_text)) is not None:
                speak(registered_tool_response)
            elif (project_response := handle_project_command(output_text)) is not None:
                speak(project_response)
            elif (forge_response := handle_forge_command(output_text)) is not None:
                speak(forge_response)
            elif output_text.startswith("tell me"):
                output_text = output_text.replace(" p.m.","PM")
                output_text = output_text.replace(" a.m.","AM")
                if "11:" in output_text or "12:" in output_text:
                    input_manage(output_text)
                    clear_file()
                else:
                    for number in numbers:
                        if number in output_text:
                           output_text = output_text.replace(number,f"0{number}")
                           input_manage(output_text)
                           clear_file()
                           
            elif output_text.startswith("set alarm"):
                output_text = output_text.replace(" p.m.","PM")
                output_text = output_text.replace(" a.m.","AM")
                if "11:" in output_text or "12:" in output_text:
                    input_manage_Alam(output_text)
                    clear_file()
                else:
                    for number in numbers:
                        if number in output_text:
                           output_text = output_text.replace(number,f"0{number}")
                           input_manage_Alam(output_text)
                           clear_file()

            elif output_text.startswith("learn this") or output_text.startswith("save this knowledge"):
                fact = re.sub(r"^(?:learn this|save this knowledge)\s*:?\s*", "", output_text).strip()
                if save_knowledge(fact):
                    speak("Saved. I will retrieve that information when it is relevant.")
                else:
                    speak("Saved nothing. The fact was missing, which is an impressive way to waste a sentence.")

            elif output_text in {"what have you learned", "show saved knowledge", "what knowledge do you have"}:
                speak("I have saved knowledge available to relevant questions. Ask me about a topic to retrieve it.")

            elif output_text in {"forget learned knowledge", "clear learned knowledge"}:
                clear_knowledge()
                speak("Cleared the saved knowledge base.")

            elif (preference_request := parse_preference_request(output_text)):
                kind, key, value = preference_request
                if kind == "instruction":
                    remember_instruction(value)
                else:
                    remember_preference(key, value)
                speak("Understood. I will remember that preference.")

            elif "what do you remember" in output_text or "what do you know about me" in output_text:
                speak(describe_preferences())

            elif output_text in {"forget everything", "forget what you remember", "clear my preferences"}:
                forget_preferences()
                speak("I cleared your saved preferences.")

            elif output_text in {"approve improvement", "apply improvement", "approve this improvement"}:
                result = apply_pending_improvement()
                speak(result["message"])

            elif output_text.startswith("improve yourself") or output_text.startswith(f"improve {APP_NAME.lower()}"):
                request = re.sub(rf"^improve(?: yourself| {APP_NAME.lower()})?\s*", "", output_text).strip()
                if not request:
                    request = f"Review {APP_NAME.title()} behavior and suggest a useful improvement."
                result = create_improvement_proposal(request)
                if not result["ok"]:
                    save_improvement_request(request)
                speak(result["message"])

            elif "weather" in output_text:
                weather_request = re.sub(
                    r"^(?:what(?:'s| is)|tell me|check)\s+(?:the\s+)?weather(?:\s+in)?\s*",
                    "",
                    output_text,
                )
                weather_request = re.sub(r"\b(today|now|right now)\b", "", weather_request).strip()
                weather_request = re.sub(r"^in\s+", "", weather_request).strip()
                speak(get_weather_by_address(weather_request))

            elif output_text.startswith("close") or output_text.startswith("shut down"):
                closed = close_App(output_text)
                target = re.sub(r"^(?:close|shut down)\s*", "", output_text).strip()
                if target and closed:
                    speak(f"Closed {target}.")
                elif target:
                    speak(f"I could not find {target} running.")
                else:
                    speak("I closed the active application.")

            elif (has_wake_word or is_follow_up) and not output_text.startswith("open") and not should_propose_extension(output_text):
                try:
                    with open('log.txt','a', encoding='utf-8') as f:
                        f.write('\n'+'You : '+ output_text)
                        response = Main_Brain(output_text)
                        f.write('\n'+f'{APP_NAME.title()} : '+ response + '\n')
                    speak(response)
                    _extend_follow_up_window()
                    gap_request = pop_capability_gap()
                    if gap_request:
                        _offer_tool_for(gap_request)
                except Exception as e:
                    print(f"Error processing {APP_NAME.title()} command: {e}")
                    speak("Sorry, I encountered an error processing your request")

            elif output_text.startswith("create"):
                if "file" in output_text:
                    create_file(output_text)

            elif "what is this" in output_text or "what can you see" in output_text:
                        image_path = "captured_image.png"
                        if capture_image_and_save(image_path):
                            encoded_image = encode_image_to_base64(image_path)
                            answer = vision_brain(encoded_image)
                            speak(answer)

            elif "what is in front of mobile camera" in output_text or "what can you see use mobile camera" in output_text:
                        image_path = "captured_image.png"
                        if capture_image_and_save(image_path):
                            encoded_image = encode_image_to_base64(image_path)
                            answer = mobile_vision_brain(encoded_image)
                            speak(answer)

            elif "check weather" in output_text:
                text = output_text.replace("check weather in","")
                ans = get_weather_by_address(text)
                speak(ans)

            elif "send message on whatsapp" in output_text:
                send_msg_wa()

            elif "generate image" in output_text:
                 text = output_text.replace("generate image","")
                 text = text.strip()
                 generate_image(text)
                 speak("image generated successfully")

            elif "check mike" in output_text or "check mike health" in output_text or "check microphone" in output_text:
                 mike_health()

            elif "check speaker health" in output_text or "check speaker" in output_text:
                 speaker_health_test()

            elif "check brightness percentage" in output_text:
                 check_br_persentage()

            elif "set brightness percentage" in output_text:
                 set = output_text.replace("set brightness percentage","")
                 set_brightness_windows(int(set))

            elif "check volume level" in output_text:
                get_volume_windows()
                 
            elif "set volume level" in output_text:
                 set = output_text.replace("set volume level","")
                 set = set.replace("%","")
                 set_volume_windows(int(set))

            elif "check running application" in output_text:
                 check_running_app()
            elif has_wake_word and should_propose_extension(output_text):
                speak(create_extension_proposal(output_text))
            else:
                handled = Auto_main_brain(output_text)
                if not handled and (has_wake_word or is_follow_up):
                    _offer_tool_for(output_text)
                    speak("I don't have a way to handle that yet. Would you like me to ask Forge to build a small app or helper?")
                    _extend_follow_up_window()

            if output_text and not is_stop_command(output_text):
                set_voice_state("IDLE")


def Jarvis():
    clear_file()
    t1 = threading.Thread(target=listen)
    t2 = threading.Thread(target=check_inputs)
    t3 = threading.Thread(target=watch_for_stop_commands, daemon=True)
    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()


def watch_for_stop_commands():
    last_input = ""
    while True:
        try:
            with open("input.txt", "r", encoding="utf-8-sig") as file:
                input_text = file.read().strip()
            if input_text and input_text != last_input and is_stop_command(input_text):
                stop_speaking()
            last_input = input_text
        except OSError:
            pass
        time.sleep(0.1)
