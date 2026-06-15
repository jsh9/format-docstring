from __future__ import annotations

from collections.abc import Callable

import pytest

from format_docstring.line_wrap_utils import (
    add_leading_indent,
    finalize_lines,
    fix_typos_in_section_headings,
    is_bulleted_list,
    is_code_fence,
    is_examples_code_block,
    is_google_doctest_block,
    is_google_examples_code_block,
    is_literal_block_paragraph,
    is_rST_table,
    is_rst_code_block,
    merge_lines_and_strip,
    process_temp_output,
    segment_lines_by_wrappability,
    wrap_preserving_indent,
)


@pytest.mark.parametrize(
    ('lines', 'width', 'expected'),
    [
        (
            ['    This is an indented paragraph that should wrap.'],
            30,
            [
                '    This is an indented',
                '    paragraph that should',
                '    wrap.',
            ],
        ),
        (
            ['NoIndentButLongEnoughToWrap into multiple parts'],
            20,
            [
                'NoIndentButLongEnoughToWrap',
                'into multiple parts',
            ],
        ),
        (
            ['    Short line'],
            30,
            ['    Short line'],
        ),
        (
            ['Exact width line'],
            len('Exact width line'),
            ['Exact width line'],
        ),
        (
            ['    supercalifragilisticexpialidocious'],
            10,
            ['    supercalifragilisticexpialidocious'],
        ),
        (
            ['    with\ttab here'],
            14,
            [
                '    with',
                '    tab here',
            ],
        ),
        (
            ['abc def'],
            2,
            [
                'abc',
                'def',
            ],
        ),
        (
            ['        a b c d e'],
            10,
            [
                '        a',
                '        b',
                '        c',
                '        d',
                '        e',
            ],
        ),
        # Re-wrapping tests: paragraph wrapped to 50 can be re-wrapped to 30
        (
            [
                '    This is a very long paragraph that needs to be wrapped',
                '    because it exceeds the line length limit significantly.',
            ],
            30,
            [
                '    This is a very long',
                '    paragraph that needs to be',
                '    wrapped because it exceeds',
                '    the line length limit',
                '    significantly.',
            ],
        ),
        # Re-wrapping tests: paragraph wrapped to 30 can be re-wrapped to 50
        (
            [
                '    This is a very',
                '    long paragraph that',
                '    needs to be wrapped',
            ],
            50,
            [
                '    This is a very long paragraph that needs to be',
                '    wrapped',
            ],
        ),
        # Multiple paragraphs preserve paragraph breaks
        (
            [
                '    First paragraph is quite long.',
                '    It continues here.',
                '',
                '    Second paragraph is also long.',
                '    It continues here too.',
            ],
            40,
            [
                '    First paragraph is quite long. It',
                '    continues here.',
                '',
                '    Second paragraph is also long. It',
                '    continues here too.',
            ],
        ),
        # Test with rST table (should be preserved)
        (
            [
                'Here is some text that should wrap. 1.',
                '',
                '+------+-----+',
                '| Name | Age |',
                '+------+-----+',
                '| John | 25  |',
                '+------+-----+',
                '',
                'More text that should wrap.',
            ],
            20,
            [
                'Here is some text',
                'that should wrap. 1.',
                '',
                '+------+-----+',
                '| Name | Age |',
                '+------+-----+',
                '| John | 25  |',
                '+------+-----+',
                '',
                'More text that',
                'should wrap.',
            ],
        ),
        # Test with bulleted list (should be preserved)
        (
            [
                'This is a very long line of text that should be wrapped. 2',
                '',
                '- First list item that is quite long',
                '- Second list item that is also long',
                '',
                'Another long line that should be wrapped.',
            ],
            25,
            [
                'This is a very long line',
                'of text that should be',
                'wrapped. 2',
                '',
                '- First list item that is quite long',
                '- Second list item that is also long',
                '',
                'Another long line that',
                'should be wrapped.',
            ],
        ),
    ],
)
def test_wrap_preserving_indent(
        lines: list[str], width: int, expected: list[str]
) -> None:
    assert wrap_preserving_indent(lines, width) == expected


@pytest.mark.parametrize(
    ('docstring', 'leading_indent', 'expected'),
    [
        ('Hello', 4, '\n    Hello'),
        ('\n    Hello', 4, '\n    Hello'),  # unchanged when already present
        ('Hello', None, 'Hello'),
        ('Hello', 0, '\nHello'),
    ],
)
def test_add_leading_indent(
        docstring: str, leading_indent: int | None, expected: str
) -> None:
    assert add_leading_indent(docstring, leading_indent) == expected


@pytest.mark.parametrize(
    ('lines', 'leading_indent', 'expected'),
    [
        (
            ['foo  ', '   ', 'bar   '],
            None,
            'foo\n\nbar',
        ),
        (
            ['foo  ', '   ', 'bar   '],
            2,
            'foo\n\nbar\n  ',
        ),
        (
            ['   ', '   '],
            3,
            '\n   ',
        ),
    ],
)
def test_finalize_lines(
        lines: list[str], leading_indent: int | None, expected: str
) -> None:
    assert finalize_lines(lines, leading_indent) == expected


