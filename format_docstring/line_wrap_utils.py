from __future__ import annotations

import re
import textwrap
from collections.abc import Callable
from typing import Literal

from format_docstring.section_utils import (
    is_google_section_header,
    is_google_unknown_section_header,
    is_known_docstring_section_name,
)

# Regex pattern to split text into paragraphs (multiple consecutive newlines)
_PARAGRAPH_SPLIT_PATTERN = re.compile(r'\n\s*\n')
_SECTION_UNDERLINE_MIN_LENGTH = 2
# A bullet (``-``, ``*``, ``+``) or enumerator (``1.``, ``1)``, ``(1)``) list
# marker and the spaces after it. The only definition of a list marker; see
# ``_match_list_item_marker``.
_LIST_ITEM_MARKER_PATTERN = re.compile(
    r'(?:(?P<bullet>[-*+])'
    r'|\d+(?P<enum_suffix>[.)])'
    r'|(?P<enum_parens>\(\d+\)))'
    r' +'
)
# Directives whose body is code: the rST code directives, IPython's
# ``ipython`` directive, the ``sphinx.ext.doctest`` directives, and
# sphinx-prompt's ``prompt``. These usually take an argument
# (``.. ipython:: python``, ``.. doctest:: group``), so their line does not
# end with ``::`` and the literal block rule misses them.
_RST_CODE_DIRECTIVE_NAMES = (
    'code-block',
    'sourcecode',
    'code',
    'ipython',
    'doctest',
    'testcode',
    'testoutput',
    'testsetup',
    'testcleanup',
    'prompt',
)
# As in docutils, one space may come before the ``::``.
_RST_CODE_DIRECTIVE_PATTERN = re.compile(
    r'^\s*\.\.\s+(?:'
    + '|'.join(_RST_CODE_DIRECTIVE_NAMES)
    + r') ?::(?:\s+.*)?$',
    re.IGNORECASE,
)

_UnwrappableKind = Literal[
    'code_directive',
    'literal_block',
    'table',
    'list',
    'doctest',
    'code_fence',
]
# The kinds ``_split_out_literal_blocks`` protects before wrapping. Code
# directives and literal blocks can continue past a blank line, which NumPy
# keeps in a separate ``temp_out`` element.
_RST_BLOCK_KINDS: frozenset[_UnwrappableKind] = frozenset({
    'code_directive',
    'literal_block',
})
# Used only after a wrapper has entered Examples. Keep the match conservative
# so prose examples still flow through the normal paragraph wrapper.
_PYTHON_EXAMPLE_START_PATTERN = re.compile(
    r'^(?:'
    r'(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]+\])*)'
    r'(?:\s*,\s*[A-Za-z_]\w*)*\s*(?::\s*[^=]+)?'
    r'\s*(?:[-+*/%@&|^]?=|:=)(?!=)|'
    r'(?:await\s+)?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*\(|'
    r'from\s+\S+\s+import\s+|'
    r'import\s+|'
    r'def\s+\w+|'
    r'class\s+\w+|'
    r'if\s+.+:|'
    r'elif\s+.+:|'
    r'else:|'
    r'for\s+.+:|'
    r'while\s+.+:|'
    r'with\s+.+:|'
    r'try:|'
    r'except\b.*:|'
    r'finally:|'
    r'match\s+.+:|'
    r'case\s+.+:|'
    r'return\b|'
    r'yield\b|'
    r'raise\b|'
    r'assert\b|'
    r'pass\b|'
    r'break\b|'
    r'continue\b|'
    r'@[A-Za-z_]'
    r')'
)

# Matches rST inline literals. Like docutils, the opening backtick pair must
# be followed by non-whitespace and the closing pair preceded by it, so a
# space-padded pair inside a literal does not end it early.
_INLINE_LITERAL_PATTERN = re.compile(r'``(?=\S).+?(?<=\S)``')
# Whitespace inside a literal is masked with a code point from Supplementary
# Private Use Area-A that encodes the original character (space, tab, NBSP,
# ...), so the round trip is exact for every kind of whitespace. Each
# placeholder is one code point and is not whitespace for ``textwrap`` or
# ``str.split``, so masked literals wrap as single words without changing line
# widths. Every ``str.isspace`` character is below U+3000.
_INLINE_LITERAL_PLACEHOLDER_BASE = 0xF0000
_INLINE_LITERAL_PLACEHOLDER_PATTERN = re.compile(r'[\U000f0000-\U000f3000]')

ParameterMetadata = dict[str, tuple[str | None, str | None]]
_SectionBoundaryPredicate = Callable[[list[str], int], bool]

_RETURN_PROSE_LABELS = {
    'output',
    'outputs',
    'result',
    'results',
    'return value',
    'return values',
    'value',
    'values',
}


def validate_include_arg_defaults(
        *,
        include_arg_types: bool,
        include_arg_defaults: bool,
) -> None:
    """
    Validate argument defaults are not emitted without argument types.

    Defaults share the signature metadata slot with types; rejecting this
    combination prevents type-less signatures that contain only ``default=...``
    metadata.
    """
    if include_arg_types or not include_arg_defaults:
        return

    msg = (
        'include_arg_defaults=True requires include_arg_types=True. Set '
        'include_arg_defaults=False when omitting argument types.'
    )
    raise ValueError(msg)


def add_leading_indent(docstring: str, leading_indent: int | None) -> str:
    r"""
    Ensure a docstring starts with a newline + indent when requested.

    If ``leading_indent`` is a positive integer and the docstring body doesn't
    already begin with ``"\n" + ' ' * leading_indent``, prepend it. Otherwise,
    return the docstring unchanged.
    """
    if leading_indent is not None:
        needed_prefix: str = '\n' + (' ' * leading_indent)
        if not docstring.startswith(needed_prefix):
            return needed_prefix + docstring

    return docstring


def _is_labeled_return_prose(label: str, description: str) -> bool:
    """
    Return True for labeled prose such as ``Result: ready.``.

    These labels are common prose prefixes in returns/yields sections. The
    allow-list keeps annotation sync from mistaking them for names or types and
    dropping the label from the description.
    """
    label_normalized = ' '.join(label.strip().lower().split())
    description_stripped = description.strip()
    return (
        label_normalized in _RETURN_PROSE_LABELS
        and bool(description_stripped)
        and (
            any(char.isspace() for char in description_stripped)
            or description_stripped.endswith(('.', '!', '?'))
        )
    )


