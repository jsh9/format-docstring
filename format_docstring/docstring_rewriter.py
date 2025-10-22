from __future__ import annotations

import ast
import io
import operator
import tokenize
from typing import TYPE_CHECKING

from format_docstring.line_wrap_google import wrap_docstring_google
from format_docstring.line_wrap_numpy import (
    handle_single_line_docstring,
    wrap_docstring_numpy,
)

if TYPE_CHECKING:
    from format_docstring.line_wrap_utils import ParameterMetadata

ModuleClassOrFunc = (
    ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
)

NO_FORMAT_DOCSTRING_MARKER = 'no-format-docstring'


def _determine_newline(text: str) -> str:
    r"""
    Return the dominant newline style detected in ``text``.

    Defaults to ``\n`` when no Windows/Mac classic newlines are present.
    """
    if '\r\n' in text:
        return '\r\n'

    if '\r' in text:
        return '\r'

    return '\n'


def _has_inline_no_format_comment(source_code: str, end_pos: int) -> bool:
    """
    Return True if the closing quotes share a line with the sentinel comment.
    """
    source_len = len(source_code)
    line_end = source_code.find('\n', end_pos)
    if line_end == -1:
        line_end = source_len

    same_line_segment = source_code[end_pos:line_end].lower()
    hash_index = same_line_segment.find('#')
    if hash_index == -1:
        return False

    return NO_FORMAT_DOCSTRING_MARKER in same_line_segment[hash_index:]


def _normalize_signature_segment(segment: str | None) -> str | None:
    r"""
    Normalize signature fragments while preserving author-intended quoting.

    Parameters
    ----------
    segment : str | None
        Raw text captured from a function signature (annotation or default).

    Returns
    -------
    str | None
        The fragment with condensed whitespace. Double-quoted literals are kept
        double quoted; single-quoted literals are left untouched.

    Examples
    --------
    >>> _normalize_signature_segment('Optional["Widget"]')
    'Optional["Widget"]'
    >>> _normalize_signature_segment('Optional[\\n    "Widget"\\n]')
    'Optional["Widget"]'
    >>> _normalize_signature_segment(None) is None
    True
    """
    if segment is None:
        return None

    normalized: str = segment.strip()
    if '\n' in normalized or '\r' in normalized or '\t' in normalized:
        # `ast.unparse(ast.parse(...))` neatly flattens whitespace but it also
        # canonicalises string quotes to single quotes. We still rely on it for
        # whitespace normalization, so capture its output first.
        try:
            canonical = ast.unparse(ast.parse(normalized))
        except (SyntaxError, ValueError):
            return ' '.join(normalized.split())

        # Remember the exact string literal tokens from the original text. The
        # iterator order mirrors the unparse traversal so we can reapply them.
        original_strings: list[str] = []
        try:
            original_strings.extend(
                tok.string
                for tok in tokenize.generate_tokens(
                    io.StringIO(normalized).readline
                )
                if tok.type == tokenize.STRING
            )
        except tokenize.TokenError:
            original_strings = []

        string_iter = iter(original_strings)
        try:
            rebuilt_tokens: list[tokenize.TokenInfo] = []
            for tok in tokenize.generate_tokens(
                io.StringIO(canonical).readline
            ):
                current_tok: tokenize.TokenInfo = tok
                if tok.type == tokenize.STRING:
                    replacement = next(string_iter, None)
                    if replacement is not None:
                        try:
                            # Only swap the string token when both literals
                            # evaluate to the same value; this ensures we
                            # preserve double-quoted forward references without
                            # rewriting single-quoted strings unnecessarily.
                            if ast.literal_eval(
                                replacement
                            ) == ast.literal_eval(tok.string):
                                current_tok = tok._replace(string=replacement)
                        except Exception:  # noqa: BLE001
                            pass

                rebuilt_tokens.append(current_tok)
                if current_tok.type == tokenize.ENDMARKER:
                    break

            # Untokenize the rebuilt stream while trimming the leading/trailing
            # whitespace introduced by the tokeniser.
            normalized = tokenize.untokenize(rebuilt_tokens).strip()
        except tokenize.TokenError:
            normalized = canonical

    return normalized


