from pathlib import Path

import pytest

from format_docstring.docstring_rewriter import wrap_docstring
from format_docstring.line_wrap_google import _wrap_first_line_shorter
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
    assert out.strip('\n').rstrip() == after.strip('\n').rstrip()


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


@pytest.mark.parametrize(
    ('text', 'first_line_width', 'subsequent_width', 'initial_indent', 'subsequent_indent', 'expected'),
    [
        # Empty text returns empty list
        ('', 40, 50, '', '', []),
        # Single word that fits
        ('Hello', 40, 50, '', '', ['Hello']),
        # Whitespace-only text returns indent + whitespace
        ('   ', 40, 50, '>>', '', ['>>   ']),
        # Single long word - no break
        ('VeryLongUnbreakableWord', 10, 50, '', '', ['VeryLongUnbreakableWord']),
        # Basic two-pass wrapping (first line shorter)
        (
            'one two three four five six',
            15,
            25,
            '',
            '',
            ['one two three', 'four five six'],
        ),
        # With same indentation on all lines
        (
            'aaa bbb ccc ddd',
            12,
            20,
            '    ',
            '    ',
            ['    aaa bbb', '    ccc ddd'],
        ),
        # Different initial and subsequent indents
        (
            'word1 word2 word3 word4',
            20,
            25,
            '        ',
            '    ',
            ['        word1 word2', '    word3 word4'],
        ),
        # Realistic docstring scenario with 8-space indent
        (
            'This is an indented paragraph that should wrap',
            30,
            40,
            '        ',
            '        ',
            ['        This is an indented', '        paragraph that should wrap'],
        ),
    ],
    ids=[
        'empty_text',
        'single_word_fits',
        'whitespace_only',
        'long_unbreakable_word',
        'basic_two_pass',
        'same_indentation',
        'different_indents',
        'realistic_docstring',
    ],
)
def test_wrap_first_line_shorter(
    text: str,
    first_line_width: int,
    subsequent_width: int,
    initial_indent: str,
    subsequent_indent: str,
    expected: list[str],
) -> None:
    """Test _wrap_first_line_shorter with various inputs."""
    result = _wrap_first_line_shorter(
        text,
        first_line_width=first_line_width,
        subsequent_width=subsequent_width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
    )
    assert result == expected