@pytest.mark.parametrize(
    ('temp_out', 'width', 'expected'),
    [
        (
            [
                'Examples::',
                '',
                ['    code line 1', '    code line 2'],
            ],
            20,
            [
                'Examples::',
                '',
                '    code line 1',
                '    code line 2',
            ],
        ),
        (
            [
                'Examples::',
                '',
                [
                    '    literal block with long text that should remain'
                    ' on one line even though width is short'
                ],
            ],
            30,
            [
                'Examples::',
                '',
                (
                    '    literal block with long text that should remain'
                    ' on one line even though width is short'
                ),
            ],
        ),
        (
            [
                'Examples::',
                '',
                '',  # 2 empty lines: not protected by `::` above -> will wrap
                [
                    (
                        '    literal block with long text that should remain'
                        ' on one line even though width is short'
                    )
                ],
            ],
            30,
            [
                'Examples::',
                '',
                '',
                '    literal block with long',
                '    text that should remain on',
                '    one line even though width',
                '    is short',
            ],
        ),
        (
            [
                'Examples::',
                'no blank separator',
                ['    code line 1', '    code line 2'],
            ],
            40,
            [
                'Examples::',
                'no blank separator',
                '    code line 1 code line 2',
            ],
        ),
        (
            [
                'Examples::',
                '',
                '',
                'Trailing text',
            ],
            25,
            [
                'Examples::',
                '',
                '',
                'Trailing text',
            ],
        ),
    ],
)
def test_process_temp_output_merges_literal_block(
        temp_out: list[str | list[str]],
        width: int,
        expected: list[str],
) -> None:
    assert process_temp_output(temp_out, width) == expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        (
            '    something like this\n    and this is the second\n    line,'
            '\n    and this is the 3rd\n    line.',
            'something like this and this is the second line, and this is the'
            ' 3rd line.',
        ),
        (
            'no indent here\nand here\ntoo',
            'no indent here and here too',
        ),
        (
            '  leading spaces  \n  trailing spaces  \n  both  ',
            'leading spaces trailing spaces both',
        ),
        (
            'single line',
            'single line',
        ),
        (
            '    \n    \n    ',
            '',
        ),
        (
            'first line\n\nsecond line\n\nthird line',
            'first line\n\nsecond line\n\nthird line',
        ),
        (
            '    mixed    \nno indent\n    indent again    ',
            'mixed no indent indent again',
        ),
        (
            '',
            '',
        ),
        (
            'line one\n    indented line two\nline three',
            'line one indented line two line three',
        ),
        (
            '\n\n\n',
            '',
        ),
        (
            'paragraph one line one\nparagraph one line two\n\nparagraph two'
            ' line one\nparagraph two line two',
            'paragraph one line one paragraph one line two\n\nparagraph two'
            ' line one paragraph two line two',
        ),
        (
            '  first para  \n  continues here  \n\n  second para'
            '  \n  continues here  ',
            'first para continues here\n\nsecond para continues here',
        ),
        (
            'single\n\n\n\nmultiple breaks\n\nhere',
            'single\n\nmultiple breaks\n\nhere',
        ),
        (
            'line 1\nline 2\n\n\nline 3\nline 4\n\n\n\nline 5',
            'line 1 line 2\n\nline 3 line 4\n\nline 5',
        ),
    ],
)
def test_merge_lines_and_strip(text: str, expected: str) -> None:
    assert merge_lines_and_strip(text) == expected