def _render_signature_piece(
        node: ast.AST | None, source_code: str
) -> str | None:
    """
    Return the source representation for an annotation/default expression.
    """
    if node is None:
        return None

    text: str | None = ast.get_source_segment(source_code, node)
    if text is None:
        text = ast.unparse(node)

    return _normalize_signature_segment(text)


def _collect_param_metadata(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source_code: str,
) -> ParameterMetadata:
    """
    Build a lookup of parameter name -> (annotation, default) strings.
    """
    metadata: ParameterMetadata = {}

    def record(
            name: str,
            annotation_node: ast.AST | None,
            default_node: ast.AST | None = None,
            *,
            aliases: tuple[str, ...] = (),
    ) -> None:
        """
        Store the annotation/default text for ``name`` and any syntactic
        aliases.

        Parameters
        ----------
        name : str
            The canonical parameter identifier (without leading ``*``/``**``).
        annotation_node : ast.AST | None
            AST node representing the annotation extracted from the signature.
        default_node : ast.AST | None, default=None
            AST node representing the default value; ``None`` when absent.
        aliases : tuple[str, ...], default=()
            Additional keys (e.g. ``*args``) that should map to the same
            metadata payload.
        """
        annotation = _render_signature_piece(annotation_node, source_code)
        default = _render_signature_piece(default_node, source_code)
        metadata[name] = (annotation, default)
        for alias in aliases:
            metadata[alias] = (annotation, default)

    positional_args = list(node.args.posonlyargs) + list(node.args.args)
    positional_defaults = list(node.args.defaults)
    defaults_start = len(positional_args) - len(positional_defaults)
    for idx, arg in enumerate(positional_args):
        default_node: ast.AST | None = None
        if idx >= defaults_start:
            default_node = positional_defaults[idx - defaults_start]

        record(arg.arg, arg.annotation, default_node)

    if node.args.vararg is not None:
        vararg = node.args.vararg
        record(
            vararg.arg,
            vararg.annotation,
            aliases=(f'*{vararg.arg}',),
        )

    for kw_arg, kw_default in zip(
        node.args.kwonlyargs, node.args.kw_defaults, strict=False
    ):
        record(kw_arg.arg, kw_arg.annotation, kw_default)

    if node.args.kwarg is not None:
        kwarg = node.args.kwarg
        record(
            kwarg.arg,
            kwarg.annotation,
            aliases=(f'**{kwarg.arg}',),
        )

    return metadata


def _collect_class_metadata(
        node: ast.ClassDef,
        source_code: str,
) -> tuple[ParameterMetadata, ParameterMetadata]:
    """
    Build metadata for class docstrings using ``__init__`` and class attrs.
    """
    init_metadata: ParameterMetadata = {}
    attribute_metadata: ParameterMetadata = {}

    init_method: ast.FunctionDef | None = None
    for stmt in node.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == '__init__':
            init_method = stmt
            break

    if init_method is not None:
        init_metadata = _collect_param_metadata(init_method, source_code)
        # ``self``/``cls`` rarely appear in docstrings; drop to avoid noise.
        init_metadata.pop('self', None)
        init_metadata.pop('cls', None)

    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign):
            target = stmt.target
            if not isinstance(target, ast.Name):
                continue

            annotation = _render_signature_piece(stmt.annotation, source_code)
            default = _render_signature_piece(stmt.value, source_code)
            attribute_metadata[target.id] = (annotation, default)
            continue

        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1:
                continue

            assign_target = stmt.targets[0]
            if not isinstance(assign_target, ast.Name):
                continue

            # Record that this attribute explicitly has no annotation/default.
            attribute_metadata[assign_target.id] = ('', None)

    return init_metadata, attribute_metadata


