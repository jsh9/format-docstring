from __future__ import annotations

import ast

from format_docstring.line_wrap_google import wrap_docstring_google
from format_docstring.line_wrap_numpy import (
    handle_single_line_docstring,
    wrap_docstring_numpy,
)

ModuleClassOrFunc = (
    ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
)


def fix_src(
        source_code: str,
        *,
        line_length: int = 79,
        docstring_style: str = 'numpy',
) -> str:
    """Return code with only docstrings updated to wrapped content.

    Parameters
    ----------
    source_code : str
        The full Python source code to process.
    line_length : int, default=79
        Target maximum line length for wrapping logic.

    docstring_style : str, default='numpy'
        The docstring style to target ('numpy' or 'google').

    Returns
    -------
    str
        The updated source code. Only docstring literals are changed; all
        other formatting is preserved.

    Notes
    -----
    This function avoids ``ast.unparse`` and instead replaces docstring
    literal spans directly in the original text to preserve non-docstring
    formatting and comments.

    """
    tree: ast.Module = ast.parse(source_code)
    line_starts: list[int] = calc_line_starts(source_code)

    replacements: list[tuple[int, int, str]] = []

    # Module-level docstring
    rep = build_replacement_docstring(
        tree, source_code, line_starts, line_length, docstring_style
    )
    if rep is not None:
        replacements.append(rep)

    # Class/function-level docstrings
    for node in ast.walk(tree):
        if isinstance(
            node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            rep = build_replacement_docstring(
                node, source_code, line_starts, line_length, docstring_style
            )
            if rep is not None:
                replacements.append(rep)

    # Apply replacements from the end to avoid shifting offsets
    if not replacements:
        return source_code

    replacements.sort(key=lambda x: x[0], reverse=True)
    new_src = source_code
    for start, end, text in replacements:
        new_src = new_src[:start] + text + new_src[end:]

    return new_src


def calc_line_starts(source_code: str) -> list[int]:
    """Return starting offsets for each line in the source string.

    Parameters
    ----------
    source_code : str
        The source text to analyze.

    Returns
    -------
    list[int]
        A list of absolute indices for the start of each line.

    """
    starts: list[int] = [0]
    for i, ch in enumerate(source_code):
        if ch == '\n':
            starts.append(i + 1)

    return starts


def build_replacement_docstring(
        node: ModuleClassOrFunc,
        source_code: str,
        line_starts: list[int],
        line_length: int,
        docstring_style: str = 'numpy',
) -> tuple[int, int, str] | None:
    """Compute a single docstring replacement for the given node.

    Parameters
    ----------
    node : ModuleClassOrFunc
        The AST node owning the docstring.
    source_code : str
        The original source text.
    line_starts : list[int]
        Line start offsets from :func:`_line_starts`.
    line_length : int
        Target maximum line length for wrapping logic.

    docstring_style : str, default='numpy'
        The docstring style to target ('numpy' or 'google').

    Returns
    -------
    tuple[int, int, str] or None
        A tuple ``(start, end, new_literal)`` indicating the replacement
        range and text, or ``None`` if no change is needed.

    """
    docstring_obj: ast.Expr | None = find_docstring(node)
    if docstring_obj is None:
        return None

    val: ast.Constant = docstring_obj.value  # type: ignore[assignment]
    if not hasattr(val, 'lineno') or not hasattr(val, 'end_lineno'):
        return None

    start: int = calc_abs_pos(line_starts, val.lineno, val.col_offset)
    end: int = calc_abs_pos(line_starts, val.end_lineno, val.end_col_offset)  # type: ignore[arg-type]  # noqa: LN002
    original_literal = source_code[start:end]

    doc: str | None = ast.get_docstring(node, clean=False)
    if doc is None:
        return None

    # Use the docstring literal's column offset as the indentation level for
    # formatting. This lets the wrapper ensure leading/trailing newlines plus
    # matching spaces are present so closing quotes align with the parent's
    # indentation.
    leading_indent: int = getattr(val, 'col_offset', 0)

    # Only enforce leading/trailing newline+indent for multi-line docstrings
    # or when wrapping will occur. Keep short single-line docstrings unchanged.
    leading_indent_: int | None = (
        leading_indent if ('\n' in doc or len(doc) > line_length) else None
    )

    wrapped: str = wrap_docstring(
        doc,
        line_length=line_length,
        docstring_style=docstring_style,
        leading_indent=leading_indent_,  # type: ignore[arg-type]
    )

    new_literal: str | None = rebuild_literal(original_literal, wrapped)

    new_literal = handle_single_line_docstring(
        whole_docstring_literal=new_literal,
        docstring_content=wrapped,
        docstring_starting_col=val.col_offset,
        docstring_ending_col=val.end_col_offset,  # type: ignore[arg-type]
        line_length=line_length,
    )

    if new_literal is None or new_literal == original_literal:
        return None

    return start, end, new_literal


def find_docstring(node: ModuleClassOrFunc) -> ast.Expr | None:
    """Return the first statement if it is a string-literal docstring.

    Parameters
    ----------
    node : ModuleClassOrFunc
        An ``ast.Module``, ``ast.ClassDef``, ``ast.FunctionDef``, or
        ``ast.AsyncFunctionDef`` node.

    Returns
    -------
    ast.Expr or None
        The ``ast.Expr`` node that holds the docstring literal, if present;
        otherwise ``None``.

    """
    body: list[ast.stmt] | None = getattr(node, 'body', None)
    if not body:
        return None

    first = body[0]
    if not isinstance(first, ast.Expr):
        return None

    val = first.value
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return first

    return None


def calc_abs_pos(line_starts: list[int], lineno: int, col: int) -> int:
    """Convert a (lineno, col) pair to an absolute index.

    Parameters
    ----------
    line_starts : list[int]
        Precomputed start offsets for each line, from :func:`_line_starts`.
    lineno : int
        1-based line number.
    col : int
        0-based column offset.

    Returns
    -------
    int
        The absolute character index into the source string.

    """
    return line_starts[lineno - 1] + col


def rebuild_literal(original_literal: str, content: str) -> str | None:
    """Rebuild a string literal preserving prefix and quote style.

    Parameters
    ----------
    original_literal : str
        The exact text of the original string literal including any prefix
        and surrounding quotes.
    content : str
        The new inner content (without surrounding quotes).

    Returns
    -------
    str or None
        A new literal string with the same prefix and quotes and the new
        content. Returns ``None`` if the original cannot be parsed.

    """
    i = 0
    n = len(original_literal)
    while i < n and original_literal[i] in 'rRuUbBfF':
        i += 1

    prefix = original_literal[:i]

    delim = ''
    if original_literal[i : i + 3] in ('"""', "'''"):
        delim = original_literal[i : i + 3]
        i += 3
    elif i < n and original_literal[i] in ('"', "'"):
        delim = original_literal[i]
        i += 1
    else:
        return None

    return f'{prefix}{delim}{content}{delim}'


def wrap_docstring(
        docstring: str,
        line_length: int = 79,
        docstring_style: str = 'numpy',
        leading_indent: int = 0,
) -> str:
    """Wrap a docstring to the given line length (stub).

    Parameters
    ----------
    docstring : str
        The original docstring contents without quotes.
    line_length : int, default=79
        Target maximum line length for wrapping logic.
    docstring_style : str, default="numpy"
        The docstring style to target ('numpy' or 'google').
    leading_indent : int, default=0
        The number of indentation spaces of this docstring.

    Returns
    -------
    str
        The transformed docstring contents.

    Notes
    -----
    This function dispatches to style-specific implementations:
    - 'numpy'  -> wrap_docstring_numpy
    - 'google' -> wrap_docstring_google

    """
    style = (docstring_style or '').strip().lower()
    if style == 'google':
        return wrap_docstring_google(
            docstring, line_length, leading_indent=leading_indent
        )
    # Default to NumPy-style for unknown/unspecified styles to be permissive.
    return wrap_docstring_numpy(
        docstring, line_length, leading_indent=leading_indent
    )
