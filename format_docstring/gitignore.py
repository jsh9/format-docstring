"""Hierarchical .gitignore matching for file discovery."""

from __future__ import annotations

import os
from pathlib import Path

from pathspec import GitIgnoreSpec


class GitIgnoreMatcher:
    """Match paths against cached ancestor and nested .gitignore files."""

    def __init__(self) -> None:
        self._specs: dict[Path, GitIgnoreSpec | None] = {}

    def _load(self, directory: Path) -> GitIgnoreSpec | None:
        if directory not in self._specs:
            ignore_file = directory / '.gitignore'
            try:
                text = ignore_file.read_text(encoding='utf-8')
            except FileNotFoundError:
                self._specs[directory] = None
            except UnicodeError as exc:
                msg = f'Invalid .gitignore {ignore_file}: {exc}'
                raise ValueError(msg) from exc
            else:
                try:
                    self._specs[directory] = GitIgnoreSpec.from_lines(
                        text.splitlines()
                    )
                except ValueError as exc:
                    msg = f'Invalid .gitignore {ignore_file}: {exc}'
                    raise ValueError(msg) from exc

        return self._specs[directory]

    def is_ignored(self, path: Path) -> bool:
        """Check a path and its parents without resolving symbolic links."""
        # resolve() would follow symlinks and change the rule scope.
        path = Path(os.path.abspath(path))  # noqa: PTH100
        parents = [*reversed(path.parent.parents), path.parent]
        # A repository (including a worktree) bounds inherited ignore rules.
        for index in range(len(parents) - 1, -1, -1):
            if (parents[index] / '.git').exists():
                parents = parents[index:]
                break

        specs: list[tuple[Path, GitIgnoreSpec]] = []
        for directory in parents:
            if self._matches(directory, specs, is_directory=True):
                return True

            spec = self._load(directory)
            if spec is not None:
                specs.append((directory, spec))

        return self._matches(path, specs, is_directory=path.is_dir())

    @staticmethod
    def _matches(
            path: Path,
            specs: list[tuple[Path, GitIgnoreSpec]],
            *,
            is_directory: bool,
    ) -> bool:
        ignored = False
        for base, spec in specs:
            relative = path.relative_to(base).as_posix()
            if is_directory:
                relative += '/'

            result = spec.check_file(relative)
            if result.include is not None:
                ignored = result.include

        return ignored
