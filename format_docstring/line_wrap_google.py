import re
import textwrap
from dataclasses import dataclass
from typing import Final

from format_docstring.line_wrap_numpy import (
    _fix_rst_backticks,
    _unwrap_generator_annotation,
)
from format_docstring.line_wrap_utils import (
    ParameterMetadata,
    _is_labeled_return_prose,
    add_leading_indent,
    finalize_lines,
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
GOOGLE_MIN_SIGNATURE_DESC_WIDTH: Final[int] = 10
GOOGLE_SIGNATURE_MAX_TOKENS: Final[int] = 2


@dataclass(slots=True)
class _GooglePass1State:
    """Mutable state for pass-one Google section scanning."""

    output: list[str]
    current_section: str = ''
    current_section_indent: int = 0


@dataclass(slots=True)
class _GoogleSignatureSectionInfo:
    """Normalized facts about the active Google signature section."""

    section_lower: str
    is_return_section: bool
    is_yields_section: bool
    metadata: ParameterMetadata | None


@dataclass(slots=True)
class _GoogleSignatureCandidate:
    """Standardized candidate line and its signature classification."""

    line: str
    is_signature: bool


@dataclass(slots=True)
class _GoogleUnwrappedSignatureItem:
    """Pass-one output for one consumed Google signature item."""

    lines: list[str]
    next_index: int


@dataclass(slots=True)
class _GoogleLineParts:
    """A line split into indentation and stripped text."""

    line: str
    stripped: str
    indent_str: str
    indent_level: int


@dataclass(slots=True)
class _GoogleParagraphJoinState:
    """Mutable state for joining ordinary Google prose paragraphs."""

    result: list[str]
    paragraph_lines: list[str]
    paragraph_indent: str
    leading_indent: int | None
    in_examples_section: bool


@dataclass(slots=True)
class _GoogleWrapState:
    """Mutable state for pass-two Google wrapping."""

    output: list[str]
    leading_indent: int
    line_length: int
    compact_first_line: bool
    opening_quotes_on_own_line: bool
    is_first_line: bool = True
    in_signature_section: bool = False
    custom_section_indent: int | None = None
    in_examples_section: bool = False


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
        include_arg_types: bool = True,
        include_arg_defaults: bool = True,
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
        include_arg_types=include_arg_types,
        include_arg_defaults=include_arg_defaults,
        compact_first_line=should_compact_first_line,
    )

    return _pass2_wrap_google_docstring(
        unwrapped,
        line_length=line_length,
        leading_indent=leading_indent,
        closing_indent=closing_indent,
        compact_first_line=should_compact_first_line,
        opening_quotes_on_own_line=opening_quotes_on_own_line,
    )


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
        # Kept for parity with the NumPy pass signature.
        line_length: int,  # noqa: ARG001
        leading_indent: int | None = None,
        closing_indent: int | None = None,
        parameter_metadata: ParameterMetadata | None = None,
        return_annotation: str | None = None,
        attribute_metadata: ParameterMetadata | None = None,
        include_arg_types: bool = True,
        include_arg_defaults: bool = True,
        compact_first_line: bool = False,
) -> str:
    """
    Wrap Google-style docstrings.

    Phase 1 implementation:
    - Calculates base indentation.
    - Identifies sections (Args, Returns, etc.).
    - Preserves fenced code blocks before section parsing.
    - Identifies signature lines.
    - Unwraps descriptions onto the signature line.
    """
    docstring_ = _normalize_google_docstring_indent(
        docstring,
        leading_indent,
    )
    lines: list[str] = docstring_.splitlines()
    if not lines:
        return docstring_

    state = _GooglePass1State(output=[])
    line_idx: int = 0
    return_annotation_str: str | None = (
        return_annotation.strip() if return_annotation else None
    )

    while line_idx < len(lines):
        parts = _split_google_line(lines[line_idx])

        if not parts.line.strip():
            state.output.append(parts.line)
            line_idx += 1
            continue

        protected_end_idx = _consume_google_protected_block(lines, line_idx)
        if protected_end_idx is not None:
            state.output.extend(lines[line_idx:protected_end_idx])
            line_idx = protected_end_idx
            continue

        canonical = canonical_google_section_header(parts.stripped)
        if canonical is not None:
            _compact_pending_google_summary(
                state,
                compact_first_line=compact_first_line,
                leading_indent=leading_indent,
            )
            _emit_google_section_header(state, parts, canonical)
            line_idx += 1
            continue

        if _is_google_unknown_section_boundary(state, parts):
            _compact_pending_google_summary(
                state,
                compact_first_line=compact_first_line,
                leading_indent=leading_indent,
            )
            _emit_google_unknown_section_header(state, parts)
            line_idx += 1
            continue

        if is_google_signature_section_header(state.current_section):
            section_info = _google_signature_section_info(
                state.current_section,
                parameter_metadata,
                attribute_metadata,
            )
            signature_item = _unwrap_google_signature_item(
                lines,
                line_idx,
                parts,
                section_info,
                return_annotation_str,
                include_arg_types=include_arg_types,
                include_arg_defaults=include_arg_defaults,
            )
            if signature_item is not None:
                state.output.extend(signature_item.lines)
                line_idx = signature_item.next_index
                continue

        state.output.append(parts.line)
        line_idx += 1

    _compact_pending_google_summary(
        state,
        compact_first_line=compact_first_line,
        leading_indent=leading_indent,
    )

    return finalize_lines(state.output, closing_indent)


