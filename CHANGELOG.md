# Change Log

All notable changes to this project will be documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.7] - 2025-10-14

- Fixed
  - Backtick fixing logic to properly distinguish between inline literals and
    external links (e.g., `` `Python <https://example.org>`_ ``)
  - Refactored `_fix_rst_backticks()` to use pre-compiled regex pattern for
    better performance

## [0.1.6] - 2025-10-13

- Added
  - New `--fix-rst-backticks` option to automatically convert single backticks
    to double backticks per rST syntax
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.5...0.1.6

## [0.1.5] - 2025-10-13

- Added
  - Support for `... ` (continuation of REPL lines) in the Examples section
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.4...0.1.5

## [0.1.4] - 2025-10-12

- Added
  - Support for detecting misspelled section title: "Example"
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.3...0.1.4

## [0.1.3] - 2025-10-12

- Fixed
  - A bug in counting line length for single-line docstrings
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.2...0.1.3

## [0.1.2] - 2025-10-08

- Added
  - Support for 1 blank line after `::`
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.1...0.1.2

## [0.1.1] - 2025-10-06

- Fixed
  - A bug where single-line docstrings exceeding length limit aren't handled
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.0...0.1.1

## [0.1.0] - 2025-10-06

- Added
  - Initial release of format-docstring
  - Support for NumPy-style docstring formatting
  - Limited support for Google-style docstrings
  - CLI tools: `format-docstring` and `format-docstring-jupyter`
  - Configuration via `pyproject.toml` with `[tool.format_docstring]` section
  - Options for line length, docstring style, and file exclusion patterns
  - Pre-commit hooks for Python files and Jupyter notebooks
  - Comprehensive test suite with pytest
  - Type checking with mypy
  - Support for Python 3.10-3.12
- Full diff
  - N/A
