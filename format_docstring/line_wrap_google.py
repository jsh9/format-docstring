import re
import textwrap
from typing import Final

from format_docstring.line_wrap_numpy import (
    _unwrap_generator_annotation,
)
from format_docstring.line_wrap_utils import (
    ParameterMetadata,
    add_leading_indent,
    finalize_lines,
    _is_labeled_return_prose,
    is_code_fence,
    is_google_doctest_block,
    is_google_examples_code_block,
    merge_lines_and_strip,
    segment_lines_by_wrappability,
)
from format_docstring.section_utils import (
    canonical_google_section_header,
    is_google_attribute_section_header,
    is_google_parameter_section_header,
    is_google_returns_or_yields_section_header,
    is_google_section_header,
    is_google_signature_section_header,
    is_google_unknown_section_header,
    is_google_yields_section_header,
)

# Google docstrings can preserve string prefixes such as ``rf`` when rebuilt,
# so first-line wrapping reserves two prefix characters plus opening quotes.
GOOGLE_OPENING_QUOTES_WIDTH: Final[int] = 5
GOOGLE_COMPACT_OPENING_QUOTES_WIDTH: Final[int] = 5


def wrap_docstring_google(
        docstring: str,
        *,
        line_length: int,
        leading_indent: int | None = None,
        append_closing_indent: bool = True,
        fix_rst_backticks: bool = True,
        parameter_metadata: ParameterMetadata | None = None,
        return_annotation: str | None = None,
        attribute_metadata: ParameterMetadata | None = None,
        compact_first_line: bool = False,
) -> str:
    """
    Wrap Google-style docstrings.

    This first normalizes rST inline literals, then unwraps section bodies, and
    finally wraps them to the target line length. The backtick pass must run
    first because single backticks can expand to double backticks; doing that
    after wrapping can make the final output exceed ``line_length``.
    """
    docstring_ = docstring
    if fix_rst_backticks:
        from format_docstring.line_wrap_numpy import _fix_rst_backticks

        docstring_ = _fix_rst_backticks(docstring_)

    should_compact_first_line = (
        compact_first_line
        and _should_compact_google_first_line(docstring_, leading_indent)
    )
    opening_quotes_on_own_line = compact_first_line and (
        not should_compact_first_line
    )
    closing_indent = leading_indent if append_closing_indent else None
    unwrapped = _pass1_unwrap_google_docstring(
        docstring_,
        line_length=line_length,
        leading_indent=leading_indent,
        closing_indent=closing_indent,
        parameter_metadata=parameter_metadata,
        return_annotation=return_annotation,
        attribute_metadata=attribute_metadata,
        compact_first_line=should_compact_first_line,
    )

    wrapped = _pass2_wrap_google_docstring(
        unwrapped,
        line_length=line_length,
        leading_indent=leading_indent,
        closing_indent=closing_indent,
        compact_first_line=should_compact_first_line,
        opening_quotes_on_own_line=opening_quotes_on_own_line,
    )

    return wrapped


def _should_compact_google_first_line(
        docstring: str,
        leading_indent: int | None,
) -> bool:
    """
    Return True when content can safely share the opening quotes.

    End-to-end Google formatting uses compact opening lines for normally
    aligned docstrings. Deliberately over- or under-indented docstrings keep
    their first content line on the next physical line so the formatter does
    not erase indentation that the fixture is explicitly exercising.
    """
    if not docstring.startswith('\n'):
        return True

    expected_indent = leading_indent or 0
    for line in docstring.splitlines():
        if line.strip():
            return len(line) - len(line.lstrip()) == expected_indent

    return True