def _normalize_google_docstring_indent(
        docstring: str,
        leading_indent: int | None,
) -> str:
    """
    Add leading indentation only when Google content needs it.

    Google formatting preserves deliberately over-indented or already-aligned
    first content lines. This mirrors the prior pass-one setup before any
    section parsing occurs.
    """
    if leading_indent is None or leading_indent <= 0:
        return add_leading_indent(docstring, leading_indent)

    if docstring.startswith('\n'):
        return docstring

    if _google_docstring_needs_leading_indent(docstring, leading_indent):
        return add_leading_indent(docstring, leading_indent)

    return docstring


def _google_docstring_needs_leading_indent(
        docstring: str,
        leading_indent: int,
) -> bool:
    """Return True if the first content line is under-indented."""
    for line in docstring.splitlines():
        if line.strip():
            existing_indent = len(line) - len(line.lstrip())
            return existing_indent < leading_indent

    return True


def _split_google_line(line: str) -> _GoogleLineParts:
    """Split a line into commonly reused Google parser fields."""
    stripped = line.lstrip()
    indent_str = line[: len(line) - len(stripped)]
    return _GoogleLineParts(
        line=line,
        stripped=stripped,
        indent_str=indent_str,
        indent_level=len(indent_str),
    )


def _consume_google_protected_block(
        lines: list[str],
        line_idx: int,
) -> int | None:
    """
    Return the exclusive end index for protected code or doctest blocks.

    These blocks must be consumed before section/signature parsing because
    their content can look like Google section headers.
    """
    is_fence, fence_end_idx = is_code_fence(lines, line_idx)
    if is_fence:
        return fence_end_idx

    is_doctest, doctest_end_idx = is_google_doctest_block(lines, line_idx)
    if is_doctest:
        return doctest_end_idx

    return None


def _compact_pending_google_summary(
        state: _GooglePass1State,
        *,
        compact_first_line: bool,
        leading_indent: int | None,
) -> None:
    """
    Compact buffered summary text before sections or final output.

    Once a real or custom section starts, later content must keep section
    structure instead of moving beside opening quotes.
    """
    if not (compact_first_line and not state.current_section and state.output):
        return

    _compact_google_summary_output(
        state.output,
        leading_indent=leading_indent,
    )


def _emit_google_section_header(
        state: _GooglePass1State,
        parts: _GoogleLineParts,
        canonical: str,
) -> None:
    """Emit a canonical Google section header and update pass-one state."""
    state.current_section = canonical.lower()
    state.current_section_indent = parts.indent_level
    state.output.append(parts.indent_str + canonical)


def _is_google_unknown_section_boundary(
        state: _GooglePass1State,
        parts: _GoogleLineParts,
) -> bool:
    """Return True if an unknown header should end signature parsing."""
    if not _is_google_unknown_section_header(parts.stripped):
        return False

    return (
        not state.current_section and _has_summary_content(state.output)
    ) or parts.indent_level <= state.current_section_indent


def _emit_google_unknown_section_header(
        state: _GooglePass1State,
        parts: _GoogleLineParts,
) -> None:
    """Emit an unknown section boundary without canonicalizing its text."""
    state.current_section = parts.stripped.lower()
    state.current_section_indent = parts.indent_level
    state.output.append(parts.line)