@pytest.mark.parametrize(
    ('lines', 'expected'),
    [
        # Test basic typo corrections
        (
            ['Return', '------'],
            ['Returns', '-------'],
        ),
        (
            ['Parameter', '---------'],
            ['Parameters', '----------'],
        ),
        (
            ['Other Parameter', '---------------'],
            ['Other Parameters', '----------------'],
        ),
        (
            ['Attribute', '---------'],
            ['Attributes', '----------'],
        ),
        (
            ['Yield', '-----'],
            ['Yields', '------'],
        ),
        (
            ['Raise', '-----'],
            ['Raises', '------'],
        ),
        # Test with indentation
        (
            ['    Return', '    ------'],
            ['    Returns', '    -------'],
        ),
        (
            ['  Parameter', '  ---------'],
            ['  Parameters', '  ----------'],
        ),
        # Test mixed content with typos
        (
            [
                'Some function description.',
                '',
                'Parameter',
                '---------',
                'x : int',
                '    The parameter x.',
                '',
                'Return',
                '------',
                'str',
                '    The return value.',
            ],
            [
                'Some function description.',
                '',
                'Parameters',
                '----------',
                'x : int',
                '    The parameter x.',
                '',
                'Returns',
                '-------',
                'str',
                '    The return value.',
            ],
        ),
        # Test no changes when no typos
        (
            ['Returns', '-------'],
            ['Returns', '-------'],
        ),
        (
            ['Parameters', '----------'],
            ['Parameters', '----------'],
        ),
        # Test edge cases
        (
            [],
            [],
        ),
        (
            ['Single line'],
            ['Single line'],
        ),
        # Test non-section headings are not affected
        (
            ['Return value is good', 'Not a dash line'],
            ['Return value is good', 'Not a dash line'],
        ),
        # Test insufficient dashes (less than 2)
        (
            ['Return', '-'],
            ['Return', '-'],
        ),
        # Test sufficient dashes (>= 2)
        (
            ['Return', '--'],
            ['Returns', '-------'],
        ),
        # Test dashes with extra characters
        (
            ['Return', '------extra'],
            ['Return', '------extra'],
        ),
        # Test multiple typos in same docstring
        (
            [
                'Function description.',
                '',
                'Parameter',
                '---------',
                'x : int',
                '    First param.',
                '',
                'Yield',
                '-----',
                'str',
                '    Yielded value.',
                '',
                'Raise',
                '-----',
                'ValueError',
                '    When x is negative.',
            ],
            [
                'Function description.',
                '',
                'Parameters',
                '----------',
                'x : int',
                '    First param.',
                '',
                'Yields',
                '------',
                'str',
                '    Yielded value.',
                '',
                'Raises',
                '------',
                'ValueError',
                '    When x is negative.',
            ],
        ),
        # Test case-insensitive matching
        (
            ['reTurn', '------'],
            ['Returns', '-------'],
        ),
        (
            ['PARAMETER', '---------'],
            ['Parameters', '----------'],
        ),
        (
            ['other parameter', '---------------'],
            ['Other Parameters', '----------------'],
        ),
        (
            ['AtTrIbUtE', '---------'],
            ['Attributes', '----------'],
        ),
        (
            ['YiElD', '-----'],
            ['Yields', '------'],
        ),
        (
            ['RAISE', '-----'],
            ['Raises', '------'],
        ),
        # Test mixed case with indentation
        (
            ['    reTuRn', '    ------'],
            ['    Returns', '    -------'],
        ),
        # Test case-insensitive with mixed content
        (
            [
                'Some function description.',
                '',
                'paRaMeter',
                '---------',
                'x : int',
                '    The parameter x.',
                '',
                'reTUrn',
                '------',
                'str',
                '    The return value.',
            ],
            [
                'Some function description.',
                '',
                'Parameters',
                '----------',
                'x : int',
                '    The parameter x.',
                '',
                'Returns',
                '-------',
                'str',
                '    The return value.',
            ],
        ),
        # Test case-only corrections (correct spelling, wrong case)
        (
            ['returns', '-------'],
            ['Returns', '-------'],
        ),
        (
            ['parameters', '----------'],
            ['Parameters', '----------'],
        ),
        (
            ['other parameters', '----------------'],
            ['Other Parameters', '----------------'],
        ),
        (
            ['attributes', '----------'],
            ['Attributes', '----------'],
        ),
        (
            ['yields', '------'],
            ['Yields', '------'],
        ),
        (
            ['raises', '------'],
            ['Raises', '------'],
        ),
        # Test case-only corrections with indentation
        (
            ['    parameters', '    ----------'],
            ['    Parameters', '    ----------'],
        ),
        (
            ['  returns', '  -------'],
            ['  Returns', '  -------'],
        ),
    ],
)
def test_fix_typos_in_section_headings(
        lines: list[str], expected: list[str]
) -> None:
    assert fix_typos_in_section_headings(lines) == expected