def _pass1_unwrap_google_docstring(
        docstring: str,
        *,
        line_length: int,  # Unused in pass 1, but kept for signature compatibility
        leading_indent: int | None = None,
        closing_indent: int | None = None,
        parameter_metadata: ParameterMetadata | None = None,
        return_annotation: str | None = None,
        attribute_metadata: ParameterMetadata | None = None,
        compact_first_line: bool = False,
) -> str:
    """
    Wrap Google-style docstrings.

    Phase 1 implementation:
    - Calculates base indentation.
    - Identifies sections (Args, Returns, etc.).
    - Preserves fenced code blocks before section parsing.
    - Identifies signature lines.
    - Unwraps descriptions onto the signature line, respecting preservation rules.
    """
    # 1. Base indentation
    # For Google style, check if content already has proper indentation
    # before adding a leading indent prefix
    if leading_indent is not None and leading_indent > 0:
        if docstring.startswith('\n'):
            docstring_ = docstring
        else:
            needs_leading_indent = True
            for line in docstring.splitlines():
                if line.strip():
                    existing_indent = len(line) - len(line.lstrip())
                    needs_leading_indent = existing_indent < leading_indent
                    break

            if needs_leading_indent:
                docstring_ = add_leading_indent(docstring, leading_indent)
            else:
                docstring_ = docstring
    else:
        docstring_ = add_leading_indent(docstring, leading_indent)

    lines: list[str] = docstring_.splitlines()
    if not lines:
        return docstring_

    temp_out: list[str | list[str]] = []
    i: int = 0
    current_section: str = ''
    current_section_indent = 0
    return_annotation_str: str | None = (
        return_annotation.strip() if return_annotation else None
    )

    def compact_pending_summary() -> None:
        """
        Compact buffered summary text before a section boundary or final output.

        Google end-to-end formatting can put the first summary sentence beside
        the opening quotes. Once a real or custom section starts, later lines
        must keep section structure instead of being merged into the summary.
        """
        if not (compact_first_line and not current_section and temp_out):
            return

        _compact_google_summary_output(
            temp_out,
            leading_indent=leading_indent,
        )

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent_length = len(line) - len(stripped)

        if not line.strip():
            if not current_section:
                # Still in summary, accumulate empty lines to preserve structure
                # (or just pass them? summary processing will handle segmentation)
                temp_out.append(line)
            else:
                temp_out.append(line)

            i += 1
            continue

        # Preserve fenced code blocks before section/signature parsing. This
        # avoids treating sample code inside a fence as Google docstring syntax.
        is_fence, fence_end_idx = is_code_fence(lines, i)
        if is_fence:
            temp_out.extend(lines[i:fence_end_idx])
            i = fence_end_idx
            continue

        # Doctests must be protected before section parsing because their
        # output can be indistinguishable from an ``Args:``-style header.
        # The Google detector only exits on peer/outer section indentation.
        is_doctest, doctest_end_idx = is_google_doctest_block(
            lines,
            i,
        )
        if is_doctest:
            temp_out.extend(lines[i:doctest_end_idx])
            i = doctest_end_idx
            continue

        canonical = canonical_google_section_header(stripped)
        if canonical is not None:
            # A section header freezes summary parsing; compact the buffered
            # prose first so later section content cannot move beside quotes.
            compact_pending_summary()

            current_section = canonical.lower()
            current_section_indent = indent_length
            # Normalize section header to canonical Google-style form
            # e.g., "parameter:" -> "Args:", "return:" -> "Returns:"
            indent = line[: len(line) - len(stripped)]
            temp_out.append(indent + canonical)

            i += 1
            continue

        if (
            _is_google_unknown_section_header(stripped)
            and (
                (not current_section and _has_summary_content(temp_out))
                or indent_length <= current_section_indent
            )
        ):
            # Unknown bare headers end signature parsing without becoming
            # canonical Google sections. This preserves custom sections such as
            # ``Todo:`` while keeping following prose out of ``Args:`` parsing.
            compact_pending_summary()
            current_section = stripped.lower()
            current_section_indent = indent_length
            temp_out.append(line)
            i += 1
            continue

        if is_google_signature_section_header(current_section):
            section_lower = current_section.lower()
            is_return_section = (
                is_google_returns_or_yields_section_header(section_lower)
            )
            is_yields_section = is_google_yields_section_header(section_lower)
            metadata_for_section = parameter_metadata
            if is_google_attribute_section_header(section_lower):
                metadata_for_section = attribute_metadata

            # Check if this line is a signature line.
            # Google style items are like: "  name (type): description" or "  name: description"
            # They must be indented relative to the section header.
            # (We won't strictly enforce relative indent check here for simplicity, but we rely on the regex)
            # Simplistic detection: "word ... :" or "word ( ... ) :"
            # And it must NOT be a continuation line (though strict differentiation is hard without lookbehind).
            # We'll use a heuristic: It looks like a signature if it starts with a word, optionally has parens, end with colon.

            # Normalize loose Google signatures before detection so forms like
            # `arg(type):text` are parsed like well-formed `arg (type): text`.
            # Without this, malformed spacing is preserved as part of the
            # signature and the wrapping pass cannot repair it later.
            standardized_line = _normalize_google_signature_spacing(
                _standardize_default_value(line)
            )
            standardized_stripped = standardized_line.lstrip()

            if is_return_section:
                desired_annotation = return_annotation_str
                if desired_annotation is not None and is_yields_section:
                    desired_annotation = (
                        _unwrap_generator_annotation(desired_annotation)
                        or desired_annotation
                    )

                rewritten_named_return = (
                    _rewrite_google_named_return_signature(
                        standardized_line,
                        desired_annotation,
                    )
                )
                if rewritten_named_return is not None:
                    standardized_line = rewritten_named_return
                    standardized_stripped = standardized_line.lstrip()
                elif (
                    desired_annotation is not None
                    and _is_google_return_signature(standardized_stripped)
                ):
                    standardized_line = _rewrite_google_return_signature(
                        standardized_line,
                        desired_annotation,
                    )
                    standardized_stripped = standardized_line.lstrip()
                elif (
                    desired_annotation is not None
                    and _is_google_return_description(standardized_stripped)
                ):
                    # A prose-only Returns entry still needs the real
                    # annotation. Merge them now so pass two can wrap it like a
                    # normal Google return signature with an inline
                    # description.
                    indent = standardized_line[
                        : len(standardized_line) - len(standardized_stripped)
                    ]
                    standardized_line = (
                        f'{indent}{desired_annotation}: '
                        f'{standardized_stripped.strip()}'
                    )
                    standardized_stripped = standardized_line.lstrip()

            is_signature = _is_google_signature(standardized_stripped)
            if is_return_section:
                # Return and yield rows can be type signatures that the
                # generic Google item detector rejects, especially rST roles
                # such as ``:class:`Widget`:``. Classify them here so
                # line-wrap-only calls get signature continuation indentation
                # even when no source annotation is available for sync.
                is_signature = is_signature or (
                    _is_google_return_signature(standardized_stripped)
                )

            if is_signature:
                # Detected a signature line.
                # Now we need to gobble up the description lines that follow.
                # The description block consists of subsequent lines that are indented MORE than the current line,
                # OR (in some loose formatting) simply belong to this item until the next item starts.
                # Standard Google style: description lines are indented.

                # However, the user request says: "unwrap the arg's description ... onto the signature line"
                # So we need to:
                # 1. Parse the signature line itself to split "Signature" vs "Inline Description"
                #    e.g. "arg1 (int): description starts here" -> Sig: "arg1 (int):", Desc: "description starts here"
                # 2. Collect subsequent indented lines.
                # 3. Use segment_lines_by_wrappability on the full description (inline + collected).
                # 4. If the first segment is wrappable text, merge it and append to signature.
                # 5. Keep others as is.

                signature_part, inline_desc = _split_google_signature(
                    standardized_line
                )
                if (
                    is_google_parameter_section_header(section_lower)
                    or is_google_attribute_section_header(section_lower)
                ):
                    signature_part = _rewrite_google_parameter_signature(
                        signature_part,
                        metadata_for_section,
                    )

                current_item_indent = indent_length
                description_lines: list[str] = []
                if inline_desc:
                    description_lines.append(inline_desc)

                # Consume following lines
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_stripped = next_line.lstrip()
                    next_indent = len(next_line) - len(next_stripped)

                    if not next_line.strip():
                        # Empty lines might be part of the description
                        # (e.g. paragraph breaks within the item).
                        # We keep them, but if we hit the next signature, we stop.
                        # A bit tricky: empty lines are ambiguous. We consume them for now.
                        description_lines.append('')
                        j += 1
                        continue

                    if is_return_section:
                        # Google returns/yields describe one value, so later
                        # same-indent rows are preserved as raw description
                        # text instead of becoming separate return entries.
                        if (
                            _is_google_section_header(next_stripped)
                            or _is_google_unknown_section_header(
                                next_stripped
                            )
                            or next_indent < current_item_indent
                        ):
                            break
                    elif next_indent <= current_item_indent:
                        # Use <= because a new item would be at the same indentation level.
                        # Sections ending would be less indentation (usually).
                        # So if indent went back to current_item level or less, we stop.
                        # Exception: if it's a continuation line but the user has messy indent?
                        # We assume standard formatting: continuations must be indented.
                        break

                    description_lines.append(
                        next_line
                    )  # We might need to dedent this for processing?
                    j += 1

                if (
                    is_return_section
                    and inline_desc is None
                    and any(
                        desc_line.strip() for desc_line in description_lines
                    )
                    and not signature_part.rstrip().endswith(':')
                ):
                    # Bare return types need a delimiter once pass one pulls
                    # their indented description inline; otherwise pass two
                    # would emit words as ``type description`` instead of
                    # preserving the Google ``type: description`` shape.
                    signature_part = f'{signature_part.rstrip()}:'

                # Description lines use two coordinate systems: inline text is
                # already dedented, while following lines still carry source
                # indentation. Normalize before segmentation so preserved
                # blocks are later re-indented exactly once.
                processed_desc_lines = _dedent_lines(
                    description_lines,
                    current_item_indent,
                    has_inline_description=inline_desc is not None,
                )

                # Segment
                segments = segment_lines_by_wrappability(
                    processed_desc_lines, style='google'
                )

                new_signature_line = signature_part
                remaining_lines_to_append: list[str] = []

                if segments:
                    first_seg_lines, is_wrappable = segments[0]
                    if is_wrappable:
                        trailing_empty_lines = []
                        while (
                            first_seg_lines and not first_seg_lines[-1].strip()
                        ):
                            trailing_empty_lines.append(first_seg_lines.pop())
                        # Restore order (popped from end)
                        trailing_empty_lines.reverse()

                        merged_text = merge_lines_and_strip(
                            '\n'.join(first_seg_lines)
                        )

                        if merged_text:
                            merged_lines = merged_text.splitlines()

                            sig_combined = (
                                f'{signature_part} {merged_lines[0]}'
                            )

                            if len(merged_lines) > 1:
                                parts = [sig_combined]
                                indent_pad = ' ' * (current_item_indent + 4)

                                for ml in merged_lines[1:]:
                                    if ml.strip():
                                        parts.append(indent_pad + ml)
                                    else:
                                        parts.append('')

                                new_signature_line = '\n'.join(parts)
                            else:
                                new_signature_line = sig_combined
                        else:
                            new_signature_line = signature_part

                        indent_str = ' ' * (current_item_indent + 4)
                        for _ in trailing_empty_lines:
                            remaining_lines_to_append.append('')

                        for seg_lines, _ in segments[1:]:
                            # Pass one dedents description blocks before
                            # segmentation, so preserved blocks must be shifted
                            # back to Google's continuation indent here.
                            for l in seg_lines:
                                remaining_lines_to_append.append(
                                    indent_str + l if l.strip() else ''
                                )

                    else:
                        # Tables and literal blocks cannot be merged inline.
                        # Keep them under the item after restoring indent.
                        new_signature_line = signature_part
                        indent_str = ' ' * (current_item_indent + 4)
                        for l in first_seg_lines:
                            remaining_lines_to_append.append(
                                indent_str + l if l.strip() else ''
                            )

                        for seg_lines, _ in segments[1:]:
                            for l in seg_lines:
                                remaining_lines_to_append.append(
                                    indent_str + l if l.strip() else ''
                                )

                else:
                    new_signature_line = signature_part.rstrip()

                temp_out.append(new_signature_line)
                temp_out.extend(remaining_lines_to_append)

                i = j
                continue

        # Default behaviour for non-signature lines or unknown sections
        temp_out.append(line)
        i += 1

    compact_pending_summary()

    return finalize_lines(temp_out, closing_indent)


