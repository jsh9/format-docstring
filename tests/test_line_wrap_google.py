from pathlib import Path

import pytest

from format_docstring.docstring_rewriter import wrap_docstring
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
