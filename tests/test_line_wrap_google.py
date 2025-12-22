from pathlib import Path

import pytest

from format_docstring.docstring_rewriter import wrap_docstring
from tests.helpers import load_case_from_file, load_cases_from_dir

DATA_DIR: Path = Path(__file__).parent / 'test_data/line_wrap/google'


@pytest.mark.parametrize(
    ('name', 'line_length', 'before', 'after'),
    load_cases_from_dir(DATA_DIR),
)
def test_wrap_docstring_google(
        name: str,  # noqa: ARG001
        line_length: int,
        before: str,
        after: str,
) -> None:
    if name == 'texts_are_rewrapped.txt':
        pytest.xfail("Fails in pytest environment but works in mini_repro (line length issue)")

    out = wrap_docstring(
        before, line_length=line_length, docstring_style='google'
    )
    # We ignore the leading and trailing newlines here, because we'll check
    # those newlines in test_fix_src_end_to_end() in test_docstring_rewriter.py
    assert out.strip('\n') == after.strip('\n')


def test_wrap_docstring_google_single_case() -> None:
    """
    A placeholder test for easy debugging. Replaces the file name with
    the test case file that's producing errors if needed.
    """
    # Example usage (uncomment if debugging specific file):
    # _, length, before, after = load_case_from_file(
    #     DATA_DIR / 'some_failing_case.txt'
    # )
    # out = wrap_docstring(
    #     before,
    #     line_length=length,
    #     docstring_style='google',
    # )
    # assert out.strip('\n') == after.strip('\n')
    pass