@pytest.mark.parametrize(
    ('lines', 'start_idx', 'expected_is_table', 'expected_end_idx'),
    [
        # Basic grid table
        (
            [
                '+------+-----+',
                '| Name | Age |',
                '+======+=====+',
                '| John | 25  |',
                '+------+-----+',
            ],
            0,
            True,
            5,
        ),
        # Grid table with multiple rows
        (
            [
                '+------+-----+',
                '| Name | Age |',
                '+======+=====+',
                '| John | 25  |',
                '+------+-----+',
                '| Jane | 30  |',
                '+------+-----+',
            ],
            0,
            True,
            7,
        ),
        # Simple table
        (
            [
                '===== =====',
                'Name  Age',
                '===== =====',
                'John  25',
                'Jane  30',
                '===== =====',
            ],
            0,
            True,
            6,
        ),
        # Grid table followed by non-table content
        (
            [
                '+------+-----+',
                '| Name | Age |',
                '+------+-----+',
                '',
                'This is not a table',
            ],
            0,
            True,
            3,
        ),
        # Simple table followed by non-table content
        (
            [
                '===== =====',
                'Name  Age',
                '===== =====',
                '',
                'This is not a table',
            ],
            0,
            True,
            3,
        ),
        # Not a table - missing grid structure
        (
            [
                '| Name | Age |',
                '| John | 25  |',
            ],
            0,
            False,
            0,
        ),
        # Not a table - invalid grid start
        (
            [
                'Name Age',
                '--------',
            ],
            0,
            False,
            0,
        ),
        # Empty lines
        (
            [],
            0,
            False,
            0,
        ),
        # Single line
        (
            ['+------+-----+'],
            0,
            False,
            0,
        ),
        # Grid table starting at different index
        (
            [
                'Some text',
                '+------+-----+',
                '| Name | Age |',
                '+------+-----+',
            ],
            1,
            True,
            4,
        ),
        # Invalid start index
        (
            ['+------+-----+', '| Name | Age |'],
            5,
            False,
            5,
        ),
        # Grid table with indentation
        (
            [
                '    +------+-----+',
                '    | Name | Age |',
                '    +------+-----+',
            ],
            0,
            True,
            3,
        ),
        # Minimal grid table
        (
            [
                '+-+',
                '|A|',
                '+-+',
            ],
            0,
            True,
            3,
        ),
        # Simple table with headers
        (
            [
                '===== ===== =====',
                'A     B     C',
                '===== ===== =====',
                '1     2     3',
                '===== ===== =====',
            ],
            0,
            True,
            5,
        ),
        # Invalid simple table - no ending separator
        (
            [
                '===== =====',
                'Name  Age',
                '===== =====',
                'John  25',
            ],
            0,
            False,
            0,
        ),
        # Grid table with header separator
        (
            [
                '+------+-----+',
                '| Name | Age |',
                '+======+=====+',
                '| John | 25  |',
                '| Jane | 30  |',
                '+------+-----+',
            ],
            0,
            True,
            6,
        ),
        # Not a table - incomplete grid
        (
            [
                '+------+-----',
                '| Name | Age |',
                '+------+-----+',
            ],
            0,
            False,
            0,
        ),
        # Simple table minimal
        (
            [
                '===',
                'A',
                '===',
            ],
            0,
            True,
            3,
        ),
    ],
)
def test_is_rST_table(  # noqa: N802
        lines: list[str],
        start_idx: int,
        *,
        expected_is_table: bool,
        expected_end_idx: int,
) -> None:
    is_table, end_idx = is_rST_table(lines, start_idx)
    assert is_table == expected_is_table
    assert end_idx == expected_end_idx


@pytest.mark.parametrize(
    ('lines', 'start_idx', 'expected_is_list', 'expected_end_idx'),
    [
        # Basic unordered list with dashes
        (
            [
                '- First item',
                '- Second item',
                '- Third item',
            ],
            0,
            True,
            3,
        ),
        # Basic unordered list with asterisks
        (
            [
                '* First item',
                '* Second item',
                '* Third item',
            ],
            0,
            True,
            3,
        ),
        # Basic unordered list with plus signs
        (
            [
                '+ First item',
                '+ Second item',
                '+ Third item',
            ],
            0,
            True,
            3,
        ),
        # Basic ordered list with dots
        (
            [
                '1. First item',
                '2. Second item',
                '3. Third item',
            ],
            0,
            True,
            3,
        ),
        # Basic ordered list with parentheses
        (
            [
                '1) First item',
                '2) Second item',
                '3) Third item',
            ],
            0,
            True,
            3,
        ),
        # Single list item
        (
            ['- Only item'],
            0,
            True,
            1,
        ),
        # List with indentation
        (
            [
                '    - Indented first',
                '    - Indented second',
            ],
            0,
            True,
            2,
        ),
        # List followed by non-list content
        (
            [
                '- First item',
                '- Second item',
                '',
                'Not a list item',
            ],
            0,
            True,
            2,
        ),
        # Mixed list types (should stop at first mismatch)
        (
            [
                '- First item',
                '1. Second item',
                '- Third item',
            ],
            0,
            True,
            1,
        ),
        # Not a list - no bullet/number
        (
            [
                'Regular text',
                'More text',
            ],
            0,
            False,
            0,
        ),
        # Not a list - missing space after bullet
        (
            [
                '-No space',
                '-Still no space',
            ],
            0,
            False,
            0,
        ),
        # Not a list - missing space after number
        (
            [
                '1.No space',
                '2.Still no space',
            ],
            0,
            False,
            0,
        ),
        # Empty lines
        (
            [],
            0,
            False,
            0,
        ),
        # Empty first line
        (
            [''],
            0,
            False,
            0,
        ),
        # List starting at different index
        (
            [
                'Some text',
                '- First item',
                '- Second item',
            ],
            1,
            True,
            3,
        ),
        # Invalid start index
        (
            ['- Item'],
            5,
            False,
            5,
        ),
        # Ordered list with multi-digit numbers
        (
            [
                '10. Tenth item',
                '11. Eleventh item',
                '99. Ninety-ninth item',
            ],
            0,
            True,
            3,
        ),
        # List interrupted by empty line
        (
            [
                '- First item',
                '- Second item',
                '',
                '- Third item',
            ],
            0,
            True,
            2,
        ),
        # Mixed indentation in unordered list
        (
            [
                '- First item',
                '  - Indented second',
                '- Third item',
            ],
            0,
            True,
            3,
        ),
        # Different ordered list formats mixed (should stop)
        (
            [
                '1. First with dot',
                '2) Second with paren',
            ],
            0,
            True,
            1,
        ),
        # List with complex content
        (
            [
                '- Item with `code`',
                '- Item with **bold** text',
                '- Item with [link](url)',
            ],
            0,
            True,
            3,
        ),
        # Multi-line unordered list items
        (
            [
                '- First item that spans',
                '  multiple lines with',
                '  continuation content',
                '- Second item also',
                '  has multiple lines',
                '- Third item',
            ],
            0,
            True,
            6,
        ),
        # Multi-line ordered list items
        (
            [
                '1. First numbered item',
                '   with continuation',
                '2. Second numbered item',
                '   also has continuation',
                '   and more content',
                '3. Third item',
            ],
            0,
            True,
            6,
        ),
        # Mixed single and multi-line items
        (
            [
                '- Single line item',
                '- Multi-line item',
                '  with continuation',
                '- Another single line',
                '- Final multi-line',
                '  with more content',
            ],
            0,
            True,
            6,
        ),
        # Multi-line item with deeply indented content
        (
            [
                '* Item with code block',
                '    def function():',
                '        return True',
                '* Second item',
            ],
            0,
            True,
            4,
        ),
        # Multi-line item interrupted by non-continuation
        (
            [
                '- First item',
                '  with continuation',
                'Not a continuation - too little indent',
                '- Second item',
            ],
            0,
            True,
            2,
        ),
        # Parenthesized numbered list
        (
            [
                '(1) First parenthesized item',
                '(2) Second parenthesized item',
                '(3) Third parenthesized item',
            ],
            0,
            True,
            3,
        ),
        # Multi-line parenthesized numbered list
        (
            [
                '(1) First item with',
                '    continuation lines',
                '(2) Second item also',
                '    has continuations',
                '(3) Third item',
            ],
            0,
            True,
            5,
        ),
        # Mixed parenthesized format should stop at format change
        (
            [
                '(1) Parenthesized format',
                '2. Dot format',
            ],
            0,
            True,
            1,
        ),
        # Parenthesized format with complex content
        (
            [
                '(1) Item with `code` and **bold**',
                '(2) Item with [link](url)',
                '(10) Double-digit item',
            ],
            0,
            True,
            3,
        ),
    ],
)
def test_is_bulleted_list(
        lines: list[str],
        start_idx: int,
        *,
        expected_is_list: bool,
        expected_end_idx: int,
) -> None:
    is_list, end_idx = is_bulleted_list(lines, start_idx)
    assert is_list == expected_is_list
    assert end_idx == expected_end_idx


