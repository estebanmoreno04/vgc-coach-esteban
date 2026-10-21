"""Parse JavaScript object/array literals (data, not code) into Python values.

VGC History publishes its data as a script (``window.VH = ...``) whose
constants are plain literals with unquoted keys. This module reads those
literals without executing anything: only strings, numbers, booleans, null,
arrays and objects are accepted. Anything else raises ``ValueError``.
"""

from __future__ import annotations

import json
import re
from typing import Any


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+|//[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<number>-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<ident>[A-Za-z_$][\w$]*)
  | (?P<punct>[{}\[\]:,])
    """,
    re.VERBOSE | re.DOTALL,
)
_LITERALS = {"true": True, "false": False, "null": None}


def extract_constant(source: str, name: str) -> Any:
    """Parse the literal assigned by ``const <name> = ...`` in ``source``."""
    match = re.search(rf"\b(?:const|let|var)\s+{re.escape(name)}\s*=\s*", source)
    if not match:
        raise ValueError(f"constant {name!r} not found")
    value, _ = parse_literal(source, match.end())
    return value


def parse_literal(source: str, start: int = 0) -> tuple[Any, int]:
    """Parse one literal starting at ``start``; return (value, end offset)."""
    tokens = _Tokens(source, start)
    value = _parse_value(tokens)
    return value, tokens.position


class _Tokens:
    def __init__(self, source: str, position: int) -> None:
        self.source = source
        self.position = position
        self._peeked: tuple[str, str, int] | None = None

    def peek(self) -> tuple[str, str]:
        if self._peeked is None:
            self._peeked = self._next_raw()
        kind, text, _ = self._peeked
        return kind, text

    def take(self) -> tuple[str, str]:
        kind, text = self.peek()
        assert self._peeked is not None
        self.position = self._peeked[2]
        self._peeked = None
        return kind, text

    def _next_raw(self) -> tuple[str, str, int]:
        position = self.position
        while True:
            match = _TOKEN_RE.match(self.source, position)
            if not match:
                if position >= len(self.source):
                    return "eof", "", position
                raise ValueError(f"unexpected character at offset {position}")
            position = match.end()
            if match.lastgroup != "ws":
                return match.lastgroup, match.group(), position


def _parse_value(tokens: _Tokens) -> Any:
    kind, text = tokens.take()
    if kind == "string":
        return _decode_string(text)
    if kind == "number":
        number = float(text)
        return int(number) if number.is_integer() and re.fullmatch(r"-?\d+", text) else number
    if kind == "ident":
        if text in _LITERALS:
            return _LITERALS[text]
        raise ValueError(f"identifier {text!r} is not a literal value")
    if text == "[":
        return _parse_array(tokens)
    if text == "{":
        return _parse_object(tokens)
    raise ValueError(f"unexpected token {text!r}")


def _parse_array(tokens: _Tokens) -> list[Any]:
    items: list[Any] = []
    while True:
        if tokens.peek()[1] == "]":
            tokens.take()
            return items
        items.append(_parse_value(tokens))
        _, separator = tokens.take()
        if separator == "]":
            return items
        if separator != ",":
            raise ValueError(f"expected ',' or ']' but found {separator!r}")


def _parse_object(tokens: _Tokens) -> dict[str, Any]:
    result: dict[str, Any] = {}
    while True:
        kind, text = tokens.take()
        if text == "}":
            return result
        if kind == "string":
            key = _decode_string(text)
        elif kind in {"ident", "number"}:
            key = text
        else:
            raise ValueError(f"unexpected object key {text!r}")
        if tokens.take()[1] != ":":
            raise ValueError(f"expected ':' after key {key!r}")
        result[key] = _parse_value(tokens)
        _, separator = tokens.take()
        if separator == "}":
            return result
        if separator != ",":
            raise ValueError(f"expected ',' or '}}' but found {separator!r}")


def _decode_string(text: str) -> str:
    if text.startswith("'"):
        inner = text[1:-1].replace('\\"', '"').replace('"', '\\"').replace("\\'", "'")
        text = f'"{inner}"'
    return json.loads(text)
