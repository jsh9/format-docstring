from pathlib import Path

import pytest

from format_docstring.docstring_rewriter import wrap_docstring
from format_docstring.line_wrap_google import _parse_param_signature_line
from tests.helpers import load_case_from_file, load_cases_from_dir

DATA_DIR: Path = Path(__file__).parent / 'test_data/line_wrap/google'


@pytest.mark.parametrize(
    ('name', 'line_length', 'before', 'after'),
    load_cases_from_dir(DATA_DIR),
)
def test_wrap_docstring(
        name: str,  # noqa: ARG001
        line_length: int,
        before: str,
        after: str,
) -> None:
    out = wrap_docstring(
        before, line_length=line_length, docstring_style='google'
    )
    assert out.strip('\n') == after.strip('\n')


def test_wrap_docstring_single_case() -> None:
    _, length, before, after = load_case_from_file(
        DATA_DIR / 'contents_that_are_not_wrapped.txt'
    )
    out = wrap_docstring(
        before,
        line_length=length,
        docstring_style='google',
        fix_rst_backticks=False,
    )
    assert out.strip('\n') == after.strip('\n')


@pytest.mark.parametrize(
    ('line', 'expected_name', 'expected_annotation', 'expected_inline_desc'),
    [
        (
            '    arg4 (float default: 3.14): Fourth argument.',
            'arg4',
            'float default: 3.14',
            'Fourth argument.',
        ),
        (
            'arg1 (dict[str, int]): Description',
            'arg1',
            'dict[str, int]',
            'Description',
        ),
    ],
)
def test_parse_param_signature_line_handles_colons(
        line: str,
        expected_name: str,
        expected_annotation: str,
        expected_inline_desc: str,
) -> None:
    parsed = _parse_param_signature_line(line)
    assert parsed is not None
    _indent, name, annotation, inline_desc = parsed
    assert name == expected_name
    assert annotation == expected_annotation
    assert inline_desc.strip() == expected_inline_desc
