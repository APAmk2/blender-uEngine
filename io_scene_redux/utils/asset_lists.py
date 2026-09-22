import re
from pathlib import Path


_KEY_RE = re.compile(r'^\s*\["((?:\\.|[^"\\])*)"\]\s*=')
_BARE_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_CACHE = {}


def _code(line):
    """Remove Lua comments while retaining quoted strings and braces."""
    result = []
    quoted = False
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            result.append(char)
        elif line.startswith("--", index) or line.startswith("//", index):
            break
        else:
            result.append(char)
        index += 1
    return "".join(result)


def _brace_delta(code):
    quoted = False
    escaped = False
    delta = 0
    for char in code:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def _unescape(value):
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            escaped = value[index + 1]
            result.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
            index += 2
        else:
            result.append(value[index])
            index += 1
    return "".join(result)


def _table_keys(source, table_name):
    assignment = re.compile(
        r"^\s*" + re.escape(table_name) + r"\s*=\s*(?:create_section\s*)?\{")
    keys = []
    depth = 0
    active = False
    for line in source.splitlines():
        code = _code(line)
        if not active:
            if assignment.match(code):
                active = True
                depth = _brace_delta(code)
            continue
        if depth == 1:
            match = _KEY_RE.match(code)
            if match:
                keys.append(_unescape(match.group(1)))
            else:
                match = _BARE_KEY_RE.match(code)
                if match:
                    keys.append(match.group(1))
        depth += _brace_delta(code)
        if depth <= 0:
            break
    return keys


def _read(path, tables):
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return ()
    signature = (stat.st_mtime_ns, stat.st_size, tables)
    cached = _CACHE.get(path)
    if cached and cached[0] == signature:
        return cached[1]
    try:
        source = path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return ()
    names = sorted({name for table in tables for name in _table_keys(source, table)},
                   key=str.casefold)
    result = tuple(names)
    _CACHE[path] = (signature, result)
    return result


def shader_names(content_root):
    path = Path(content_root) / "scripts" / "shaders.lua"
    return _read(path, ("render_subst_shader", "render_subst_obsolette"))


def material_names(content_root):
    path = Path(content_root) / "scripts" / "materials.lua"
    return _read(path, ("materials",))


def clear_cache():
    _CACHE.clear()