def finalize_lines(out_lines: list[str], leading_indent: int | None) -> str:
    """
    Trim trailing spaces, normalize blank lines, and append closing indent.

    - Trims trailing spaces from each line.
    - Converts lines that are only whitespace to truly empty lines.
    - Removes a trailing newline if present.
    - If ``leading_indent`` is provided and positive, ensures the result ends
      with a newline plus that many spaces (so closing quotes align).
    """
    out = [line.rstrip(' ') for line in out_lines]
    result = '\n'.join(
        '' if (line.strip() == '') else line for line in out
    ).rstrip('\n')

    if leading_indent is not None:
        suffix = '\n' + (' ' * leading_indent)
        if not result.endswith(suffix):
            result += suffix

    return result


def collect_to_temp_output(temp_out: list[str | list[str]], line: str) -> None:
    """
    Collect ``line`` into temporary output.

    If the last element of ``temp_out`` is ``list[str]``, append ``line`` into
    it. If the last element of ``temp_out`` is ``str``, add new (empty) list as
    the last element and use ``line`` as the first element of this new (empty)
    list.
    """
    if len(temp_out) == 0:
        temp_out.append(line)
        return

    if isinstance(temp_out[-1], list):
        temp_out[-1].append(line)
    else:
        temp_out.append([line])


def process_temp_output(
        temp_out: list[str | list[str]],
        width: int,
) -> list[str]:
    """
    Wrap the ``list[str]`` elements in ``temp_out``.

    ``str`` elements are emitted unchanged. Lines of rST literal blocks
    (introduced by a paragraph ending with ``::``) and of code directives (such
    as ``.. code-block:: python``) are emitted unchanged too, even when they
    sit in ``list[str]`` elements; see ``_split_out_literal_blocks``.
    """
    out: list[str] = []

    for element in _split_out_literal_blocks(temp_out):
        if isinstance(element, str):
            out.append(element)
        else:
            out.extend(wrap_preserving_indent(element, width))

    return out


def _split_out_literal_blocks(
        temp_out: list[str | list[str]],
) -> list[str | list[str]]:
    """
    Move literal block and code directive lines out of ``list[str]`` elements.

    The spans are found on the flattened ``temp_out``, not one element at a
    time, because wrappers emit blank lines as separate ``str`` elements. A
    block with blank lines in it is therefore spread across several elements,
    and only the flattened lines show where it ends. Each protected line
    becomes a ``str`` element so it is emitted unchanged. The unprotected lines
    of a ``list[str]`` element stay grouped, so a block that starts or ends in
    the middle of an element splits it into separately wrapped parts.

    Spans start only at lines of ``list[str]`` elements and at blank lines. A
    non-blank ``str`` element was already classified by the caller (fenced
    code, doctest lines, section headings, signature lines), so a span may
    cover it but never starts at it. Otherwise doctest output such as ``~~~~~``
    would read as an unclosed fence that hides every later block. Blank lines
    must still start spans, because a literal block can start at the blank line
    after ``::`` and cover classified lines.
    """
    lines: list[str] = []
    can_start_span: list[bool] = []
    for element in temp_out:
        if isinstance(element, str):
            lines.append(element)
            can_start_span.append(not element.strip())
        elif isinstance(element, list):
            lines.extend(element)
            can_start_span.extend([True] * len(element))
        else:
            raise TypeError(
                f'`element` has unexpected type: {type(element)}.'
                ' Please contact the author.'
            )

    is_protected: list[bool] = [False] * len(lines)
    idx = 0
    while idx < len(lines):
        if not can_start_span[idx]:
            idx += 1
            continue

        kind, end_idx = _find_unwrappable_span(lines, idx, style='numpy')
        if kind is None:
            idx += 1
            continue

        # Other spans (tables, lists, fences) are left to
        # ``segment_lines_by_wrappability`` but skipped whole here. A row or
        # item line ending with ``::`` would otherwise start a block that
        # splits the element, so that neither part is recognized as a table or
        # list, and both are wrapped.
        if kind in _RST_BLOCK_KINDS:
            is_protected[idx:end_idx] = [True] * (end_idx - idx)

        idx = end_idx

    result: list[str | list[str]] = []
    offset = 0
    for element in temp_out:
        if isinstance(element, str):
            result.append(element)
            offset += 1
            continue

        # Split the element at its protected lines: each protected line
        # becomes a ``str``, and each run of other lines stays a ``list[str]``.
        element_protected = is_protected[offset : offset + len(element)]
        run: list[str] = []
        for line, protected in zip(element, element_protected, strict=True):
            if not protected:
                run.append(line)
                continue

            if run:
                result.append(run)
                run = []

            result.append(line)

        if run:
            result.append(run)

        offset += len(element)

    return result


def wrap_preserving_indent(lines: list[str], width: int) -> list[str]:
    """
    Wrap lines while preserving structure of tables, lists, and indentation.

    Uses segmentation to identify rST tables and bulleted lists which shouldn't
    be wrapped, and only wraps the regular text content while preserving
    indentation and paragraph structure.

    Parameters
    ----------
    lines : list[str]
        The list of lines to process.
    width : int
        The target line width for wrapping.

    Returns
    -------
    list[str]
        The processed lines with wrappable content wrapped and non-wrappable
        content (tables, lists) preserved.
    """
    if not lines:
        return []

    # Segment lines into wrappable and non-wrappable chunks
    segments = segment_lines_by_wrappability(lines)

    result: list[str] = []

    for segment_lines, is_wrappable in segments:
        if not is_wrappable:
            # Don't wrap tables and lists - preserve them exactly
            result.extend(segment_lines)
        else:
            # Wrap regular text content
            wrapped_segment = _wrap_text_segment(segment_lines, width)
            result.extend(wrapped_segment)

    return result


