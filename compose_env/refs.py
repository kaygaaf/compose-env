"""Find Compose variable references in strings.

Compose treats ``$$`` as a literal dollar sign. A reference counts as
defaulted when it uses ``${VAR:-default}`` or ``${VAR-default}`` (the
default may be empty). ``${VAR:?error}`` is required. ``${VAR:+alt}``
is optional.
"""

from __future__ import annotations

import re

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def iter_references(text: str):
    """Yield ``(name, has_default)`` for each Compose interpolation in ``text``."""
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "$":
            index += 1
            continue
        if index + 1 < length and text[index + 1] == "$":
            index += 2
            continue
        if index + 1 < length and text[index + 1] == "{":
            end = text.find("}", index + 2)
            if end == -1:
                index += 2
                continue
            parsed = _parse_braced(text[index + 2 : end])
            if parsed is not None:
                yield parsed
            index = end + 1
            continue
        match = _NAME.match(text, index + 1)
        if match:
            yield match.group(0), False
            index = match.end()
            continue
        index += 1


def _parse_braced(body: str) -> tuple[str, bool] | None:
    match = _NAME.match(body)
    if not match or match.start() != 0:
        return None
    name = match.group(0)
    rest = body[match.end() :]
    if rest == "":
        return name, False
    if rest.startswith(":-") or rest.startswith("-"):
        return name, True
    if rest.startswith(":+") or rest.startswith("+"):
        return name, True
    if rest.startswith(":?") or rest.startswith("?"):
        return name, False
    return None
