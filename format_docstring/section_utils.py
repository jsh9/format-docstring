from __future__ import annotations

import re
from typing import Final

GOOGLE_PARAMETER_SECTION_NAMES: Final[set[str]] = {
    'arg',
    'args',
    'argument',
    'arguments',
    'keyword arg',
    'keyword args',
    'keyword argument',
    'keyword arguments',
    'other arg',
    'other args',
    'other argument',
    'other arguments',
    'other parameter',
    'other parameters',
    'parameter',
    'parameters',
}
GOOGLE_RETURN_SECTION_NAMES: Final[set[str]] = {'return', 'returns'}
GOOGLE_YIELDS_SECTION_NAMES: Final[set[str]] = {'yield', 'yields'}
GOOGLE_RAISES_SECTION_NAMES: Final[set[str]] = {'raise', 'raises'}
GOOGLE_ATTRIBUTE_SECTION_NAMES: Final[set[str]] = {
    'attribute',
    'attributes',
}
GOOGLE_EXAMPLE_SECTION_NAMES: Final[set[str]] = {'example', 'examples'}
GOOGLE_NOTES_SECTION_NAMES: Final[set[str]] = {'note', 'notes'}
GOOGLE_WARNINGS_SECTION_NAMES: Final[set[str]] = {'warning', 'warnings'}

GOOGLE_SECTION_NAMES: Final[set[str]] = (
    GOOGLE_PARAMETER_SECTION_NAMES
    | GOOGLE_RETURN_SECTION_NAMES
    | GOOGLE_YIELDS_SECTION_NAMES
    | GOOGLE_RAISES_SECTION_NAMES
    | GOOGLE_ATTRIBUTE_SECTION_NAMES
    | GOOGLE_EXAMPLE_SECTION_NAMES
    | GOOGLE_NOTES_SECTION_NAMES
    | GOOGLE_WARNINGS_SECTION_NAMES
)
GOOGLE_SIGNATURE_SECTION_NAMES: Final[set[str]] = (
    GOOGLE_PARAMETER_SECTION_NAMES
    | GOOGLE_RETURN_SECTION_NAMES
    | GOOGLE_YIELDS_SECTION_NAMES
    | GOOGLE_RAISES_SECTION_NAMES
    | GOOGLE_ATTRIBUTE_SECTION_NAMES
)

_GOOGLE_SECTION_CANONICAL_BY_NAME: Final[dict[str, str]] = {
    **dict.fromkeys({'arg', 'args', 'argument', 'arguments'}, 'Args:'),
    **dict.fromkeys({'parameter', 'parameters'}, 'Args:'),
    **dict.fromkeys({'keyword arg', 'keyword args', 'keyword argument', 'keyword arguments'}, 'Keyword Args:'),
    **dict.fromkeys({'other arg', 'other args', 'other argument', 'other arguments', 'other parameter', 'other parameters'}, 'Other Args:'),
    **dict.fromkeys(GOOGLE_RETURN_SECTION_NAMES, 'Returns:'),
    **dict.fromkeys(GOOGLE_YIELDS_SECTION_NAMES, 'Yields:'),
    **dict.fromkeys(GOOGLE_RAISES_SECTION_NAMES, 'Raises:'),
    **dict.fromkeys(GOOGLE_ATTRIBUTE_SECTION_NAMES, 'Attributes:'),
    **dict.fromkeys(GOOGLE_EXAMPLE_SECTION_NAMES, 'Examples:'),
    **dict.fromkeys(GOOGLE_NOTES_SECTION_NAMES, 'Notes:'),
    **dict.fromkeys(GOOGLE_WARNINGS_SECTION_NAMES, 'Warnings:'),
}


def normalize_docstring_section_name(line: str) -> str:
    """Return a lowercase section name without a trailing colon."""
    return line.strip().rstrip(':').lower()


def is_known_docstring_section_name(line: str) -> bool:
    """Return True when ``line`` names a known docstring section."""
    return normalize_docstring_section_name(line) in GOOGLE_SECTION_NAMES


def is_google_section_header(line: str) -> bool:
    """Return True when ``line`` is a known Google-style section header."""
    stripped = line.strip()
    return (
        stripped.endswith(':')
        and not stripped.endswith('::')
        and normalize_docstring_section_name(stripped) in GOOGLE_SECTION_NAMES
    )


def is_google_unknown_section_header(line: str) -> bool:
    """
    Return True when ``line`` is a bare custom Google section header.

    Custom headers are not canonicalized, but they still delimit sections. The
    wrappers use this to stop parsing a previous block without treating prose
    labels or literal-block ``::`` markers as section starts.
    """
    stripped = line.strip()
    if is_google_section_header(stripped):
        return False

    if not stripped.endswith(':') or stripped.endswith('::'):
        return False

    title = stripped[:-1].strip()
    return bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]*', title))


def canonical_google_section_header(line: str) -> str | None:
    """Return the canonical Google header for ``line``, if known."""
    if not is_google_section_header(line):
        return None

    return _GOOGLE_SECTION_CANONICAL_BY_NAME[
        normalize_docstring_section_name(line)
    ]


def is_google_signature_section_header(line: str) -> bool:
    """Return True when ``line`` names a Google signature section."""
    return (
        is_google_section_header(line)
        and normalize_docstring_section_name(line)
        in GOOGLE_SIGNATURE_SECTION_NAMES
    )


def is_google_parameter_section_header(line: str) -> bool:
    """Return True when ``line`` names a Google parameter section."""
    return (
        is_google_section_header(line)
        and normalize_docstring_section_name(line)
        in GOOGLE_PARAMETER_SECTION_NAMES
    )


def is_google_returns_or_yields_section_header(line: str) -> bool:
    """Return True when ``line`` names a Google return or yield section."""
    return (
        is_google_section_header(line)
        and normalize_docstring_section_name(line)
        in GOOGLE_RETURN_SECTION_NAMES | GOOGLE_YIELDS_SECTION_NAMES
    )


def is_google_yields_section_header(line: str) -> bool:
    """Return True when ``line`` names a Google yield section."""
    return (
        is_google_section_header(line)
        and normalize_docstring_section_name(line)
        in GOOGLE_YIELDS_SECTION_NAMES
    )


def is_google_attribute_section_header(line: str) -> bool:
    """Return True when ``line`` names a Google attribute section."""
    return (
        is_google_section_header(line)
        and normalize_docstring_section_name(line)
        in GOOGLE_ATTRIBUTE_SECTION_NAMES
    )