def _wrap_text_segment(lines: list[str], width: int) -> list[str]:
    """
    Wrap a segment of regular text lines while preserving indentation and
    paragraphs.

    This is the core wrapping logic extracted from the original
    wrap_preserving_indent.
    """
    if not lines:
        return []

    # Convert lines back to text for processing
    text = '\n'.join(lines)

    # Get original indentation from the first non-empty line
    first_line = ''
    for line in lines:
        if line.strip():
            first_line = line
            break

    if not first_line:
        return lines  # All empty lines

    stripped_first: str = first_line.lstrip(' ')
    indent_len: int = len(first_line) - len(stripped_first)
    indent: str = ' ' * indent_len

    # First merge lines within paragraphs while preserving paragraph breaks
    merged_text: str = merge_lines_and_strip(text)

    # Split into paragraphs and process each one
    paragraphs: list[str] = merged_text.split('\n\n')

    avail: int = max(1, width - indent_len)
    tw: textwrap.TextWrapper = textwrap.TextWrapper(
        width=avail,
        break_long_words=False,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
    )

    out: list[list[str]] = []
    for paragraph in paragraphs:
        if paragraph.strip():  # Only process non-empty paragraphs
            stripped_para: str = paragraph.lstrip(' ')
            wrapped_lines: list[str] = wrap_keeping_inline_literals(
                stripped_para, tw.wrap
            )
            indented_lines: list[str] = (
                [indent + line for line in wrapped_lines]
                if wrapped_lines
                else [indent + paragraph]
            )
            out.append(indented_lines)
        else:
            # Empty paragraph means extra line break - preserve it
            out.append([''])

        out.append([''])  # Add empty line separator

    # Flatten and remove the trailing empty line
    result: list[str] = [item for sublist in out for item in sublist]
    if result and result[-1] == '':
        result.pop()

    result_: list[str] = result or lines

    return _add_back_leading_or_trailing_newline(
        original_lines=lines,
        wrapped_lines=result_,
    )


def find_inline_literal_spans(text: str) -> list[tuple[int, int]]:
    """Return the ``(start, end)`` index pairs of rST inline literals."""
    if '``' not in text:
        return []

    return [match.span() for match in _INLINE_LITERAL_PATTERN.finditer(text)]


def is_inside_inline_literal(text: str, index: int) -> bool:
    """Return True if ``text[index]`` lies inside an rST inline literal."""
    return any(
        start <= index < end for start, end in find_inline_literal_spans(text)
    )


def protect_inline_literal_spaces(text: str) -> str:
    """
    Replace whitespace inside rST inline literals with non-space placeholders.

    Line wrappers break at whitespace and drop it at the break, which would
    split a literal across lines and lose runs of spaces inside it (e.g.
    ``'  '``). ``textwrap`` also expands tabs and ``str.split`` collapses every
    kind of Unicode whitespace, so each whitespace character is masked with a
    placeholder that encodes it. Masking makes each literal one unbreakable
    word; ``restore_inline_literal_spaces`` undoes it exactly.
    """
    if '``' not in text:
        return text

    return _INLINE_LITERAL_PATTERN.sub(
        lambda match: ''.join(
            chr(_INLINE_LITERAL_PLACEHOLDER_BASE + ord(char))
            if char.isspace()
            else char
            for char in match.group(0)
        ),
        text,
    )


def restore_inline_literal_spaces(text: str) -> str:
    """Undo ``protect_inline_literal_spaces``."""
    return _INLINE_LITERAL_PLACEHOLDER_PATTERN.sub(
        lambda match: chr(
            ord(match.group(0)) - _INLINE_LITERAL_PLACEHOLDER_BASE
        ),
        text,
    )


def wrap_keeping_inline_literals(
        text: str,
        wrap: Callable[[str], list[str]],
) -> list[str]:
    """
    Wrap ``text`` with ``wrap`` without breaking inside inline literals.

    Whitespace inside literals is masked before wrapping and restored in the
    wrapped lines. The round trip is exact, so a misdetected literal can only
    move a line break, never change the text. Text that already contains a
    placeholder code point (possible via an escape sequence, because docstrings
    are wrapped after evaluation) is wrapped unmasked so it is never corrupted.
    """
    if _INLINE_LITERAL_PLACEHOLDER_PATTERN.search(text):
        return wrap(text)

    return [
        restore_inline_literal_spaces(line)
        for line in wrap(protect_inline_literal_spaces(text))
    ]


def _add_back_leading_or_trailing_newline(
        original_lines: list[str],
        wrapped_lines: list[str],
) -> list[str]:
    if len(original_lines) == 0 or len(wrapped_lines) == 0:
        return wrapped_lines

    new_result: list[str] = []
    if original_lines[0] == '':
        new_result = ['', *wrapped_lines]
    else:
        new_result = wrapped_lines

    if original_lines[-1] == '':
        return [*new_result, '']

    return new_result


def merge_lines_and_strip(text: str) -> str:
    r"""
    Merge lines within paragraphs, preserving paragraph breaks.

    Takes a multi-line string where each line may have leading or trailing
    whitespace. Lines within the same paragraph (separated by single newlines)
    are merged with spaces, while paragraph breaks (multiple consecutive
    newlines) are preserved as double newlines.

    Parameters
    ----------
    text : str
        The input text containing multiple lines with potential leading or
        trailing whitespace and paragraph breaks.

    Returns
    -------
    str
        The processed text with lines merged within paragraphs and paragraph
        breaks preserved as double newlines.

    Examples
    --------
    >>> text = '    something like this\\n    and this is the 2nd\\n    line,'
    >>> merge_lines_and_strip(text)
    'something like this and this is the 2nd line,'

    >>> text = 'first para\\nstill first\\n\\nsecond para\\nstill second'
    >>> merge_lines_and_strip(text)
    'first para still first\\n\\nsecond para still second'
    """
    # Split on multiple newlines to separate paragraphs
    paragraphs = _PARAGRAPH_SPLIT_PATTERN.split(text)

    processed_paragraphs = []
    for paragraph in paragraphs:
        # For each paragraph, split into lines, strip whitespace, and join with
        # spaces
        lines = paragraph.split('\n')
        stripped_lines = [line.strip() for line in lines if line.strip()]
        if stripped_lines:  # Only add non-empty paragraphs
            processed_paragraphs.append(' '.join(stripped_lines))

    return '\n\n'.join(processed_paragraphs)