def _join_paragraph_lines(
        lines: list[str],
        leading_indent: int | None,
        *,
        initial_in_examples_section: bool = False,
) -> list[str]:
    """
    Group consecutive non-signature lines into joined paragraphs.

    This prevents URLs and inline elements from being broken across lines when
    individual lines are wrapped. Signatures (lines matching Google-style
    parameter patterns) are kept separate. Python-like Examples code is also
    kept separate because joining it here would destroy line breaks before the
    preservation check in pass two can run.

    Parameters
    ----------
    lines : list[str]
        The lines from a wrappable segment.
    leading_indent : int | None
        The leading indentation level.
    initial_in_examples_section : bool, default=False
        Whether this segment starts inside an ``Examples:`` section.

    Returns
    -------
    list[str]
        Lines with consecutive non-signature prose joined into single lines.
    """
    if not lines:
        return lines

    result: list[str] = []
    paragraph_lines: list[str] = []
    paragraph_indent: str = ''
    # Wrappability segmentation can split an Examples section around a doctest
    # block. Preserve the caller's section state so later plain code is not
    # joined as prose after the protected doctest segment.
    in_examples_section = initial_in_examples_section

    def flush_paragraph() -> None:
        """Join accumulated paragraph lines and add to result."""
        nonlocal paragraph_lines, paragraph_indent
        if paragraph_lines:
            # Join stripped content with spaces
            joined_content = ' '.join(
                line.lstrip() for line in paragraph_lines
            )
            # Re-apply the original paragraph indent
            result.append(paragraph_indent + joined_content)
            paragraph_lines = []
            paragraph_indent = ''

    line_idx = 0
    while line_idx < len(lines):
        line = lines[line_idx]
        if not line.strip():
            # Empty line - flush current paragraph and preserve empty line
            flush_paragraph()
            result.append(line)
            line_idx += 1
            continue

        stripped = line.lstrip()
        indent_str = line[: len(line) - len(stripped)]
        indent_level = len(indent_str)

        canonical = canonical_google_section_header(stripped)
        if canonical is not None:
            in_examples_section = canonical == 'Examples:'
        elif (
            _is_google_unknown_section_header(stripped)
            and indent_level <= (leading_indent or 0)
        ):
            in_examples_section = False

        if in_examples_section:
            # Protect plain code before paragraph joining. This pass is the
            # last point where the original line boundaries are still intact.
            is_examples_code, examples_code_end_idx = (
                is_google_examples_code_block(
                    lines,
                    line_idx,
                )
            )
            if is_examples_code:
                flush_paragraph()
                result.extend(lines[line_idx:examples_code_end_idx])
                line_idx = examples_code_end_idx
                continue

        # Check if this is a signature line
        is_sig = False
        if not stripped.startswith(('"""', "'''")):
            if leading_indent and len(indent_str) < (leading_indent or 0):
                is_sig = False
            else:
                is_sig = _is_google_signature(stripped)

        if is_sig:
            # Signature line - flush any accumulated paragraph and add signature
            flush_paragraph()
            result.append(line)
        else:
            # Non-signature line - accumulate for paragraph joining
            if not paragraph_lines:
                # First line of new paragraph - capture indent
                paragraph_indent = indent_str
            elif indent_str != paragraph_indent:
                # Indent changed - flush previous paragraph and start new one
                flush_paragraph()
                paragraph_indent = indent_str

            paragraph_lines.append(line)

        line_idx += 1

    # Flush any remaining paragraph
    flush_paragraph()

    return result