def _google_signature_section_info(
        current_section: str,
        parameter_metadata: ParameterMetadata | None,
        attribute_metadata: ParameterMetadata | None,
) -> _GoogleSignatureSectionInfo:
    """Collect facts needed while parsing one Google signature section."""
    section_lower = current_section.lower()
    metadata = parameter_metadata
    if is_google_attribute_section_header(section_lower):
        metadata = attribute_metadata

    return _GoogleSignatureSectionInfo(
        section_lower=section_lower,
        is_return_section=is_google_returns_or_yields_section_header(
            section_lower
        ),
        is_yields_section=is_google_yields_section_header(section_lower),
        metadata=metadata,
    )


def _unwrap_google_signature_item(
        lines: list[str],
        line_idx: int,
        parts: _GoogleLineParts,
        section_info: _GoogleSignatureSectionInfo,
        return_annotation: str | None,
        *,
        include_arg_types: bool = True,
        include_arg_defaults: bool = True,
) -> _GoogleUnwrappedSignatureItem | None:
    """Unwrap one Google signature item, if the current line is an item."""
    candidate = _standardize_google_signature_candidate(
        parts.line,
        section_info,
        return_annotation,
    )
    if not candidate.is_signature:
        return None

    signature_part, inline_desc = _split_google_signature(candidate.line)
    if is_google_parameter_section_header(
        section_info.section_lower
    ) or is_google_attribute_section_header(section_info.section_lower):
        signature_part = _rewrite_google_parameter_signature(
            signature_part,
            section_info.metadata,
            include_arg_types=include_arg_types,
            include_arg_defaults=include_arg_defaults,
        )

    description_lines, next_index = _collect_google_description_lines(
        lines,
        line_idx,
        current_item_indent=parts.indent_level,
        inline_desc=inline_desc,
        section_info=section_info,
    )
    signature_part = _ensure_google_return_signature_delimiter(
        signature_part,
        inline_desc,
        description_lines,
        is_return_section=section_info.is_return_section,
    )
    processed_desc_lines = _dedent_lines(
        description_lines,
        parts.indent_level,
        has_inline_description=inline_desc is not None,
    )
    segments = segment_lines_by_wrappability(
        processed_desc_lines,
        style='google',
    )

    return _GoogleUnwrappedSignatureItem(
        lines=_merge_google_signature_description_segments(
            signature_part,
            segments,
            parts.indent_level,
        ),
        next_index=next_index,
    )


def _standardize_google_signature_candidate(
        line: str,
        section_info: _GoogleSignatureSectionInfo,
        return_annotation: str | None,
) -> _GoogleSignatureCandidate:
    """Normalize a possible signature and decide if it is parseable."""
    standardized_line = _normalize_google_signature_spacing(
        _standardize_default_value(line)
    )
    standardized_stripped = standardized_line.lstrip()

    if section_info.is_return_section:
        standardized_line, standardized_stripped = (
            _sync_google_return_signature_candidate(
                standardized_line,
                standardized_stripped,
                section_info,
                return_annotation,
            )
        )

    is_signature = _is_google_signature(standardized_stripped)
    if section_info.is_return_section:
        is_signature = is_signature or _is_google_return_signature(
            standardized_stripped
        )

    return _GoogleSignatureCandidate(
        line=standardized_line,
        is_signature=is_signature,
    )


def _sync_google_return_signature_candidate(
        line: str,
        stripped: str,
        section_info: _GoogleSignatureSectionInfo,
        return_annotation: str | None,
) -> tuple[str, str]:
    """Apply return/yield annotation sync to one candidate line."""
    desired_annotation = _desired_google_return_annotation(
        section_info,
        return_annotation,
    )
    rewritten_named_return = _rewrite_google_named_return_signature(
        line,
        desired_annotation,
    )
    if rewritten_named_return is not None:
        return rewritten_named_return, rewritten_named_return.lstrip()

    if desired_annotation is None:
        return line, stripped

    if _is_google_return_signature(stripped):
        rewritten = _rewrite_google_return_signature(line, desired_annotation)
        return rewritten, rewritten.lstrip()

    if _is_google_return_description(stripped):
        indent = line[: len(line) - len(stripped)]
        rewritten = f'{indent}{desired_annotation}: {stripped.strip()}'
        return rewritten, rewritten.lstrip()

    return line, stripped


