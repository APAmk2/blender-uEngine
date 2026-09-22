"""Read the SDK's data-only create_section skeleton Lua archive.

This is a parser, not a Lua interpreter. Executable Lua constructs are rejected.
"""

import base64
import re
import struct

from .common import FormatError
from .skeleton import Bone, Locator, Skeleton


TOKEN = re.compile(r'''\s+|/\*.*?\*/|--[^\n]*|"(?:\\.|[^"\\])*"|[{},=]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|[A-Za-z_][\w]*''', re.S)


def _lex(source):
    tokens = []
    pos = 0
    while pos < len(source):
        match = TOKEN.match(source, pos)
        if not match:
            raise FormatError("Unsupported Lua syntax at offset %d" % pos)
        value = match.group()
        pos = match.end()
        if value.isspace() or value.startswith("/*") or value.startswith("--"):
            continue
        tokens.append(value)
    return tokens


class Parser:
    def __init__(self, source):
        self.tokens = _lex(source)
        self.pos = 0

    def take(self, expected=None):
        if self.pos >= len(self.tokens):
            raise FormatError("Unexpected end of skeleton Lua")
        value = self.tokens[self.pos]
        self.pos += 1
        if expected is not None and value != expected:
            raise FormatError("Expected %r, got %r" % (expected, value))
        return value

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def value(self):
        token = self.take()
        if token == "create_section":
            self.take("{")
            result = {}
            ordinal = 0
            while self.peek() != "}":
                if self.peek() is None:
                    raise FormatError("Unclosed create_section")
                if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1] == "=":
                    name = self.take()
                    self.take("=")
                else:
                    name = ordinal
                    ordinal += 1
                result[name] = self.value()
                if self.peek() == ",":
                    self.take(",")
                elif self.peek() != "}":
                    raise FormatError("Expected separator in create_section")
            self.take("}")
            return result
        if token.startswith('"'):
            # Lua archive strings in the samples only use simple escapes.
            return bytes(token[1:-1], "utf-8").decode("unicode_escape")
        if token in ("true", "false"):
            return token == "true"
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", token):
            return float(token) if any(c in token for c in ".eE") else int(token)
        raise FormatError("Unsupported Lua value %r" % token)


def _float(value):
    if isinstance(value, str) and value.isdecimal():
        return struct.unpack("<f", struct.pack("<I", int(value)))[0]
    return float(value)


def _vec(section, size):
    if not isinstance(section, dict) or len(section) != size:
        raise FormatError("Expected %d-vector" % size)
    return tuple(_float(section[i]) for i in range(size))


def _records(section):
    if not isinstance(section, dict):
        return []
    return [section[key] for key in sorted(section) if isinstance(key, str) and key.startswith("rec_")]


def read_skeleton_lua(source):
    parser = Parser(source)
    parser.take("skeleton")
    parser.take("=")
    root = parser.value()
    if parser.peek() is not None:
        raise FormatError("Extra data after skeleton section")
    bones = [Bone(item["name"], item.get("parent", ""), _vec(item["q"], 4),
                  _vec(item["t"], 3), int(item.get("bp", 0)))
             for item in _records(root.get("bones"))]
    locators = [Locator(item["name"], item.get("parent", ""),
                        _vec(item["q"], 4), _vec(item["t"], 3),
                        int(bool(item.get("editor_type", False))) |
                        (2 if item.get("skip_fx", False) else 0))
                for item in _records(root.get("locators"))]
    partitions = []
    for item in _records(root.get("partitions")):
        influence = item["infl"]
        count = int(influence[0])
        if isinstance(influence.get(1), dict):
            encoded = "".join(influence[1][index] for index in sorted(influence[1]))
            try:
                values = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise FormatError("Invalid partition influence data") from exc
        else:
            try:
                values = bytes(int(influence[index + 1]) for index in range(count))
            except (KeyError, ValueError) as exc:
                raise FormatError("Invalid inline partition influence data") from exc
        if count != len(values) or count != len(bones):
            raise FormatError("Partition influence count does not match bones")
        partitions.append((item["name"], values))
    params = [(item["name"], _float(item["b"]), _float(item["e"]),
               _float(item["loop"])) for item in _records(root.get("params"))]
    return Skeleton(bones, int(root.get("crc", 0)), locators, partitions, params,
                    motions=root.get("motions", ""))