def fix_typos_in_section_headings(lines: list[str]) -> list[str]:
    """Fix typos such as 'Return' in section headings."""
    min_num_lines_to_form_a_section_header: int = 2
    if len(lines) < min_num_lines_to_form_a_section_header:
        return lines

    # Define typo corrections (case-insensitive keys, proper case values)
    typo_corrections = {
        'return': 'Returns',
        'return:': 'Returns',
        'returns:': 'Returns',
        'parameter': 'Parameters',
        'parameter:': 'Parameters',
        'parameters:': 'Parameters',
        'other parameter': 'Other Parameters',
        'other parameter:': 'Other Parameters',
        'other parameters:': 'Other Parameters',
        'attribute': 'Attributes',
        'attribute:': 'Attributes',
        'attributes:': 'Attributes',
        'yield': 'Yields',
        'yield:': 'Yields',
        'yields:': 'Yields',
        'raise': 'Raises',
        'raise:': 'Raises',
        'raises:': 'Raises',
        'note': 'Notes',
        'note:': 'Notes',
        'notes:': 'Notes',
        'example': 'Examples',
        'example:': 'Examples',
        'examples:': 'Examples',
        # Also handle correctly spelled but wrong case
        'returns': 'Returns',
        'parameters': 'Parameters',
        'other parameters': 'Other Parameters',
        'attributes': 'Attributes',
        'yields': 'Yields',
        'raises': 'Raises',
        'notes': 'Notes',
        'examples': 'Examples',
    }

    result = lines.copy()

    for i in range(len(lines) - 1):
        current_line = lines[i].strip()
        next_line = lines[i + 1].strip()

        # Check if next line is dashes (at least 2 dashes, only dashes and
        # whitespace)
        min_hyphens_in_section_header: int = 2
        if len(next_line) >= min_hyphens_in_section_header and all(
            c == '-' for c in next_line
        ):
            # Current line is a section heading, check for typos
            # (which are case-insensitive)
            current_line_lower = current_line.lower()
            if current_line_lower in typo_corrections:
                corrected_heading = typo_corrections[current_line_lower]
                # Preserve original indentation
                original_indent = lines[i][
                    : len(lines[i]) - len(lines[i].lstrip())
                ]
                result[i] = original_indent + corrected_heading
                # Fix dashes to match corrected heading length
                dashes_indent = lines[i + 1][
                    : len(lines[i + 1]) - len(lines[i + 1].lstrip())
                ]
                result[i + 1] = dashes_indent + '-' * len(corrected_heading)

    return result


def segment_lines_by_wrappability(
        lines: list[str],
        *,
        style: str = 'numpy',
        first_line_indent: int | None = None,
) -> list[tuple[list[str], bool]]:
    """
    Segment lines into chunks that can or cannot be wrapped.

    Scans through the lines to detect rST code directives, literal blocks
    (paragraphs following ::), rST tables, and bulleted lists, which should not
    be wrapped. Other content can be wrapped. Blocks are checked before tables
    and lists, so a ``::`` block whose first line is a list item or table row
    is kept whole.

    Also detects fenced code blocks using backticks or tildes. Fence handling
    is intentionally style-agnostic because both wrappers must preserve literal
    content before their own section parsers run. For Google-style docstrings,
    detects doctest blocks (>>>) as well.

    Parameters
    ----------
    lines : list[str]
        The list of lines to segment.
    style : str, default='numpy'
        The docstring style being processed. Supported values:
        - 'numpy': Detect code directives, literal blocks, tables, lists, and
          code fences
        - 'google': Additionally detect doctest blocks, and measure a list
          item's literal block from its marker (see
          ``is_literal_block_paragraph``)
    first_line_indent : int | None, default=None
        The real indent of ``lines[0]`` when its own indent was stripped, as
        for a Google compact summary; see ``is_literal_block_paragraph``.

    Returns
    -------
    list[tuple[list[str], bool]]
        A list of tuples where each tuple contains:
        - list[str]: consecutive lines forming a segment
        - bool: True if these lines can be wrapped, False if they should not be
          wrapped

        rST tables, bulleted lists, and literal blocks have wrappable=False,
        other content has wrappable=True.

    Examples
    --------
    >>> lines = [
    ...     'Some text that can be wrapped',
    ...     '- First list item',
    ...     '- Second list item',
    ...     'More wrappable text',
    ... ]
    >>> result = segment_lines_by_wrappability(lines)
    >>> len(result)
    3
    >>> result[0]
    (['Some text that can be wrapped'], True)
    >>> result[1]
    (['- First list item', '- Second list item'], False)
    >>> result[2]
    (['More wrappable text'], True)
    """
    segments: list[tuple[list[str], bool]] = []
    wrappable_start: int | None = None
    current_idx = 0
    while current_idx < len(lines):
        kind, end_idx = _find_unwrappable_span(
            lines,
            current_idx,
            style=style,
            first_line_indent=first_line_indent,
        )
        if kind is None:
            if wrappable_start is None:
                wrappable_start = current_idx

            current_idx += 1
            continue

        if wrappable_start is not None:
            segments.append((lines[wrappable_start:current_idx], True))
            wrappable_start = None

        segments.append((lines[current_idx:end_idx], False))
        current_idx = end_idx

    if wrappable_start is not None:
        segments.append((lines[wrappable_start:], True))

    return segments


