import re

APP_NAME = "SARA"
APP_VERSION = "2.0.3"
WAKE_WORD_ALIASES = (APP_NAME.lower(), "sarah")
WAKE_WORD_PATTERN = rf"^(?:okay\s+|hey\s+)?(?:{'|'.join(map(re.escape, WAKE_WORD_ALIASES))})(?=[\s,]|$)[\s,]*"