@pytest.mark.parametrize(
    ('lines', 'expected_segments'),
    [
        # Empty input
        (
            [],
            [],
        ),
        # Only wrappable text
        (
            [
                'This is some text',
                'that can be wrapped',
                'across multiple lines',
            ],
            [
                (
                    [
                        'This is some text',
                        'that can be wrapped',
                        'across multiple lines',
                    ],
                    True,
                ),
            ],
        ),
        # Only a bulleted list
        (
            [
                '- First item',
                '- Second item',
                '- Third item',
            ],
            [
                (['- First item', '- Second item', '- Third item'], False),
            ],
        ),
        # Only an rST grid table
        (
            [
                '+------+-----+',
                '| Name | Age |',
                '+------+-----+',
                '| John | 25  |',
                '+------+-----+',
            ],
            [
                (
                    [
                        '+------+-----+',
                        '| Name | Age |',
                        '+------+-----+',
                        '| John | 25  |',
                        '+------+-----+',
                    ],
                    False,
                ),
            ],
        ),
        # Only an rST simple table
        (
            [
                '===== =====',
                'Name  Age',
                '===== =====',
                'John  25',
                '===== =====',
            ],
            [
                (
                    [
                        '===== =====',
                        'Name  Age',
                        '===== =====',
                        'John  25',
                        '===== =====',
                    ],
                    False,
                ),
            ],
        ),
        # Text followed by list
        (
            [
                'Here is some intro text',
                'that explains the list below:',
                '',
                '- First item',
                '- Second item',
            ],
            [
                (
                    [
                        'Here is some intro text',
                        'that explains the list below:',
                        '',
                    ],
                    True,
                ),
                (['- First item', '- Second item'], False),
            ],
        ),
        # List followed by text
        (
            [
                '1. First step',
                '2. Second step',
                '3. Third step',
                '',
                'This concludes the steps.',
            ],
            [
                (['1. First step', '2. Second step', '3. Third step'], False),
                (['', 'This concludes the steps.'], True),
            ],
        ),
        # Text, table, more text
        (
            [
                'Here is a table:',
                '',
                '+------+-----+',
                '| Name | Age |',
                '+------+-----+',
                '',
                'That was the table.',
            ],
            [
                (['Here is a table:', ''], True),
                (
                    ['+------+-----+', '| Name | Age |', '+------+-----+'],
                    False,
                ),
                (['', 'That was the table.'], True),
            ],
        ),
        # Multiple lists separated by text
        (
            [
                'First list:',
                '- Item A',
                '- Item B',
                '',
                'Second list:',
                '1. Step 1',
                '2. Step 2',
            ],
            [
                (['First list:'], True),
                (['- Item A', '- Item B'], False),
                (['', 'Second list:'], True),
                (['1. Step 1', '2. Step 2'], False),
            ],
        ),
        # Multiple tables
        (
            [
                'Table 1:',
                '===== =====',
                'A     B',
                '===== =====',
                '1     2',
                '===== =====',
                '',
                'Table 2:',
                '+---+---+',
                '| C | D |',
                '+---+---+',
            ],
            [
                (['Table 1:'], True),
                (
                    [
                        '===== =====',
                        'A     B',
                        '===== =====',
                        '1     2',
                        '===== =====',
                    ],
                    False,
                ),
                (['', 'Table 2:'], True),
                (['+---+---+', '| C | D |', '+---+---+'], False),
            ],
        ),
        # Complex mix: text, list, text, table, text
        (
            [
                'Introduction paragraph.',
                '',
                'Here are some items:',
                '* First item',
                '* Second item',
                '',
                'And here is data:',
                '',
                '+------+-------+',
                '| Name | Value |',
                '+======+=======+',
                '| Test | 123   |',
                '+------+-------+',
                '',
                'Conclusion.',
            ],
            [
                (
                    ['Introduction paragraph.', '', 'Here are some items:'],
                    True,
                ),
                (['* First item', '* Second item'], False),
                (['', 'And here is data:', ''], True),
                (
                    [
                        '+------+-------+',
                        '| Name | Value |',
                        '+======+=======+',
                        '| Test | 123   |',
                        '+------+-------+',
                    ],
                    False,
                ),
                (['', 'Conclusion.'], True),
            ],
        ),
        # Single line segments
        (
            [
                'Line 1',
                '- List item',
                'Line 2',
            ],
            [
                (['Line 1'], True),
                (['- List item'], False),
                (['Line 2'], True),
            ],
        ),
        # Adjacent non-wrappable structures
        (
            [
                '- List item 1',
                '- List item 2',
                '+-----+-----+',
                '| A   | B   |',
                '+-----+-----+',
                '1. Step 1',
                '2. Step 2',
            ],
            [
                (['- List item 1', '- List item 2'], False),
                (['+-----+-----+', '| A   | B   |', '+-----+-----+'], False),
                (['1. Step 1', '2. Step 2'], False),
            ],
        ),
        # List interrupted by empty line (should create separate segments)
        (
            [
                '- First item',
                '- Second item',
                '',
                '- Third item after gap',
            ],
            [
                (['- First item', '- Second item'], False),
                ([''], True),
                (['- Third item after gap'], False),
            ],
        ),
        # Mixed ordered list formats (should split)
        (
            [
                'Text before',
                '1. First with dot',
                '2) Second with paren',
                'Text after',
            ],
            [
                (['Text before'], True),
                (['1. First with dot'], False),
                (['2) Second with paren'], False),
                (['Text after'], True),
            ],
        ),
        # Literal block following ::
        (
            [
                'This is an example::',
                '',
                '    def function():',
                '        return True',
                '    print("Hello")',
                '',
                'Back to regular text',
            ],
            [
                (['This is an example::'], True),
                (
                    [
                        '',
                        '    def function():',
                        '        return True',
                        '    print("Hello")',
                        '',
                    ],
                    False,
                ),
                (['Back to regular text'], True),
            ],
        ),
        # Unindented content after ``::`` is prose, not a literal block.
        (
            [
                'Here is code::',
                'import sys',
                'print(sys.version)',
                '',
                'Regular text again',
            ],
            [
                (
                    [
                        'Here is code::',
                        'import sys',
                        'print(sys.version)',
                        '',
                        'Regular text again',
                    ],
                    True,
                ),
            ],
        ),
        # Multiple literal blocks
        (
            [
                'First example::',
                '',
                '    code block 1',
                '    more code',
                '',
                'Second example::',
                '',
                '    code block 2',
                '',
                'Regular text',
            ],
            [
                (['First example::'], True),
                (['', '    code block 1', '    more code', ''], False),
                (['Second example::'], True),
                (['', '    code block 2', ''], False),
                (['Regular text'], True),
            ],
        ),
        # Literal block with mixed content
        (
            [
                'Example with table and literal::',
                '',
                '    def func():',
                '        pass',
                '',
                '- List item',
                '- Another item',
            ],
            [
                (['Example with table and literal::'], True),
                (['', '    def func():', '        pass', ''], False),
                (['- List item', '- Another item'], False),
            ],
        ),
        # rST code directive block followed by prose
        (
            [
                'Examples:',
                '',
                '.. code-block:: python',
                '',
                '    value = `template`',
                '',
                'Back to regular text',
            ],
            [
                (['Examples:', ''], True),
                (
                    [
                        '.. code-block:: python',
                        '',
                        '    value = `template`',
                        '',
                    ],
                    False,
                ),
                (['Back to regular text'], True),
            ],
        ),
        # Text ending with :: but no following content
        (
            [
                'This ends with double colon::',
                '',
            ],
            [
                (['This ends with double colon::', ''], True),
            ],
        ),
    ],
)
def test_segment_lines_by_wrappability(
        lines: list[str], expected_segments: list[tuple[list[str], bool]]
) -> None:
    result = segment_lines_by_wrappability(lines)
    assert result == expected_segments


