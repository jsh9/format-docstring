import json
from pathlib import Path
from shutil import copy2
from textwrap import dedent

import pytest
from click.testing import CliRunner

from format_docstring.main_jupyter import main as cli_main_ipynb

DATA_DIR = Path(__file__).parent / 'test_data/integration_test'


@pytest.mark.parametrize(
    ('style', 'style_args'),
    [
        ('numpy', ['--docstring-style', 'numpy']),
        ('google', ['--docstring-style', 'google']),
    ],
)
def test_integration_cli_ipynb(
        tmp_path: Path, style: str, style_args: list[str]
) -> None:
    """Run CLI on a copied .ipynb file and compare to expected output."""
    data_dir = DATA_DIR / style
    before = data_dir / 'before.ipynb'
    after = data_dir / 'after.ipynb'

    work_file = tmp_path / 'work.ipynb'
    copy2(before, work_file)

    runner = CliRunner()
    res = runner.invoke(cli_main_ipynb, [*style_args, str(work_file)])
    assert res.exit_code in {0, 1}, res.output

    actual = json.loads(work_file.read_text())
    expected = json.loads(after.read_text())
    assert actual == expected


@pytest.mark.parametrize(
    ('style', 'style_args'),
    [
        ('numpy', ['--docstring-style', 'numpy']),
        ('google', ['--docstring-style', 'google']),
    ],
)
def test_integration_cli_ipynb_len50(
        tmp_path: Path, style: str, style_args: list[str]
) -> None:
    """Run CLI with --line-length 50 on .ipynb and compare to expected."""
    data_dir = DATA_DIR / style
    before = data_dir / 'before.ipynb'
    after = data_dir / 'after_50.ipynb'

    work_file = tmp_path / 'work.ipynb'
    copy2(before, work_file)

    runner = CliRunner()
    res = runner.invoke(
        cli_main_ipynb, [*style_args, '--line-length', '50', str(work_file)]
    )
    assert res.exit_code in {0, 1}, res.output

    actual = json.loads(work_file.read_text())
    expected = json.loads(after.read_text())
    assert actual == expected


def test_cli_ipynb_verbose_diff(tmp_path: Path) -> None:
    """Ensure ``--verbose diff`` prints a diff for notebook rewrites."""
    fixture = Path(__file__).parent / 'test_data/jupyter/verbose_before.ipynb'
    work_file = tmp_path / 'work.ipynb'
    copy2(fixture, work_file)

    runner = CliRunner()
    result = runner.invoke(
        cli_main_ipynb, ['--verbose', 'diff', str(work_file)]
    )
    assert result.exit_code in {0, 1}, result.output
    assert '(before)' in result.output
    assert '(after)' in result.output
    assert '@@' in result.output
    assert 'docstring should be rewritten because it is very' in result.output

    # Ensure contents changed.
    original = json.loads(fixture.read_text())
    updated = json.loads(work_file.read_text())
    assert original != updated


def test_cli_ipynb_config_verbose_diff(tmp_path: Path) -> None:
    """Config file enables verbose diff for notebook rewrites."""
    config_file = tmp_path / 'pyproject.toml'
    config_file.write_text('[tool.format_docstring]\nverbose = "diff"\n')

    fixture = Path(__file__).parent / 'test_data/jupyter/verbose_before.ipynb'
    work_file = tmp_path / 'work.ipynb'
    copy2(fixture, work_file)

    runner = CliRunner()
    result = runner.invoke(
        cli_main_ipynb, ['--config', str(config_file), str(work_file)]
    )
    assert result.exit_code in {0, 1}, result.output
    assert '(before)' in result.output
    assert '(after)' in result.output
    assert '@@' in result.output
    assert 'docstring should be rewritten because it is very' in result.output

    # Ensure contents changed after formatting.
    assert json.loads(work_file.read_text()) != json.loads(fixture.read_text())