def _find_unwrappable_span(
        lines: list[str],
        start_idx: int,
        *,
        style: str,
        first_line_indent: int | None = None,
) -> tuple[_UnwrappableKind | None, int]:
    """
    Find the unwrappable span that starts at ``lines[start_idx]``, if any.

    This is the one detection order, shared by
    ``segment_lines_by_wrappability`` and ``_split_out_literal_blocks``. Code
    directives come before literal blocks because ``.. code-block::`` without
    an argument also ends with ``::``. Both come before tables and lists, so a
    ``::`` block whose first line is a list item or table row is kept whole. A
    list item or table row that ends with ``::`` is still consumed whole by the
    list or table check, because a scan reaches a list or table at its first
    line.

    Parameters
    ----------
    lines : list[str]
        The lines being scanned.
    start_idx : int
        The index of the line to check.
    style : str
        The docstring style, ``'numpy'`` or ``'google'``. Google also detects
        doctest blocks.
    first_line_indent : int | None, default=None
        The real indent of ``lines[0]`` when its own indent was stripped; see
        ``is_literal_block_paragraph``.

    Returns
    -------
    tuple[_UnwrappableKind | None, int]
        The kind of span and the index after it, or ``(None, start_idx)`` when
        ``lines[start_idx]`` does not start an unwrappable span.
    """
    is_span, end_idx = is_rst_code_block(lines, start_idx)
    if is_span:
        return 'code_directive', end_idx

    is_span, end_idx = is_literal_block_paragraph(
        lines, start_idx, style=style, first_line_indent=first_line_indent
    )
    if is_span:
        return 'literal_block', end_idx

    is_span, end_idx = is_rST_table(lines, start_idx)
    if is_span:
        return 'table', end_idx

    is_span, end_idx = is_bulleted_list(lines, start_idx)
    if is_span:
        return 'list', end_idx

    if style == 'google':
        is_span, end_idx = is_google_doctest_block(lines, start_idx)
        if is_span:
            return 'doctest', end_idx

    # Protect fenced code before collecting prose so both wrappers keep
    # backtick and tilde fence contents out of later wrapping passes.
    is_span, end_idx = is_code_fence(lines, start_idx)
    if is_span:
        return 'code_fence', end_idx

    return None, start_idx


def is_rst_block(
        lines: list[str],
        start_idx: int,
        *,
        style: str,
) -> tuple[bool, int]:
    """
    Check if an rST code directive or ``::`` literal block starts here.

    Both are literal text, so the wrappers consume them before section parsing.
    Otherwise a heading or signature-like line inside one (such as ``Returns``
    over a hyphen underline in an rST sample) would switch the parser's section
    and change how the text after the block is read.

    Parameters
    ----------
    lines : list[str]
        The lines being scanned.
    start_idx : int
        The index of the line to check. A code directive starts at its
        directive line, a literal block at the line after the ``::`` line.
    style : str
        The docstring style, ``'numpy'`` or ``'google'``; see
        ``is_literal_block_paragraph``.

    Returns
    -------
    tuple[bool, int]
        Whether a block starts at ``start_idx``, and the index after it (or
        ``start_idx`` when none starts there).
    """
    is_code, end_idx = is_rst_code_block(lines, start_idx)
    if is_code:
        return True, end_idx

    return is_literal_block_paragraph(lines, start_idx, style=style)


def find_table_or_list_end(lines: list[str], start_idx: int) -> int:
    """
    Return the index after the rST table or bulleted list at ``start_idx``.

    Parameters
    ----------
    lines : list[str]
        The lines being scanned.
    start_idx : int
        The index of the line to check.

    Returns
    -------
    int
        The index after the table or list that starts at ``start_idx``, or
        ``start_idx`` when none starts there.
    """
    is_table, end_idx = is_rST_table(lines, start_idx)
    if is_table:
        return end_idx

    _, end_idx = is_bulleted_list(lines, start_idx)
    return end_idx


def is_examples_code_block(
        lines: list[str],
        start_idx: int,
) -> tuple[bool, int]:
    """
    Return True for Python-like code blocks inside an Examples section.

    Callers are responsible for invoking this only while already inside an
    Examples section. The detector keeps plain prose wrappable but preserves
    obvious code statements, comment lines, and same/deeper-indented output.
    This is intentionally conservative because non-code prose in Examples
    should still use normal paragraph wrapping when it is separated from code.
    """
    return _scan_examples_code_block(
        lines,
        start_idx,
        is_boundary=_is_docstring_section_boundary,
    )


def is_google_examples_code_block(
        lines: list[str],
        start_idx: int,
) -> tuple[bool, int]:
    """
    Return True for Python-like code blocks in Google ``Examples:``.

    Google needs a stricter boundary predicate than the default detector:
    indented ``Args:``-like output is example content, but peer or outer
    ``Name:`` headers should end the protected block.
    """
    google_section_indent = _find_previous_google_section_indent(
        lines,
        start_idx,
    )

    def is_boundary(candidate_lines: list[str], idx: int) -> bool:
        return _is_google_examples_section_boundary(
            candidate_lines,
            idx,
            section_indent=google_section_indent,
        )

    return _scan_examples_code_block(
        lines,
        start_idx,
        is_boundary=is_boundary,
    )


def _scan_examples_code_block(
        lines: list[str],
        start_idx: int,
        *,
        is_boundary: _SectionBoundaryPredicate,
) -> tuple[bool, int]:
    """
    Scan one Examples code/output block using ``is_boundary``.

    The first line must look like Python code or a Python comment. Once that
    start is accepted, same/deeper-indented nonblank lines are preserved too so
    repr output and plain output keep their original line breaks. The injected
    boundary keeps this scanner style-neutral while allowing Google to use
    indentation-aware section exits.
    """
    if start_idx >= len(lines):
        return False, start_idx

    if is_boundary(lines, start_idx):
        return False, start_idx

    first_line = lines[start_idx]
    if not _looks_like_examples_code_start(first_line):
        return False, start_idx

    base_indent = _indent_width(first_line)
    current_idx = start_idx

    while current_idx < len(lines):
        line = lines[current_idx]
        stripped = line.strip()

        if current_idx > start_idx:
            if not stripped:
                break

            if is_boundary(lines, current_idx):
                break

            if _indent_width(line) < base_indent:
                break

        current_idx += 1

    return True, current_idx


def _looks_like_examples_code_start(line: str) -> bool:
    """Return True when ``line`` starts a Python-like example statement."""
    stripped = line.strip()
    return (
        bool(stripped)
        and not stripped.startswith(('>>>', '...'))
        and (
            stripped.startswith('#')
            or bool(_PYTHON_EXAMPLE_START_PATTERN.match(stripped))
        )
    )


