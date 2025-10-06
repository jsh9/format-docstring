import ast
from pathlib import Path
from textwrap import dedent

import pytest

import format_docstring.docstring_rewriter
from format_docstring import docstring_rewriter


@pytest.mark.parametrize(
    'src, expected',
    [
        ('', [0]),
        ('a\n\nxyz\n', [0, 2, 3, 7]),
        ('one\ntwo\nthree', [0, 4, 8]),
        ('\n', [0, 1]),
    ],
)
def test_calc_line_starts(src: str, expected: list[int]) -> None:
    """Validate line start offsets across several inputs."""
    assert docstring_rewriter.calc_line_starts(src) == expected


@pytest.mark.parametrize(
    'src, lineno, col, expected',
    [
        ('a\n\nxyz\n', 1, 0, 0),
        ('a\n\nxyz\n', 2, 0, 2),
        ('a\n\nxyz\n', 3, 2, 5),
        ('one\ntwo\nthree', 2, 1, 5),
    ],
)
def test_calc_abs_pos(src: str, lineno: int, col: int, expected: int) -> None:
    """Convert (lineno, col) to absolute indices using starts mapping."""
    starts = docstring_rewriter.calc_line_starts(src)
    assert docstring_rewriter.calc_abs_pos(starts, lineno, col) == expected


@pytest.mark.parametrize(
    'literal, content, expected',
    [
        ("'abc'", 'X', "'X'"),
        ('"abc"', 'Y', '"Y"'),
        ('"""abc"""', 'Z', '"""Z"""'),
        ('r"""abc"""', 'Q', 'r"""Q"""'),
        ("f'abc'", 'M', "f'M'"),
    ],
)
def test_rebuild_literal(literal: str, content: str, expected: str) -> None:
    """Ensure original prefixes and quote styles are preserved."""
    assert docstring_rewriter.rebuild_literal(literal, content) == expected


@pytest.mark.parametrize(
    'src, selector, has_doc',
    [
        (
            dedent(
                '''
                """mod doc"""

                class C:
                    """cls doc"""
                    pass

                def f():
                    """fn doc"""
                    return 1
                '''
            ),
            'module',
            True,
        ),
        ('x = 1\n', 'module', False),
        (
            dedent(
                '''
                class C:
                    """cls doc"""
                    pass
                '''
            ),
            'class',
            True,
        ),
        (
            dedent(
                '''
                def f():
                    """fn doc"""
                    return 1
                '''
            ),
            'function',
            True,
        ),
    ],
)
def test_find_docstring(src: str, selector: str, has_doc: bool) -> None:
    """Detect docstring Expr for module/class/function or absence thereof."""
    tree = ast.parse(src)
    if selector == 'module':
        node = tree
    elif selector == 'class':
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    else:
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef))

    expr = docstring_rewriter.find_docstring(node)
    assert (expr is not None) is has_doc


@pytest.mark.parametrize(
    'src, node_kind',
    [
        (
            dedent(
                '''
                """orig"""

                def f():
                    """doc"""
                    return 0
                '''
            ),
            'module',
        ),
        (
            dedent(
                '''
                def f():
                    """doc"""
                    return 0
                '''
            ),
            'function',
        ),
        (
            dedent(
                '''
                class C:
                    """cls"""
                    pass
                '''
            ),
            'class',
        ),
    ],
)
def test_build_replacement_docstring_no_change_for_short(
        src: str, node_kind: str
) -> None:
    """Short docstrings under limit should not produce replacements."""
    tree = ast.parse(src)
    starts = docstring_rewriter.calc_line_starts(src)

    if node_kind == 'module':
        node = tree
    elif node_kind == 'class':
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    else:
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef))

    rep = docstring_rewriter.build_replacement_docstring(node, src, starts, 79)
    assert rep is None


def test_module_level_docstring() -> None:
    """Module level docstring should be properly wrapped."""
    long_text = ' '.join(['word'] * 40)  # ~200 chars
    src = dedent(
        f'''
        """{long_text}"""

        def f():
            return 0
        '''
    )

    tree = ast.parse(src)
    starts = docstring_rewriter.calc_line_starts(src)
    rep = docstring_rewriter.build_replacement_docstring(tree, src, starts, 79)

    assert rep == (
        1,
        206,
        '"""\nword word word word word word word word word word word word'
        ' word word word word\nword word word word word word word word word'
        ' word word word word word word word\nword word word word word word'
        ' word word\n"""',
    )