def _append_google_summary_merged(
        output: list[str | list[str]],
        merged: str,
        *,
        leading_indent: int | None,
        is_first_segment: bool,
) -> bool:
    """
    Append merged summary text while preserving Google literal shape.

    The first summary paragraph may share the opening triple quotes. Later
    paragraphs still need the docstring owner's indentation so compacting the
    opening line does not make following prose start at column zero.
    """
    if not merged:
        return False

    indent = ' ' * (leading_indent or 0)
    emitted_content = False
    for idx, line in enumerate(merged.splitlines()):
        if not line.strip():
            output.append('')
            continue

        if is_first_segment and idx == 0:
            output.append(line)
        else:
            output.append(indent + line)

        emitted_content = True

    return emitted_content


def _compact_google_summary_output(
        output: list[str | list[str]],
        *,
        leading_indent: int | None,
) -> None:
    """
    Merge buffered summary paragraphs for compact Google docstrings.

    The summary buffer can contain already-protected literal segments. Segmenting
    before merging keeps those blocks intact while still allowing ordinary prose
    to move beside the opening quotes.
    """
    summary_lines_flat = []
    for item in output:
        if isinstance(item, list):
            summary_lines_flat.extend(item)
        else:
            summary_lines_flat.append(item)

    segments = segment_lines_by_wrappability(
        summary_lines_flat,
        style='google',
    )

    output.clear()
    first_segment_processed = False
    for seg_lines, is_wrappable in segments:
        if not is_wrappable:
            output.extend(seg_lines)
            first_segment_processed = True
            continue

        trailing_empty_lines = []
        while seg_lines and not seg_lines[-1].strip():
            trailing_empty_lines.append(seg_lines.pop())

        trailing_empty_lines.reverse()

        leading_empty_lines = []
        while seg_lines and not seg_lines[0].strip():
            leading_empty_lines.append(seg_lines.pop(0))

        merged = merge_lines_and_strip('\n'.join(seg_lines))
        if first_segment_processed:
            output.extend('' for _ in leading_empty_lines)

        if merged:
            first_segment_processed = (
                _append_google_summary_merged(
                    output,
                    merged,
                    leading_indent=leading_indent,
                    is_first_segment=not first_segment_processed,
                )
                or first_segment_processed
            )

        output.extend('' for _ in trailing_empty_lines)


def _has_summary_content(items: list[str | list[str]]) -> bool:
    """Return True when buffered pre-section lines contain nonblank text."""
    for item in items:
        if isinstance(item, list):
            if any(line.strip() for line in item):
                return True
            continue

        if item.strip():
            return True

    return False


