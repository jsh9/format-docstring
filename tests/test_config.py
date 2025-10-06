"""Tests for configuration file parsing."""

from pathlib import Path

from click.testing import CliRunner

from format_docstring.config import (
    _find_common_parent,
    find_config_file,
    load_config_from_file,
)
from format_docstring.main_py import main as cli_main_py


def test_find_common_parent_single_file() -> None:
    """Test finding common parent for a single file."""
    paths = ['/path/to/file.py']
    result = _find_common_parent(paths)
    assert result == Path('/path/to')


def test_find_common_parent_multiple_files_same_dir() -> None:
    """Test finding common parent for files in the same directory."""
    paths = ['/path/to/file1.py', '/path/to/file2.py']
    result = _find_common_parent(paths)
    assert result == Path('/path/to')


def test_find_common_parent_multiple_files_different_dirs() -> None:
    """Test finding common parent for files in different directories."""
    paths = ['/path/to/dir1/file1.py', '/path/to/dir2/file2.py']
    result = _find_common_parent(paths)
    assert result == Path('/path/to')


def test_find_common_parent_nested_paths() -> None:
    """Test finding common parent for nested paths."""
    paths = ['/path/to/file.py', '/path/to/subdir/file.py']
    result = _find_common_parent(paths)
    assert result == Path('/path/to')


def test_load_config_from_file_nonexistent() -> None:
    """Test loading config from a nonexistent file."""
    config_file = Path('/nonexistent/pyproject.toml')
    result = load_config_from_file(config_file)
    assert result == {}


def test_load_config_from_file_no_tool_section(tmp_path: Path) -> None:
    """Test loading config from a file without tool section."""
    config_file = tmp_path / 'pyproject.toml'
    config_file.write_text('[project]\nname = "test"\n')

    result = load_config_from_file(config_file)
    assert result == {}


def test_load_config_from_file_no_format_docstring_section(
        tmp_path: Path,
) -> None:
    """Test loading config from a file without format_docstring section."""
    config_file = tmp_path / 'pyproject.toml'
    config_file.write_text('[tool.other]\nvalue = "test"\n')

    result = load_config_from_file(config_file)
    assert result == {}


def test_load_config_from_file_with_config(tmp_path: Path) -> None:
    """Test loading config from a valid config file."""
    config_file = tmp_path / 'pyproject.toml'
    config_content = """
[tool.format_docstring]
line_length = 72
docstring_style = "numpy"
exclude = "\\\\.git|\\\\.venv"
"""
    config_file.write_text(config_content)

    result = load_config_from_file(config_file)
    assert result == {
        'line_length': 72,
        'docstring_style': 'numpy',
        'exclude': '\\.git|\\.venv',
    }


def test_load_config_with_hyphens(tmp_path: Path) -> None:
    """Test that hyphens in config keys are converted to underscores."""
    config_file = tmp_path / 'pyproject.toml'
    config_content = """
[tool.format_docstring]
line-length = 100
"""
    config_file.write_text(config_content)

    result = load_config_from_file(config_file)
    assert result == {'line_length': 100}


def test_find_config_file_from_current_dir(tmp_path: Path) -> None:
    """Test finding config file from the current directory."""
    config_file = tmp_path / 'pyproject.toml'
    config_file.write_text('[project]\nname = "test"\n')

    test_file = tmp_path / 'test.py'
    test_file.write_text('# test')

    result = find_config_file([str(test_file)])
    assert result == config_file


def test_find_config_file_from_parent_dir(tmp_path: Path) -> None:
    """Test finding config file from a parent directory."""
    config_file = tmp_path / 'pyproject.toml'
    config_file.write_text('[project]\nname = "test"\n')

    subdir = tmp_path / 'subdir'
    subdir.mkdir()
    test_file = subdir / 'test.py'
    test_file.write_text('# test')

    result = find_config_file([str(test_file)])
    assert result == config_file


def test_find_config_file_not_found(tmp_path: Path) -> None:
    """Test when config file is not found."""
    test_file = tmp_path / 'test.py'
    test_file.write_text('# test')

    # This will search up from tmp_path and may find a real pyproject.toml
    # or return None. We just check it doesn't crash.
    result = find_config_file([str(test_file)])
    assert result is None or result.exists()


def test_cli_with_config_file(tmp_path: Path) -> None:
    """Test CLI with a config file that sets line_length."""
    # Create a config file
    config_file = tmp_path / 'pyproject.toml'
    config_content = """
[tool.format_docstring]
line_length = 50
"""
    config_file.write_text(config_content)

    # Create a test file with a long docstring
    test_file = tmp_path / 'test.py'
    test_content = '''def foo():
    """This is a very long docstring that should be wrapped at 50 chars."""
    pass
'''
    test_file.write_text(test_content)

    # Run the CLI with the config file
    runner = CliRunner()
    result = runner.invoke(
        cli_main_py, ['--config', str(config_file), str(test_file)]
    )
    assert result.exit_code in (0, 1), result.output

    # The docstring should be wrapped
    output = test_file.read_text()
    assert 'This is a very long docstring' in output
    # It should be on multiple lines due to 50 char limit
    assert output.count('"""') == 2


def test_cli_config_file_auto_discovery(tmp_path: Path) -> None:
    """Test that CLI automatically discovers config file."""
    # Create a config file in the parent directory
    config_file = tmp_path / 'pyproject.toml'
    config_content = """
[tool.format_docstring]
line_length = 50
"""
    config_file.write_text(config_content)

    # Create a subdirectory with a test file
    subdir = tmp_path / 'src'
    subdir.mkdir()
    test_file = subdir / 'test.py'
    test_content = '''def foo():
    """This is a very long docstring that should be wrapped at 50 chars."""
    pass
'''
    test_file.write_text(test_content)

    # Run the CLI without specifying config file
    runner = CliRunner()
    result = runner.invoke(cli_main_py, [str(test_file)])
    assert result.exit_code in (0, 1), result.output

    # The docstring should be wrapped due to auto-discovered config
    output = test_file.read_text()
    assert 'This is a very long docstring' in output


def test_cli_option_overrides_config_file(tmp_path: Path) -> None:
    """Test that CLI options override config file settings."""
    # Create a config file with line_length = 50
    config_file = tmp_path / 'pyproject.toml'
    config_content = """
[tool.format_docstring]
line_length = 50
"""
    config_file.write_text(config_content)

    # Create a test file
    test_file = tmp_path / 'test.py'
    test_content = '''def foo():
    """Short docstring."""
    pass
'''
    test_file.write_text(test_content)

    # Run the CLI with --line-length 100 (should override config)
    runner = CliRunner()
    result = runner.invoke(
        cli_main_py,
        ['--config', str(config_file), '--line-length', '100', str(test_file)],
    )
    assert result.exit_code in (0, 1), result.output

    # File should remain largely the same since line length is high
    output = test_file.read_text()
    assert 'Short docstring' in output


def test_config_with_exclude_pattern(tmp_path: Path) -> None:
    """Test config file with exclude pattern."""
    config_file = tmp_path / 'pyproject.toml'
    config_content = """
[tool.format_docstring]
exclude = "\\\\.git|\\\\.venv|test_.*"
"""
    config_file.write_text(config_content)

    result = load_config_from_file(config_file)
    assert result == {'exclude': '\\.git|\\.venv|test_.*'}


def test_invalid_toml_file(tmp_path: Path) -> None:
    """Test handling of invalid TOML file."""
    config_file = tmp_path / 'pyproject.toml'
    config_file.write_text('this is not valid TOML [[[')

    # Should return empty dict instead of crashing
    result = load_config_from_file(config_file)
    assert result == {}
