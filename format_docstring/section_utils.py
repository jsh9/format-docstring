from __future__ import annotations

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
    **{name: 'Args:' for name in {'arg', 'args', 'argument', 'arguments'}},
    **{name: 'Args:' for name in {'parameter', 'parameters'}},
    **{
        name: 'Keyword Args:'
        for name in {
            'keyword arg',
            'keyword args',
            'keyword argument',
            'keyword arguments',
        }
    },
    **{
        name: 'Other Args:'
        for name in {
            'other arg',
            'other args',
            'other argument',
            'other arguments',
            'other parameter',
            'other parameters',
        }
    },
    **{name: 'Returns:' for name in GOOGLE_RETURN_SECTION_NAMES},
    **{name: 'Yields:' for name in GOOGLE_YIELDS_SECTION_NAMES},
    **{name: 'Raises:' for name in GOOGLE_RAISES_SECTION_NAMES},
    **{name: 'Attributes:' for name in GOOGLE_ATTRIBUTE_SECTION_NAMES},
    **{name: 'Examples:' for name in GOOGLE_EXAMPLE_SECTION_NAMES},
    **{name: 'Notes:' for name in GOOGLE_NOTES_SECTION_NAMES},
    **{name: 'Warnings:' for name in GOOGLE_WARNINGS_SECTION_NAMES},
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
