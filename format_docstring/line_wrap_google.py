from __future__ import annotations

import re
from dataclasses import dataclass

from format_docstring.line_wrap_numpy import (
    _rewrite_parameter_signature,
    _split_tuple_annotation,
    _standardize_default_value,
    _unwrap_generator_annotation,
    _fix_rst_backticks,
)
from format_docstring.line_wrap_utils import (
    ParameterMetadata,
    add_leading_indent,
    collect_to_temp_output,
    finalize_lines,
    fix_typos_in_section_headings,
    wrap_preserving_indent,
)

_INLINE_SENTINEL = '\x00FD_INLINE\x00'

_PARAM_NAME_RE = re.compile(r'^\*{0,2}[A-Za-z_][A-Za-z0-9_]*$')


@dataclass
class _SignatureInfo:
    text: str
    desc_indent: str
    has_description: bool
    inline_on_signature: bool


def wrap_docstring_google(
        docstring: str,
        *,
        line_length: int,
        leading_indent: int | None = None,
        fix_rst_backticks: bool = True,
        parameter_metadata: ParameterMetadata | None = None,
        return_annotation: str | None = None,
        attribute_metadata: ParameterMetadata | None = None,
) -> str:
    """Wrap Google-style docstrings using lightweight heuristics."""
    docstring_ = add_leading_indent(docstring, leading_indent)
    if fix_rst_backticks:
        docstring_ = _fix_rst_backticks(docstring_)

    lines = docstring_.splitlines()
    if not lines:
        return docstring_

    section_params = {
        'args',
        'arguments',
        'parameters',
        'other args',
        'other arguments',
        'other parameters',
    }
    section_attributes = {
        'attributes',
    }
    section_returns = {
        'returns',
        'return',
        'yields',
        'yield',
    }
    section_raises = {
        'raises',
        'raise',
    }
    section_examples = {
        'examples',
        'example',
    }
    known_headings = (
        section_params
        | section_attributes
        | section_returns
        | section_raises
        | section_examples
        | {
            'notes',
            'note',
            'seealso',
            'see also',
            'references',
            'reference',
        }
    )

    temp_out: list[str | list[str]] = []
    signature_infos: list[_SignatureInfo] = []
    in_code_fence = False
    current_section = ''
    in_examples = False

    return_annotation_str = return_annotation.strip() if return_annotation else None
    return_components = (
        _split_tuple_annotation(return_annotation_str)
        if return_annotation_str is not None
        else None
    )
    return_component_index = 0
    return_signature_style_determined = False
    return_use_multiple_signatures = False

    i = 0
    while i < len(lines):
        line = lines[i]

        if line == '':
            temp_out.append(line)
            i += 1
            continue

        stripped = line.lstrip(' ')
        indent_length = len(line) - len(stripped)

        if stripped.startswith('```'):
            in_code_fence = not in_code_fence
            temp_out.append(line)
            i += 1
            continue

        heading = _match_google_section_heading(line, known_headings)
        if heading:
            current_section = heading
            in_examples = heading in section_examples
            temp_out.append(line)
            i += 1
            continue

        if in_code_fence:
            temp_out.append(line)
            i += 1
            continue

        if in_examples and stripped.startswith(('>>> ', '... ')):
            temp_out.append(line)
            i += 1
            continue

        section_lower = current_section.lower()

        if section_lower in section_params | section_attributes:
            metadata_for_section = parameter_metadata
            if section_lower in section_attributes:
                metadata_for_section = attribute_metadata or parameter_metadata

            processed, next_index = _maybe_process_parameter_signature(
                lines,
                i,
                indent_length,
                leading_indent,
                metadata_for_section,
                temp_out,
                signature_infos,
                line_length,
            )
            if processed:
                i = next_index
                continue

            collect_to_temp_output(temp_out, line)
            i += 1
            continue

        if section_lower in section_returns:
            processed, result = _maybe_process_return_signature(
                lines,
                i,
                indent_length,
                leading_indent,
                temp_out,
                signature_infos,
                section_lower.startswith('yield'),
                return_annotation_str,
                return_components,
                return_component_index,
                return_signature_style_determined,
                return_use_multiple_signatures,
                known_headings,
                line_length,
            )
            (
                return_component_index,
                return_signature_style_determined,
                return_use_multiple_signatures,
                next_index,
            ) = result
            if processed:
                i = next_index
                continue

            collect_to_temp_output(temp_out, line)
            i += 1
            continue

        if section_lower in section_raises:
            processed, next_index = _maybe_process_raises_signature(
                lines,
                i,
                indent_length,
                leading_indent,
                temp_out,
                signature_infos,
                line_length,
            )
            if processed:
                i = next_index
                continue

            collect_to_temp_output(temp_out, line)
            i += 1
            continue

        collect_to_temp_output(temp_out, line)
        i += 1

    out = _process_temp_output_google(temp_out, width=line_length)
    merged = _merge_signature_lines(out, signature_infos)
    return finalize_lines(merged, leading_indent)


