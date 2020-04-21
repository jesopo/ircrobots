from typing import List

BOLD      = "\x02"
COLOR     = "\x03"
INVERT    = "\x16"
ITALIC    = "\x1D"
UNDERLINE = "\x1F"
RESET     = "\x0F"

FORMATTERS = [
    BOLD,
    INVERT,
    ITALIC,
    UNDERLINE,
    RESET
]

def tokens(s: str) -> List[str]:
    tokens: List[str] = []

    s_copy = list(s)
    while s_copy:
        token = s_copy.pop(0)
        if token == COLOR:
            for i in range(2):
                if s_copy and s_copy[0].isdigit():
                    token += s_copy.pop(0)
            if (len(s_copy) > 1 and
                    s_copy[0] == "," and
                    s_copy[1].isdigit()):
                token += s_copy.pop(0)
                token += s_copy.pop(0)
                if s_copy and s_copy[0].isdigit():
                    token += s_copy.pop(0)

            tokens.append(token)
        elif token in FORMATTERS:
            tokens.append(token)
    return tokens

def strip(s: str):
    for token in tokens(s):
        s = s.replace(token, "", 1)
    return s