def _pass2_wrap_google_docstring(
        docstring: str,
        *,
        line_length: int,
        leading_indent: int | None = None,
        closing_indent: int | None = None,
        compact_first_line: bool = False,
        opening_quotes_on_own_line: bool = False,
) -> str:
    """
    Wrap the unwrapped docstring (Pass 2).

    - Splits lines.
    - Segments by wrappability (Literal blocks, etc.).
    - Wraps wrappable segments.
    """
    leading_indent = leading_indent or 0

    # Split into lines
    lines = docstring.splitlines()

    # Segment
    segments = segment_lines_by_wrappability(lines, style='google')

    final_output: list[str] = []
    is_first_line = True
    # ``_is_google_signature`` is intentionally broad. Track section state so
    # labels in Notes/Examples/custom sections wrap as prose instead of taking
    # Args-style continuation indentation.
    in_signature_section = False
    # Track custom bare sections only for wrapping width. Pass one already
    # stopped signature parsing; pass two still needs to wrap custom-section
    # prose without treating the source indentation as part of the text budget.
    custom_section_indent: int | None = None
    in_examples_section = False

    for seg_lines, is_wrappable in segments:
        if not is_wrappable:
            # Code blocks, tables, etc. Keep as is.
            final_output.extend(seg_lines)
            is_first_line = False  # Segments are non-empty
            continue

        # Wrappable text
        # It consists of lines that Pass 1 merged (e.g. signature + inline desc)
        # or separate paragraphs.

        # Pre-process segment: Group consecutive non-signature lines into
        # joined paragraphs to prevent breaking URLs and inline elements.
        # The Examples state is tracked outside the segment loop because code
        # fences and doctests are separate non-wrappable segments.
        processed_lines = _join_paragraph_lines(
            seg_lines,
            leading_indent,
            initial_in_examples_section=in_examples_section,
        )

        line_idx = 0
        while line_idx < len(processed_lines):
            line = processed_lines[line_idx]
            if not line.strip():
                final_output.append(line)
                if opening_quotes_on_own_line and is_first_line:
                    is_first_line = False

                line_idx += 1
                continue

            stripped = line.lstrip()
            indent_str = line[: len(line) - len(stripped)]
            indent_level = len(indent_str)
            if _is_google_section_header(stripped):
                custom_section_indent = None
                in_examples_section = (
                    canonical_google_section_header(stripped) == 'Examples:'
                )
                in_signature_section = _is_google_signature_section_header(
                    stripped
                )
            elif (
                _is_google_unknown_section_header(stripped)
                and indent_level <= leading_indent
            ):
                custom_section_indent = indent_level
                in_examples_section = False
                in_signature_section = False
            elif (
                custom_section_indent is not None
                and indent_level <= custom_section_indent
            ):
                custom_section_indent = None

            if in_examples_section:
                # Check again after paragraph joining so code blocks that were
                # kept intact above do not fall through to ``textwrap.fill``.
                is_examples_code, examples_code_end_idx = (
                    is_google_examples_code_block(
                        processed_lines,
                        line_idx,
                    )
                )
                if is_examples_code:
                    final_output.extend(
                        processed_lines[line_idx:examples_code_end_idx]
                    )
                    is_first_line = False
                    line_idx = examples_code_end_idx
                    continue

            if is_first_line:
                # For first line, calculate total width for textwrap accounting for:
                # - The line's own indentation (already in indent_level)
                # - Additional leading_indent only if line indent < leading_indent
                # - +5 for the opening """ and its quote
                base_indent = leading_indent or 0
                if indent_level < base_indent:
                    # Line has less indent than expected, add the difference
                    indent_level += base_indent - indent_level
                # Add 5 for the opening """ position (3 quotes + space + 1)
                indent_level += 5

            # Check if signature
            # Exclude lines starting with quotes (Summary start)
            if (
                not in_signature_section
                or stripped.startswith(('"""', "'''"))
                or (leading_indent and indent_level < leading_indent)
            ):
                is_sig = False
            else:
                is_sig = _is_google_signature(stripped)

            if is_sig:
                final_output.extend(
                    _wrap_google_signature_line(
                        line,
                        line_length=line_length,
                        indent_str=indent_str,
                    )
                )

            # Normal text paragraph (Summary or Description continuation if failed detection)
            # Just wrap it respecting current indent.

            else:
                if (
                    not in_signature_section
                    and not _is_google_section_header(stripped)
                    and not stripped.rstrip().endswith('::')
                    and _is_google_signature(stripped)
                ):
                    # Preserve existing colon-spacing cleanup for label-like
                    # prose, but keep it on the normal prose wrapping path so
                    # sections such as Notes do not gain signature indents.
                    line = _normalize_google_signature_spacing(line)
                    stripped = line.lstrip()
                    indent_str = line[: len(line) - len(stripped)]
                    indent_level = len(indent_str)

            if not is_sig and is_first_line:
                actual_indent_str = indent_str
                subsequent_indent_str = ' ' * (leading_indent or 0)
                opening_width = (
                    GOOGLE_COMPACT_OPENING_QUOTES_WIDTH
                    if compact_first_line
                    else GOOGLE_OPENING_QUOTES_WIDTH
                )
                first_line_width = max(
                    1,
                    line_length - (leading_indent or 0) - opening_width,
                )
                wrapped_lines = _wrap_first_line_shorter(
                    line.strip(),
                    first_line_width=first_line_width,
                    subsequent_width=line_length,
                    initial_indent=actual_indent_str,
                    subsequent_indent=subsequent_indent_str,
                )
                final_output.extend(wrapped_lines)

            elif not is_sig:
                # Existing logic for other lines
                subsequent_indent = indent_str
                wrap_width = line_length
                if (
                    not opening_quotes_on_own_line
                    and leading_indent is not None
                    and len(indent_str) < leading_indent
                ):
                    subsequent_indent = ' ' * leading_indent
                wrapped = textwrap.fill(
                    line.strip(),
                    width=wrap_width,
                    initial_indent=indent_str,
                    subsequent_indent=subsequent_indent,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                final_output.extend(wrapped.splitlines())

            is_first_line = False
            line_idx += 1

    return finalize_lines(final_output, closing_indent)


def _wrap_google_signature_line(
        line: str,
        *,
        line_length: int,
        indent_str: str,
) -> list[str]:
    """
    Wrap one Google signature line while keeping the signature intact.

    Google signatures can contain spaces inside annotations, so wrapping the
    whole row as prose could split the signature itself. Pass two keeps the
    signature as the first-line prefix and only wraps the description under the
    standard continuation indent.
    """
    normalized_line = _normalize_google_signature_spacing(line)
    sig_part, desc_part = _split_google_signature(normalized_line)
    sig_part_stripped = sig_part.rstrip()
    subsequent_indent = indent_str + '    '

    if len(sig_part_stripped) > line_length:
        output = [sig_part_stripped]
        if desc_part and desc_part.strip():
            output.extend(
                _wrap_google_signature_description(
                    desc_part,
                    line_length=line_length,
                    subsequent_indent=subsequent_indent,
                )
            )

        return output

    if not desc_part or not desc_part.strip():
        return [sig_part_stripped]

    first_line_prefix = sig_part_stripped + ' '
    remaining_first = line_length - len(first_line_prefix)
    first_word = desc_part.split()[0] if desc_part else ''
    if remaining_first < 10 or len(first_word) > remaining_first:
        return [
            sig_part_stripped,
            *_wrap_google_signature_description(
                desc_part,
                line_length=line_length,
                subsequent_indent=subsequent_indent,
            ),
        ]

    wrapped = textwrap.fill(
        desc_part,
        width=line_length,
        initial_indent=first_line_prefix,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped.splitlines()


def _wrap_google_signature_description(
        description: str,
        *,
        line_length: int,
        subsequent_indent: str,
) -> list[str]:
    """Wrap a Google signature description on continuation lines."""
    wrapped = textwrap.fill(
        description,
        width=line_length,
        initial_indent=subsequent_indent,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped.splitlines()


def _wrap_first_line_shorter(
        text: str,
        *,
        first_line_width: int,
        subsequent_width: int,
        initial_indent: str,
        subsequent_indent: str,
) -> list[str]:
    """
    Wrap text with a shorter first line width (for Google-style opening
    quotes).

    The first physical line is wrapped to ``first_line_width`` while later
    lines use ``subsequent_width``. Callers pass a shorter first width because
    compact Google docstrings put content beside the literal opener, and the
    rebuilt literal can preserve prefixes such as ``rf`` before the quotes.

    Parameters: text: The text to wrap (should not include leading whitespace).
    first_line_width: Maximum width for the first line. subsequent_width:
    Maximum width for subsequent lines. initial_indent: Indent string for the
    first line. subsequent_indent: Indent string for subsequent lines.

    Returns: A list of wrapped lines.
    """
    if not text.strip():
        return [initial_indent + text] if text else []

    words = text.split()
    if not words:
        return []

    lines = []
    current_line = initial_indent
    current_width = first_line_width
    is_first_line = True

    for word in words:
        if is_first_line and not lines and current_line == initial_indent:
            current_line = current_line + word
            continue

        # Check if adding this word would exceed the line width
        if current_line == initial_indent or current_line == subsequent_indent:
            # Line is empty (just indent), add word directly
            test_line = current_line + word
        else:
            test_line = current_line + ' ' + word

        if len(test_line) <= current_width:
            current_line = test_line
        else:
            # Word doesn't fit, start a new line
            if current_line.strip():  # Only add non-empty lines
                lines.append(current_line)

            if is_first_line:
                is_first_line = False
                current_width = subsequent_width

            current_line = subsequent_indent + word

    # Add the last line if it has content
    if current_line.strip():
        lines.append(current_line)

    return lines


# Matches the signature prefix before the description delimiter, e.g.
# `arg(type)` or `**kwargs(dict[str, Any])`. We capture the name and
# parenthesized type separately so malformed spacing can be canonicalized
# before the broader signature parser decides whether the line is an entry.
_GOOGLE_TYPED_SIGNATURE_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<name>\*{0,2}[A-Za-z_]\w*)\s*'
    r'(?P<type>\(.+\))$'
)
_GOOGLE_SIGNATURE_BODY_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<name>\*{0,2}[A-Za-z_]\w*)'
    r'(?:\s*\((?P<annotation>.*)\))?$'
)
_GOOGLE_RST_ROLE_SIGNATURE_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<signature>:[^:]+:`[^`]+`:)\s*'
    r'(?P<description>.*)$'
)
_GOOGLE_KNOWN_TYPE_NAMES: Final[set[str]] = {
    'Any',
    'Callable',
    'Dict',
    'Generator',
    'Iterator',
    'List',
    'Mapping',
    'None',
    'Optional',
    'Sequence',
    'Set',
    'Tuple',
    'bool',
    'bytes',
    'complex',
    'dict',
    'float',
    'frozenset',
    'int',
    'list',
    'object',
    'set',
    'str',
    'tuple',
}


def _is_google_section_header(line: str) -> bool:
    """Return True when ``line`` is a recognized Google section header."""
    return is_google_section_header(line)


def _is_google_signature_section_header(line: str) -> bool:
    """
    Return True for sections whose entries use Google signatures.

    Pass two uses this to distinguish real signature rows from label-like prose
    such as ``Warning:`` in ``Notes:``.
    """
    return is_google_signature_section_header(line)


def _is_google_unknown_section_header(stripped_line: str) -> bool:
    """
    Return True for bare, unrecognized Google-style section headers.

    These headers are boundaries, not semantic sections. Recognizing them
    prevents a custom block after ``Args:`` from being parsed as another
    argument while preserving the author's header text.
    """
    return is_google_unknown_section_header(stripped_line)


def _lookup_google_metadata(
        name: str,
        metadata: ParameterMetadata | None,
) -> tuple[str | None, str | None] | None:
    """Return metadata for regular and variadic Google parameter names."""
    if not metadata:
        return None

    meta = metadata.get(name)
    if meta is None and name.startswith('**'):
        meta = metadata.get(name[2:])

    if meta is None and name.startswith('*'):
        meta = metadata.get(name[1:])

    return meta


def _split_google_annotation_pieces(annotation: str) -> list[str]:
    """Split a Google annotation on top-level commas."""
    pieces: list[str] = []
    current: list[str] = []
    bracket_depth = 0
    quote_char = ''

    for char in annotation:
        if quote_char:
            current.append(char)
            if char == quote_char:
                quote_char = ''

            continue

        if char in {'"', "'"}:
            quote_char = char
            current.append(char)
            continue

        if char in '[({':
            bracket_depth += 1
        elif char in '])}' and bracket_depth > 0:
            bracket_depth -= 1

        if char == ',' and bracket_depth == 0:
            piece = ''.join(current).strip()
            if piece:
                pieces.append(piece)

            current = []
            continue

        current.append(char)

    piece = ''.join(current).strip()
    if piece:
        pieces.append(piece)

    return pieces


def _strip_google_metadata_markers(annotation: str) -> str:
    """
    Remove docstring-only optional/default markers before source sync.

    When function metadata supplies the default value, stale ``optional`` or
    existing ``default=...`` text in the docstring should not be preserved as a
    second default marker.
    """
    pieces = []
    for piece in _split_google_annotation_pieces(annotation):
        piece_lower = piece.lower()
        if piece_lower == 'optional':
            continue

        if piece_lower.startswith('default='):
            continue

        pieces.append(piece)

    return ', '.join(pieces)


def _rewrite_google_parameter_signature(
        signature_part: str,
        metadata: ParameterMetadata | None,
) -> str:
    """Rewrite an ``Args:`` or ``Attributes:`` signature from metadata."""
    stripped_colon = signature_part.rstrip()
    if not stripped_colon.endswith(':'):
        return signature_part

    body = stripped_colon[:-1]
    match = _GOOGLE_SIGNATURE_BODY_PATTERN.fullmatch(body)
    if not match:
        return signature_part

    name = match.group('name')
    meta = _lookup_google_metadata(name, metadata)
    if meta is None:
        return signature_part

    annotation, default = meta
    existing_annotation = (match.group('annotation') or '').strip()
    annotation_text = (
        annotation if annotation is not None else existing_annotation
    )
    if default is not None:
        annotation_text = _strip_google_metadata_markers(annotation_text)

    pieces: list[str] = []
    if annotation_text:
        pieces.append(annotation_text)

    if default is not None:
        pieces.append(f'default={default}')

    indent = match.group('indent')
    if not pieces:
        return f'{indent}{name}:'

    return f'{indent}{name} ({", ".join(pieces)}):'


def _looks_like_google_type(text: str) -> bool:
    """
    Return True when a return signature body looks like a type.

    Multi-word strings are only considered type-like when they contain type
    syntax. This keeps prose-only return descriptions from being mistaken for
    annotations during source-sync.
    """
    stripped = text.strip()
    if not stripped:
        return False

    if stripped.endswith(('.', '!', '?')):
        return False

    if any(char.isspace() for char in stripped):
        return any(token in stripped for token in ('[', ']', '|', '"', "'"))

    if any(token in stripped for token in ('[', ']', '|', '.', '"', "'")):
        return True

    return stripped in _GOOGLE_KNOWN_TYPE_NAMES or stripped[:1].isupper()


def _is_google_return_description(stripped_line: str) -> bool:
    """
    Return True when a return item is prose rather than a signature.

    The source annotation is inserted ahead of these lines so syncing a
    ``Returns:`` section does not discard the existing description.
    """
    if not stripped_line or _is_google_section_header(stripped_line):
        return False

    return not _is_google_return_signature(stripped_line)


def _is_google_return_signature(stripped_line: str) -> bool:
    """Return True for Google ``Returns:``/``Yields:`` item signatures."""
    if not stripped_line:
        return False

    if stripped_line.startswith(':'):
        return bool(
            _GOOGLE_RST_ROLE_SIGNATURE_PATTERN.fullmatch(stripped_line)
        )

    if _is_google_section_header(stripped_line):
        return False

    if ':' not in stripped_line:
        return _looks_like_google_type(stripped_line)

    # Labeled prose uses the same delimiter as Google signatures. Reject it
    # here so return sync inserts the annotation without losing the label.
    if _is_google_labeled_return_prose(stripped_line):
        return False

    signature_part, _ = _split_google_signature(stripped_line)
    body = signature_part.rstrip()
    if not body.endswith(':'):
        return False

    return _looks_like_google_return_type_body(body[:-1])


def _looks_like_google_return_type_body(body: str) -> bool:
    """
    Return True when a Google return/yield row names a type.

    Google ``Returns:`` and ``Yields:`` describe values rather than declaring
    named return variables. Type rows such as ``str:`` or ``MyType:`` remain
    syncable signatures; typed variable rows are normalized separately so the
    variable name can be discarded without losing the inline type.
    """
    match = _GOOGLE_SIGNATURE_BODY_PATTERN.fullmatch(body)
    if not match:
        indent_len = len(body) - len(body.lstrip())
        candidate = body[indent_len:].strip()
        return _looks_like_google_type(candidate)

    if match.group('annotation') is not None:
        return False

    return _looks_like_google_type(match.group('name'))


def _is_google_labeled_return_prose(stripped_line: str) -> bool:
    """
    Return True when a colon-bearing Google return item is prose.

    Google return descriptions and signatures both use ``:``. This normalizes
    the signature-shaped prefix before applying the shared prose-label rule so
    common labels like ``Result:`` do not get mistaken for custom types.
    """
    signature_part, description = _split_google_signature(stripped_line)
    if description is None:
        return False

    body = signature_part.rstrip()
    if not body.endswith(':'):
        return False

    label = body[:-1].strip()
    match = _GOOGLE_SIGNATURE_BODY_PATTERN.fullmatch(label)
    if match and match.group('annotation') is None:
        label = match.group('name')

    return _is_labeled_return_prose(label, description)


def _rewrite_google_named_return_signature(
        line: str,
        annotation: str | None,
) -> str | None:
    """
    Return a normalized type row for ``name (type): desc`` returns.

    Google returns and yields do not declare variable names, so the name is
    discarded while the parenthesized type is kept when no synced annotation is
    available.
    """
    signature_part, description = _split_google_signature(line)
    stripped_colon = signature_part.rstrip()
    if not stripped_colon.endswith(':'):
        return None

    body = stripped_colon[:-1]
    match = _GOOGLE_SIGNATURE_BODY_PATTERN.fullmatch(body)
    if not match:
        return None

    existing_annotation = (match.group('annotation') or '').strip()
    if not existing_annotation:
        return None

    if not _looks_like_google_type(existing_annotation):
        return None

    return_type = annotation or existing_annotation
    indent = match.group('indent')
    if description is None:
        return f'{indent}{return_type}'

    return f'{indent}{return_type}: {description}'


def _rewrite_google_return_signature(line: str, annotation: str) -> str:
    """Rewrite a Google ``Returns:``/``Yields:`` signature line."""
    rst_match = _GOOGLE_RST_ROLE_SIGNATURE_PATTERN.fullmatch(line)
    if rst_match:
        desc = rst_match.group('description').strip()
        if desc:
            return f'{rst_match.group("indent")}{annotation}: {desc}'

        return f'{rst_match.group("indent")}{annotation}'

    signature_part, description = _split_google_signature(line)
    if description is None:
        indent_len = len(line) - len(line.lstrip())
        return f'{line[:indent_len]}{annotation}'

    stripped_colon = signature_part.rstrip()
    if not stripped_colon.endswith(':'):
        return line

    body = stripped_colon[:-1]
    match = _GOOGLE_SIGNATURE_BODY_PATTERN.fullmatch(body)
    if not match:
        indent_len = len(body) - len(body.lstrip())
        candidate = body[indent_len:].strip()
        if _looks_like_google_type(candidate):
            return f'{body[:indent_len]}{annotation}: {description}'

        return f'{signature_part} {description}'

    name = match.group('name')
    existing_annotation = match.group('annotation')
    indent = match.group('indent')
    if existing_annotation is not None or not _looks_like_google_type(name):
        return f'{indent}{annotation}: {body.strip()}: {description}'

    return f'{indent}{annotation}: {description}'


def _find_google_signature_colon(line: str) -> int:
    """
    Return the delimiter colon outside brackets and parentheses.

    Google signatures use that colon to separate the signature from the
    description. Skipping nested colons prevents rare type expressions from
    being split in the middle before signature spacing is normalized for
    malformed Google signature fixtures.
    """
    nesting = 0
    for idx, char in enumerate(line):
        if char in '([{':
            nesting += 1
        elif char in ')]}':
            nesting -= 1
        elif char == ':' and nesting == 0:
            return idx

    return -1


def _normalize_google_signature_spacing(line: str) -> str:
    """
    Canonicalize spacing in a Google signature line before parsing.

    This fixes loose forms such as ``arg(type):text`` and ``arg (type) : text``
    so the later signature splitter sees the same shape as a well-formed Google
    entry. This is needed for the strengthened ``colon_spacing_fix`` fixture,
    which now feeds malformed Google syntax instead of only wrapping
    already-valid signatures. Lines without a delimiter colon are left
    untouched because they are continuation text or non-Google entries.
    """
    if line.lstrip().startswith(':'):
        return line

    colon_index = _find_google_signature_colon(line)
    if colon_index == -1:
        return line

    signature = line[:colon_index].rstrip()
    description = line[colon_index + 1 :].strip()

    match = _GOOGLE_TYPED_SIGNATURE_PATTERN.fullmatch(signature)
    if match:
        signature = (
            f'{match.group("indent")}{match.group("name")} '
            f'{match.group("type")}'
        )

    if not description:
        return f'{signature}:'

    return f'{signature}: {description}'


def _is_google_signature(stripped_line: str) -> bool:
    """
    Check if a line looks like a Google style parameter signature. Examples:
    arg1 (int): Description arg2: Description arg3 (list[int] | None):
    Description *args: Description **kwargs: Description
    """
    # Regex:
    # Start of string
    # Optional stars (* or **)
    # Identifier
    # Optional space
    # Optional parens enclosing type
    # Colon
    # (Descripion can follow)

    # Very permissive match on identifiers and types to catch complex types
    # Must end with colon, or colon followed by text.

    # Note: This might match "Note:", "Returns:", etc. if we aren't careful.
    # But we check against `section_headers` outside this function (or caller handles indentation).
    # Also "Returns:" usually has no type in parens in the header itself.

    # Matches:
    # word:
    # word (type):
    # *word:
    # **word:
    # complex[type]:  (for Returns)

    # We want to match "Anything that looks like a signature followed by colon".
    # But we must avoid matching simple text that happens to have a colon,
    # although at the signature indentation level, that IS a signature in Google style.

    # We'll use a broader pattern:
    # Start, any chars not containing newline (non-greedy), colon, end.
    # But we want to ensure it's not JUST a colon.

    if ':' not in stripped_line:
        return False

    # Reject lines that look like URLs or inline links
    # - Starting with < (likely an inline URL like <https://...)
    # - Starting with http: or https:
    if (
        stripped_line.startswith('<')
        or stripped_line.startswith('http:')
        or stripped_line.startswith('https:')
    ):
        return False

    sig, desc = _split_google_signature(stripped_line)

    # Remove the trailing colon
    sig_body = sig.rsplit(':', 1)[0].strip()

    if not sig_body:
        return False

    # Validation Logic:
    # 1. Check for top-level commas (must be inside parens/brackets).
    # 2. Check for number of top-level whitespace-separated tokens.
    #    - Max 2 tokens.
    #    - If 2 tokens, the second must start with '('.

    nesting = 0
    tokens = []
    current_token = []

    for char in sig_body:
        if char in '([{':
            nesting += 1
            current_token.append(char)
        elif char in ')]}':
            nesting -= 1
            current_token.append(char)
        elif char == ',' and nesting == 0:
            # Top-level comma -> Not a signature (unless tuple in parens, covered above)
            return False
        elif char.isspace() and nesting == 0:
            if current_token:
                tokens.append(''.join(current_token))
                current_token = []
        else:
            current_token.append(char)

    if current_token:
        tokens.append(''.join(current_token))

    if nesting != 0:
        return False  # Unbalanced

    # Filter out pipe operators (|) which are used for type unions
    # e.g., "list[int] | None" -> tokens = ["list[int]", "|", "None"]
    # We want meaningful tokens only for validation
    meaningful_tokens = [t for t in tokens if t != '|']

    if not meaningful_tokens:
        return False

    # Type hint detection: recognize type hints by their structural patterns
    # Type hints typically:
    # 1. Contain brackets [] (e.g., list[int], dict[str, Any])
    # 2. Contain pipe operators | (e.g., str | None)
    # 3. Are single identifiers (e.g., int, str, MyType)
    # 4. Follow the pattern "name (type)" for Args
    #
    # In contrast, prose text is multiple plain words without brackets.

    has_brackets = '[' in sig_body
    has_pipe = '|' in tokens

    if has_brackets or has_pipe:
        # Contains type hint patterns - this is a valid signature
        # Don't validate further since type annotations can be arbitrarily complex
        return True

    # No brackets or pipes - use original logic for simple patterns
    # like "arg_name" or "arg_name (type)"
    if len(meaningful_tokens) > 2:
        return False  # Too many parts (likely a sentence)

    if len(meaningful_tokens) == 2:
        # Must be `name (type)` style
        # First part: identifier
        # Second part: starts with (
        if not meaningful_tokens[1].startswith('('):
            return False

    # If 1 token, usually valid (arg or type).
    # e.g. `arg` or `int` or `MyCustomType`.

    return True


# Regex pattern to match various default value formats within parentheses
# Matches: default 10, default is True, default: 3.14, default  :  {}, default=42
_DEFAULT_VALUE_PATTERN = re.compile(
    r'\bdefault\s*(?:is\s*|:\s*|=\s*)?\s*', re.IGNORECASE
)


def _standardize_default_value(signature: str) -> str:
    """
    Standardize default value format to 'default=xxx'.

    Converts various formats:
    - 'default 10' -> 'default=10'
    - 'default is True' -> 'default=True'
    - 'default: 3.14' -> 'default=3.14'
    - 'default  :  {}' -> 'default={}'
    - 'default=42' -> 'default=42' (already correct)

    Parameters
    ----------
    signature : str
        A signature line like 'arg1 (int, default 10):'

    Returns
    -------
    str
        The signature with standardized default value format.
    """
    # Find the parentheses content in the signature
    # Pattern: name (type, default xxx):
    paren_match = re.search(r'\(([^)]*)\)', signature)
    if not paren_match:
        return signature

    paren_content = paren_match.group(1)

    # Check if 'default' is in the parentheses
    if 'default' not in paren_content.lower():
        return signature

    # Find 'default' followed by various delimiters and value
    # Pattern handles: default 10, default is value, default: value, default=value
    # Also handles irregular spacing like 'default  :   {}'
    # The pattern captures:
    # - 'default' keyword
    # - optional separator (is, :, =) with optional whitespace around it
    # - the value (non-whitespace sequence)
    default_pattern = re.compile(
        r'\bdefault\s*(?:is\s+|:\s*|=)?(\S+)', re.IGNORECASE
    )

    def normalize_default(match: re.Match) -> str:
        value = match.group(1)
        return f'default={value}'

    new_paren_content = default_pattern.sub(normalize_default, paren_content)

    # Replace the old parentheses content with the new one
    new_signature = (
        signature[: paren_match.start(1)]
        + new_paren_content
        + signature[paren_match.end(1) :]
    )

    return new_signature


def _split_google_signature(line: str) -> tuple[str, str | None]:
    """
    Split a signature line into the signature part (including colon) and the
    description part. Returns (signature_part, description_part).
    description_part might be None or empty string if nothing follows.
    """
    rst_match = _GOOGLE_RST_ROLE_SIGNATURE_PATTERN.fullmatch(line)
    if rst_match:
        # rST roles start with a colon, so the generic delimiter scanner would
        # split before the role name. Keep the whole role as the signature so
        # the description wraps under Google's continuation indent.
        sig = f'{rst_match.group("indent")}{rst_match.group("signature")}'
        desc = rst_match.group('description')
        if not desc.strip():
            return sig, None

        return sig, desc.strip()

    colon_index = _find_google_signature_colon(line)
    if colon_index == -1:
        return line, None

    sig = line[: colon_index + 1]
    desc = line[colon_index + 1 :]

    if not desc.strip():
        return sig, None

    return sig, desc.strip()


def _dedent_lines(
        lines: list[str],
        base_indent: int,
        *,
        has_inline_description: bool,
) -> list[str]:
    """
    Return description lines relative to the Google item indentation.

    Pass one stores inline text from ``arg: text`` without leading
    indentation, but stores following description lines exactly as they appear
    in the docstring. Later wrapping re-indents preserved blocks relative to
    the item, so block lines must first be shifted to a common baseline. When
    no inline description exists, the first collected line is part of that
    block too; dedenting it prevents lists and tables from being indented
    twice.
    """
    if not lines:
        return lines

    if has_inline_description and len(lines) <= 1:
        return lines

    block_start_idx = 1 if has_inline_description else 0
    block_lines = lines[block_start_idx:]

    # Strip only the common block indent. Full stripping would destroy relative
    # indentation inside tables, literal blocks, and nested lists.
    indents = []
    for l in block_lines:
        if l.strip():
            indents.append(len(l) - len(l.lstrip()))

    min_indent = min(indents) if indents else 0

    out = []
    if has_inline_description:
        # The inline description is already in item-relative coordinates.
        out.append(lines[0])

    for l in block_lines:
        if l.strip():
            out.append(l[min_indent:])
        else:
            out.append('')

    return out