def _desired_google_return_annotation(
        section_info: _GoogleSignatureSectionInfo,
        return_annotation: str | None,
) -> str | None:
    """Return the source annotation to sync into a return/yield section."""
    if return_annotation is None:
        return None

    if section_info.is_yields_section:
        return (
            _unwrap_generator_annotation(return_annotation)
            or return_annotation
        )

    return return_annotation


def _collect_google_description_lines(
        lines: list[str],
        line_idx: int,
        *,
        current_item_indent: int,
        inline_desc: str | None,
        section_info: _GoogleSignatureSectionInfo,
) -> tuple[list[str], int]:
    """Collect raw description lines belonging to one signature item."""
    description_lines: list[str] = []
    if inline_desc:
        description_lines.append(inline_desc)

    next_idx = line_idx + 1
    while next_idx < len(lines):
        next_parts = _split_google_line(lines[next_idx])
        if not next_parts.line.strip():
            description_lines.append('')
            next_idx += 1
            continue

        if _is_google_description_boundary(
            next_parts,
            current_item_indent=current_item_indent,
            is_return_section=section_info.is_return_section,
        ):
            break

        description_lines.append(next_parts.line)
        next_idx += 1

    return description_lines, next_idx


def _is_google_description_boundary(
        parts: _GoogleLineParts,
        *,
        current_item_indent: int,
        is_return_section: bool,
) -> bool:
    """Return True if ``parts`` starts a new section or item."""
    if is_return_section:
        return (
            _is_google_section_header(parts.stripped)
            or _is_google_unknown_section_header(parts.stripped)
            or parts.indent_level < current_item_indent
        )

    return parts.indent_level <= current_item_indent


def _ensure_google_return_signature_delimiter(
        signature_part: str,
        inline_desc: str | None,
        description_lines: list[str],
        *,
        is_return_section: bool,
) -> str:
    """Add a delimiter to bare return types before merging descriptions."""
    if not is_return_section or inline_desc is not None:
        return signature_part

    if not any(desc_line.strip() for desc_line in description_lines):
        return signature_part

    if signature_part.rstrip().endswith(':'):
        return signature_part

    return f'{signature_part.rstrip()}:'


def _merge_google_signature_description_segments(
        signature_part: str,
        segments: list[tuple[list[str], bool]],
        current_item_indent: int,
) -> list[str]:
    """Merge the first wrappable description segment into a signature."""
    if not segments:
        return [signature_part.rstrip()]

    first_seg_lines, is_wrappable = segments[0]
    indent_str = ' ' * (current_item_indent + 4)
    if not is_wrappable:
        return [
            signature_part,
            *_reindent_google_description_segments(
                segments,
                indent_str=indent_str,
            ),
        ]

    trailing_empty_lines = _pop_trailing_blank_lines(first_seg_lines)
    merged_text = merge_lines_and_strip('\n'.join(first_seg_lines))
    output = [
        _combine_google_signature_description(
            signature_part,
            merged_text,
            current_item_indent=current_item_indent,
        ),
        *('' for _ in trailing_empty_lines),
    ]
    output.extend(
        _reindent_google_description_segments(
            segments[1:],
            indent_str=indent_str,
        )
    )
    return output


def _combine_google_signature_description(
        signature_part: str,
        merged_text: str,
        *,
        current_item_indent: int,
) -> str:
    """Return a signature line with merged prose when available."""
    if not merged_text:
        return signature_part

    merged_lines = merged_text.splitlines()
    sig_combined = f'{signature_part} {merged_lines[0]}'
    if len(merged_lines) == 1:
        return sig_combined

    indent_pad = ' ' * (current_item_indent + 4)
    parts = [sig_combined]
    for merged_line in merged_lines[1:]:
        if merged_line.strip():
            parts.append(indent_pad + merged_line)
        else:
            parts.append('')

    return '\n'.join(parts)


