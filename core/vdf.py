"""Minimal parser for Steam text KeyValues files (libraryfolders.vdf, appmanifest_*.acf). Keys are lowercased."""
import re

TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*')

def loads(text):
    stack, key = [{}], None
    for m in TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            d = {}
            stack[-1][key] = d
            stack.append(d)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
        elif s is not None:
            s = s.replace("\\\\", "\\").replace('\\"', '"')
            if key is None:
                key = s.lower()
            else:
                stack[-1][key] = s
                key = None
    return stack[0]
