from __future__ import annotations

import sys
from pathlib import Path

import click

import format_docstring.docstring_rewriter as rewriter
from format_docstring import __version__
from format_docstring.base_fixer import BaseFixer
from format_docstring.config import (
    ConfigFileCommand,
    validate_cli_include_options,
)


@click.command(cls=ConfigFileCommand)
@click.version_option(version=__version__)
@click.argument('paths', nargs=-1, type=click.Path())
@click.option(
    '--config',
    type=click.Path(exists=False, file_okay=True, dir_okay=False),
    default=None,
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
@click.option(
    '--fix-rst-backticks',
    type=bool,
    default=True,
    show_default=True,
    help='Fix single backticks to double backticks per rST syntax',
)
@click.option(
    '--include-arg-types',
    type=bool,
    default=True,
    show_default=True,
    help='Include argument type hints in parameter docstrings',
)
@click.option(
    '--include-arg-defaults',
    type=bool,
    default=True,
    show_default=True,
    help='Include argument defaults in parameter docstrings',
)
@click.option(
    '--include-return-and-yield-types',
    type=bool,
    default=True,
    show_default=True,
    help='Include return and yield type hints in docstrings',
)
@click.option(
    '--verbose',
    type=click.Choice(['default', 'diff'], case_sensitive=False),
    default='default',
    show_default=True,
    help='Increase logging detail; "diff" prints unified diffs for rewrites',
)
def main(
        paths: tuple[str, ...],
        config: str | None,  # noqa: ARG001 (exposed for Click)
        *,
        exclude: str,
        line_length: int,
        docstring_style: str,
        fix_rst_backticks: bool,
        include_arg_types: bool,
        include_arg_defaults: bool,
        include_return_and_yield_types: bool,
        verbose: str,
) -> None:
    """Format .py files."""
    ret = 0

    # Reject incompatible include flags before the loop so one invalid
    # invocation cannot partially rewrite earlier paths before failing.
    validate_cli_include_options(
        docstring_style,
        include_arg_types=include_arg_types,
        include_arg_defaults=include_arg_defaults,
        include_return_and_yield_types=include_return_and_yield_types,
    )

    for path in paths:
        fixer = PythonFileFixer(
            path=path,
            exclude_pattern=exclude,
            line_length=line_length,
            fix_rst_backticks=fix_rst_backticks,
            include_arg_types=include_arg_types,
            include_arg_defaults=include_arg_defaults,
            include_return_and_yield_types=include_return_and_yield_types,
            verbose=verbose.lower(),
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
            *,
            fix_rst_backticks: bool = True,
            include_arg_types: bool = True,
            include_arg_defaults: bool = True,
            include_return_and_yield_types: bool = True,
            verbose: str = 'default',
    ) -> None:
        super().__init__(
            path=path,
            exclude_pattern=exclude_pattern,
            verbose=verbose.lower(),
        )
        self.line_length = line_length
        self.fix_rst_backticks = fix_rst_backticks
        self.include_arg_types = include_arg_types
        self.include_arg_defaults = include_arg_defaults
        self.include_return_and_yield_types = include_return_and_yield_types
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

            source_bytes = Path(filename).read_bytes()

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
            fix_rst_backticks=self.fix_rst_backticks,
            include_arg_types=self.include_arg_types,
            include_arg_defaults=self.include_arg_defaults,
            include_return_and_yield_types=(
                self.include_return_and_yield_types
            ),
        )

        if filename == '-':
            print(source_text, end='')
        elif source_text != source_text_orig:
            print(f'Rewriting {filename}', file=sys.stderr)
            self.print_diff(filename, source_text_orig, source_text)
            Path(filename).write_bytes(source_text.encode())

        return int(source_text != source_text_orig)


if __name__ == '__main__':
    raise SystemExit(main())