def _reindent_google_description_segments(
        segments: list[tuple[list[str], bool]],
        *,
        indent_str: str,
) -> list[str]:
    """Restore Google continuation indentation to preserved segments."""
    output: list[str] = []
    for seg_lines, _ in segments:
        output.extend(
            indent_str + line if line.strip() else '' for line in seg_lines
        )

    return output


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

    state = _GoogleParagraphJoinState(
        result=[],
        paragraph_lines=[],
        paragraph_indent='',
        leading_indent=leading_indent,
        in_examples_section=initial_in_examples_section,
    )

    line_idx = 0
    while line_idx < len(lines):
        parts = _split_google_line(lines[line_idx])
        if not parts.line.strip():
            _flush_google_paragraph(state)
            state.result.append(parts.line)
            line_idx += 1
            continue

        _update_google_paragraph_examples_state(state, parts)
        examples_end_idx = _consume_google_paragraph_examples_code(
            state,
            lines,
            line_idx,
        )
        if examples_end_idx is not None:
            line_idx = examples_end_idx
            continue

        if _is_google_paragraph_signature(parts, state.leading_indent):
            _flush_google_paragraph(state)
            state.result.append(parts.line)
        else:
            _queue_google_paragraph_line(state, parts)

        line_idx += 1

    _flush_google_paragraph(state)

    return state.result


def _flush_google_paragraph(state: _GoogleParagraphJoinState) -> None:
    """Join and emit the pending ordinary prose paragraph."""
    if not state.paragraph_lines:
        return

    joined_content = ' '.join(line.lstrip() for line in state.paragraph_lines)
    state.result.append(state.paragraph_indent + joined_content)
    state.paragraph_lines = []
    state.paragraph_indent = ''


def _update_google_paragraph_examples_state(
        state: _GoogleParagraphJoinState,
        parts: _GoogleLineParts,
) -> None:
    """Track whether paragraph joining is currently inside Examples."""
    canonical = canonical_google_section_header(parts.stripped)
    if canonical is not None:
        state.in_examples_section = canonical == 'Examples:'
    elif _is_google_unknown_section_header(
        parts.stripped
    ) and parts.indent_level <= (state.leading_indent or 0):
        state.in_examples_section = False


def _consume_google_paragraph_examples_code(
        state: _GoogleParagraphJoinState,
        lines: list[str],
        line_idx: int,
) -> int | None:
    """Preserve Examples code before paragraph joining destroys boundaries."""
    if not state.in_examples_section:
        return None

    is_examples_code, examples_code_end_idx = is_google_examples_code_block(
        lines,
        line_idx,
    )
    if not is_examples_code:
        return None

    _flush_google_paragraph(state)
    state.result.extend(lines[line_idx:examples_code_end_idx])
    return examples_code_end_idx


def _is_google_paragraph_signature(
        parts: _GoogleLineParts,
        leading_indent: int | None,
) -> bool:
    """Return True if paragraph joining should keep this line separate."""
    if parts.stripped.startswith(('"""', "'''")):
        return False

    if leading_indent and len(parts.indent_str) < leading_indent:
        return False

    return _is_google_signature(parts.stripped)


def _queue_google_paragraph_line(
        state: _GoogleParagraphJoinState,
        parts: _GoogleLineParts,
) -> None:
    """Add a line to the pending paragraph, flushing on indent changes."""
    if not state.paragraph_lines:
        state.paragraph_indent = parts.indent_str
    elif parts.indent_str != state.paragraph_indent:
        _flush_google_paragraph(state)
        state.paragraph_indent = parts.indent_str

    state.paragraph_lines.append(parts.line)


def _append_google_summary_merged(
        output: list[str],
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
        output: list[str],
        *,
        leading_indent: int | None,
) -> None:
    """
    Merge buffered summary paragraphs for compact Google docstrings.

    Segmenting before merging keeps literal blocks intact while still allowing
    ordinary prose to move beside the opening quotes.
    """
    segments = segment_lines_by_wrappability(
        output,
        style='google',
    )

    output.clear()
    first_segment_processed = False
    for seg_lines, is_wrappable in segments:
        if not is_wrappable:
            output.extend(seg_lines)
            first_segment_processed = True
            continue

        trailing_empty_lines = _pop_trailing_blank_lines(seg_lines)
        leading_empty_lines = _pop_leading_blank_lines(seg_lines)
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


def _pop_leading_blank_lines(lines: list[str]) -> list[str]:
    """Remove and return leading blank lines from ``lines``."""
    blank_lines = []
    while lines and not lines[0].strip():
        blank_lines.append(lines.pop(0))

    return blank_lines


