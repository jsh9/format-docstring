from __future__ import annotations

import re
import textwrap

# Regex pattern to split text into paragraphs (multiple consecutive newlines)
_PARAGRAPH_SPLIT_PATTERN = re.compile(r'\n\s*\n')


def add_leading_indent(docstring: str, leading_indent: int | None) -> str:
    r"""Ensure a docstring starts with a newline + indent when requested.

    If ``leading_indent`` is a positive integer and the docstring body doesn't
    already begin with ``"\n" + ' ' * leading_indent``, prepend it. Otherwise,
    return the docstring unchanged.
    """
    if leading_indent is not None:
        needed_prefix: str = '\n' + (' ' * leading_indent)
        if not docstring.startswith(needed_prefix):
            return needed_prefix + docstring

    return docstring


def finalize_lines(out_lines: list[str], leading_indent: int | None) -> str:
    """Trim trailing spaces, normalize blank lines, and append closing indent.

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
            result = result + suffix

    return result


def collect_to_temp_output(temp_out: list[str | list[str]], line: str) -> None:
    """
    Collect `line` into temporary output.

    If the last element of `temp_out` is `list[str]`, append `line` into it. If
    the last element of `temp_out` is `str`, add new (empty) list as the last
    element and use `line` as the first element of this new (empty) list.
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
    Wrap the `list[str]` elements in `temp_out`.

    To preserve literal blocks indicated by ``::``, the function first scans
    ``temp_out`` for the pattern ``<line ending with '::'>``, followed by
    ``''`` (exactly 1 empty line), followed by non-empty content. When found,
    those three entries are merged into
    a single ``list[str]`` so the literal block (including the separating blank
    line) is wrapped as one unit.
    """

    def _to_list(element: str | list[str]) -> list[str]:
        return [element] if isinstance(element, str) else list(element)

    def _ends_with_literal_block_marker(element: str | list[str]) -> bool:
        if isinstance(element, str):
            return element.endswith('::')

        if not element:
            return False

        return element[-1].endswith('::')

    def _is_empty_string(element: str | list[str]) -> bool:
        return isinstance(element, str) and element == ''

    def _has_content(element: str | list[str]) -> bool:
        if isinstance(element, str):
            return element != ''

        return any(line != '' for line in element)

    merged_temp_out: list[str | list[str]] = []
    idx = 0
    while idx < len(temp_out):
        current = temp_out[idx]
        next_idx = idx + 1
        next_next_idx = idx + 2

        if (
            _ends_with_literal_block_marker(current)
            and next_next_idx < len(temp_out)
            and _is_empty_string(temp_out[next_idx])
            and _has_content(temp_out[next_next_idx])
        ):
            merged_element: list[str] = []
            merged_element.extend(_to_list(current))
            merged_element.extend(_to_list(temp_out[next_idx]))
            merged_element.extend(_to_list(temp_out[next_next_idx]))
            merged_temp_out.append(merged_element)
            idx += 3
            continue

        merged_temp_out.append(current)
        idx += 1

    out: list[str] = []

    for element in merged_temp_out:
        if isinstance(element, str):
            out.append(element)
        elif isinstance(element, list):
            wrapped: list[str] = wrap_preserving_indent(element, width)
            if (
                '' in element
                and '' not in wrapped
                and element.index('') < len(element) - 1
            ):
                insertion_idx = min(element.index(''), len(wrapped))
                wrapped = (
                    wrapped[:insertion_idx] + [''] + wrapped[insertion_idx:]
                )

            out.extend(wrapped)
        else:
            raise RuntimeError("Something's wrong. Please contact the author.")

    return fix_typos_in_section_headings(out)


def wrap_preserving_indent(lines: list[str], width: int) -> list[str]:
    """Wrap lines while preserving structure of tables, lists, and indentation.

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
        The processed lines with wrappable content wrapped and
        non-wrappable content (tables, lists) preserved.
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
    """Wrap a segment of regular text lines while preserving indentation and
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
            wrapped_lines: list[str] = tw.wrap(stripped_para)
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

    result_: list[str] = result if result else lines

    return _add_back_leading_or_trailing_newline(
        original_lines=lines,
        wrapped_lines=result_,
    )


def _add_back_leading_or_trailing_newline(
        original_lines: list[str],
        wrapped_lines: list[str],
) -> list[str]:
    if len(original_lines) == 0 or len(wrapped_lines) == 0:
        return wrapped_lines

    new_result: list[str] = []
    if original_lines[0] == '':
        new_result = [''] + wrapped_lines
    else:
        new_result = wrapped_lines

    if original_lines[-1] == '':
        return new_result + ['']

    return new_result


def merge_lines_and_strip(text: str) -> str:
    r"""Merge lines within paragraphs, preserving paragraph breaks.

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
    if len(lines) < 2:
        return lines

    # Define typo corrections (case-insensitive keys, proper case values)
    typo_corrections = {
        'return': 'Returns',
        'parameter': 'Parameters',
        'other parameter': 'Other Parameters',
        'attribute': 'Attributes',
        'yield': 'Yields',
        'raise': 'Raises',
        'note': 'Notes',
        'example': 'Examples',
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
        if len(next_line) >= 2 and all(c == '-' for c in next_line):
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
) -> list[tuple[list[str], bool]]:
    """Segment lines into chunks that can or cannot be wrapped.

    Scans through the lines to detect rST tables, bulleted lists, and literal
    blocks (paragraphs following ::), which should not be wrapped. Other
    content can be wrapped.

    Parameters
    ----------
    lines : list[str]
        The list of lines to segment.

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
    if not lines:
        return []

    segments: list[tuple[list[str], bool]] = []
    current_idx = 0

    while current_idx < len(lines):
        # Check for rST table
        is_table, table_end_idx = is_rST_table(lines, current_idx)
        if is_table:
            # Add table segment (not wrappable)
            table_lines = lines[current_idx:table_end_idx]
            segments.append((table_lines, False))
            current_idx = table_end_idx
            continue

        # Check for bulleted list
        is_list, list_end_idx = is_bulleted_list(lines, current_idx)
        if is_list:
            # Add list segment (not wrappable)
            list_lines = lines[current_idx:list_end_idx]
            segments.append((list_lines, False))
            current_idx = list_end_idx
            continue

        # Check for literal block following ::
        is_literal, literal_end_idx = _is_literal_block_paragraph(
            lines, current_idx
        )
        if is_literal:
            # Add literal block segment (not wrappable)
            literal_lines = lines[current_idx:literal_end_idx]
            segments.append((literal_lines, False))
            current_idx = literal_end_idx
            continue

        # Neither table, list, nor literal block - collect wrappable content
        start_idx = current_idx
        current_idx += 1

        # Continue collecting wrappable lines until we hit a table/list/literal
        # or end
        while current_idx < len(lines):
            is_table, _ = is_rST_table(lines, current_idx)
            is_list, _ = is_bulleted_list(lines, current_idx)
            is_literal, _ = _is_literal_block_paragraph(lines, current_idx)

            if is_table or is_list or is_literal:
                break

            current_idx += 1

        # Add wrappable segment
        wrappable_lines = lines[start_idx:current_idx]
        segments.append((wrappable_lines, True))

    return segments


def is_rST_table(lines: list[str], start_idx: int = 0) -> tuple[bool, int]:
    """Check if lines starting at start_idx form a reStructuredText table.

    rST supports two table formats:
    1. Simple tables: columns separated by spaces, header/data separated by
       `=` lines
    2. Grid tables: cells enclosed by + and - characters forming a grid

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int, optional
        The starting index to check from, by default 0.

    Returns
    -------
    tuple[bool, int]
        A tuple of (is_table, end_idx) where is_table indicates if an rST
        table was found starting at start_idx, and end_idx is the index after
        the last line of the table (or start_idx if no table found).
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
    """Check for rST grid table format.

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
    """Check for rST simple table format.

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
    """Check if line is a grid table separator (starts with + and
    contains + - =).
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
    """Check if lines starting at start_idx form a bulleted list.

    A bulleted list consists of consecutive list items that start with:
    - Unordered: -, *, or + followed by space
    - Ordered: number followed by . or ) and space (like "1. " or "1) ")

    Multi-line list items are supported. Continuation lines must be indented
    more than the list item marker and contain some content.

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int, optional
        The starting index to check from, by default 0.

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


