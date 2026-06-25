from pathlib import Path
from shutil import copy2
from textwrap import dedent

import pytest
from click.testing import CliRunner

from format_docstring.main_py import main as cli_main_py

DATA_DIR = Path(__file__).parent / 'test_data/integration_test'


@pytest.mark.parametrize(
    ('style', 'style_args'),
    [
        ('numpy', ['--docstring-style', 'numpy']),
        ('google', ['--docstring-style', 'google']),
    ],
)
def test_integration_cli_py(
        tmp_path: Path, style: str, style_args: list[str]
) -> None:
    """Run CLI on a copied file and compare to expected output."""
    data_dir = DATA_DIR / style
    before = data_dir / 'before.py'
    after = data_dir / 'after.py'

    work_file = tmp_path / 'work.py'
    copy2(before, work_file)

    runner = CliRunner()
    res = runner.invoke(cli_main_py, [*style_args, str(work_file)])
    assert res.exit_code in {0, 1}, res.output

    actual = work_file.read_text()
    expected = after.read_text()
    assert actual == expected


@pytest.mark.parametrize(
    ('style', 'style_args'),
    [
        ('numpy', ['--docstring-style', 'numpy']),
        ('google', ['--docstring-style', 'google']),
    ],
)
def test_integration_cli_py_len50(
        tmp_path: Path, style: str, style_args: list[str]
) -> None:
    """Run CLI with --line-length 50 and compare to expected output."""
    data_dir = DATA_DIR / style
    before = data_dir / 'before.py'
    after = data_dir / 'after_50.py'

    work_file = tmp_path / 'work.py'
    copy2(before, work_file)

    runner = CliRunner()
    res = runner.invoke(
        cli_main_py, [*style_args, '--line-length', '50', str(work_file)]
    )
    assert res.exit_code in {0, 1}, res.output

    actual = work_file.read_text()
    expected = after.read_text()
    assert actual == expected


def test_cli_verbose_diff_outputs_diff(tmp_path: Path) -> None:
    """Ensure that ``--verbose diff`` prints a unified diff when rewriting."""
    data_dir = DATA_DIR / 'numpy'
    before = data_dir / 'before.py'
    after = data_dir / 'after.py'

    work_file = tmp_path / 'work.py'
    copy2(before, work_file)

    runner = CliRunner()
    result = runner.invoke(cli_main_py, ['--verbose', 'diff', str(work_file)])
    assert result.exit_code in {0, 1}, result.output
    assert '(before)' in result.output
    assert '(after)' in result.output
    assert '@@' in result.output
    assert 'Class Alpha performs an operation with a very' in result.output

    assert work_file.read_text() == after.read_text()


def test_cli_config_verbose_diff(tmp_path: Path) -> None:
    """Verify that pyproject.toml can enable verbose diff output."""
    config_file = tmp_path / 'pyproject.toml'
    config_file.write_text('[tool.format_docstring]\nverbose = "diff"\n')

    test_file = tmp_path / 'doc.py'
    test_file.write_text('''def foo():
    """A docstring that should be rewritten because it is way too long and stays on a single line without wrapping which we expect to change once formatting runs."""
    pass
''')  # noqa: E501

    runner = CliRunner()
    result = runner.invoke(
        cli_main_py, ['--config', str(config_file), str(test_file)]
    )
    assert result.exit_code in {0, 1}, result.output
    assert '(before)' in result.output
    assert '(after)' in result.output
    assert '@@' in result.output
    assert 'should be rewritten because it is way too long' in result.output

    # Ensure the file was rewritten
    output = test_file.read_text()
    assert output.count('"""') == 2


def test_cli_include_arg_options_strip_google_signature(
        tmp_path: Path,
) -> None:
    """
    Verify CLI include options strip Google arg metadata when disabled.

    This guards the Click plumbing so boolean command-line values reach the
    rewriter instead of only working through direct ``fix_src`` calls.
    """
    test_file = tmp_path / 'doc.py'
    test_file.write_text(
        dedent(
            '''
            def foo(x: int = 3):
                """Do it.

                Args:
                    x (float, default=9): Value. The default is automatic.
                """
                return x
            '''
        ).lstrip()
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_main_py,
        [
            '--docstring-style',
            'google',
            '--include-arg-types=False',
            '--include-arg-defaults=False',
            str(test_file),
        ],
    )
    assert result.exit_code in {0, 1}, result.output

    output = test_file.read_text()
    assert 'x: Value. The default is automatic.' in output
    assert 'x (float' not in output
    assert 'default=9' not in output


def test_cli_include_return_and_yield_types_strip_google_output_types(
        tmp_path: Path,
) -> None:
    """
    Verify CLI strips Google return/yield types when disabled.

    This protects the Click-to-fixer plumbing for both ``Returns`` and
    ``Yields`` rows, which share the same option and wrapper path.
    """
    test_file = tmp_path / 'doc.py'
    test_file.write_text(
        dedent(
            '''
            def foo() -> dict[str, str]:
                """Do it.

                Returns:
                    dict[str, str]: Mapping result.
                """
                return {}

            def bar() -> Iterator[int]:
                """Yield it.

                Yields:
                    int: Next value.
                """
                yield 1
            '''
        ).lstrip()
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_main_py,
        [
            '--docstring-style',
            'google',
            '--include-return-and-yield-types=False',
            str(test_file),
        ],
    )
    assert result.exit_code in {0, 1}, result.output

    output = test_file.read_text()
    assert 'Mapping result.' in output
    assert 'Next value.' in output
    assert 'dict[str, str]: Mapping result.' not in output
    assert 'int: Next value.' not in output


def test_cli_numpy_include_return_and_yield_types_false_errors(
        tmp_path: Path,
) -> None:
    """
    Verify NumPy rejects disabled return/yield type lines before rewriting.

    The CLI must fail before constructing fixers so strict numpydoc behavior
    cannot partially rewrite files and then report an option error.
    """
    test_file = tmp_path / 'doc.py'
    original = dedent(
        '''
        def foo() -> int:
            """Do it.

            Returns
            -------
            int
                Value.
            """
            return 1
        '''
    ).lstrip()
    test_file.write_text(original)

    runner = CliRunner()
    result = runner.invoke(
        cli_main_py,
        [
            '--docstring-style',
            'numpy',
            '--include-return-and-yield-types=False',
            str(test_file),
        ],
    )

    assert result.exit_code != 0
    assert 'NumPy/numpydoc requires' in result.output
    assert test_file.read_text() == original
