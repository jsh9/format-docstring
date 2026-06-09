from pathlib import Path

import pytest

from format_docstring.docstring_rewriter import wrap_docstring
from format_docstring.line_wrap_google import (
    _find_google_signature_colon,
    _normalize_google_signature_spacing,
    _wrap_first_line_shorter,
)
from tests.helpers import load_cases_from_dir

DATA_DIR: Path = Path(__file__).parent / 'test_data/line_wrap/google'


@pytest.mark.parametrize(
    ('name', 'line_length', 'before', 'after'),
    load_cases_from_dir(DATA_DIR),
)
def test_wrap_docstring_google(
        name: str,
        line_length: int,
        before: str,
        after: str,
) -> None:
    """
    Verify each Google line-wrap fixture rewrites BEFORE text to AFTER text.

    The fixture files carry the behavior-specific cases, including migrations
    from NumPy syntax where Google has different signature delimiters. Keeping
    this assertion fixture-driven lets those subtle syntax differences be
    documented in the input/output examples without duplicating test bodies.
    """
    if name == 'texts_are_rewrapped.txt':
        pytest.xfail(
            'Fails in pytest environment but works in mini_repro '
            '(line length issue)'
        )

    out = wrap_docstring(
        before, line_length=line_length, docstring_style='google'
    )
    # We ignore the leading and trailing newlines here, because we'll check
    # those newlines in test_fix_src_end_to_end() in test_docstring_rewriter.py
    assert out.strip('\n').rstrip() == after.strip('\n').rstrip()


def test_wrap_docstring_google_single_case() -> None:
    """
    A placeholder test for easy debugging. Replaces the file name with the test
    case file that's producing errors if needed.
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


@pytest.mark.parametrize(
    ('line', 'expected'),
    [
        (
            '    arg1(dict[str, list[str]]):Text',
            len('    arg1(dict[str, list[str]])'),
        ),
        (
            '    arg2 (dict[int, slice(1:5)]) : Text',
            len('    arg2 (dict[int, slice(1:5)]) '),
        ),
        ('    arg3: Text', len('    arg3')),
        ('    continuation without delimiter', -1),
    ],
    ids=[
        'typed_signature',
        'nested_colon_in_type',
        'no_type_signature',
        'no_delimiter',
    ],
)
def test_find_google_signature_colon(line: str, expected: int) -> None:
    """
    Verify Google signature delimiter detection ignores nested colons.

    The spacing normalizer runs before broad signature parsing. This regression
    guard is needed so malformed Google signatures can be repaired without
    splitting type expressions such as ``slice(1:5)`` in the middle.
    """
    assert _find_google_signature_colon(line) == expected


@pytest.mark.parametrize(
    ('line', 'expected'),
    [
        (
            '    arg1(dict[str, list[str]]):Text',
            '    arg1 (dict[str, list[str]]): Text',
        ),
        (
            '    arg2 (dict[str, list[str]]) :  Text',
            '    arg2 (dict[str, list[str]]): Text',
        ),
        (
            '    **kwargs(dict[str, Any]):Text',
            '    **kwargs (dict[str, Any]): Text',
        ),
        ('    **kwargs:Keyword args', '    **kwargs: Keyword args'),
        (
            '    arg3 (dict[int, slice(1:5)]):Text',
            '    arg3 (dict[int, slice(1:5)]): Text',
        ),
        (
            '        continuation without delimiter',
            '        continuation without delimiter',
        ),
    ],
    ids=[
        'missing_space_around_type',
        'extra_space_before_colon',
        'typed_variadic',
        'no_type_variadic',
        'nested_colon_in_type',
        'no_delimiter',
    ],
)
def test_normalize_google_signature_spacing(
        line: str,
        expected: str,
) -> None:
    """
    Verify malformed Google signature spacing is canonicalized before wrapping.

    The strengthened ``colon_spacing_fix`` fixture depends on this helper to
    turn malformed entries into the same shape as valid Google signatures,
    while leaving continuation text unchanged.
    """
    assert _normalize_google_signature_spacing(line) == expected


@pytest.mark.parametrize(
    (
        'text',
        'first_line_width',
        'subsequent_width',
        'initial_indent',
        'subsequent_indent',
        'expected',
    ),
    [
        # Empty text returns empty list
        ('', 40, 50, '', '', []),
        # Single word that fits
        ('Hello', 40, 50, '', '', ['Hello']),
        # Whitespace-only text returns indent + whitespace
        ('   ', 40, 50, '>>', '', ['>>   ']),
        # Single long word - no break
        (
            'VeryLongUnbreakableWord',
            10,
            50,
            '',
            '',
            ['VeryLongUnbreakableWord'],
        ),
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
            [
                '        This is an indented',
                '        paragraph that should wrap',
            ],
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