def _is_list_item(line: str) -> bool:
    """Check if a line is a list item (ordered or unordered)."""
    return _is_unordered_list_item(line) or _is_ordered_list_item(line)


def _is_unordered_list_item(line: str) -> bool:
    """Check if a line is an unordered list item (starts with -, *, or +)."""
    stripped = line.lstrip()
    return (
        stripped.startswith('- ')
        or stripped.startswith('* ')
        or stripped.startswith('+ ')
    )


def _is_ordered_list_item(line: str) -> bool:
    """Check if a line is an ordered list item.

    Supports formats:
    - number. (e.g., "1. ", "2. ")
    - number) (e.g., "1) ", "2) ")
    - (number) (e.g., "(1) ", "(2) ")
    """
    stripped = line.lstrip()
    if not stripped:
        return False

    # Look for patterns:
    # - digits followed by . or ) followed by space
    # - ( followed by digits followed by ) followed by space
    import re

    pattern = r'^(\d+[.)] |\(\d+\) )'
    return bool(re.match(pattern, stripped))


def _get_list_format(line: str) -> str | None:
    """Get the format of an ordered list item.

    Returns
    -------
    - '.' for "1. " format
    - ')' for "1) " format
    - '()' for "(1) " format
    - None if not an ordered list item
    """
    stripped = line.lstrip()
    if not stripped:
        return None

    import re

    dot_match = re.match(r'^\d+\. ', stripped)
    paren_match = re.match(r'^\d+\) ', stripped)
    full_paren_match = re.match(r'^\(\d+\) ', stripped)

    if dot_match:
        return '.'

    if paren_match:
        return ')'

    if full_paren_match:
        return '()'

    return None


def _is_continuation_line(line: str, list_item_indent: int) -> bool:
    """Check if a line is a continuation of a multi-line list item.

    A continuation line is indented further than the list item marker
    and contains some content.
    """
    if not line or not line.strip():
        return False

    # Get the indentation level of this line
    stripped = line.lstrip(' ')
    line_indent = len(line) - len(stripped)

    # Must be indented more than the list item marker to be a continuation
    return line_indent > list_item_indent


def _is_literal_block_paragraph(
        lines: list[str], start_idx: int
) -> tuple[bool, int]:
    """Check if lines starting at start_idx form a literal block following ::.

    A literal block is a paragraph that follows a line ending with ::
    (double colon). The entire paragraph should not be wrapped.

    Parameters
    ----------
    lines : list[str]
        The list of lines to check.
    start_idx : int
        The starting index to check from.

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

    # Current line starts a literal block - find its end
    current_idx = start_idx
    while current_idx < len(lines):
        line = lines[current_idx].strip()

        # Empty line ends the literal block
        if not line:
            break

        current_idx += 1

    # Need at least one line to be a literal block
    return current_idx > start_idx, current_idx