def test_cli_ipynb_include_arg_options_strip_google_signature(
        tmp_path: Path,
) -> None:
    """
    Verify notebook CLI include options strip Google arg metadata.

    Notebook cells take a separate fixer path with magic reconstruction, so
    this proves the new flags are passed through that path too.
    """
    source = dedent(
        '''
        def foo(x: int = 3):
            """Do it.

            Args:
                x (float, default=9): Value. The default is automatic.
            """
            return x
        '''
    ).lstrip()
    notebook = {
        'cells': [
            {
                'cell_type': 'code',
                'execution_count': None,
                'metadata': {},
                'outputs': [],
                'source': source.splitlines(keepends=True),
            }
        ],
        'metadata': {},
        'nbformat': 4,
        'nbformat_minor': 5,
    }
    work_file = tmp_path / 'work.ipynb'
    work_file.write_text(json.dumps(notebook), encoding='utf-8')

    runner = CliRunner()
    result = runner.invoke(
        cli_main_ipynb,
        [
            '--docstring-style',
            'google',
            '--include-arg-types=False',
            '--include-arg-defaults=False',
            str(work_file),
        ],
    )
    assert result.exit_code in {0, 1}, result.output

    updated = json.loads(work_file.read_text())
    updated_source = ''.join(updated['cells'][0]['source'])
    assert 'x: Value. The default is automatic.' in updated_source
    assert 'x (float' not in updated_source
    assert 'default=9' not in updated_source


def test_cli_ipynb_include_return_and_yield_types_strip_google_types(
        tmp_path: Path,
) -> None:
    """
    Verify notebook CLI strips Google return/yield types when disabled.

    Notebook formatting reconstructs cell source after magic handling, so this
    proves the option survives that separate fixer path.
    """
    source = dedent(
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
    notebook = {
        'cells': [
            {
                'cell_type': 'code',
                'execution_count': None,
                'metadata': {},
                'outputs': [],
                'source': source.splitlines(keepends=True),
            }
        ],
        'metadata': {},
        'nbformat': 4,
        'nbformat_minor': 5,
    }
    work_file = tmp_path / 'work.ipynb'
    work_file.write_text(json.dumps(notebook), encoding='utf-8')

    runner = CliRunner()
    result = runner.invoke(
        cli_main_ipynb,
        [
            '--docstring-style',
            'google',
            '--include-return-and-yield-types=False',
            str(work_file),
        ],
    )
    assert result.exit_code in {0, 1}, result.output

    updated = json.loads(work_file.read_text())
    updated_source = ''.join(updated['cells'][0]['source'])
    assert 'Mapping result.' in updated_source
    assert 'Next value.' in updated_source
    assert 'dict[str, str]: Mapping result.' not in updated_source
    assert 'int: Next value.' not in updated_source


def test_cli_ipynb_numpy_include_return_and_yield_types_false_errors(
        tmp_path: Path,
) -> None:
    """
    Verify notebook CLI rejects disabled return/yield type lines for NumPy.

    The failure should happen before JSON rewriting so invalid NumPy config
    does not alter notebook formatting or metadata.
    """
    source = dedent(
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
    notebook = {
        'cells': [
            {
                'cell_type': 'code',
                'execution_count': None,
                'metadata': {},
                'outputs': [],
                'source': source.splitlines(keepends=True),
            }
        ],
        'metadata': {},
        'nbformat': 4,
        'nbformat_minor': 5,
    }
    work_file = tmp_path / 'work.ipynb'
    original_text = json.dumps(notebook)
    work_file.write_text(original_text, encoding='utf-8')

    runner = CliRunner()
    result = runner.invoke(
        cli_main_ipynb,
        [
            '--docstring-style',
            'numpy',
            '--include-return-and-yield-types=False',
            str(work_file),
        ],
    )

    assert result.exit_code != 0
    assert 'NumPy/numpydoc requires' in result.output
    assert work_file.read_text() == original_text
