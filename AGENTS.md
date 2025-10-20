# AGENTS.md

This guide briefs coding agents working on `format-docstring`. Use it to get
oriented before making changes.

## 1. Quick Snapshot

- Formats NumPy-style docstrings (with experimental Google support) in `.py`
  files and Jupyter notebooks while preserving surrounding code.
- Distributed as a CLI (`format-docstring`, `format-docstring-jupyter`) with
  minimum Python 3.10, packaged via `setuptools`.
- Core dependencies: `click`, `docstring_parser_fork`,
  `jupyter-notebook-parser`, and `tomli/tomllib` for configuration loading.
- Version is sourced dynamically in `format_docstring/__init__.py`.

## 2. Repository Layout

- `format_docstring/main_py.py` – Click CLI for Python files; validates input
  and delegates to `PythonFileFixer`.
- `format_docstring/main_jupyter.py` – CLI for `.ipynb` files built on
  `JupyterNotebookParser`/`JupyterNotebookRewriter`.
- `format_docstring/base_fixer.py` – Shared directory traversal, exclusion
  regex handling, and `fix_one_directory_or_one_file` orchestration.
- `format_docstring/docstring_rewriter.py` – AST-based docstring extraction and
  replacement that leaves non-docstring text untouched.
- `format_docstring/line_wrap_numpy.py` / `line_wrap_google.py` –
  Style-specific wrapping helpers; NumPy path is the production code path,
  Google is partial.
- `format_docstring/line_wrap_utils.py` – Shared utilities for wrapping (indent
  management, bullet handling, preserving literal blocks, etc.).
- `format_docstring/config.py` – `pyproject.toml` discovery, parsing, and Click
  default injection.
- `tests/` – Pytest suite with fixture-driven cases in `tests/test_data/`; see
  `tests/helpers.py` for fixture loading helpers.

## 3. Implementation Notes

- `docstring_rewriter.fix_src` parses with `ast.parse`, collects docstring
  literals, and rewrites source slices using absolute offsets from
  `calc_line_starts`; this avoids `ast.unparse` and keeps comments/spacing.
- For functions, `_collect_param_metadata` records signature annotations and
  default values so NumPy `Parameters` signatures in docstrings are
  resynchronised with the real function definition. Defaulted parameters omit
  redundant `, optional`, and forward references keep their original quoting.
- Return annotations are likewise projected into `Returns`/`Yields` sections,
  mirroring tuple element splits when the docstring already enumerates them.
- `Raises` section entries are treated like signature lines in the NumPy
  wrapper so exception names stay untouched while descriptions wrap.
- Wrapping honors NumPy section heuristics, rST constructs, code fences,
  `Examples` prompts, and literal blocks introduced by `::`.
- `_normalize_signature_segment` flattens multiline annotations via
  `ast.unparse` but uses token-level replay to preserve the author's quoting
  style for forward references and string defaults.
- CLI exposes `--docstring-style`, but the Python entry-point currently raises
  if a non-NumPy style is requested; Jupyter flow passes style through
  unchanged.
- `BaseFixer` subclasses return `1` when any file changed so callers can
  surface non-zero exit codes.
- Notebook fixer round-trips JSON via `json.dump(..., indent=1)` and rewrites
  cells only when content changes, preserving magics with `reconstruct_source`.

## 4. Configuration

- User-facing configuration lives under `[tool.format_docstring]` inside
  `pyproject.toml` and supports `line_length`, `docstring_style`, `exclude`,
  `fix_rst_backticks`, and `verbose` (`default` or `diff` to print unified
  diffs on rewrites).
- `config.inject_config_from_file` auto-discovers the nearest `pyproject.toml`
  (walking up from targets) and merges values into Click’s `default_map`.
- Default exclude pattern is `\.git|\.tox|\.pytest_cache`; tests tweak it as
  needed.

## 5. Development Workflow

- Install: `pip install -e .` for the project,
  `pip install -r requirements.dev` for tooling.
- Tests: `pytest --tb=long`, or target modules such as
  `pytest tests/test_docstring_rewriter.py`.
- Lint/format: `muff check --fix --config=muff.toml format_docstring tests`,
  `muff format --diff --config=muff.toml format_docstring tests`.
- Type checking: `mypy format_docstring/`.
- Tox: `tox` for the full matrix (py310–py313, mypy, lint), or focused runs
  like `tox -e py311`, `tox -e mypy`, `tox -e muff-format`.
- CLI smoke tests: `format-docstring --help`,
  `format-docstring-jupyter --help`.
- Pre-commit: `pre-commit run -a`.

## 6. Testing Notes

- Fixture files under `tests/test_data/line_wrap` and
  `tests/test_data/end_to_end` use `LINE_LENGTH: <int>` headers followed by
  `BEFORE`/`AFTER` sections split by `**********`.
- Regression fixture
  `tests/test_data/end_to_end/numpy/signature_dont_sync_raises.txt` guards
  against mutating exception names in `Raises` blocks.
- `tests/test_playground.py` focuses on regression snippets;
  `tests/test_config.py` exercises config discovery and CLI overrides.
- When modifying wrapping rules, update both the helper (`line_wrap_utils.py`)
  and the corresponding expectation files in `tests/test_data/`.

## 7. Style Guidance

- Formatting rules mirror `muff.toml` (line length 79, single quotes, NumPy
  docstring convention). Respect these when adding code.
- Keep docstring style tests conservative: avoid mutating non-docstring
  content, and add regression cases whenever handling around literal sections
  or tables changes.

## 8. What is a "signature line"?

They are the lines in the docstring where input and return args are defined,
for example, in this docstring:

```python
"""
Do something

Parameters
----------
arg1 : str
    Arg 1
arg2 : int = 2
    Arg 2

Returns
-------
dict[str, str]
   The mapping
```

Signature lines are:

- arg1 : str
- arg2 : int = 2
- dict[str, str]