def test_wrap_docstring_numpy_parameters_and_examples() -> None:
    """Wrap only descriptions; keep signatures and examples intact."""
    doc = dedent(
        """
        Summary line outside sections that should be wrapped if very long. This sentence is intentionally made quite long to exceed the width.

        Parameters
        ----------
        arg1 : list[str] | None | int, default=3
            The first argument. There is something wrong with this thing and it needs a longer description that will wrap.

        Returns
        -------
        int
            The answer that is calculated by the function and the explanation for the return value is long enough to be wrapped.

        Examples
        --------
        >>> very_long_call_name(with_many, arguments, making, the_line, way, too, long)
        ```
        very very very very very very very very very very long code that should stay as is, period.
        ```
        """  # noqa: E501
    ).strip('\n')

    wrapped = format_docstring.docstring_rewriter.wrap_docstring(
        doc, line_length=79
    )

    temp: str = 'very very very very very very very very very very'

    assert (
        wrapped
        == f"""
Summary line outside sections that should be wrapped if very long. This
sentence is intentionally made quite long to exceed the width.

Parameters
----------
arg1 : list[str] | None | int, default=3
    The first argument. There is something wrong with this thing and it needs a
    longer description that will wrap.

Returns
-------
int
    The answer that is calculated by the function and the explanation for the
    return value is long enough to be wrapped.

Examples
--------
>>> very_long_call_name(with_many, arguments, making, the_line, way, too, long)
```
{temp} long code that should stay as is, period.
```
"""
    )


DATA_DIR: Path = Path(__file__).parent / 'test_data/end_to_end/numpy'


def _load_end_to_end_test_cases() -> list[tuple[str, str, str, int]]:
    """Load end-to-end test cases from test data files."""
    test_cases: list[tuple[str, str, str, int]] = []
    for filepath in DATA_DIR.glob('*.txt'):
        loaded: tuple[str, str, str, int] | None = _load_test_case(filepath)
        if loaded is not None:
            test_cases.append(loaded)

    return test_cases


def _load_test_case(filepath: Path) -> tuple[str, str, str, int] | None:
    """Load end-to-end test cases from test data files."""
    with filepath.open('r') as f:
        content: str = f.read()

        lines: list[str] = content.split('\n')
        line_length: int = int(lines[0].split(':')[1].strip())

        # Find all separators
        separators: list[int] = []
        for i, line in enumerate(lines):
            if line.strip() == '**********':
                separators.append(i)

        if len(separators) < 2:
            return None

        first_separator = separators[0]
        second_separator = separators[1]

        # Extract before content (between 1st and 2nd separators)
        before_lines = []
        for i in range(first_separator + 1, second_separator):
            if (
                lines[i].strip() or before_lines
            ):  # Include empty lines if we've started collecting
                before_lines.append(lines[i])

        # Remove trailing empty lines
        while before_lines and not before_lines[-1].strip():
            before_lines.pop()

        # Extract after content (after second separator)
        after_lines = []
        for i in range(second_separator + 1, len(lines)):
            if (
                lines[i].strip() or after_lines
            ):  # Include empty lines if we've started collecting
                after_lines.append(lines[i])

        # Remove trailing empty lines
        while after_lines and not after_lines[-1].strip():
            after_lines.pop()

        before_content: str = '\n'.join(before_lines)
        after_content: str = '\n'.join(after_lines)

        test_case_name: str = filepath.stem

    return test_case_name, before_content, after_content, line_length


@pytest.mark.parametrize(
    'test_name, input_src, expected_src, line_length',
    _load_end_to_end_test_cases(),
    ids=lambda case: case[0] if isinstance(case, tuple) else str(case),
)
def test_fix_src_end_to_end(
        test_name: str,
        input_src: str,
        expected_src: str,
        line_length: int,
) -> None:
    """Test end-to-end docstring rewriting with fix_src() function."""
    result = docstring_rewriter.fix_src(input_src, line_length=line_length)
    assert result == expected_src


def test_fix_src_single_case() -> None:
    """
    A placeholder test for easy debugging. You can replace the file name with
    the test case file that's producing errors.
    """
    test_case_name, before_src, after_src, line_length = _load_test_case(
        DATA_DIR / 'single_line_docstring.txt'
    )
    out: str = docstring_rewriter.fix_src(before_src, line_length=line_length)
    assert out == after_src