def _maybe_process_parameter_signature(
        lines: list[str],
        idx: int,
        indent_length: int,
        leading_indent: int | None,
        metadata: ParameterMetadata | None,
        temp_out: list[str | list[str]],
        signature_infos: list[_SignatureInfo],
        line_length: int,
) -> tuple[bool, int]:
    base_indent = leading_indent or 0
    min_section_indent = base_indent + 4
    if base_indent < indent_length < min_section_indent:
        return False, idx + 1

    parsed = _parse_param_signature_line(lines[idx])
    if parsed is None:
        return False, idx + 1

    indent, name, existing_annotation, inline_desc = parsed
    indent, normalized_indent_len = _normalize_entry_indent(
        indent, indent_length, leading_indent
    )
    rebuilt = _build_parameter_signature(indent, name, existing_annotation, metadata)

    available = _available_inline_width(rebuilt, line_length)
    (
        desc_lines,
        next_index,
        desc_indent_len,
        has_description,
        inline_first_chunk,
    ) = _gather_description_lines(
        lines,
        idx,
        indent_length,
        inline_desc,
        normalized_indent_len,
        available,
    )

    temp_out.append(rebuilt)
    for desc_line in desc_lines:
        if desc_line == '':
            temp_out.append(desc_line)
        else:
            collect_to_temp_output(temp_out, desc_line)

    signature_infos.append(
        _SignatureInfo(
            text=rebuilt,
            desc_indent=' ' * desc_indent_len,
            has_description=has_description,
            inline_on_signature=inline_first_chunk,
        )
    )
    return True, next_index


def _maybe_process_return_signature(
        lines: list[str],
        idx: int,
        indent_length: int,
        leading_indent: int | None,
        temp_out: list[str | list[str]],
        signature_infos: list[_SignatureInfo],
        is_yields_section: bool,
        return_annotation: str | None,
        return_components: list[str] | None,
        return_component_index: int,
        return_signature_style_determined: bool,
        return_use_multiple_signatures: bool,
        known_headings: set[str],
        line_length: int,
) -> tuple[
    bool,
    tuple[int, bool, bool, int],
]:
    next_state = (
        return_component_index,
        return_signature_style_determined,
        return_use_multiple_signatures,
        idx + 1,
    )
    base_indent = leading_indent or 0
    min_section_indent = base_indent + 4
    if base_indent < indent_length < min_section_indent:
        return False, next_state

    desired_annotation = return_annotation

    if not return_signature_style_determined:
        return_use_multiple_signatures = _detect_multiple_return_signatures_google(
            lines, idx, leading_indent, known_headings
        )
        return_signature_style_determined = True

    if (
        return_use_multiple_signatures
        and return_components
        and return_component_index < len(return_components)
    ):
        desired_annotation = return_components[return_component_index]
        return_component_index += 1
    elif (
        return_use_multiple_signatures
        and return_components
        and return_component_index >= len(return_components)
    ):
        desired_annotation = return_components[-1]

    if is_yields_section:
        desired_annotation = (
            _unwrap_generator_annotation(desired_annotation) or desired_annotation
        )

    parsed = _parse_return_signature_line(lines[idx])
    if parsed is None:
        return False, (
            return_component_index,
            return_signature_style_determined,
            return_use_multiple_signatures,
            idx + 1,
        )

    indent, name, existing_annotation, inline_desc = parsed
    indent, normalized_indent_len = _normalize_entry_indent(
        indent, indent_length, leading_indent
    )
    annotation_text = desired_annotation or existing_annotation
    if annotation_text is None and name is None:
        return False, (
            return_component_index,
            return_signature_style_determined,
            return_use_multiple_signatures,
            idx + 1,
        )

    type_hint = _build_return_type_hint(name, annotation_text, existing_annotation)
    rebuilt = f'{indent}{type_hint}:'

    available = _available_inline_width(rebuilt, line_length)
    (
        desc_lines,
        next_index,
        desc_indent_len,
        has_description,
        inline_first_chunk,
    ) = _gather_description_lines(
        lines,
        idx,
        indent_length,
        inline_desc,
        normalized_indent_len,
        available,
    )

    temp_out.append(rebuilt)
    for desc_line in desc_lines:
        if desc_line == '':
            temp_out.append(desc_line)
        else:
            collect_to_temp_output(temp_out, desc_line)

    signature_infos.append(
        _SignatureInfo(
            text=rebuilt,
            desc_indent=' ' * desc_indent_len,
            has_description=has_description,
            inline_on_signature=inline_first_chunk,
        )
    )

    return True, (
        return_component_index,
        return_signature_style_determined,
        return_use_multiple_signatures,
        next_index,
    )


