import re
from pathlib import Path


def get_file_extension(text):
    if "python file" in text:
        ex = ".py"
    elif "java file" in text:
        ex = ".java"
    elif "text file" in text:
        ex = ".txt"
    elif "html file" in text:
        ex = ".html"
    elif "css file" in text:
        ex = ".css"
    elif "javascript file" in text:
        ex = ".js"
    elif "json file" in text:
        ex = ".json"
    elif "xml file" in text:
        ex = ".xml"
    elif "csv file" in text:
        ex = ".csv"
    elif "markdown file" in text:
        ex = ".md"
    elif "yaml file" in text:
        ex = ".yaml"
    elif "image file" in text:
        ex = ".jpg"  # You can add more image extensions if needed
    elif "video file" in text:
        ex = ".mp4"  # You can add more video extensions if needed
    elif "audio file" in text:
        ex = ".mp3"  # You can add more audio extensions if needed
    elif "pdf file" in text:
        ex = ".pdf"
    elif "word file" in text:
        ex = ".docx"
    elif "excel file" in text:
        ex = ".xlsx"
    elif "powerpoint file" in text:
        ex = ".pptx"
    elif "zip file" in text:
        ex = ".zip"
    elif "tar file" in text:
        ex = ".tar"
    else:
        ex = ""  # Default case if no match found
    return ex

def update_text(text):
    if "python file" in text:
        text = text.replace("python file", "")
    elif "java file" in text:
        text = text.replace("java file", "")
    elif "text file" in text:
        text = text.replace("text file", "")
    elif "html file" in text:
        text = text.replace("html file", "")
    elif "css file" in text:
        text = text.replace("css file", "")
    elif "javascript file" in text:
        text = text.replace("javascript file", "")
    elif "json file" in text:
        text = text.replace("json file", "")
    elif "xml file" in text:
        text = text.replace("xml file", "")
    elif "csv file" in text:
        text = text.replace("csv file", "")
    elif "markdown file" in text:
        text = text.replace("markdown file", "")
    elif "yaml file" in text:
        text = text.replace("yaml file", "")
    elif "image file" in text:
        text = text.replace("image file", "")
    elif "video file" in text:
        text = text.replace("video file", "")
    elif "audio file" in text:
        text = text.replace("audio file", "")
    elif "pdf file" in text:
        text = text.replace("pdf file", "")
    elif "word file" in text:
        text = text.replace("word file", "")
    elif "excel file" in text:
        text = text.replace("excel file", "")
    elif "powerpoint file" in text:
        text = text.replace("powerpoint file", "")
    elif "zip file" in text:
        text = text.replace("zip file", "")
    elif "tar file" in text:
        text = text.replace("tar file", "")
    else:
        pass
    return text



def create_file(text):
    selected_ex = get_file_extension(text)
    if not selected_ex:
        return "I can create a file only when you specify its type."
    name = re.sub(r"^(?:please\s+)?create(?:\s+a)?\s+", "", text.strip(), flags=re.IGNORECASE)
    name = re.sub(
        r"^(?:python|java|text|html|css|javascript|json|xml|csv|markdown|yaml|image|video|audio|pdf|word|excel|powerpoint|zip|tar)\s+file\s+",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"^(?:named|with name)\s*:?\s*", "", name, flags=re.IGNORECASE).strip()
    if name.casefold().endswith(selected_ex):
        name = name[:-len(selected_ex)]
    if not name:
        name = "demo"
    reserved_names = {"CON", "PRN", "AUX", "NUL"}
    reserved_names.update(f"COM{i}" for i in range(1, 10))
    reserved_names.update(f"LPT{i}" for i in range(1, 10))
    if (
        len(name) > 100
        or not re.fullmatch(r"[A-Za-z0-9 _.-]+", name)
        or name in {".", ".."}
        or name.endswith((".", " "))
        or name.split(".", 1)[0].upper() in reserved_names
    ):
        return "That filename is not valid for a safe file in SARA's working folder."
    path = Path.cwd() / f"{name}{selected_ex}"
    try:
        with path.open("x", encoding="utf-8"):
            pass
    except FileExistsError:
        return f"I did not overwrite the existing file {path.name}."
    except OSError as error:
        return f"I could not create {path.name}: {error}"
    return f"Created {path.name} in SARA's working folder."