def fix_src(
        source_code: str,
        *,
        line_length: int = 79,
        docstring_style: str = 'numpy',
        fix_rst_backticks: bool = True,
) -> str:
    """
    Return code with only docstrings updated to wrapped content.

    Parameters
    ----------
    source_code : str
        The full Python source code to process.
    line_length : int, default=79
        Target maximum line length for wrapping logic.
    docstring_style : str, default='numpy'
        The docstring style to target ('numpy' or 'google').
    fix_rst_backticks : bool, default=True
        If True, automatically fix single backticks to double backticks per rST
        syntax.

    Returns
    -------
    str
        The updated source code. Only docstring literals are changed; all other
        formatting is preserved.

    Notes
    -----
    This function avoids ``ast.unparse`` and instead replaces docstring literal
    spans directly in the original text to preserve non-docstring formatting
    and comments.
    """
    tree: ast.Module = ast.parse(source_code, type_comments=True)
    line_starts: list[int] = calc_line_starts(source_code)

    # Store (start, end, replacement text) tuples
    replacements: list[tuple[int, int, str]] = []

    # Module-level docstring
    replacement = build_replacement_docstring(
        tree,
        source_code=source_code,
        line_starts=line_starts,
        line_length=line_length,
        docstring_style=docstring_style,
        fix_rst_backticks=fix_rst_backticks,
    )
    if replacement is not None:
        replacements.append(replacement)

    # Class/function-level docstrings
    for node in ast.walk(tree):
        if isinstance(
            node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            replacement = build_replacement_docstring(
                node,
                source_code=source_code,
                line_starts=line_starts,
                line_length=line_length,
                docstring_style=docstring_style,
                fix_rst_backticks=fix_rst_backticks,
            )
            if replacement is not None:
                replacements.append(replacement)

    # Apply replacements from the end to avoid shifting offsets
    if not replacements:
        return source_code

    # Sort by starting index descending
    replacements.sort(key=operator.itemgetter(0), reverse=True)
    new_src = source_code
    for start, end, text in replacements:
        new_src = new_src[:start] + text + new_src[end:]

    return new_src


def calc_line_starts(source_code: str) -> list[int]:
    """
    Return starting offsets for each line in the source string.

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
        *,
        source_code: str,
        line_starts: list[int],
        line_length: int,
        docstring_style: str = 'numpy',
        fix_rst_backticks: bool = True,
) -> tuple[int, int, str] | None:
    """
    Compute a single docstring replacement for the given node.

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
    fix_rst_backticks : bool, default=True
        If True, automatically fix single backticks to double backticks per rST
        syntax.

    Returns
    -------
    tuple[int, int, str] | None
        A tuple ``(start, end, new_literal)`` indicating the replacement range
        and text, or ``None`` if no change is needed.
    """
    docstring_obj: ast.Expr | None = find_docstring(node)
    if docstring_obj is None:
        return None

    val: ast.Constant = docstring_obj.value  # type: ignore[assignment]
    if not hasattr(val, 'lineno') or not hasattr(val, 'end_lineno'):
        return None

    start: int = calc_abs_pos(line_starts, val.lineno, val.col_offset)
    end: int = calc_abs_pos(line_starts, val.end_lineno, val.end_col_offset)  # type: ignore[arg-type]
    original_literal = source_code[start:end]

    if _has_inline_no_format_comment(source_code, end):
        return None

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

    param_metadata: ParameterMetadata | None = None
    attribute_metadata: ParameterMetadata | None = None
    return_annotation: str | None = None
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        param_metadata = _collect_param_metadata(node, source_code)
        return_annotation = _render_signature_piece(node.returns, source_code)
    elif isinstance(node, ast.ClassDef):
        init_metadata, class_attr_metadata = _collect_class_metadata(
            node, source_code
        )
        if init_metadata:
            param_metadata = init_metadata

        if class_attr_metadata:
            attribute_metadata = class_attr_metadata

    wrapped: str = wrap_docstring(
        doc,
        line_length=line_length,
        docstring_style=docstring_style,
        leading_indent=leading_indent_,  # type: ignore[arg-type]
        fix_rst_backticks=fix_rst_backticks,
        function_param_metadata=param_metadata,
        function_return_annotation=return_annotation,
        class_attribute_metadata=attribute_metadata,
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
    """
    Return the first statement if it is a string-literal docstring.

    Parameters
    ----------
    node : ModuleClassOrFunc
        An ``ast.Module``, ``ast.ClassDef``, ``ast.FunctionDef``, or
        ``ast.AsyncFunctionDef`` node.

    Returns
    -------
    ast.Expr | None
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
    """
    Convert a (lineno, col) pair to an absolute index.

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
    """
    Rebuild a string literal preserving prefix and quote style.

    Parameters
    ----------
    original_literal : str
        The exact text of the original string literal including any prefix and
        surrounding quotes.
    content : str
        The new inner content (without surrounding quotes).

    Returns
    -------
    str | None
        A new literal string with the same prefix and quotes and the new
        content. Returns ``None`` if the original cannot be parsed.
    """
    i = 0
    n = len(original_literal)
    while i < n and original_literal[i] in 'rRuUbBfF':
        i += 1

    prefix = original_literal[:i]

    delim = ''
    if original_literal[i : i + 3] in {'"""', "'''"}:
        delim = original_literal[i : i + 3]
        i += 3
    elif i < n and original_literal[i] in {'"', "'"}:
        delim = original_literal[i]
        i += 1
    else:
        return None

    newline: str = _determine_newline(original_literal)
    if newline != '\n':
        normalized_content = content.replace('\r\n', '\n').replace('\r', '\n')
        content = newline.join(normalized_content.split('\n'))

    return f'{prefix}{delim}{content}{delim}'


def wrap_docstring(
        docstring: str,
        line_length: int = 79,
        docstring_style: str = 'numpy',
        leading_indent: int = 0,
        *,
        fix_rst_backticks: bool = True,
        function_param_metadata: ParameterMetadata | None = None,
        function_return_annotation: str | None = None,
        class_attribute_metadata: ParameterMetadata | None = None,
) -> str:
    """
    Wrap a docstring to the given line length (stub).

    Parameters
    ----------
    docstring : str
        The original docstring contents without quotes.
    line_length : int, default=79
        Target maximum line length for wrapping logic.
    docstring_style : str, default='numpy'
        The docstring style to target ('numpy' or 'google').
    leading_indent : int, default=0
        The number of indentation spaces of this docstring.
    fix_rst_backticks : bool, default=True
        If True, automatically fix single backticks to double backticks per rST
        syntax.
    function_param_metadata : ParameterMetadata | None, default=None
        The parameter metadata (a mapping from parameter names to (type hint,
        default value) tuple) of the function node.
    function_return_annotation : str | None, default=None
        The function's return annotation text (normalized), used to keep
        ``Returns``/``Yields`` signature lines synchronized.
    class_attribute_metadata : ParameterMetadata | None, default=None
        Attribute metadata for class docstrings (names mapped to annotations
        and default values) collected from class-level assignments.

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
            docstring,
            line_length=line_length,
            leading_indent=leading_indent,
            fix_rst_backticks=fix_rst_backticks,
            parameter_metadata=function_param_metadata,
            return_annotation=function_return_annotation,
            attribute_metadata=class_attribute_metadata,
        )
    # Default to NumPy-style for unknown/unspecified styles to be permissive.
    return wrap_docstring_numpy(
        docstring,
        line_length=line_length,
        leading_indent=leading_indent,
        fix_rst_backticks=fix_rst_backticks,
        parameter_metadata=function_param_metadata,
        attribute_metadata=class_attribute_metadata,
        return_annotation=function_return_annotation,
    )