def _maybe_process_raises_signature(
        lines: list[str],
        idx: int,
        indent_length: int,
        leading_indent: int | None,
        temp_out: list[str | list[str]],
        signature_infos: list[_SignatureInfo],
        line_length: int,
) -> tuple[bool, int]:
    base_indent = leading_indent or 0
    min_section_indent = base_indent + 4
    if base_indent < indent_length < min_section_indent:
        return False, idx + 1

    parsed = _parse_raise_signature_line(lines[idx])
    if parsed is None:
        return False, idx + 1

    indent, name, inline_desc = parsed
    indent, normalized_indent_len = _normalize_entry_indent(
        indent, indent_length, leading_indent
    )
    rebuilt = f'{indent}{name}:'
    available = _available_inline_width(rebuilt, line_length)
    (
        desc_lines,
        next_index,
        desc_indent_len,
        has_description,
        inline_first_chunk,
    ) = _gather_description_lines(
        lines,
        idx,
        indent_length,
        inline_desc,
        normalized_indent_len,
        available,
    )

    temp_out.append(rebuilt)
    for desc_line in desc_lines:
        if desc_line == '':
            temp_out.append(desc_line)
        else:
            collect_to_temp_output(temp_out, desc_line)

    signature_infos.append(
        _SignatureInfo(
            text=rebuilt,
            desc_indent=' ' * desc_indent_len,
            has_description=has_description,
            inline_on_signature=inline_first_chunk,
        )
    )
    return True, next_index


def _parse_param_signature_line(
        line: str,
) -> tuple[str, str, str | None, str] | None:
    stripped = line.lstrip(' ')
    indent_length = len(line) - len(stripped)
    indent = line[:indent_length]

    if ':' not in stripped:
        return None

    lhs, rhs = stripped.split(':', 1)
    lhs = lhs.rstrip()
    inline_desc = rhs.lstrip(' \t')
    if not lhs:
        return None

    name, annotation = _split_name_and_annotation(lhs)
    if name is None:
        return None

    return indent, name, annotation, inline_desc


def _parse_return_signature_line(
        line: str,
) -> tuple[str, str | None, str | None, str] | None:
    stripped = line.lstrip(' ')
    indent_length = len(line) - len(stripped)
    indent = line[:indent_length]

    lhs, rhs = _split_on_first_colon(stripped)
    inline_desc = rhs.lstrip(' \t')
    lhs = lhs.strip()
    if not lhs and not inline_desc:
        return None

    name = None
    annotation = None

    if ' :' in lhs or ':' in lhs:
        parts = lhs.split(':', 1)
        potential_name = parts[0].strip()
        if potential_name:
            name = potential_name
        annotation = parts[1].strip() if len(parts) > 1 else None
    elif '(' in lhs and lhs.endswith(')'):
        name, annotation = _split_name_and_annotation(lhs)
    else:
        annotation = lhs or None

    if name is None and annotation is None:
        return None

    return indent, name, annotation, inline_desc


def _parse_raise_signature_line(
        line: str,
) -> tuple[str, str, str] | None:
    stripped = line.lstrip(' ')
    indent_length = len(line) - len(stripped)
    indent = line[:indent_length]

    lhs, rhs = _split_on_first_colon(stripped)
    lhs = lhs.strip()
    if not lhs:
        return None

    inline_desc = rhs.lstrip(' \t')
    return indent, lhs, inline_desc