@pytest.mark.parametrize(
    ('lines', 'start_idx', 'detector', 'expected_is_code', 'expected_end_idx'),
    [
        (
            [
                (
                    '    result = call_function_with_a_really_long_argument_'
                    'name(first_argument, second_argument, third_argument)'
                ),
                '    print(result)',
                '',
                '    Back to prose.',
            ],
            0,
            is_examples_code_block,
            True,
            2,
        ),
        (
            [
                '    result = call_function(',
                '        first_argument,',
                '        second_argument,',
                '    )',
                '    print(result)',
            ],
            0,
            is_examples_code_block,
            True,
            5,
        ),
        (
            [
                (
                    '    # Use `raw` mode with a long comment that should '
                    'remain byte-for-byte as example code.'
                ),
                '    result = call(value)',
            ],
            0,
            is_examples_code_block,
            True,
            2,
        ),
        (
            [
                '    result = build_mapping(alpha, beta, gamma)',
                (
                    "    {'alpha': 'a very long value that is output and "
                    "should stay as written', 'beta': 2}"
                ),
            ],
            0,
            is_examples_code_block,
            True,
            2,
        ),
        (
            [
                (
                    '    This is a very long prose sentence in an examples '
                    'section that should still be wrapped by the formatter.'
                ),
            ],
            0,
            is_examples_code_block,
            False,
            0,
        ),
        (
            [
                '    result = compute_value()',
                'Args:',
                '    value: Description.',
            ],
            0,
            is_examples_code_block,
            True,
            1,
        ),
        (
            [
                'Examples:',
                '    result = compute_value()',
                '    Args:',
                '    done',
                'Args:',
                '    value: Description.',
            ],
            1,
            is_google_examples_code_block,
            True,
            4,
        ),
    ],
    ids=[
        'assignment_and_call',
        'multiline_call',
        'leading_comment',
        'repr_output',
        'prose_is_not_code',
        'stops_at_section',
        'google_indented_header_output',
    ],
)
def test_is_examples_code_block(
        lines: list[str],
        start_idx: int,
        detector: Callable[
            [list[str], int],
            tuple[bool, int],
        ],
        *,
        expected_is_code: bool,
        expected_end_idx: int,
) -> None:
    """
    Verify Examples code detection preserves only Python-like code blocks.

    This guard is needed because undetected example code enters the prose
    wrapping path, where adjacent lines are merged and long lines are wrapped.
    The same cases exercise default and Google detectors so the shared scanner
    can stay generic while boundary behavior remains style-specific.
    """
    is_code, end_idx = detector(lines, start_idx)
    assert is_code == expected_is_code
    assert end_idx == expected_end_idx