def is_code_fence(lines: list[str], start_idx: int = 0) -> tuple[bool, int]:
    """
    Check if lines starting at start_idx form a fenced code block.

    Fenced code blocks are delimited by triple backticks (```) or tildes (~~~).
    The opening fence can optionally include a language identifier.

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int, default=0
        The starting index to check from.

    Returns
    -------
    tuple[bool, int]
        A tuple of (is_code_fence, end_idx) where is_code_fence indicates if a
        code fence was found starting at start_idx, and end_idx is the index
        after the closing fence line (or start_idx if no code fence found).

    Examples
    --------
    >>> lines = ['```python', 'def foo():', '    pass', '```', 'more text']
    >>> is_code_fence(lines, 0)
    (True, 4)
    >>> is_code_fence(lines, 4)
    (False, 4)
    """
    if start_idx >= len(lines):
        return False, start_idx

    line = lines[start_idx]
    stripped = line.lstrip()

    # Check for opening fence (``` or ~~~)
    if not stripped.startswith(('```', '~~~')):
        return False, start_idx

    # Determine the fence character used
    fence_char = stripped[0]  # Either ` or ~

    # Find the closing fence
    for i in range(start_idx + 1, len(lines)):
        line_i = lines[i].lstrip()
        if (
            line_i.startswith(fence_char * 3)
            and line_i.rstrip() == fence_char * 3
        ):
            # Found closing fence
            return True, i + 1

    # No closing fence found - treat the rest as code block
    return True, len(lines)


def _indent_width(line: str) -> int:
    """Return the width of leading whitespace in ``line``."""
    return len(line) - len(line.lstrip())


def is_rst_code_block(
        lines: list[str], start_idx: int = 0
) -> tuple[bool, int]:
    """
    Check if lines starting at start_idx form an rST code directive block.

    Code directives are introduced by lines such as ``.. code-block:: python``,
    ``.. ipython:: python`` or ``.. doctest:: group`` (see
    ``_RST_CODE_DIRECTIVE_NAMES``). Their indented body is code-like content,
    so wrapping and rST backtick normalization should preserve it.

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int, default=0
        The starting index to check from.

    Returns
    -------
    tuple[bool, int]
        A tuple of (is_rst_code_block, end_idx) where end_idx is the index
        after the protected directive block.
    """
    if start_idx >= len(lines):
        return False, start_idx

    directive_line = lines[start_idx].rstrip()
    if not _RST_CODE_DIRECTIVE_PATTERN.fullmatch(directive_line):
        return False, start_idx

    directive_indent = _indent_width(lines[start_idx])
    current_idx = start_idx + 1
    while current_idx < len(lines):
        line = lines[current_idx]
        if not line.strip():
            current_idx += 1
            continue

        if _indent_width(line) <= directive_indent:
            break

        current_idx += 1

    return True, current_idx


def is_rST_table(lines: list[str], start_idx: int = 0) -> tuple[bool, int]:  # noqa: N802
    """
    Check if lines starting at start_idx form a reStructuredText table.

    rST supports two table formats:
    1. Simple tables: columns separated by spaces, header/data separated by
       ``=`` lines
    2. Grid tables: cells enclosed by + and - characters forming a grid

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int, default=0
        The starting index to check from.

    Returns
    -------
    tuple[bool, int]
        A tuple of (is_table, end_idx) where is_table indicates if an rST table
        was found starting at start_idx, and end_idx is the index after the
        last line of the table (or start_idx if no table found).
    """
    if start_idx >= len(lines):
        return False, start_idx

    # Try to detect grid table first
    grid_result = _is_grid_table(lines, start_idx)
    if grid_result[0]:
        return grid_result

    # Try to detect simple table
    simple_result = _is_simple_table(lines, start_idx)
    if simple_result[0]:
        return simple_result

    return False, start_idx


def _is_grid_table(lines: list[str], start_idx: int) -> tuple[bool, int]:
    """
    Check for rST grid table format.

    Grid tables look like:
    +-----+-----+
    | A   | B   |
    +=====+=====+
    | 1   | 2   |
    +-----+-----+
    """
    if start_idx >= len(lines):
        return False, start_idx

    first_line = lines[start_idx].strip()
    if not first_line or not _is_grid_separator_line(first_line):
        return False, start_idx

    # Find the end of the grid table
    current_idx = start_idx + 1
    in_table = True
    has_content = False

    while current_idx < len(lines) and in_table:
        line = lines[current_idx].strip()

        if not line:
            # Empty line ends the table
            break

        if _is_grid_separator_line(line):
            # Separator line continues the table
            current_idx += 1
        elif _is_grid_content_line(line):
            # Content line continues the table
            has_content = True
            current_idx += 1
        else:
            # Non-table line ends the table
            break

    # Must have at least one content line to be a valid table
    return has_content and current_idx > start_idx + 1, current_idx


def _is_simple_table(lines: list[str], start_idx: int) -> tuple[bool, int]:
    """
    Check for rST simple table format.

    Simple tables look like:
    ===== =====
    A     B
    ===== =====
    1     2
    ===== =====
    """
    if start_idx >= len(lines):
        return False, start_idx

    first_line = lines[start_idx].strip()
    if not first_line or not _is_simple_separator_line(first_line):
        return False, start_idx

    # Find the end of the simple table
    current_idx = start_idx + 1
    has_content = False

    while current_idx < len(lines):
        line = lines[current_idx].strip()

        if not line:
            # Empty line ends the table
            break

        if _is_simple_separator_line(line):
            # Separator line continues the table
            current_idx += 1
        elif _is_simple_content_line(line, first_line):
            # Content line continues the table
            has_content = True
            current_idx += 1
        else:
            # Non-table line ends the table
            break

    # Must have at least one content line and end with separator
    return (
        has_content
        and current_idx > start_idx + 1
        and current_idx <= len(lines)
        and _is_simple_separator_line(lines[current_idx - 1].strip())
    ), current_idx


def _is_grid_separator_line(line: str) -> bool:
    """
    Check if line is a grid table separator (starts with + and contains + - =).
    """
    if not line or not line.startswith('+'):
        return False
    # Should contain only +, -, =, and spaces
    # Must end with + to be a complete separator line
    return (
        all(c in '+-= ' for c in line)
        and '+' in line
        and line.rstrip().endswith('+')
    )


def _is_grid_content_line(line: str) -> bool:
    """Check if line is a grid table content line (starts and ends with |)."""
    stripped = line.strip()
    return stripped.startswith('|') and stripped.endswith('|')


