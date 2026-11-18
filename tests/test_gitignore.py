# Pytest supplies booleans; discovery tests access the shared helper directly.
# ruff: noqa: SLF001, FBT001

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from format_docstring.gitignore import GitIgnoreMatcher
from format_docstring.main_jupyter import JupyterNotebookFixer
from format_docstring.main_jupyter import main as notebook_main
from format_docstring.main_py import PythonFileFixer
from format_docstring.main_py import main as python_main


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Bound tests independently of the host's ancestor ignore files."""
    (tmp_path / '.git').mkdir()
    return tmp_path


@pytest.mark.parametrize(
    ('rules', 'filename', 'ignored'),
    [
        ('*.py\n', 'sub/code.py', True),
        ('/code.py\n', 'sub/code.py', False),
        ('/code.py\n', 'code.py', True),
        ('sub/*.py\n', 'sub/code.py', True),
        ('**/generated/*.py\n', 'sub/generated/code.py', True),
        ('cache/\n', 'cache/code.py', True),
        ('cache/\n', 'cache', False),
        ('# code.py\n\n', 'code.py', False),
        ('\\#code.py\n', '#code.py', True),
        ('\\!code.py\n', '!code.py', True),
        ('*.py\n!code.py\n', 'code.py', False),
        ('!code.py\n*.py\n', 'code.py', True),
        ('sub/\n!sub/code.py\n', 'sub/code.py', True),
        ('sub/\n!sub/\nsub/*\n!sub/code.py\n', 'sub/code.py', False),
    ],
)
def test_patterns(
        project: Path, rules: str, filename: str, ignored: bool
) -> None:
    (project / '.gitignore').write_text(rules)
    target = project / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    assert GitIgnoreMatcher().is_ignored(target) is ignored


def test_nested_overrides_and_ancestor_rules(project: Path) -> None:
    (project / '.gitignore').write_text('*.py\n')
    child = project / 'src'
    child.mkdir()
    (child / '.gitignore').write_text('!keep.py\n')
    for name in ['keep.py', 'skip.py']:
        (child / name).touch()

    matcher = GitIgnoreMatcher()
    assert not matcher.is_ignored(child / 'keep.py')
    assert matcher.is_ignored(child / 'skip.py')
    fixer = PythonFileFixer(str(child))
    assert fixer._get_files_to_process(child, '*.py') == [child / 'keep.py']


def test_repository_boundary(project: Path) -> None:
    (project / '.gitignore').write_text('*.py\n')
    nested = project / 'nested'
    nested.mkdir()
    (nested / '.git').mkdir()

    target = nested / 'code.py'
    target.touch()
    assert not GitIgnoreMatcher().is_ignored(target)


def test_worktree_boundary(project: Path) -> None:
    (project / '.gitignore').write_text('*.py\n')
    nested = project / 'nested'
    nested.mkdir()
    (nested / '.git').write_text('gitdir: /unused/worktree\n')

    target = nested / 'code.py'
    target.touch()
    assert not GitIgnoreMatcher().is_ignored(target)


def test_outside_repository_and_relative_paths(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / '.gitignore').write_text('/code.py\n')
    target = tmp_path / 'code.py'
    target.touch()
    monkeypatch.chdir(tmp_path)
    matcher = GitIgnoreMatcher()
    assert matcher.is_ignored(target)
    assert matcher.is_ignored(Path('code.py'))


def test_prunes_ignored_directories_and_sorts(project: Path) -> None:
    (project / '.gitignore').write_text('ignored/\n')
    ignored = project / 'ignored'
    ignored.mkdir()
    (ignored / 'code.py').touch()
    for name in ['z.py', 'a.py']:
        (project / name).touch()

    fixer = PythonFileFixer(str(project))
    assert fixer._get_files_to_process(project, '*.py') == [
        project / 'a.py',
        project / 'z.py',
    ]