def _pop_trailing_blank_lines(lines: list[str]) -> list[str]:
    """Remove and return trailing blanks from ``lines`` in source order."""
    blank_lines = []
    while lines and not lines[-1].strip():
        blank_lines.append(lines.pop())

    blank_lines.reverse()
    return blank_lines


def _has_summary_content(items: list[str]) -> bool:
    """Return True when buffered pre-section lines contain nonblank text."""
    return any(item.strip() for item in items)


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
    state = _GoogleWrapState(
        output=[],
        leading_indent=leading_indent or 0,
        line_length=line_length,
        compact_first_line=compact_first_line,
        opening_quotes_on_own_line=opening_quotes_on_own_line,
    )
    segments = segment_lines_by_wrappability(
        docstring.splitlines(),
        style='google',
    )

    for seg_lines, is_wrappable in segments:
        if not is_wrappable:
            _append_google_unwrappable_segment(state, seg_lines)
            continue

        _wrap_google_wrappable_segment(state, seg_lines)

    return finalize_lines(state.output, closing_indent)


def _append_google_unwrappable_segment(
        state: _GoogleWrapState,
        seg_lines: list[str],
) -> None:
    """Append protected pass-two content without wrapping it."""
    state.output.extend(seg_lines)
    state.is_first_line = False


def _wrap_google_wrappable_segment(
        state: _GoogleWrapState,
        seg_lines: list[str],
) -> None:
    """Wrap one pass-two segment that may contain ordinary prose."""
    processed_lines = _join_paragraph_lines(
        seg_lines,
        state.leading_indent,
        initial_in_examples_section=state.in_examples_section,
    )

    line_idx = 0
    while line_idx < len(processed_lines):
        line_idx = _wrap_google_processed_line(
            state,
            processed_lines,
            line_idx,
        )


def _wrap_google_processed_line(
        state: _GoogleWrapState,
        processed_lines: list[str],
        line_idx: int,
) -> int:
    """Wrap or preserve one already-joined pass-two line."""
    parts = _split_google_line(processed_lines[line_idx])
    if not parts.line.strip():
        _append_google_blank_wrapped_line(state, parts.line)
        return line_idx + 1

    _update_google_wrap_section_state(state, parts)
    examples_end_idx = _consume_google_wrap_examples_code(
        state,
        processed_lines,
        line_idx,
    )
    if examples_end_idx is not None:
        return examples_end_idx

    effective_indent = _google_effective_signature_indent(state, parts)
    if _is_google_signature_line_in_context(state, parts, effective_indent):
        state.output.extend(
            _wrap_google_signature_line(
                parts.line,
                line_length=state.line_length,
                indent_str=parts.indent_str,
            )
        )
    else:
        prose_parts = _normalize_google_label_like_prose(state, parts)
        _wrap_google_prose_line(state, prose_parts)

    state.is_first_line = False
    return line_idx + 1


def _append_google_blank_wrapped_line(
        state: _GoogleWrapState,
        line: str,
) -> None:
    """Append a blank line and update opening-line state if needed."""
    state.output.append(line)
    if state.opening_quotes_on_own_line and state.is_first_line:
        state.is_first_line = False


def _update_google_wrap_section_state(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
) -> None:
    """Track Google section context while pass two wraps prose."""
    if _is_google_section_header(parts.stripped):
        state.custom_section_indent = None
        state.in_examples_section = (
            canonical_google_section_header(parts.stripped) == 'Examples:'
        )
        state.in_signature_section = _is_google_signature_section_header(
            parts.stripped
        )
    elif (
        _is_google_unknown_section_header(parts.stripped)
        and parts.indent_level <= state.leading_indent
    ):
        state.custom_section_indent = parts.indent_level
        state.in_examples_section = False
        state.in_signature_section = False
    elif (
        state.custom_section_indent is not None
        and parts.indent_level <= state.custom_section_indent
    ):
        state.custom_section_indent = None


def _consume_google_wrap_examples_code(
        state: _GoogleWrapState,
        processed_lines: list[str],
        line_idx: int,
) -> int | None:
    """Preserve Examples code that survived paragraph joining."""
    if not state.in_examples_section:
        return None

    is_examples_code, examples_code_end_idx = is_google_examples_code_block(
        processed_lines,
        line_idx,
    )
    if not is_examples_code:
        return None

    state.output.extend(processed_lines[line_idx:examples_code_end_idx])
    state.is_first_line = False
    return examples_code_end_idx


