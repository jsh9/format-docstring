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
        with open(config_file, 'rb') as fp:
            raw_config = tomllib.load(fp)

        # Extract [tool.format_docstring] section
        format_docstring_section = raw_config.get('tool', {}).get(
            'format_docstring', {}
        )

        # Normalize keys: replace hyphens with underscores
        return {
            k.replace('-', '_'): v for k, v in format_docstring_section.items()
        }
    except Exception:
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
    Click callback to inject configuration from a config file.

    This is used as a callback for the --config option.

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
