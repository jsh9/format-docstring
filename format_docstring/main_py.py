from __future__ import annotations

import sys
from pathlib import Path

import click

import format_docstring.docstring_rewriter as rewriter
from format_docstring import __version__
from format_docstring.base_fixer import BaseFixer
from format_docstring.config import inject_config_from_file


@click.command()
@click.version_option(version=__version__)
@click.argument('paths', nargs=-1, type=click.Path())
@click.option(
    '--config',
    type=click.Path(exists=False, file_okay=True, dir_okay=False),
    is_eager=True,
    callback=inject_config_from_file,
    default='pyproject.toml',
    help=(
        'Path to a pyproject.toml config file. '
        'If not specified, searches for pyproject.toml in parent directories. '
        'Command-line options take precedence over config file settings.'
    ),
)
@click.option(
    '--exclude',
    type=str,
    default=r'\.git|\.tox|\.pytest_cache',
    help='Regex pattern to exclude files/directories',
)
@click.option(
    '--line-length',
    type=int,
    default=79,
    show_default=True,
    help='Maximum line length for wrapping docstrings',
)
@click.option(
    '--docstring-style',
    type=click.Choice(['numpy', 'google'], case_sensitive=False),
    default='numpy',
    show_default=True,
    help='Docstring style to target',
)
def main(
        paths: tuple[str, ...],
        config: str | None,  # noqa: ARG001 (used by Click callback)
        exclude: str,
        line_length: int,
        docstring_style: str,
) -> None:
    """Format .py files."""
    ret = 0

    if docstring_style.lower() != 'numpy':
        raise ValueError('Only "numpy" style is supported for now.')

    for path in paths:
        fixer = PythonFileFixer(
            path=path, exclude_pattern=exclude, line_length=line_length
        )
        fixer.docstring_style = docstring_style
        ret |= fixer.fix_one_directory_or_one_file()

    if ret != 0:
        raise SystemExit(ret)


class PythonFileFixer(BaseFixer):
    """Fixer for Python source files."""

    def __init__(
            self,
            path: str,
            exclude_pattern: str = r'\.git|\.tox|\.pytest_cache',
            line_length: int = 79,
    ) -> None:
        super().__init__(path=path, exclude_pattern=exclude_pattern)
        self.line_length = line_length
        self.docstring_style: str = 'numpy'

    def fix_one_file(self, filename: str) -> int:
        """Fix formatting in a single Python file."""
        if filename == '-':
            source_bytes: bytes = sys.stdin.buffer.read()
        else:
            file_path: Path = Path(filename)
            if not file_path.is_file():
                msg: str = f'{filename} is not a file (skipping)'
                print(msg, file=sys.stderr)
                return 0

            with open(filename, 'rb') as fb:
                source_bytes = fb.read()

        try:
            source_text: str = source_bytes.decode()
            source_text_orig: str = source_text
        except UnicodeDecodeError:
            error_msg: str = f'{filename} is non-utf-8 (not supported)'
            print(error_msg, file=sys.stderr)
            return 1

        source_text = rewriter.fix_src(
            source_text,
            line_length=self.line_length,
            docstring_style=self.docstring_style,
        )

        if filename == '-':
            print(source_text, end='')
        elif source_text != source_text_orig:
            print(f'Rewriting {filename}', file=sys.stderr)
            with open(filename, 'wb') as f:
                f.write(source_text.encode())

        return int(source_text != source_text_orig)


if __name__ == '__main__':
    raise SystemExit(main())