def _split_on_first_colon(text: str) -> tuple[str, str]:
    for idx, ch in enumerate(text):
        if ch != ':':
            continue
        next_char = text[idx + 1] if idx + 1 < len(text) else ''
        if next_char and next_char not in {' ', '\t'}:
            continue
        return text[:idx], text[idx + 1 :]

    return text, ''


def _split_name_and_annotation(segment: str) -> tuple[str | None, str | None]:
    if '(' in segment and segment.endswith(')'):
        open_idx = segment.find('(')
        close_idx = segment.rfind(')')
        if open_idx < close_idx:
            name = segment[:open_idx].strip()
            annotation = segment[open_idx + 1 : close_idx].strip()
            if name and _is_valid_param_name(name):
                return name, annotation or None
            return None, None

    stripped = segment.strip()
    if stripped and _is_valid_param_name(stripped):
        return stripped, None

    return None, None


def _is_valid_param_name(name: str) -> bool:
    return bool(_PARAM_NAME_RE.match(name))


def _normalize_entry_indent(
        indent: str, indent_length: int, leading_indent: int | None
) -> tuple[str, int]:
    base_indent = leading_indent if leading_indent is not None else 0
    desired = base_indent + 4
    if indent_length >= desired:
        return indent, indent_length
    return ' ' * desired, desired


def _build_parameter_signature(
        indent: str,
        name: str,
        existing_annotation: str | None,
        metadata: ParameterMetadata | None,
) -> str:
    placeholder = f'{indent}{name} : {existing_annotation or ""}'
    standardized = _standardize_default_value(placeholder)
    rewritten = _rewrite_parameter_signature(standardized, metadata)

    colon_idx = rewritten.find(':')
    annotation_text = rewritten[colon_idx + 1 :].strip() if colon_idx != -1 else ''
    annotation_segment = f' ({annotation_text})' if annotation_text else ''
    return f'{indent}{name}{annotation_segment}:'


def _build_return_type_hint(
        name: str | None,
        annotation_from_signature: str | None,
        fallback_annotation: str | None,
) -> str:
    annotation = annotation_from_signature or fallback_annotation or ''
    if name:
        if annotation:
            return f'{name} ({annotation})'
        return name

    return annotation or 'object'


def _gather_description_lines(
        lines: list[str],
        idx: int,
        scan_indent_length: int,
        inline_desc: str,
        output_indent_length: int,
        first_line_available: int | None,
) -> tuple[list[str], int, int, bool, bool]:
    desc_lines: list[str] = []
    has_description = False
    inline_consumed = False
    default_indent_len = output_indent_length + 4
    desc_indent_len = default_indent_len
    indent_str = ' ' * default_indent_len
    first_line_marked = False

    def _append_desc_line(text: str) -> None:
        nonlocal first_line_marked, has_description
        if not text:
            desc_lines.append('')
            return

        if not first_line_marked:
            desc_lines.append(f'{_INLINE_SENTINEL}{text}')
            first_line_marked = True
        else:
            desc_lines.append(text)
        has_description = True

    inline_text = inline_desc.strip()
    if inline_text:
        first_chunk, remainder = _split_inline_text(
            inline_text, first_line_available
        )
        if first_chunk:
            _append_desc_line(f'{indent_str}{first_chunk}')
            inline_consumed = True
        if remainder:
            _append_desc_line(f'{indent_str}{remainder}')

    j = idx + 1
    base_scan_indent = scan_indent_length + 4
    while j < len(lines):
        candidate = lines[j]
        if candidate.strip() == '':
            if has_description:
                desc_lines.append('')
            j += 1
            continue

        next_indent = len(candidate) - len(candidate.lstrip(' '))
        if next_indent < base_scan_indent:
            break

        relative_indent = max(0, next_indent - base_scan_indent)
        content = candidate[next_indent:].rstrip()
        _append_desc_line(f'{indent_str}{" " * relative_indent}{content}')
        j += 1

    return desc_lines, j, desc_indent_len, has_description, inline_consumed


def _available_inline_width(signature_line: str, max_width: int) -> int | None:
    stripped = signature_line.rstrip()
    prefix_len = len(stripped) + 1  # include space before description
    remaining = max_width - prefix_len
    if remaining <= 0:
        return None
    return remaining


