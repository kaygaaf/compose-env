"""Find Compose variable references in strings.

Compose treats ``$$`` as a literal dollar sign. A reference counts as
defaulted when it uses ``${VAR:-default}`` or ``${VAR-default}`` (the
default may be empty). ``${VAR:?error}`` is required. ``${VAR:+alt}``
is optional.

A plain ``$VAR`` inside a default is not a separate reference. Compose
substitutes an empty string and continues. A ``${INNER:?message}``
nested in a default or alternate is required only on the branch Compose
would actually run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Guard:
    """A branch that has to match before a nested reference is live.

    ``must_be_unset`` is true for defaults and required-error text, which
    Compose only expands when the name is missing. It is false for ``:+``
    and ``+``, which only expand when the name is set.
    """

    name: str
    must_be_unset: bool


@dataclass(frozen=True)
class Reference:
    name: str
    has_default: bool
    guards: tuple[Guard, ...] = ()


def iter_references(text: str):
    """Yield ``(name, has_default)`` for interpolations that always apply."""
    for ref in walk(text):
        if ref.guards:
            continue
        yield ref.name, ref.has_default


def walk(text: str) -> list[Reference]:
    """Return every interpolation, including ones guarded by an outer branch."""
    return list(_walk(text, guards=()))


def _closing_brace(text: str, open_index: int) -> int:
    """Index of the ``}`` that closes the ``{`` at ``open_index``, or -1."""
    depth = 0
    index = open_index
    length = len(text)
    while index < length:
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _walk(text: str, guards: tuple[Guard, ...]):
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
            end = _closing_brace(text, index + 1)
            if end == -1:
                index += 2
                continue
            parsed = _parse_braced(text[index + 2 : end])
            index = end + 1
            if parsed is None:
                continue
            name, kind, operand = parsed
            yield from _emit(name, kind, operand, guards)
            continue
        match = _NAME.match(text, index + 1)
        if match:
            yield from _emit(match.group(0), "bare", "", guards)
            index = match.end()
            continue
        index += 1


def _emit(name: str, kind: str, operand: str, guards: tuple[Guard, ...]):
    if kind == "bare":
        # A bare name inside a default or error message is not required.
        # Compose substitutes an empty string and keeps going.
        if not guards:
            yield Reference(name, False)
        return
    if kind == "default":
        yield Reference(name, True, guards)
        if operand:
            yield from _walk(operand, guards + (Guard(name, True),))
        return
    if kind == "presence":
        yield Reference(name, True, guards)
        if operand:
            yield from _walk(operand, guards + (Guard(name, False),))
        return
    yield Reference(name, False, guards)
    if operand:
        yield from _walk(operand, guards + (Guard(name, True),))


def _parse_braced(body: str) -> tuple[str, str, str] | None:
    match = _NAME.match(body)
    if not match or match.start() != 0:
        return None
    name = match.group(0)
    rest = body[match.end() :]
    if rest == "":
        return name, "bare", ""
    if rest.startswith(":-"):
        return name, "default", rest[2:]
    if rest.startswith("-"):
        return name, "default", rest[1:]
    if rest.startswith(":+"):
        return name, "presence", rest[2:]
    if rest.startswith("+"):
        return name, "presence", rest[1:]
    if rest.startswith(":?"):
        return name, "required", rest[2:]
    if rest.startswith("?"):
        return name, "required", rest[1:]
    return None