def _google_effective_signature_indent(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
) -> int:
    """Return indent used by pass-two signature context checks."""
    if not state.is_first_line:
        return parts.indent_level

    if parts.indent_level < state.leading_indent:
        return state.leading_indent + GOOGLE_OPENING_QUOTES_WIDTH

    return parts.indent_level + GOOGLE_OPENING_QUOTES_WIDTH


def _is_google_signature_line_in_context(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
        effective_indent: int,
) -> bool:
    """Return True when a line should receive signature wrapping."""
    if not state.in_signature_section:
        return False

    if parts.stripped.startswith(('"""', "'''")):
        return False

    if state.leading_indent and effective_indent < state.leading_indent:
        return False

    return _is_google_signature(parts.stripped)


def _normalize_google_label_like_prose(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
) -> _GoogleLineParts:
    """Normalize signature-like labels that should still wrap as prose."""
    if not _should_normalize_google_label_like_prose(state, parts):
        return parts

    return _split_google_line(_normalize_google_signature_spacing(parts.line))


def _should_normalize_google_label_like_prose(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
) -> bool:
    """Return True for colon labels outside signature sections."""
    return (
        not state.in_signature_section
        and not _is_google_section_header(parts.stripped)
        and not parts.stripped.rstrip().endswith('::')
        and _is_google_signature(parts.stripped)
    )


def _wrap_google_prose_line(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
) -> None:
    """Wrap one pass-two prose line using first-line rules when needed."""
    if state.is_first_line:
        _wrap_google_first_prose_line(state, parts)
    else:
        _wrap_google_normal_prose_line(state, parts)


def _wrap_google_first_prose_line(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
) -> None:
    """Wrap the first physical docstring line with opening-quote budget."""
    opening_width = (
        GOOGLE_COMPACT_OPENING_QUOTES_WIDTH
        if state.compact_first_line
        else GOOGLE_OPENING_QUOTES_WIDTH
    )
    first_line_width = max(
        1,
        state.line_length - state.leading_indent - opening_width,
    )
    state.output.extend(
        _wrap_first_line_shorter(
            parts.line.strip(),
            first_line_width=first_line_width,
            subsequent_width=state.line_length,
            initial_indent=parts.indent_str,
            subsequent_indent=' ' * state.leading_indent,
        )
    )