def _split_inline_text(
        text: str, first_line_available: int | None
) -> tuple[str, str]:
    if not text:
        return '', ''

    if first_line_available is None:
        return text, ''

    if len(text) <= first_line_available:
        return text, ''

    split_idx = text.rfind(' ', 0, first_line_available + 1)
    if split_idx <= 0:
        next_space = text.find(' ')
        if next_space == -1:
            return text, ''
        first = text[:next_space].rstrip()
        rest = text[next_space:].lstrip()
        return first, rest

    first = text[:split_idx].rstrip()
    rest = text[split_idx:].lstrip()
    if not first:
        return '', text

    return first, rest


def _match_google_section_heading(
        line: str, known_headings: set[str]
) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None

    if stripped.endswith(':'):
        stripped = stripped[:-1].strip()

    lowered = stripped.lower()
    if lowered in known_headings:
        return lowered

    return None


def _merge_signature_lines(
        lines: list[str], signature_infos: list[_SignatureInfo]
) -> list[str]:
    if not signature_infos:
        return lines

    merged: list[str] = []
    sig_idx = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if sig_idx < len(signature_infos) and line == signature_infos[sig_idx].text:
            info = signature_infos[sig_idx]
            sig_idx += 1
            if info.has_description and info.inline_on_signature:
                desc_idx = i + 1
                if desc_idx < len(lines) and lines[desc_idx].startswith(info.desc_indent):
                    desc_text = lines[desc_idx][len(info.desc_indent):].lstrip(' ')
                    merged.append(f'{line.rstrip()} {desc_text}'.rstrip())
                    i = desc_idx + 1
                    continue
            merged.append(line)
            i += 1
            continue

        merged.append(line)
        i += 1

    return merged


def _strip_inline_marker(line: str) -> tuple[str, bool]:
    if line.startswith(_INLINE_SENTINEL):
        return line[len(_INLINE_SENTINEL):], True
    return line, False


def _process_temp_output_google(
        temp_out: list[str | list[str]],
        width: int,
) -> list[str]:
    def _to_list(element: str | list[str]) -> list[str]:
        return [element] if isinstance(element, str) else list(element)

    def _ends_with_literal_block_marker(element: str | list[str]) -> bool:
        if isinstance(element, str):
            text, _ = _strip_inline_marker(element)
            return text.endswith('::')

        if not element:
            return False

        text, _ = _strip_inline_marker(element[-1])
        return text.endswith('::')

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
            stripped, _ = _strip_inline_marker(element)
            out.append(stripped)
        elif isinstance(element, list):
            working = list(element)
            fixed_first_line: str | None = None
            if working:
                first = working[0]
                stripped, flagged = _strip_inline_marker(first)
                if flagged:
                    fixed_first_line = stripped
                    working = working[1:]
                else:
                    working[0] = stripped

            if fixed_first_line is not None:
                out.append(fixed_first_line)

            if not working:
                continue

            cleaned_rest = []
            for line in working:
                stripped, _ = _strip_inline_marker(line)
                cleaned_rest.append(stripped)

            wrapped: list[str] = wrap_preserving_indent(cleaned_rest, width)
            if '' in cleaned_rest and '' not in wrapped and cleaned_rest.index('') < len(cleaned_rest) - 1:
                insertion_idx = min(cleaned_rest.index(''), len(wrapped))
                wrapped = [
                    *wrapped[:insertion_idx],
                    '',
                    *wrapped[insertion_idx:],
                ]

            out.extend(wrapped)
        else:
            raise TypeError(
                f'`element` has unexpected type: {type(element)}.'
                ' Please contact the author.'
            )

    return fix_typos_in_section_headings(out)


def _detect_multiple_return_signatures_google(
        lines: list[str],
        idx: int,
        leading_indent: int | None,
        known_headings: set[str],
) -> bool:
    indent_threshold = leading_indent if leading_indent is not None else 0
    j = idx + 1
    while j < len(lines):
        candidate = lines[j]
        if _match_google_section_heading(candidate, known_headings):
            break
        if candidate.strip() == '':
            j += 1
            continue

        indent = len(candidate) - len(candidate.lstrip(' '))
        if indent <= indent_threshold:
            return True

        j += 1

    return False
