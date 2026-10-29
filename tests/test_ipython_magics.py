from __future__ import annotations

import ast

import pytest

from format_docstring.ipython_magics import (
    mask_ipython_syntax,
    unmask_ipython_syntax,
)


def _masked_line_indices(source: str) -> list[int]:
    """Return the indices of the lines that ``mask_ipython_syntax`` masks."""
    masked = mask_ipython_syntax(source)
    assert masked is not None
    original_lines = source.split('\n')
    masked_lines = masked.source.split('\n')
    assert len(masked_lines) == len(original_lines)
    return [
        idx
        for idx, (before, after) in enumerate(
            zip(original_lines, masked_lines, strict=True)
        )
        if before != after
    ]


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('%pip install numpy\nimport os', [0]),
        ('%matplotlib inline', [0]),
        ('!pip install pandas', [0]),
        ('!!ls', [0]),
        ('files = !ls -la', [0]),
        ('result = %timeit -o f()', [0]),
        ('result =%timeit -o f()', [0]),
        ('foo?', [0]),
        ('foo.bar??', [0]),
        ('?foo', [0]),
        ('/print x', [0]),
        (',f a b', [0]),
        (';f a b', [0]),
        ('for i in range(3):\n    %time f(i)', [1]),
        # A trailing backslash continues the command, and the continuation
        # line is command text even when it looks like an open string
        ('%time f(\\\n  "it\'s")\nx = 1', [0, 1]),
        ("!echo it's here\nx = 1", [0]),
        # A help query on the last line of a bracketed logical line masks all
        # of its lines
        ('foo(a,\n    b)?\nx = 1', [0, 1]),
        # Python syntax that only looks like IPython
        ('x = a % b', []),
        ('x = (a\n     % b)', []),
        ('x = 1 \\\n    % 2', []),
        ('x = a != b', []),
        ('x = "what?"  # really?', []),
        ("print(f'{x!r}')", []),
        ('x %= 2', []),
        ('x = {"a": 1}', []),
        (
            'def f():\n    """\n    %notamagic\n    !notashell\n    """',
            [],
        ),
        ("s = '''\n%notamagic\n'''", []),
        ("s = 'a\\\n%notamagic'", []),
        # An unterminated single-quoted string ends at the end of its line
        ("s = 'a\n%magic", [1]),
        ('', []),
    ],
)
def test_mask_ipython_syntax_masked_lines(
        source: str,
        expected: list[int],
) -> None:
    """Mask exactly the lines that use IPython-only syntax."""
    assert _masked_line_indices(source) == expected


@pytest.mark.parametrize(
    'source',
    [
        '%%bash\necho hi',
        '%%html\n<b>hi</b>',
        '%%writefile foo.py\nx = 1',
        '\n%%bash\necho hi',
        '%%\nx = 1',
    ],
)
def test_mask_ipython_syntax_skips_non_python_cell_magics(
        source: str,
) -> None:
    """Return None for a cell whose cell magic body is not Python."""
    assert mask_ipython_syntax(source) is None


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('%%time\ndef f():\n    pass', [0]),
        ('%%timeit -n 10\nf()', [0]),
        ('%%capture out\n!ls\nf()', [0, 1]),
        ('\n%%time\nf()', [1]),
        # Not at the start of the cell: an ordinary line magic
        ('f()\n%%time', [1]),
    ],
)
def test_mask_ipython_syntax_python_cell_magics(
        source: str,
        expected: list[int],
) -> None:
    """Mask only the magic line of a cell magic whose body is Python."""
    assert _masked_line_indices(source) == expected


def test_mask_ipython_syntax_output_parses() -> None:
    """Placeholders keep the indentation that makes the source parse."""
    source = (
        '%%time\n'
        '%load_ext autoreload\n'
        'for i in range(3):\n'
        '    %time f(i)\n'
        '    files = !ls \\\n'
        '        -la\n'
        'if True:\n'
        '    foo?\n'
    )
    masked = mask_ipython_syntax(source)
    assert masked is not None
    ast.parse(masked.source)
    assert unmask_ipython_syntax(masked.source, masked) == source


def test_mask_ipython_syntax_placeholders_avoid_existing_names() -> None:
    """Placeholder names never collide with names already in the cell."""
    source = '__format_docstring_ipython_0 = 1\n%time f()'
    masked = mask_ipython_syntax(source)
    assert masked is not None
    assert masked.source.split('\n')[0] == '__format_docstring_ipython_0 = 1'
    assert masked.source.split('\n')[1] not in source
    assert unmask_ipython_syntax(masked.source, masked) == source


def test_unmask_ipython_syntax_after_docstring_grows() -> None:
    """Restore lines by placeholder, not by line number."""
    source = 'def f():\n    """Doc."""\n%time f()'
    masked = mask_ipython_syntax(source)
    assert masked is not None
    masked_lines = masked.source.split('\n')
    rewritten = '\n'.join([
        'def f():',
        '    """',
        '    Doc.',
        '    """',
        masked_lines[2],
    ])
    assert unmask_ipython_syntax(rewritten, masked) == (
        'def f():\n    """\n    Doc.\n    """\n%time f()'
    )


def test_mask_ipython_syntax_keeps_crlf_lines() -> None:
    """A masked line keeps its carriage return when it is restored."""
    source = '%time f()\r\nx = 1\r\n'
    masked = mask_ipython_syntax(source)
    assert masked is not None
    assert '%' not in masked.source
    assert unmask_ipython_syntax(masked.source, masked) == source
