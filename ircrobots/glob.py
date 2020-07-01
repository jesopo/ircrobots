
def collapse(pattern: str) -> str:
    out = ""
    i = 0
    while i < len(pattern):
        seen_ast = False
        while pattern[i:] and pattern[i] in ["*", "?"]:
            if pattern[i] == "?":
                out += "?"
            elif pattern[i] == "*":
                seen_ast = True
            i += 1
        if seen_ast:
            out += "*"

        if pattern[i:]:
            out += pattern[i]
            i   += 1
    return out

def _match(pattern: str, s: str):
    i, j = 0, 0

    i_backup = -1
    j_backup = -1
    while j < len(s):
        p = (pattern[i:] or [None])[0]

        if p == "*":
            i += 1
            i_backup = i
            j_backup = j

        elif p in ["?", s[j]]:
            i += 1
            j += 1

        else:
            if i_backup == -1:
                return False
            else:
                j_backup += 1
                j = j_backup
                i = i_backup

    return i == len(pattern)

class Glob(object):
    def __init__(self, pattern: str):
        self._pattern = pattern
    def match(self, s: str) -> bool:
        return _match(self._pattern, s)
def compile(pattern: str) -> Glob:
    return Glob(collapse(pattern))
