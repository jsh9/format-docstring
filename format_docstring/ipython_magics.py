"""
Mask IPython-only syntax in notebook cells so that ``ast.parse`` accepts them.

Notebook cells can use IPython syntax that is not valid Python: line magics
(``%pip install numpy``), shell commands (``!ls``), help queries (``obj?``),
assignments from either (``files = !ls``), and cell magics (``%%time``). The
formatter only rewrites docstrings, so each line that uses such syntax is
replaced by a placeholder statement, the masked source is formatted, and the
original lines are then put back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Cell magics whose body is Python. Any other cell magic (``%%bash``,
# ``%%html``, ``%%writefile`` and so on) makes the whole cell non-Python.
PYTHON_CELL_MAGICS: Final[frozenset[str]] = frozenset({
    'capture',
    'prun',
    'pypy',
    'python',
    'python3',
    'time',
    'timeit',
})

# Characters that make a logical line an IPython command when they come
# first: magics (``%``), shell commands (``!``), help (``?``), and autocall
# (``/``, ``,``, ``;``). None of them can start a Python statement.
_ESCAPE_CHARS: Final[tuple[str, ...]] = ('%', '!', '?', '/', ',', ';')

_PLACEHOLDER_PREFIX: Final[str] = '__format_docstring_ipython_'


@dataclass(frozen=True)
class MaskedSource:
    """
    A cell's source with its IPython-only lines masked.

    Attributes
    ----------
    source : str
        The cell source, in which each line that uses IPython-only syntax is
        replaced by a placeholder name statement at the line's indentation. It
        has the same number of lines as the original source.
    original_lines : dict[str, str]
        Maps each placeholder name to the original line it replaces.
    """

    source: str
    original_lines: dict[str, str]


def mask_ipython_syntax(source: str) -> MaskedSource | None:
    """
    Replace the lines of ``source`` that use IPython-only syntax.

    Each masked line becomes a placeholder name (a valid expression statement),
    indented like the first line of its logical line, so the masked source
    keeps the original line structure and can still parse as the body of a
    block. Lines inside strings, such as docstrings, are never masked.

    Parameters
    ----------
    source : str
        The source of a notebook code cell.

    Returns
    -------
    MaskedSource | None
        The masked source, or None when the cell starts with a cell magic whose
        body is not Python (such as ``%%bash``).
    """
    lines: list[str] = source.split('\n')
    is_masked: list[bool] = [False] * len(lines)

    first_idx = 0
    while first_idx < len(lines) and not lines[first_idx].strip():
        first_idx += 1

    if first_idx < len(lines) and lines[first_idx].startswith('%%'):
        words = lines[first_idx][2:].split(maxsplit=1)
        if not words or words[0] not in PYTHON_CELL_MAGICS:
            return None

        # The body of a Python cell magic is Python; only mask the magic line.
        is_masked[first_idx] = True
        first_idx += 1

    for start_idx, end_idx in _find_ipython_logical_lines(lines, first_idx):
        is_masked[start_idx:end_idx] = [True] * (end_idx - start_idx)

    prefix = _PLACEHOLDER_PREFIX
    while prefix in source:
        prefix += '_'

    original_lines: dict[str, str] = {}
    masked_lines: list[str] = []
    indent = ''
    for idx, line in enumerate(lines):
        if not is_masked[idx]:
            masked_lines.append(line)
            continue

        # Continuation lines of a masked logical line take the indentation of
        # its first line, so the placeholders form a valid statement sequence.
        if idx == 0 or not is_masked[idx - 1]:
            indent = line[: len(line) - len(line.lstrip())]

        placeholder = f'{prefix}{len(original_lines)}'
        original_lines[placeholder] = line
        masked_lines.append(indent + placeholder)

    return MaskedSource(
        source='\n'.join(masked_lines),
        original_lines=original_lines,
    )


def unmask_ipython_syntax(source: str, masked: MaskedSource) -> str:
    """
    Put the original lines back in place of the placeholders.

    Parameters
    ----------
    source : str
        Source derived from ``masked.source``. Docstrings may have been
        rewritten, but placeholder lines must be unchanged.
    masked : MaskedSource
        The result of ``mask_ipython_syntax`` that ``source`` derives from.

    Returns
    -------
    str
        ``source`` with every placeholder line replaced by its original line.
    """
    if not masked.original_lines:
        return source

    lines = source.split('\n')
    for idx, line in enumerate(lines):
        original = masked.original_lines.get(line.strip())
        if original is not None:
            lines[idx] = original

    return '\n'.join(lines)


def _find_ipython_logical_lines(
        lines: list[str],
        start_idx: int,
) -> list[tuple[int, int]]:
    """
    Find the logical lines that use IPython-only syntax.

    Physical lines are grouped into logical lines the way Python's tokenizer
    groups them: a logical line continues while a bracket or a triple-quoted
    string is open, or after a trailing backslash. A logical line uses
    IPython-only syntax when it starts with an escape character (see
    ``_ESCAPE_CHARS``), or when code outside strings and comments contains
    ``?``, a ``!`` that is not part of ``!=``, or an ``=`` followed by ``%``.
    None of these is valid Python. The rest of a physical line after such
    syntax is command text, not Python, so it is not scanned for brackets or
    quotes.

    Parameters
    ----------
    lines : list[str]
        The physical lines of the cell.
    start_idx : int
        The index of the first line to scan.

    Returns
    -------
    list[tuple[int, int]]
        The ``(start, end)`` line index range of each logical line that uses
        IPython-only syntax.
    """
    ranges: list[tuple[int, int]] = []
    logical_start = start_idx
    depth = 0
    quote: str | None = None
    is_ipython = False

    for idx in range(start_idx, len(lines)):
        line = lines[idx].removesuffix('\r')
        if is_ipython or (
            idx == logical_start and line.lstrip().startswith(_ESCAPE_CHARS)
        ):
            # Command text: only a trailing backslash continues it.
            is_ipython = True
            depth = 0
            quote = None
            continues = line.endswith('\\')
        else:
            depth, quote, is_ipython, continues = _scan_python_line(
                line, depth, quote
            )

        if continues or depth > 0 or quote is not None:
            continue

        if is_ipython:
            ranges.append((logical_start, idx + 1))

        logical_start = idx + 1
        is_ipython = False

    if is_ipython:
        ranges.append((logical_start, len(lines)))

    return ranges


def _scan_python_line(
        line: str,
        depth: int,
        quote: str | None,
) -> tuple[int, str | None, bool, bool]:
    """
    Scan one physical line of Python code.

    Parameters
    ----------
    line : str
        The physical line, without its line break.
    depth : int
        The bracket depth at the start of the line.
    quote : str | None
        The quote of the string that is open at the start of the line, if any.

    Returns
    -------
    tuple[int, str | None, bool, bool]
        The bracket depth and the open string's quote at the end of the line,
        whether the line uses IPython-only syntax, and whether a trailing
        backslash continues the line. Once IPython-only syntax is found, the
        rest of the line is not scanned, and depth and quote are reset.
    """
    pos = 0
    length = len(line)
    while pos < length:
        char = line[pos]
        if quote is not None:
            if char == '\\':
                pos += 2
            elif line.startswith(quote, pos):
                pos += len(quote)
                quote = None
            else:
                pos += 1

            continue

        if char == '#':
            break

        if char in {'"', "'"}:
            quote = char * 3 if line.startswith(char * 3, pos) else char
            pos += len(quote)
            continue

        if char == '\\' and pos == length - 1:
            return depth, quote, False, True

        if _is_ipython_syntax_at(line, pos):
            return 0, None, True, line.endswith('\\')

        if char in '([{':
            depth += 1
        elif char in ')]}':
            depth = max(depth - 1, 0)

        pos += 1

    # A single-quoted string ends at the end of the line unless the line ends
    # with an escaping backslash (``pos`` then steps past the end). An
    # unterminated one is a syntax error that ``ast.parse`` reports.
    if quote is not None and len(quote) == 1 and pos <= length:
        quote = None

    return depth, quote, False, False


def _is_ipython_syntax_at(line: str, pos: int) -> bool:
    """Return True when ``line[pos]`` (outside strings) is IPython-only."""
    char = line[pos]
    if char == '?':  # help: ``obj?``, ``obj??``
        return True

    if char == '!':  # shell: ``files = !ls``; but ``!=`` is Python
        return not line.startswith('!=', pos)

    if char == '=':  # magic assignment: ``result = %timeit f()``
        return line[pos + 1 :].lstrip().startswith('%')

    return False
