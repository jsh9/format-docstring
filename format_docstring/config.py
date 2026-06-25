"""Configuration file parsing for format-docstring."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


_VALUE_OPTIONS = frozenset({
    '--config',
    '--docstring-style',
    '--exclude',
    '--fix-rst-backticks',
    '--include-arg-defaults',
    '--include-arg-types',
    '--include-return-and-yield-types',
    '--line-length',
    '--verbose',
})


class ConfigFileCommand(click.Command):
    """Click command that loads pyproject defaults before parsing options."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """
        Parse command-line arguments after injecting config-file defaults.

        Parameters
        ----------
        ctx : click.Context
            Click context used for parsing.
        args : list[str]
            Raw command-line arguments.

        Returns
        -------
        list[str]
            Remaining arguments from Click's standard parser.
        """
        config_file = _find_config_for_raw_args(args)
        if config_file and config_file.exists():
            config = load_config_from_file(config_file)
            update_click_context(ctx, config)

        return super().parse_args(ctx, args)


def _find_config_for_raw_args(args: list[str]) -> Path | None:
    """
    Resolve the config file implied by raw CLI arguments.

    Parameters
    ----------
    args : list[str]
        Raw command-line arguments before Click parses them.

    Returns
    -------
    Path | None
        Explicit config path, discovered config path, or None.
    """
    config_value, paths = _split_config_and_paths(args)
    if config_value:
        return Path(config_value)

    return find_config_file(paths)


def _split_config_and_paths(
        args: list[str],
) -> tuple[str | None, tuple[str, ...]]:
    """
    Extract the config option and positional paths from raw CLI args.

    Parameters
    ----------
    args : list[str]
        Raw command-line arguments before Click parses them.

    Returns
    -------
    tuple[str | None, tuple[str, ...]]
        Config option value and positional paths.
    """
    paths: list[str] = []
    config_value: str | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--':
            paths.extend(args[i + 1 :])
            break

        if arg == '--config':
            if i + 1 < len(args):
                config_value = args[i + 1]

            i += 2
            continue

        if arg.startswith('--config='):
            config_value = arg.split('=', 1)[1]
            i += 1
            continue

        option = arg.split('=', 1)[0]
        if option in _VALUE_OPTIONS:
            i += 1 if '=' in arg else 2
            continue

        if arg.startswith('-') and arg != '-':
            i += 1
            continue

        paths.append(arg)
        i += 1

    return config_value, tuple(paths)


def find_config_file(paths: list[str] | tuple[str, ...] | None) -> Path | None:
    """
    Find pyproject.toml by walking up from the target path(s).

    Parameters
    ----------
    paths : list[str] | tuple[str, ...] | None
        The paths to search from. If None or empty, searches from cwd.

    Returns
    -------
    Path | None
        The path to pyproject.toml if found, None otherwise.
    """
    if not paths:
        search_path = Path.cwd()
    elif len(paths) == 1:
        search_path = Path(paths[0])
        if search_path.is_file():
            search_path = search_path.parent
    else:
        # Find common parent folder
        search_path = _find_common_parent(paths)

    # Walk up the directory tree looking for pyproject.toml
    current = search_path.resolve()
    while True:
        config_file = current / 'pyproject.toml'
        if config_file.exists():
            return config_file

        parent = current.parent
        if parent == current:  # Reached root
            break

        current = parent

    return None


def _find_common_parent(paths: list[str] | tuple[str, ...]) -> Path:
    """
    Find the common parent folder of the given paths.

    Parameters
    ----------
    paths : list[str] | tuple[str, ...]
        The paths to find the common parent for.

    Returns
    -------
    Path
        The common parent folder.
    """
    path_objs = [Path(p) for p in paths]

    # For single path, return its parent if it looks like a file
    if len(path_objs) == 1:
        path = path_objs[0]
        # If it has a file extension, treat as file
        if path.suffix:
            return path.parent
        # If it exists and is a file, return parent
        if path.exists() and path.is_file():
            return path.parent
        # Otherwise treat as directory
        return path

    # For multiple paths, find common parent by comparing parts
    # Convert all file paths to their parent directories
    dir_paths = []
    for path in path_objs:
        if path.suffix or (path.exists() and path.is_file()):
            dir_paths.append(path.parent)
        else:
            dir_paths.append(path)

    # Start with the first directory
    common = dir_paths[0]

    # Find common parent by comparing parts
    for path in dir_paths[1:]:
        # Find common parts
        common_parts = []
        for p1, p2 in zip(common.parts, path.parts, strict=False):
            if p1 == p2:
                common_parts.append(p1)
            else:
                break

        if common_parts:
            common = Path(*common_parts)
        else:
            # No common parent, use cwd
            common = Path.cwd()
            break

    return common


def load_config_from_file(config_file: Path) -> dict[str, Any]:
    """
    Load configuration from a pyproject.toml file.

    Parameters
    ----------
    config_file : Path
        Path to the configuration file.

    Returns
    -------
    dict[str, Any]
        Configuration dictionary with normalized keys (underscores).
    """
    if not config_file.exists():
        return {}

    try:
        with Path(config_file).open('rb') as fp:
            raw_config = tomllib.load(fp)

        # Extract [tool.format_docstring] section
        format_docstring_section = raw_config.get('tool', {}).get(
            'format_docstring', {}
        )

        # Normalize keys: replace hyphens with underscores
        return {
            k.replace('-', '_'): v for k, v in format_docstring_section.items()
        }
    except Exception:  # noqa: BLE001
        # If there's any error reading/parsing the file, return empty config
        return {}


def update_click_context(
        ctx: click.Context,
        config: dict[str, Any],
) -> None:
    """
    Update the Click context's default_map with configuration values.

    Parameters
    ----------
    ctx : click.Context
        The Click context to update.
    config : dict[str, Any]
        Configuration dictionary to merge into the context.
    """
    if ctx.default_map is None:
        ctx.default_map = {}

    ctx.default_map.update(config)


def inject_config_from_file(
        ctx: click.Context,
        param: click.Parameter,  # noqa: ARG001 (required by Click callback signature)
        value: str | None,
) -> str | None:
    """
    Inject configuration from a file for callback-based Click integrations.

    ``ConfigFileCommand`` is preferred for the built-in CLIs because it loads
    defaults before Click parses option values.

    Parameters
    ----------
    ctx : click.Context
        The Click context.
    param : click.Parameter
        The Click parameter (unused, required by Click callback signature).
    value : str | None
        The path to the config file, or None to auto-discover.

    Returns
    -------
    str | None
        The config file path if found/specified, None otherwise.
    """
    config_file: Path | None

    if value:
        # User specified a config file
        config_file = Path(value)
    else:
        # Auto-discover config file from paths
        paths = ctx.params.get('paths')
        config_file = find_config_file(paths)

    if config_file and config_file.exists():
        config = load_config_from_file(config_file)
        update_click_context(ctx, config)
        return str(config_file)

    return None
