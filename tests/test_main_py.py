from pathlib import Path
from shutil import copy2

from click.testing import CliRunner

from format_docstring.main_py import main as cli_main_py


def test_integration_cli_py(tmp_path: Path) -> None:
    """Run CLI on a copied file and compare to expected output."""
    data_dir = Path(__file__).parent / 'test_data/integration_test/numpy'
    before = data_dir / 'before.py'
    after = data_dir / 'after.py'

    work_file = tmp_path / 'work.py'
    copy2(before, work_file)

    runner = CliRunner()
    res = runner.invoke(cli_main_py, [str(work_file)])
    assert res.exit_code in {0, 1}, res.output

    actual = work_file.read_text()
    expected = after.read_text()
    assert actual == expected


def test_integration_cli_py_len50(tmp_path: Path) -> None:
    """Run CLI with --line-length 50 and compare to expected output."""
    data_dir = Path(__file__).parent / 'test_data/integration_test/numpy'
    before = data_dir / 'before.py'
    after = data_dir / 'after_50.py'

    work_file = tmp_path / 'work.py'
    copy2(before, work_file)

    runner = CliRunner()
    res = runner.invoke(cli_main_py, ['--line-length', '50', str(work_file)])
    assert res.exit_code in {0, 1}, res.output

    actual = work_file.read_text()
    expected = after.read_text()
    assert actual == expected


def test_cli_verbose_diff_outputs_diff(tmp_path: Path) -> None:
    """Ensure that ``--verbose diff`` prints a unified diff when rewriting."""
    data_dir = Path(__file__).parent / 'test_data/integration_test/numpy'
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
