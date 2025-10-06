# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Commands

### Development Commands

- `pytest --tb=long` - Run all tests with detailed traceback
- `pytest tests/test_specific_file.py` - Run a specific test file
- `pytest tests/test_specific_file.py::test_function_name` - Run a specific
  test function

### Linting and Formatting

- `mypy format_docstring/` - Type checking
- `muff check --fix --config=muff.toml format_docstring tests` - Lint and
  auto-fix with muff
- `muff format --diff --config=muff.toml format_docstring tests` - Show
  formatting differences (use `--diff` to preview)
- `flake8 --select CLB,PAR,N400 .` - Additional linting checks
- `pre-commit run -a` - Run all pre-commit hooks

### Tox Commands

- `tox` - Run all tox environments (Python 3.10-3.13, mypy, linting)
- `tox -e py311` - Run tests on Python 3.11
- `tox -e mypy` - Run type checking
- `tox -e muff-lint` - Run muff linting
- `tox -e muff-format` - Run muff formatting check

### Building and Installation

- `pip install -e .` - Install in development mode
- `format-docstring --help` - Run the CLI tool
- `format-docstring-jupyter --help` - Run the Jupyter notebook version

## Code Architecture

### Core Components

1. **Entry Points**: Two main CLI tools defined in `pyproject.toml`:

   - `format-docstring` → `format_docstring.main_py:main` - For Python files
   - `format-docstring-jupyter` → `format_docstring.main_jupyter:main` - For
     Jupyter notebooks

2. **Base Architecture**:

   - `base_fixer.py` - Abstract base class `BaseFixer` for file processing
   - Implements file discovery, exclusion patterns, and batch processing logic
   - Subclasses implement `fix_one_file()` method for specific file types

3. **Docstring Processing**:

   - `docstring_rewriter.py` - Core docstring parsing and rewriting logic
   - `line_wrap_numpy.py` - NumPy style docstring formatting
   - `line_wrap_google.py` - Google style docstring formatting (limited
     support)
   - `line_wrap_utils.py` - Shared utilities for line wrapping

4. **Configuration System**:

   - `config.py` - Configuration file parsing and management
   - Loads settings from `pyproject.toml` ([tool.format_docstring] section)
   - Auto-discovers config file by walking up directory tree from target paths
   - CLI options override config file settings
   - Uses `tomllib` (Python 3.11+) or `tomli` (Python 3.10) for TOML parsing

5. **Style Support**:

   - Primary support: NumPy docstring style
   - Limited support: Google docstring style
   - Uses `docstring_parser_fork` library for parsing

### Key Dependencies

- `click>=8.0` - CLI framework
- `docstring_parser_fork>=0.0.14` - Docstring parsing
- `jupyter-notebook-parser>=0.1.4` - Jupyter notebook support
- `tomli>=1.1.0` (Python < 3.11) - TOML file parsing

### Configuration

- **Config File**: `pyproject.toml` with `[tool.format_docstring]` section
  - `line_length` (int): Maximum line length for wrapping (default: 79)
  - `docstring_style` (str): `"numpy"` or `"google"` (default: `"numpy"`)
  - `exclude` (str): Regex pattern to exclude files/directories
- **CLI Options**: `--line-length`, `--docstring-style`, `--exclude`,
  `--config`
- **Priority**: CLI arguments override config file settings
- **Auto-discovery**: Searches for `pyproject.toml` in parent directories
- Muff configuration in `muff.toml` with 79 character line length and single
  quotes

### Test Structure

- `tests/` directory with comprehensive test coverage
- `test_data/` subdirectory contains test fixtures
- Tests cover all main modules: line wrapping, docstring rewriting, CLI tools,
  config parsing
- Use pytest framework with detailed tracebacks
- Test case format in `test_data/`: `LINE_LENGTH: <int>` header, then
  BEFORE/AFTER sections separated by `**********`
- Config tests in `tests/test_config.py` verify TOML parsing, auto-discovery,
  and CLI override behavior

## Important Development Patterns

### Code Preservation Philosophy

- **Direct String Replacement**: The tool uses precise AST-to-source mapping to
  replace only docstrings, preserving all other code formatting, comments, and
  whitespace exactly
- **Line-Aware Processing**: Uses `calc_line_starts()` to maintain exact line
  positioning without using `ast.unparse()`
- **Conservative Approach**: Only modifies docstring content, never touches
  surrounding code structure

### NumPy Style Processing Rules

- **Section Recognition**: Automatically detects section headers (Parameters,
  Returns, etc.) and their underlines
- **Signature vs Description**: Distinguishes parameter signature lines (e.g.,
  `arg : type`) from indented description text
- **Special Case Handling**: Preserves without wrapping:
  - Examples sections with `>>>` prompts
  - rST tables (lines with `===` or `---` separators)
  - Content following `::` (literal blocks)
  - Bullet lists (lines starting with `-`)
  - Fenced code blocks (\`\`\`\` ... \`\`\`\`\`)
- **Colon Spacing**: Automatically fixes spacing around colons in parameter
  signatures to use `:` format (e.g., `arg: int` → `arg : int`, `arg    : int`
  → `arg : int`)
- **Section Title Fixes**: Corrects common typos (e.g., `Parameter` →
  `Parameters`, `ReTurn` → `Returns`) and underline lengths

### File-Based Test Pattern

- Test cases use structured text files with BEFORE/AFTER sections
- Helper function `load_cases_from_dir()` automatically discovers and loads
  test cases
- Use `pytest.mark.parametrize` with test data files for comprehensive coverage

### Pre-commit Hook

Available as pre-commit hooks (see `.pre-commit-hooks.yaml`):

- `format-docstring` - For `.py` files
- `format-docstring-jupyter` - For `.ipynb` files
