import re
import textwrap
from typing import Final

from format_docstring.line_wrap_numpy import (
    _split_tuple_annotation,
    _unwrap_generator_annotation,
)
from format_docstring.line_wrap_utils import (
    ParameterMetadata,
    add_leading_indent,
    finalize_lines,
    is_code_fence,
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
    return_components: list[str] | None = (
        _split_tuple_annotation(return_annotation_str)
        if return_annotation_str is not None
        else None
    )
    return_component_index = 0
    return_signature_style_determined = False
    return_use_multiple_signatures = False

    def flush_summary_before_section() -> None:
        """
        Compact only the leading summary before emitting a section header.

        Google end-to-end formatting can put the first summary sentence beside
        the opening quotes. Once a real or custom section starts, later lines
        must keep section structure instead of being merged into the summary.
        """
        if not (compact_first_line and not current_section and temp_out):
            return

        summary_lines_flat = []
        for item in temp_out:
            if isinstance(item, list):
                summary_lines_flat.extend(item)
            else:
                summary_lines_flat.append(item)

        segments = segment_lines_by_wrappability(
            summary_lines_flat, style='google'
        )

        temp_out.clear()
        first_segment_processed = False

        for seg_lines, is_wrappable in segments:
            if is_wrappable:
                trailing_empty_lines = []
                while seg_lines and not seg_lines[-1].strip():
                    trailing_empty_lines.append(seg_lines.pop())

                trailing_empty_lines.reverse()

                leading_empty_lines = []
                while seg_lines and not seg_lines[0].strip():
                    leading_empty_lines.append(seg_lines.pop(0))

                merged = merge_lines_and_strip('\n'.join(seg_lines))

                if first_segment_processed:
                    for _ in leading_empty_lines:
                        temp_out.append('')

                if merged:
                    first_segment_processed = (
                        _append_google_summary_merged(
                            temp_out,
                            merged,
                            leading_indent=leading_indent,
                            is_first_segment=(
                                not first_segment_processed
                            ),
                        )
                        or first_segment_processed
                    )

                for _ in trailing_empty_lines:
                    temp_out.append('')
            else:
                temp_out.extend(seg_lines)
                first_segment_processed = True

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

        # Section detection
        # Google style sections are typically "Name:" at the same indentation level as the summary (or slightly indented if nested)
        # We'll assume top-level sections match the leading_indent if provided, or are just identifiers ending in colon.
        # But for robustness, we check if the line matches a known section header.
        canonical = canonical_google_section_header(stripped)
        if canonical is not None:
            # If we were in summary mode (empty current_section), we need to process the accumulated summary lines?
            # Actually, `temp_out` holds lines in order.
            # We haven't been "unwrapping" summary lines in the loop.
            # We just appended them.
            # So `temp_out` currently contains [Line 1, Line 2, ...] of summary (wrapped separately).
            # But the requirement is to unwrap them.

            # Since we are iterating once, we can back-patch?
            # Or we can detect "Header found" and say "Everything before this was summary, go modify temp_out".

            if compact_first_line and not current_section and temp_out:
                # We have summary lines in temp_out.
                # Identify the summary block range.
                # It's everything in temp_out so far.

                # We need to process these lines with `segment_lines_by_wrappability` + merge.
                # But `temp_out` contains strings, so it matches.
                # However, we must be careful about `temp_out` structure: `list[str | list[str]]`.
                # `process_temp_output` does wrapping.
                # But here we want to UNwrap (merge lines).

                # Let's extract all lines, clean them up, segment, merge, and replace in temp_out.

                # Flatten current temp_out
                summary_lines_flat = []
                for item in temp_out:
                    if isinstance(item, list):
                        summary_lines_flat.extend(item)
                    else:
                        summary_lines_flat.append(item)

                # We also need to strip base indentation from them?
                # `add_leading_indent` added indentation.
                # But summary text usually starts after `"""` on same line (no indent) OR next lines (indented).
                # `docstring_` has leading indent normalized?
                # `leading_indent` param is the indent of the docstring BLOCK.
                # `add_leading_indent` ensures it starts with `\n` + indent.
                # So standard lines should have that indent.

                # Let's strip the common indent (likely `leading_indent`) to process text.
                # But `docstring_` was passed to splitlines().
                # If we strip, we lose relative indentation for `::` blocks?
                # `segment_lines_by_wrappability` respects `::` blocks (indented literal blocks).
                # But it expects lines to be relative to "0" or consistent?

                # If we blindly merge wrapable lines, `merge_lines_and_strip` handles the newlines.

                # Re-process summary
                new_summary = []

                # Dedent slightly for processing?
                # Actually, `segment_lines_by_wrappability` looks for `::`

                segments = segment_lines_by_wrappability(
                    summary_lines_flat, style='google'
                )

                temp_out.clear()
                first_segment_processed = False

                for seg_lines, is_wrappable in segments:
                    if is_wrappable:
                        # Check for trailing empty lines
                        trailing_empty_lines = []
                        while seg_lines and not seg_lines[-1].strip():
                            trailing_empty_lines.append(seg_lines.pop())

                        trailing_empty_lines.reverse()

                        # Check for leading empty lines
                        leading_empty_lines = []
                        while seg_lines and not seg_lines[0].strip():
                            leading_empty_lines.append(seg_lines.pop(0))

                        # Unwrap (merge)
                        merged = merge_lines_and_strip('\n'.join(seg_lines))

                        # Append leading empty lines
                        if not first_segment_processed:
                            # Skip all leading empty lines for the very first segment
                            # (or if we haven't processed any segments yet)
                            # to ensure docstring starts with text immediately after quotes.
                            pass
                        else:
                            for _ in leading_empty_lines:
                                temp_out.append('')

                        if merged:
                            first_segment_processed = (
                                _append_google_summary_merged(
                                    temp_out,
                                    merged,
                                    leading_indent=leading_indent,
                                    is_first_segment=(
                                        not first_segment_processed
                                    ),
                                )
                                or first_segment_processed
                            )

                        # Re-add trailing empty lines (indented)
                        indent_s = ' ' * (leading_indent or 0)
                        for l in trailing_empty_lines:
                            # If empty line, just newline? Or indented?
                            # finalize_lines trims whitespace-only lines to empty strings usually.
                            # But `temp_out` items are lines.
                            # If we add "", it becomes empty line.
                            # If we add "    ", it becomes indented empty line.
                            # Let's add "" to be safe/clean.
                            temp_out.append('')
                    else:
                        # Unwrappable (e.g. `::` block). Should be kept as is.
                        # `segment_lines_by_wrappability` returns original lines.
                        temp_out.extend(seg_lines)
                        first_segment_processed = (
                            True  # We have emitted content
                        )

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
            flush_summary_before_section()
            current_section = stripped.lower()
            current_section_indent = indent_length
            temp_out.append(line)
            i += 1
            continue

        # 2. Signature detection & Unwrapping
        # We only apply this logic inside specific sections
        # Use section sets to support variant spellings (e.g., "parameter:", "return:")
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

            if is_return_section and return_annotation_str is not None:
                if not return_signature_style_determined:
                    return_use_multiple_signatures = (
                        _detect_multiple_google_return_signatures(
                            lines,
                            i,
                            current_section,
                        )
                    )
                    return_signature_style_determined = True

                desired_annotation = return_annotation_str
                if (
                    return_use_multiple_signatures
                    and return_components
                    and return_component_index < len(return_components)
                ):
                    desired_annotation = return_components[
                        return_component_index
                    ]
                    return_component_index += 1
                elif (
                    return_use_multiple_signatures
                    and return_components
                    and return_component_index >= len(return_components)
                ):
                    desired_annotation = return_components[-1]

                if is_yields_section:
                    desired_annotation = (
                        _unwrap_generator_annotation(desired_annotation)
                        or desired_annotation
                    )

                if _is_google_return_signature(standardized_stripped):
                    standardized_line = _rewrite_google_return_signature(
                        standardized_line,
                        desired_annotation,
                    )
                    standardized_stripped = standardized_line.lstrip()
                elif _is_google_return_description(standardized_stripped):
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
            if is_return_section and return_annotation_str is not None:
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

                    if next_indent <= current_item_indent:
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

                # Process the collected description
                # We need to compute the "common indent" of the description lines to treat them as text blocks.
                # But wait, we want to unwrap onto the signature line.
                # The signature line effectively establishes the "indentation of the description" for the first paragraph.

                # Let's clean up description lines:
                # If they were on new lines, they have indentation. We should strip that relative indentation.
                processed_desc_lines = _dedent_lines(
                    description_lines, current_item_indent
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
                        # Merge text
                        # Check for trailing empty lines in the first segment
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
                        # Append to signature

                        # If signature line ended with space? It usually ends with colon.
                        # We want "Sig: Description".
                        if merged_text:
                            # If merged text has paragraphs (newlines), we must re-indent valid paragraphs
                            # to the item's continuation indent level so Pass 2 treats them as indented.
                            merged_lines = merged_text.splitlines()

                            # First line is inline, no indent needed (joined with signature)
                            sig_combined = (
                                f'{signature_part} {merged_lines[0]}'
                            )

                            if len(merged_lines) > 1:
                                # Start with inline line
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

                        # Add remaining segments

                        # First, re-add trailing empty lines from the first segment (once)
                        indent_str = ' ' * (current_item_indent + 4)
                        for l in trailing_empty_lines:
                            remaining_lines_to_append.append('')

                        for seg_lines, _ in segments[1:]:
                            # These need to be indented properly relative to the docstring base?
                            # Or relative to the item?
                            # Standard Google style continuation lines are indented 4 spaces (or more) from the signature start.
                            # Or they align with the description start.
                            # Since we are modifying the first line indent, let's play it safe and indent them
                            # relative to the item indent + 4 spaces.
                            # But `seg_lines` here are stripped of their ORIGINAL indentation relative to the item.
                            # We need to re-indent them.

                            # Wait, segment_lines_by_wrappability returns lines as they were passed in.
                            # But we passed in dedented lines.
                            # So we need to re-add indentation.

                            # indent_str is already calculated above
                            for l in seg_lines:
                                remaining_lines_to_append.append(
                                    indent_str + l if l.strip() else ''
                                )

                    else:
                        # First segment is NOT wrappable (e.g. table immediately).
                        # Keep it on new lines (standard flow).
                        # Or should we try to append? Usually tables start on new line.
                        # We'll just dump everything back as is, but maybe re-indented?
                        # If we touch nothing, we might strictly satisfy "only unwrap... except for these cases".
                        # Case 1 says "presreved without wrapping".
                        # So if we have a table, we append the lines.
                        # But wait, `inline_desc` might have been part of it?
                        # If valid table starts on the same line as signature? unlikely.

                        # If we have content, we just add it to remaining
                        new_signature_line = signature_part  # No inline description if it was part of unwrappable?
                        # Actually if `inline_desc` existed, it's passed to segmenter.
                        # If segmenter says "Unwrappable", it implies it matched the rules.
                        # For now let's just re-add them.

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
                    # No description content
                    new_signature_line = (
                        signature_part.rstrip()
                    )  # Ensure no trailing space if empty desc

                # Add the new signature line
                temp_out.append(new_signature_line)
                # Add any remaining lines that couldn't be unwrapped (tables etc)
                temp_out.extend(remaining_lines_to_append)

                # Advance i
                i = j
                continue

        # Default behaviour for non-signature lines or unknown sections
        temp_out.append(line)
        i += 1

    # Finally, process the output (this currently does the wrapping for other lines via the NumPy logic,
    # but we will skip that for this phase or reuse `process_temp_output` which does generic wrapping.
    # The prompt says "unwrap...", effectively we are doing that above.
    # `process_temp_output` wraps lines that are too long.
    # We want to run that to ensure everything else is wrapped?
    # Actually, the user instruction focused on "intermediate step": "unwrap... regardless of line length".
    # So we probably shouldn't run standard wrapping on the modified lines yet?
    # Or maybe we should? "base indentation level" was requested.
    # Let's return the lines we constructed.

    # We should probably flatten the list first.
    final_lines: list[str] = []
    for item in temp_out:
        if isinstance(item, list):
            final_lines.extend(item)
        else:
            final_lines.append(item)

    if compact_first_line and not current_section and temp_out:
        summary_lines_flat = []
        for item in temp_out:
            if isinstance(item, list):
                summary_lines_flat.extend(item)
            else:
                summary_lines_flat.append(item)

        segments = segment_lines_by_wrappability(
            summary_lines_flat,
            style='google',
        )
        temp_out.clear()
        first_segment_processed = False
        for seg_lines, is_wrappable in segments:
            if not is_wrappable:
                temp_out.extend(seg_lines)
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
            if not first_segment_processed:
                if merged:
                    first_segment_processed = (
                        _append_google_summary_merged(
                            temp_out,
                            merged,
                            leading_indent=leading_indent,
                            is_first_segment=True,
                        )
                        or first_segment_processed
                    )
            else:
                temp_out.extend('' for _ in leading_empty_lines)
                if merged:
                    _append_google_summary_merged(
                        temp_out,
                        merged,
                        leading_indent=leading_indent,
                        is_first_segment=False,
                    )

            temp_out.extend('' for _ in trailing_empty_lines)

    return finalize_lines(temp_out, closing_indent)


def _join_paragraph_lines(
        lines: list[str],
        leading_indent: int | None,
) -> list[str]:
    """
    Group consecutive non-signature lines into joined paragraphs.

    This prevents URLs and inline elements from being broken across lines when
    individual lines are wrapped. Signatures (lines matching Google-style
    parameter patterns) are kept separate.

    Parameters
    ----------
    lines : list[str]
        The lines from a wrappable segment.
    leading_indent : int | None
        The leading indentation level.

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

    for line in lines:
        if not line.strip():
            # Empty line - flush current paragraph and preserve empty line
            flush_paragraph()
            result.append(line)
            continue

        stripped = line.lstrip()
        indent_str = line[: len(line) - len(stripped)]

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
        processed_lines = _join_paragraph_lines(seg_lines, leading_indent)

        for line in processed_lines:
            if not line.strip():
                final_output.append(line)
                if opening_quotes_on_own_line and is_first_line:
                    is_first_line = False

                continue

            stripped = line.lstrip()
            indent_str = line[: len(line) - len(stripped)]
            indent_level = len(indent_str)
            if _is_google_section_header(stripped):
                custom_section_indent = None
                in_signature_section = _is_google_signature_section_header(
                    stripped
                )
            elif (
                _is_google_unknown_section_header(stripped)
                and indent_level <= leading_indent
            ):
                custom_section_indent = indent_level
                in_signature_section = False
            elif (
                custom_section_indent is not None
                and indent_level <= custom_section_indent
            ):
                custom_section_indent = None

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
                # It is a signature line, possibly with merged description.
                # Pass one skips signature parsing in unknown sections, but
                # pass two may still see signature-shaped prose such as
                # ``See Also`` entries. Normalize here so colon spacing remains
                # stable without reclassifying the surrounding section.
                line = _normalize_google_signature_spacing(line)
                sig_part, desc_part = _split_google_signature(
                    line
                )  # Keeps indentation on sig_part

                # Check wrapping strategy
                # If sig_part itself is too long for the FIRST line?
                # We need to account for existing indent.
                # sig_part includes the indent.

                # Strategy 1: "if the signature itself ... keys exceeded the line length limit"
                if len(sig_part.rstrip()) > line_length:
                    # Case A: Long signature.
                    # Use them as 1st line.
                    final_output.append(sig_part.rstrip())

                    # Remaining description goes to next lines
                    if desc_part and desc_part.strip():
                        # Indent + 4
                        subsequent_indent = indent_str + '    '
                        # Wrap description
                        wrapped_desc = textwrap.fill(
                            desc_part,
                            width=line_length,
                            initial_indent=subsequent_indent,
                            subsequent_indent=subsequent_indent,
                            break_long_words=False,
                            break_on_hyphens=False,
                        )
                        final_output.extend(wrapped_desc.splitlines())

                else:
                    # Case B: Signature fits.
                    # We try to put description on the same line if possible.

                    # But wait, Pass 1 merged them. So `line` IS "sig fit desc ...".
                    # We can use textwrap.fill with `initial_indent` matching `sig_part`?
                    # No, `sig_part` contains text.

                    # We want:
                    # Line 1: indent + sig + space + desc_chunk
                    # Line 2+: indent + 4 + desc_chunk

                    # We can achieve this by setting `initial_indent` to `indent_str` (Pass 1 signature already has indent),
                    # and providing the *content* as `sig_stripped + " " + desc`.
                    # But textwrap might break the signature?
                    # "if the signature itself ... use them as 1st line EVEN if they exceed".
                    # If we use textwrap, it might wrap a long signature if we treat it as words.

                    # So proper way:
                    # 1. Start with `sig_part`.
                    # 2. Append description text.

                    if not desc_part or not desc_part.strip():
                        final_output.append(sig_part.rstrip())
                        continue

                    # We have description.
                    # Calculate strict available space on first line.
                    # This is tricky because we don't want to break the signature itself.

                    # Let's try to verify if `sig_part` + first word of desc fits?
                    # Actually, we can use `textwrap` on the DESCRIPTION only, with specific indentation logic.

                    # Calculate remaining width on first line:
                    sig_len = len(
                        sig_part.rstrip()
                    )  # This includes indentation
                    # Space after colon? `sig_part` from `_split` includes colon.
                    # Pass 1 added a space if merging description.
                    # But `_split` splits at colon.
                    # The `line` from Pass 1 is `sig: desc`.
                    # `sig_part` is `   sig:`. `desc_part` is ` desc`. (leading space preserved?)
                    # `_split_google_signature` strips the description if separate return.
                    # But here we are calling it on the full line.
                    # Check `_split_google_signature` impl in file.
                    # It returns `desc.strip()`. So logic above `desc_part` has NO leading space.

                    # We need to insert a space.
                    first_line_prefix = sig_part.rstrip() + ' '
                    subsequent_indent = indent_str + '    '

                    # We want to wrap `desc_part`.
                    # The first line of description should appear after `first_line_prefix`.
                    # But `textwrap` doesn't support "prefix that assumes X chars already used".
                    # It supports `initial_indent`.

                    # Workaround:
                    # Wrap the description with `initial_indent=""` (effectively) and `subsequent_indent=subsequent_indent`.
                    # Then PREPEND `first_line_prefix` to the first line?
                    # But that assumes the first line of wrapped description fits in the remaining space.
                    # We need to tell textwrap the `width` of the first line is smaller.

                    # `textwrap` doesn't check first line width vs others separately easily.

                    # Alternative: Construct a long string `sig + " " + desc`.
                    # Use `textwrap.fill` with `subsequent_indent=subsequent_indent`.
                    # But we must ensure it doesn't break inside `sig`.
                    # `sig` usually has spaces `arg (type):`.
                    # If we treat it as one word (replace spaces with non-breaking?), textwrap will keep it together.
                    # But that seems hacking.

                    # Better approach:
                    # Use `textwrap.TextWrapper`.
                    # Manually handle first line.

                    wrapper = textwrap.TextWrapper(
                        width=line_length,
                        initial_indent='',  # We'll prepend sig manually
                        subsequent_indent=subsequent_indent,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )

                    # Calculate available width for the first line
                    # strict: `line_length` - `len(first_line_prefix)`
                    remaining_first = line_length - len(first_line_prefix)

                    if (
                        remaining_first < 10
                    ):  # Heuristic: if very little space, force wrap?
                        # Force wrap (same as Long Signature logic effectively)
                        final_output.append(sig_part.rstrip())
                        wrapped = textwrap.fill(
                            desc_part,
                            width=line_length,
                            initial_indent=subsequent_indent,
                            subsequent_indent=subsequent_indent,
                            break_long_words=False,
                            break_on_hyphens=False,
                        )
                        final_output.extend(wrapped.splitlines())
                    else:
                        # Heuristic: If the first word doesn't fit in the remaining space on the first line,
                        # force wrap to the next line.
                        # This prevents "Sig: VeryLongWord..." from overflowing the first line.
                        first_word = desc_part.split()[0] if desc_part else ''
                        if (
                            remaining_first < 10
                            or len(first_word) > remaining_first
                        ):
                            # Force wrap
                            final_output.append(sig_part.rstrip())
                            wrapped = textwrap.fill(
                                desc_part,
                                width=line_length,
                                initial_indent=subsequent_indent,
                                subsequent_indent=subsequent_indent,
                                break_long_words=False,
                                break_on_hyphens=False,
                            )
                            final_output.extend(wrapped.splitlines())
                            continue

                        # Try to fit first chunk
                        # We can construct the full text and define `initial_indent` as the signature?
                        # But `textwrap` counts `initial_indent` length against `width`.
                        # If `initial_indent` (signature) is long, it reduces separation.
                        # This matches the requirement!
                        # "Treat the whole description as the remaining contents" -> implies standard wrapping.

                        # So:
                        # filled = textwrap.fill(
                        #    sig_part.strip() + " " + desc_part,
                        #    width=line_length,
                        #    initial_indent=indent_str,  <-- Wait, we want `sig_part` AS the indent?
                        #    subsequent_indent=subsequent_indent
                        # )
                        # If we use `initial_indent=indent_str`, `textwrap` will put `sig...` after it.
                        # It might break `sig...` if it has spaces.

                        # We want `sig_part` to be treated as an atomic unit?
                        # Not necessarily. Standard Google style:
                        # arg (very long type): description
                        # If type wraps? Usually types don't wrap in signature line.
                        # They wrap indent+4.

                        # The user requirement (1): "if the signature itself ... exceeded ... use them as 1st line".
                        # This implies we DON'T want to wrap the signature itself.

                        # So if we are in this `else` block (Case B), `sig_part` fits in `line_length`.
                        # We want to keep it intact.

                        # Let's try to construct a custom initial indent string: `sig_part + " "`.
                        # But `sig_part` has `indent_str`.
                        # So `full_sig = sig_part.rstrip() + " "`.
                        # `textwrap.fill(desc_part, initial_indent=full_sig, subsequent_indent=subsequent_indent)`?
                        # `textwrap` will treat `initial_indent` as literally indentation chars?
                        # No, it just prepends it to the first line.
                        # AND it counts its length.
                        # This is EXACTLY what we want.

                        full_sig = sig_part.rstrip() + ' '

                        # Note: `sig_part` already includes the leading indentation of the line (e.g. 4 spaces).
                        # So `full_sig` is "    arg (type): ".
                        # `subsequent_indent` is "        ".

                        wrapped = textwrap.fill(
                            desc_part,
                            width=line_length,
                            initial_indent=full_sig,
                            subsequent_indent=subsequent_indent,
                            break_long_words=False,
                            break_on_hyphens=False,
                        )
                        final_output.extend(wrapped.splitlines())

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
                elif (
                    custom_section_indent is not None
                    and indent_level > custom_section_indent
                ):
                    wrap_width += leading_indent

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

    return finalize_lines(final_output, closing_indent)


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
    r'^(?P<indent>\s*):[^:]+:`[^`]+`:\s*(?P<description>.*)$'
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
    if _is_google_section_header(stripped_line):
        return False

    if not stripped_line.endswith(':') or stripped_line.endswith('::'):
        return False

    title = stripped_line[:-1].strip()
    return bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]*', title))


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
    return (
        bool(stripped_line)
        and ':' not in stripped_line
        and not _is_google_section_header(stripped_line)
        and not _looks_like_google_type(stripped_line)
    )


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

    return _is_google_signature(stripped_line)


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
    is_named_return = (
        existing_annotation is not None or not _looks_like_google_type(name)
    )
    indent = match.group('indent')
    if is_named_return:
        return f'{indent}{name} ({annotation}): {description}'

    return f'{indent}{annotation}: {description}'


def _detect_multiple_google_return_signatures(
        lines: list[str],
        start_idx: int,
        current_section: str,
) -> bool:
    """
    Return True if the current return/yield section has multiple items.

    Tuple annotations should only be split when the docstring already lists
    multiple top-level return entries; a single tuple entry keeps the complete
    tuple annotation.
    """
    start_line = lines[start_idx]
    start_indent = len(start_line) - len(start_line.lstrip())
    j = start_idx + 1
    while j < len(lines):
        candidate = lines[j]
        stripped = candidate.lstrip()
        if _is_google_section_header(stripped):
            break

        if not candidate.strip():
            j += 1
            continue

        indent = len(candidate) - len(stripped)
        if indent == start_indent and _is_google_return_signature(stripped):
            return True

        if indent < start_indent:
            break

        j += 1

    return False


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
    Splits a signature line into the signature part (including colon) and the
    description part. Returns (signature_part, description_part).
    description_part might be None or empty string if nothing follows.
    """
    # We want the FIRST colon that isn't inside brackets?
    # Type hints can contain slices `Dict[str, int]`.
    # `arg: Dict[str, int]` -> Colon at 3.
    # `Returns: Dict[str, int]` -> Colon at 7.
    # `dict[str, str]:` -> Colon at end.
    # What if `Callable[[int], int]:` ?
    # We strictly want the colon that ENDS the signature.
    # In "name (type): desc", it's the colon after `)`.
    # In "type:", it's the colon at end.

    # Simple heuristic: The colon is likely followed by space or EOL.
    # And if parens/brackets are balanced?

    # Actually, Google style requires "name (type): description".
    # The colon is a separator.
    # Let's use `partition` but we have to be careful about `dict[a:b]`.
    # `dict[int, slice(1:5)]` -> rare in signature naming?
    # Types usually don't have colons *unless* they are callable or slices.

    # If we assume the colon is the "main" delimiter.
    # Let's find the colon that is followed by space or end of string.
    # And check balance?

    # For this task, we'll try simple split on first colon,
    # but we might need to be smarter if types have colons.
    # For `dict[str, str]:`, first colon is at end. Safe.
    # For `Callable[[int, int], str]:`, first colon is inside? No `Callable` uses commas/arrows.
    # Slices `MyType[1:2]`? Rare in docstrings.

    colon_index = _find_google_signature_colon(line)
    if colon_index == -1:
        return line, None

    sig = line[: colon_index + 1]
    desc = line[colon_index + 1 :]

    if not desc.strip():
        return sig, None

    return sig, desc.strip()


def _dedent_lines(lines: list[str], base_indent: int) -> list[str]:
    """
    Dedents lines relative to the base indent of the item. Ideally, we assume
    lines are indented more than base_indent. We just strip common whitespace?
    Or strip explicitly? Let's just lstrip() and rely on logic elsewhere? No,
    ``segment_lines_by_wrappability`` expects raw strings. If we stick to
    "unwrapping", whitespace handling is key. We just want the TEXT content. So
    for text segments, we will merge_lines_and_strip anyway which handles
    whitespace. For code/tables, we likely want to PRESERVE the relative
    indentation structure? In this phase, let's just use the line contents.
    """
    # Simple strategy: just pass the lines. `merge_lines_and_strip` handles text.
    # For preserved blocks (tables), they need indentation.
    # We stripped them from the file.
    # If we return them, we need to know how much to indent.
    # In `wrap_docstring_google` we re-indent by `current_item_indent + 4`.
    # So here we probably want to strip the "extra" indentation so they are uniform?
    # Let's leave them as-is for now, but handle the first line (inline) specially.

    # Actually, `description_lines` contains [inline_desc, next_line_1, next_line_2].
    # inline_desc has valid text.
    # next_line_1 includes the indentation.
    # If we treat next_line_1 as text, we want to strip that indentation.
    dedented = []
    for idx, l in enumerate(lines):
        if idx == 0:
            dedented.append(
                l
            )  # Inline desc is already stripped of leading 'sig:'
        else:
            dedented.append(
                l.strip()
            )  # Strip completely for text merging purposes?

    # Wait, stripping completely destroys table formatting.
    # We must only strip the "base indentation" of the description block.
    # Which is unknown but likely `base_indent + 4` or `base_indent + 2`.
    # Let's calculate common indent of lines [1:]

    if len(lines) <= 1:
        return lines  # Just inline desc

    # Calculate min indent of lines 1..N (ignoring empties)
    indents = []
    for l in lines[1:]:
        if l.strip():
            indents.append(len(l) - len(l.lstrip()))

    min_indent = min(indents) if indents else 0

    out = []
    # Add first line (inline)
    out.append(lines[0])
    # Add rest, shifted by min_indent
    for l in lines[1:]:
        if l.strip():
            # If we strip `min_indent`, we preserve relative structure (important for tables)
            out.append(l[min_indent:])
        else:
            out.append('')

    return out
