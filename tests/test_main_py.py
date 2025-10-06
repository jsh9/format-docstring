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
    assert res.exit_code in (0, 1), res.output

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
    assert res.exit_code in (0, 1), res.output

    actual = work_file.read_text()
    expected = after.read_text()
    assert actual == expected