def _is_simple_separator_line(line: str) -> bool:
    """
    Check if line is a simple table separator (contains only = and spaces).
    """
    if not line:
        return False
    # Should contain only = and spaces, and at least one =
    return all(c in '= ' for c in line) and '=' in line


def _is_simple_content_line(line: str, separator_line: str) -> bool:
    """
    Check if line could be content for a simple table based on separator
    pattern.
    """
    if not line:
        return False

    # Simple heuristic: content line should not be longer than separator
    # and should contain some non-space characters
    return len(line.rstrip()) <= len(separator_line) and bool(line.strip())


def is_bulleted_list(lines: list[str], start_idx: int = 0) -> tuple[bool, int]:
    """
    Check if lines starting at start_idx form a bulleted list.

    A bulleted list consists of consecutive list items that start with:
    - Unordered: -, *, or + followed by space
    - Ordered: number followed by . or ) and space (like "1. " or "1) ")

    Multi-line list items are supported. Continuation lines must be indented
    more than the list item marker and contain some content.

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int, default=0
        The starting index to check from.

    Returns
    -------
    tuple[bool, int]
        A tuple of (is_list, end_idx) where is_list indicates if a bulleted
        list was found starting at start_idx, and end_idx is the index after
        the last line of the list (or start_idx if no list found).
    """
    if start_idx >= len(lines):
        return False, start_idx

    first_line = lines[start_idx].strip()
    if not first_line:
        return False, start_idx

    # Check if first line is a list item
    if not _is_list_item(first_line):
        return False, start_idx

    # Determine list type from first item
    is_ordered = _is_ordered_list_item(first_line)
    list_format = _get_list_format(first_line) if is_ordered else None

    # Get the indentation level of the first list item
    first_line_full = lines[start_idx]
    first_stripped = first_line_full.lstrip(' ')
    first_indent = len(first_line_full) - len(first_stripped)

    # Find consecutive list items and their continuation lines
    current_idx = start_idx + 1
    while current_idx < len(lines):
        line = lines[current_idx]
        stripped_line = line.strip()

        # Empty line ends the list
        if not stripped_line:
            break

        # Check if this line is a continuation of a multi-line list item
        if _is_continuation_line(line, first_indent):
            current_idx += 1
            continue

        # Check if this line is a new list item of the same type
        if not _is_list_item(stripped_line):
            break

        # Must be same type (ordered vs unordered)
        if _is_ordered_list_item(stripped_line) != is_ordered:
            break

        # For ordered lists, must use same format (. vs ))
        if is_ordered and _get_list_format(stripped_line) != list_format:
            break

        current_idx += 1

    # Need at least one list item to be considered a list
    return current_idx > start_idx, current_idx


def _match_list_item_marker(line: str) -> re.Match[str] | None:
    """Match the list marker at the start of ``line``, ignoring its indent."""
    return _LIST_ITEM_MARKER_PATTERN.match(line.lstrip())


def _is_list_item(line: str) -> bool:
    """Check if a line is a list item (ordered or unordered)."""
    return _match_list_item_marker(line) is not None


def _is_ordered_list_item(line: str) -> bool:
    """
    Check if a line is an ordered list item.

    Supports formats:
    - number. (e.g., "1. ", "2. ")
    - number) (e.g., "1) ", "2) ")
    - (number) (e.g., "(1) ", "(2) ")
    """
    marker = _match_list_item_marker(line)
    return marker is not None and marker['bullet'] is None


def _get_list_format(line: str) -> str | None:
    """
    Get the format of an ordered list item.

    Parameters
    ----------
    line : str
        Line of text to inspect.

    Returns
    -------
    str | None
        ``'.'`` for the ``"1. "`` style, ``')'`` for ``"1) "``, ``'()'`` for
        ``"(1) "``, or ``None`` if the line is not an ordered list item.
    """
    marker = _match_list_item_marker(line)
    if marker is None or marker['bullet'] is not None:
        return None

    if marker['enum_parens'] is not None:
        return '()'

    return marker['enum_suffix']


def _is_continuation_line(line: str, list_item_indent: int) -> bool:
    """
    Check if a line is a continuation of a multi-line list item.

    A continuation line is indented further than the list item marker and
    contains some content.
    """
    if not line or not line.strip():
        return False

    # Get the indentation level of this line
    stripped = line.lstrip(' ')
    line_indent = len(line) - len(stripped)

    # Must be indented more than the list item marker to be a continuation
    return line_indent > list_item_indent


def is_doctest_block(
        lines: list[str],
        start_idx: int,
) -> tuple[bool, int]:
    """
    Check if lines starting at start_idx form a Python doctest block.

    A doctest block starts with '>>>' and includes subsequent prompts,
    continuation prompts, and their output. Once a prompt starts a doctest,
    preserve following non-empty output lines until a blank line or another
    docstring section boundary.

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int
        The starting index to check from.

    Returns
    -------
    tuple[bool, int]
        (is_doctest, end_idx)
    """
    return _scan_doctest_block(
        lines,
        start_idx,
        is_boundary=_is_docstring_section_boundary,
    )


def is_google_doctest_block(
        lines: list[str],
        start_idx: int,
) -> tuple[bool, int]:
    """
    Check if lines starting at ``start_idx`` form a Google doctest block.

    Doctest output can be arbitrary text, including ``Args:`` or custom
    ``Todo:`` labels. Google detection therefore anchors boundaries to the
    active section indentation instead of treating every header-looking line as
    a section exit.
    """
    google_section_indent = _find_previous_google_section_indent(
        lines,
        start_idx,
    )

    def is_boundary(candidate_lines: list[str], idx: int) -> bool:
        return _is_google_examples_section_boundary(
            candidate_lines,
            idx,
            section_indent=google_section_indent,
        )

    return _scan_doctest_block(
        lines,
        start_idx,
        is_boundary=is_boundary,
    )