@pytest.mark.parametrize(
    (
        'lines',
        'start_idx',
        'detector',
        'expected_is_doctest',
        'expected_end_idx',
    ),
    [
        (
            [
                'Examples:',
                '    >>> print("Args:")',
                '    Args:',
                '    >>> print("done")',
                '    done',
                '',
                'Args:',
                '    value: Description.',
            ],
            1,
            is_google_doctest_block,
            True,
            5,
        ),
        (
            [
                'Examples:',
                '    >>> print("done")',
                '    done',
                'Args:',
                '    value: Description.',
            ],
            1,
            is_google_doctest_block,
            True,
            3,
        ),
    ],
    ids=['google_preserves_indented_header_output', 'google_stops_at_peer'],
)
def test_is_doctest_block_uses_google_indentation_boundaries(
        lines: list[str],
        start_idx: int,
        detector: Callable[
            [list[str], int],
            tuple[bool, int],
        ],
        *,
        expected_is_doctest: bool,
        expected_end_idx: int,
) -> None:
    """
    Verify Google doctest output can look like section headers.

    A peer section header exits the doctest; an indented header-looking output
    line remains part of the preserved doctest block.
    """
    is_doctest, end_idx = detector(lines, start_idx)
    assert is_doctest == expected_is_doctest
    assert end_idx == expected_end_idx