def _wrap_google_normal_prose_line(
        state: _GoogleWrapState,
        parts: _GoogleLineParts,
) -> None:
    """Wrap a non-initial Google prose line."""
    subsequent_indent = parts.indent_str
    if (
        not state.opening_quotes_on_own_line
        and len(parts.indent_str) < state.leading_indent
    ):
        subsequent_indent = ' ' * state.leading_indent

    wrapped = textwrap.fill(
        parts.line.strip(),
        width=state.line_length,
        initial_indent=parts.indent_str,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    state.output.extend(wrapped.splitlines())


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
    if (
        remaining_first < GOOGLE_MIN_SIGNATURE_DESC_WIDTH
        or len(first_word) > remaining_first
    ):
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
            current_line += word
            continue

        # Check if adding this word would exceed the line width
        if current_line in {initial_indent, subsequent_indent}:
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


def _split_google_metadata_markers(
        annotation: str,
) -> tuple[list[str], str | None, bool]:
    """Split Google annotation text into type pieces, default, and optional."""
    type_pieces: list[str] = []
    default_value: str | None = None
    has_optional = False
    for piece in _split_google_annotation_pieces(annotation):
        piece_lower = piece.lower()
        if piece_lower == 'optional':
            has_optional = True
            continue

        if piece_lower.startswith('default='):
            default_value = piece.split('=', 1)[1].strip()
            continue

        type_pieces.append(piece)

    return type_pieces, default_value, has_optional


def _rewrite_google_parameter_signature(
        signature_part: str,
        metadata: ParameterMetadata | None,
        *,
        include_arg_types: bool = True,
        include_arg_defaults: bool = True,
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
    if meta is None and include_arg_types and include_arg_defaults:
        return signature_part

    existing_annotation = (match.group('annotation') or '').strip()
    existing_type_pieces, existing_default, has_optional = (
        _split_google_metadata_markers(existing_annotation)
    )

    pieces: list[str] = []
    annotation: str | None = None
    default: str | None = None
    if meta is not None:
        annotation, default = meta

    # Source metadata is authoritative only when it has an annotation/default.
    # Otherwise, preserve existing docstring pieces unless an include flag asks
    # us to strip them; unannotated functions should not erase author docs.
    source_controls_annotation = meta is not None and annotation is not None
    source_controls_defaults = meta is not None and (
        annotation is not None or default is not None
    )

    default_text = None
    if include_arg_defaults:
        default_text = (
            default if source_controls_defaults else existing_default
        )

    if include_arg_types:
        if source_controls_annotation:
            pieces.append(annotation)
        else:
            pieces.extend(existing_type_pieces)
            if has_optional and default_text is None:
                pieces.append('optional')

    if default_text is not None:
        pieces.append(f'default={default_text}')

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
    if not _has_google_signature_delimiter(stripped_line):
        return False

    sig, _ = _split_google_signature(stripped_line)
    sig_body = _google_signature_body(sig)
    if not sig_body:
        return False

    tokens = _tokenize_google_signature_body(sig_body)
    if tokens is None:
        return False

    return _google_signature_tokens_are_valid(sig_body, tokens)


def _has_google_signature_delimiter(stripped_line: str) -> bool:
    """Return True if ``stripped_line`` may contain a signature delimiter."""
    return ':' in stripped_line and not stripped_line.startswith((
        '<',
        'http:',
        'https:',
    ))


def _google_signature_body(signature_part: str) -> str:
    """Return the signature text before the trailing delimiter colon."""
    return signature_part.rsplit(':', 1)[0].strip()


def _tokenize_google_signature_body(sig_body: str) -> list[str] | None:
    """Tokenize a signature body, rejecting invalid top-level commas."""
    nesting = 0
    tokens: list[str] = []
    current_token: list[str] = []

    for char in sig_body:
        if char in '([{':
            nesting += 1
            current_token.append(char)
        elif char in ')]}':
            nesting -= 1
            current_token.append(char)
        elif char == ',' and nesting == 0:
            return None
        elif char.isspace() and nesting == 0:
            if current_token:
                tokens.append(''.join(current_token))
                current_token = []
        else:
            current_token.append(char)

    if current_token:
        tokens.append(''.join(current_token))

    if nesting != 0:
        return None

    return tokens


def _google_signature_tokens_are_valid(
        sig_body: str,
        tokens: list[str],
) -> bool:
    """Return True if tokenized signature text is not prose."""
    meaningful_tokens = [t for t in tokens if t != '|']

    if not meaningful_tokens:
        return False

    if '[' in sig_body or '|' in tokens:
        return True

    if len(meaningful_tokens) > GOOGLE_SIGNATURE_MAX_TOKENS:
        return False

    return not (
        len(meaningful_tokens) == GOOGLE_SIGNATURE_MAX_TOKENS
        and not meaningful_tokens[1].startswith('(')
    )


# Regex pattern to match various default value formats within parentheses
# Matches: default 10, default is True, default: 3.14, and default=42.
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
    # Pattern handles: default 10, default is value, default: value, and
    # default=value.
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
    return (
        signature[: paren_match.start(1)]
        + new_paren_content
        + signature[paren_match.end(1) :]
    )


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
        base_indent: int,  # noqa: ARG001
        *,
        has_inline_description: bool,
) -> list[str]:
    """
    Return description lines relative to the Google item indentation.

    Pass one stores inline text from ``arg: text`` without leading indentation,
    but stores following description lines exactly as they appear in the
    docstring. Later wrapping re-indents preserved blocks relative to the item,
    so block lines must first be shifted to a common baseline. When no inline
    description exists, the first collected line is part of that block too;
    dedenting it prevents lists and tables from being indented twice.
    """
    if not lines:
        return lines

    if has_inline_description and len(lines) <= 1:
        return lines

    block_start_idx = 1 if has_inline_description else 0
    block_lines = lines[block_start_idx:]

    # Strip only the common block indent. Full stripping would destroy relative
    # indentation inside tables, literal blocks, and nested lists.
    indents = [
        len(line) - len(line.lstrip()) for line in block_lines if line.strip()
    ]

    min_indent = min(indents) if indents else 0

    out = []
    if has_inline_description:
        # The inline description is already in item-relative coordinates.
        out.append(lines[0])

    for line in block_lines:
        if line.strip():
            out.append(line[min_indent:])
        else:
            out.append('')

    return out