def test_symlink_directory_not_followed(project: Path) -> None:
    source = project / 'source'
    source.mkdir()
    (source / 'code.py').touch()
    (project / 'alias').symlink_to(source, target_is_directory=True)
    fixer = PythonFileFixer(str(project))
    assert fixer._get_files_to_process(project, '*.py') == [source / 'code.py']


@pytest.mark.parametrize('notebook', [False, True])
@pytest.mark.parametrize('explicit', ['file', 'directory', 'discovery'])
def test_cli_skips_ignored_targets(
        project: Path, notebook: bool, explicit: str
) -> None:
    command = notebook_main if notebook else python_main
    suffix = '.ipynb' if notebook else '.py'
    (project / '.gitignore').write_text('ignored/\n')
    directory = project / 'ignored'
    directory.mkdir()
    target = directory / f'code{suffix}'
    # Invalid content verifies ignored files are never even parsed.
    original = b'not valid Python or JSON\xff'
    target.write_bytes(original)
    argument = {'file': target, 'directory': directory, 'discovery': project}[
        explicit
    ]
    result = CliRunner().invoke(command, [str(argument)])
    assert result.exit_code == 0, result.output
    assert result.output == ''
    assert target.read_bytes() == original


@pytest.mark.parametrize('notebook', [False, True])
@pytest.mark.parametrize('key', ['respect_gitignore', 'respect-gitignore'])
@pytest.mark.parametrize('cli_value', [None, 'True', 'False'])
@pytest.mark.parametrize('config_value', ['true', 'false'])
def test_config_and_cli_precedence(
        project: Path,
        notebook: bool,
        key: str,
        cli_value: str | None,
        config_value: str,
) -> None:
    command = notebook_main if notebook else python_main
    extension = 'ipynb' if notebook else 'py'
    fixture = (
        Path(__file__).parent
        / 'test_data/integration_test/numpy'
        / f'before.{extension}'
    )
    (project / 'pyproject.toml').write_text(
        f'[tool.format_docstring]\n{key} = {config_value}\n'
    )
    (project / '.gitignore').write_text(f'*.{extension}\n')
    target = project / f'code.{extension}'
    original = fixture.read_bytes()
    target.write_bytes(original)
    args = [str(target)]
    if cli_value is not None:
        args = ['--respect-gitignore', cli_value, *args]

    result = CliRunner().invoke(command, args)
    respects = (cli_value or config_value).lower() == 'true'
    assert result.exit_code == (0 if respects else 1), result.output
    assert (target.read_bytes() == original) is respects


@pytest.mark.parametrize('notebook', [False, True])
def test_default_discovery_and_cli_equals(
        project: Path, notebook: bool
) -> None:
    command = notebook_main if notebook else python_main
    extension = 'ipynb' if notebook else 'py'
    fixture = (
        Path(__file__).parent
        / 'test_data/integration_test/numpy'
        / f'before.{extension}'
    )
    original = fixture.read_bytes()
    (project / '.gitignore').write_text(f'skip.{extension}\n')
    skip = project / f'skip.{extension}'
    keep = project / f'keep.{extension}'
    skip.write_bytes(original)
    keep.write_bytes(original)
    result = CliRunner().invoke(command, [str(project)])
    assert result.exit_code == 1, result.output
    assert skip.read_bytes() == original
    assert keep.read_bytes() != original
    result = CliRunner().invoke(
        command, ['--respect-gitignore=False', str(skip)]
    )
    assert result.exit_code == 1, result.output
    assert skip.read_bytes() != original


@pytest.mark.parametrize(
    'fixer_class', [PythonFileFixer, JupyterNotebookFixer]
)
@pytest.mark.parametrize('respect', [False, True])
def test_regex_still_excludes(
        project: Path,
        fixer_class: type[PythonFileFixer] | type[JupyterNotebookFixer],
        respect: bool,
) -> None:
    (project / '.gitignore').write_text('!code.*\n')
    target = project / 'code.py'
    target.write_bytes(b'invalid\xff')
    fixer = fixer_class(
        str(target), exclude_pattern=r'code\.', respect_gitignore=respect
    )
    assert fixer.fix_one_directory_or_one_file() == 0