def _scan_doctest_block(
        lines: list[str],
        start_idx: int,
        *,
        is_boundary: _SectionBoundaryPredicate,
) -> tuple[bool, int]:
    """
    Scan one doctest block using ``is_boundary``.

    The scanner preserves prompts and nonblank output until a blank line or a
    style-specific section boundary. Passing the boundary predicate in keeps
    the prompt/output rules shared while isolating section syntax differences.
    """
    if start_idx >= len(lines):
        return False, start_idx

    line = lines[start_idx].strip()
    if not line.startswith('>>>'):
        return False, start_idx

    current_idx = start_idx + 1
    while current_idx < len(lines):
        next_line = lines[current_idx].strip()
        if not next_line:
            break

        # Doctest output can be arbitrary prose, not just repr-like values.
        # Stop only at section boundaries so prose output stays byte-for-byte
        # while the next docstring section can still be wrapped normally.
        if is_boundary(lines, current_idx):
            break

        current_idx += 1

    return True, current_idx


def _find_previous_google_section_indent(
        lines: list[str],
        start_idx: int,
) -> int | None:
    """
    Return the nearest previous Google section header indentation.

    Doctest and example-code detection need this context because segmentation
    can start in the middle of an ``Examples:`` section, after the header
    itself has already been emitted in an earlier wrappable segment.
    """
    current_idx = start_idx - 1
    while current_idx >= 0:
        line = lines[current_idx]
        stripped = line.strip()
        if is_google_section_header(stripped):
            return _indent_width(line)

        current_idx -= 1

    return None


def _is_google_examples_section_boundary(
        lines: list[str],
        idx: int,
        *,
        section_indent: int | None,
) -> bool:
    """
    Return True when ``idx`` starts a peer/outer Google section boundary.

    Header-looking output indented inside an ``Examples:`` body is example
    content, not a real section boundary. If no active section indent can be
    recovered, fall back to the conservative generic boundary rules.
    """
    if idx >= len(lines):
        return False

    if section_indent is None:
        stripped = lines[idx].strip()
        return _is_docstring_section_boundary(
            lines,
            idx,
        ) or is_google_unknown_section_header(stripped)

    line = lines[idx]
    if _indent_width(line) > section_indent:
        return False

    stripped = line.strip()
    return is_google_section_header(
        stripped
    ) or is_google_unknown_section_header(stripped)


def _is_docstring_section_boundary(lines: list[str], idx: int) -> bool:
    """
    Return True when ``idx`` starts a known docstring section.

    Doctest preservation uses this as its only non-blank stopping point. That
    keeps plain text output intact without swallowing the rest of the docstring
    after an example block.
    """
    stripped = lines[idx].strip()
    if not stripped:
        return False

    if (
        stripped.endswith(':')
        and not stripped.endswith('::')
        and is_known_docstring_section_name(stripped)
    ):
        return True

    next_idx = idx + 1
    if next_idx >= len(lines):
        return False

    underline = lines[next_idx].strip()
    return (
        is_known_docstring_section_name(stripped)
        and len(underline) >= _SECTION_UNDERLINE_MIN_LENGTH
        and set(underline) <= {'-'}
    )


def is_literal_block_paragraph(
        lines: list[str],
        start_idx: int,
        *,
        style: str = 'numpy',
        first_line_indent: int | None = None,
) -> tuple[bool, int]:
    """
    Check if lines starting at start_idx form a literal block following ::.

    A literal block is an indented block that follows a line ending with ::
    (double colon). The entire block should not be wrapped.

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int
        The starting index to check from.
    style : str, default='numpy'
        The docstring style being processed. For a ``::`` line that starts a
        list item, NumPy follows rST: when the block is indented past the
        item's text, it is measured from that text, so the item's later
        paragraphs end the block. A block that is not indented past the text is
        measured from the marker instead. rST would not read it as a literal
        block, but it is often code, and wrapping it would join its lines.
        ``'google'`` always measures from the marker, because the Google
        wrapper re-indents wrappable text and would strip the indent the item's
        later paragraphs need.
    first_line_indent : int | None, default=None
        The real indent of ``lines[0]``, when its own indent was stripped: a
        Google compact summary sits right after the opening quotes, but it
        belongs at the docstring margin. A ``::`` line at ``lines[0]`` is then
        taken to be indented this far, so its block ends at the docstring's
        next section or paragraph at the margin. None means ``lines[0]`` has
        its real indent.

    Returns
    -------
    tuple[bool, int]
        A tuple of (is_literal_block, end_idx) where is_literal_block indicates
        if a literal block was found starting at start_idx, and end_idx is the
        index after the last line of the block (or start_idx if no block found)
    """
    if start_idx >= len(lines):
        return False, start_idx

    # Check if current line starts a paragraph after a :: line
    if start_idx == 0:
        return False, start_idx

    # Look at the previous non-empty line to see if it ends with ::
    prev_idx = start_idx - 1
    while prev_idx >= 0 and not lines[prev_idx].strip():
        prev_idx -= 1

    if prev_idx < 0:
        return False, start_idx

    prev_line = lines[prev_idx].rstrip()
    if not prev_line.endswith('::'):
        return False, start_idx

    literal_indent = _indent_width(lines[prev_idx])
    if prev_idx == 0 and first_line_indent is not None:
        literal_indent = max(literal_indent, first_line_indent)

    marker = _match_list_item_marker(lines[prev_idx])
    if style != 'google' and marker:
        # A literal block must be indented past the paragraph that introduces
        # it, and a list item's paragraph starts at the item's text. Use that
        # only when the block's first line is past the text, as explained for
        # ``style`` above.
        text_indent = literal_indent + marker.end()
        first_idx = start_idx
        while first_idx < len(lines) and not lines[first_idx].strip():
            first_idx += 1

        if (
            first_idx < len(lines)
            and _indent_width(lines[first_idx]) > text_indent
        ):
            literal_indent = text_indent

    # Only indentation ends the block, as in rST. Lines inside it that look
    # like section headers (``Arguments:`` in a CLI help sample) are literal
    # text.
    current_idx = start_idx
    has_literal_content = False
    while current_idx < len(lines):
        line = lines[current_idx]

        if not line.strip():
            current_idx += 1
            continue

        if _indent_width(line) <= literal_indent:
            break

        has_literal_content = True
        current_idx += 1

    if not has_literal_content:
        return False, start_idx

    return True, current_idx