@pytest.mark.parametrize(
    ('lines', 'start_idx', 'expected_is_literal', 'expected_end_idx'),
    [
        (
            [
                'Example::',
                '',
                '    first = `template`',
                '',
                '    second = `name`',
                '',
                'Back to prose',
            ],
            1,
            True,
            6,
        ),
        (
            [
                'Example::',
                'Not indented prose',
            ],
            1,
            False,
            1,
        ),
        (
            [
                'Summary::',
                '',
                '    code-like text',
                '',
                '    Args:',
                '        value: Description',
            ],
            1,
            True,
            4,
        ),
    ],
    ids=['internal_blank_lines', 'dedented_prose', 'section_boundary'],
)
def test_is_literal_block_paragraph_uses_indentation_boundaries(
        lines: list[str],
        start_idx: int,
        *,
        expected_is_literal: bool,
        expected_end_idx: int,
) -> None:
    """
    Verify ``::`` literal spans preserve internal blanks and stop at prose.

    This guards the rST boundary rule used by both wrapping and backtick
    masking: blank lines stay inside a literal block only while the next
    content remains indented past the introducing paragraph.
    """
    is_literal, end_idx = is_literal_block_paragraph(lines, start_idx)
    assert is_literal == expected_is_literal
    assert end_idx == expected_end_idx


@pytest.mark.parametrize(
    ('lines', 'start_idx', 'expected_is_code', 'expected_end_idx'),
    [
        (
            [
                '.. code-block:: python',
                '',
                '    value = `template`',
                '',
                'Back to prose',
            ],
            0,
            True,
            4,
        ),
        (
            [
                '  .. sourcecode:: python',
                '',
                '      value = `template`',
                '  Back to prose',
            ],
            0,
            True,
            3,
        ),
        (
            [
                '.. code::',
                '    value = `template`',
                'Back to prose',
            ],
            0,
            True,
            2,
        ),
        (
            [
                '.. note::',
                '',
                '    Not a code directive',
            ],
            0,
            False,
            0,
        ),
    ],
    ids=['code_block', 'sourcecode', 'code', 'not_code_directive'],
)
def test_is_rst_code_block_uses_indentation_boundaries(
        lines: list[str],
        start_idx: int,
        *,
        expected_is_code: bool,
        expected_end_idx: int,
) -> None:
    """
    Verify rST code directives are protected until dedented prose resumes.

    This is necessary because directive bodies can contain code syntax where
    single backticks are meaningful and must not be normalized as prose.
    """
    is_code, end_idx = is_rst_code_block(lines, start_idx)
    assert is_code == expected_is_code
    assert end_idx == expected_end_idx


@pytest.mark.parametrize(
    ('lines', 'start_idx', 'expected_is_fence', 'expected_end_idx'),
    [
        # Basic triple backtick code fence
        (
            [
                '```',
                'def foo():',
                '    pass',
                '```',
            ],
            0,
            True,
            4,
        ),
        # Code fence with language identifier
        (
            [
                '```python',
                'def foo():',
                '    pass',
                '```',
            ],
            0,
            True,
            4,
        ),
        # Triple tilde code fence
        (
            [
                '~~~',
                'code here',
                '~~~',
            ],
            0,
            True,
            3,
        ),
        # Tilde fence with language identifier
        (
            [
                '~~~bash',
                'echo "hello"',
                '~~~',
            ],
            0,
            True,
            3,
        ),
        # Code fence with indentation
        (
            [
                '    ```',
                '    def bar():',
                '        return 1',
                '    ```',
            ],
            0,
            True,
            4,
        ),
        # Not a code fence - doesn't start with ```
        (
            [
                'regular text',
                'more text',
            ],
            0,
            False,
            0,
        ),
        # Empty lines list
        (
            [],
            0,
            False,
            0,
        ),
        # Invalid start index
        (
            ['```', 'code', '```'],
            5,
            False,
            5,
        ),
        # Code fence starting at different index
        (
            [
                'Some text before',
                '```',
                'code inside fence',
                '```',
                'text after',
            ],
            1,
            True,
            4,
        ),
        # Unclosed code fence - should treat rest as code block
        (
            [
                '```',
                'code without closing',
                'more code',
            ],
            0,
            True,
            3,
        ),
        # Empty code fence
        (
            [
                '```',
                '```',
            ],
            0,
            True,
            2,
        ),
        # Code fence with multiple language specifiers (common in markdown)
        (
            [
                '```python3',
                'print("hello")',
                '```',
            ],
            0,
            True,
            3,
        ),
        # Code fence with spaces after backticks
        (
            [
                '```   ',
                'content',
                '```',
            ],
            0,
            True,
            3,
        ),
        # Line starting with `` (two backticks, not three)
        (
            [
                '``not a fence``',
                'regular text',
            ],
            0,
            False,
            0,
        ),
        # Single backtick - not a fence
        (
            [
                '`inline code`',
                'more text',
            ],
            0,
            False,
            0,
        ),
        # Code fence followed by more content
        (
            [
                '```',
                'code',
                '```',
                '',
                'Normal paragraph',
            ],
            0,
            True,
            3,
        ),
    ],
)
def test_is_code_fence(
        lines: list[str],
        start_idx: int,
        expected_is_fence: bool,
        expected_end_idx: int,
) -> None:
    is_fence, end_idx = is_code_fence(lines, start_idx)
    assert is_fence == expected_is_fence
    assert end_idx == expected_end_idx
