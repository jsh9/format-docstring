# format-docstring

A Python formatter to automatically format NumPy-style and Google-style
docstrings.

<!--TOC-->

______________________________________________________________________

**Table of Contents**

- [1. Overview](#1-overview)
- [2. Before vs After Examples](#2-before-vs-after-examples)
  - [2.1. NumPy-style docstrings](#21-numpy-style-docstrings)
  - [2.2. Google-style docstrings](#22-google-style-docstrings)
- [3. Special Formatting Rules](#3-special-formatting-rules)
  - [3.1. NumPy-style docstrings](#31-numpy-style-docstrings)
  - [3.2. Google-style docstrings](#32-google-style-docstrings)
- [4. Installation](#4-installation)
- [5. Usage](#5-usage)
  - [5.1. Command Line Interface](#51-command-line-interface)
  - [5.2. Pre-commit Hook](#52-pre-commit-hook)
  - [5.3. Opting Out of Formatting](#53-opting-out-of-formatting)
  - [5.4. What Counts as a Docstring](#54-what-counts-as-a-docstring)
- [6. Configuration](#6-configuration)
  - [6.1. Command-Line Options](#61-command-line-options)
  - [6.2. Usage Examples](#62-usage-examples)
  - [6.3. `pyproject.toml` Configuration](#63-pyprojecttoml-configuration)
- [7. Caveat](#7-caveat)

______________________________________________________________________

<!--TOC-->

## 1. Overview

`format-docstring` is a tool that automatically formats and wraps docstring
content in Python files and Jupyter notebooks.

| Feature                                   | `format-docstring` | [docformatter] | [pydocstringformatter] | [Ruff] | [Black] |
| ----------------------------------------- | ------------------ | -------------- | ---------------------- | ------ | ------- |
| Docstring wrapping                        | ✅                 | ❌             | ❌                     | ❌     | ❌      |
| Compatible with line length linter (E501) | ✅                 | ❌             | ❌                     | N/A    | N/A     |
| Fixes common docstring typos              | ✅                 | ❌             | ❌                     | ❌     | ❌      |

For stronger docstring checks, use `format-docstring` together with
[`pydoclint`](https://github.com/jsh9/pydoclint). `format-docstring` handles
formatting and wrapping, while `pydoclint` checks docstring completeness and
consistency with function signatures.

## 2. Before vs After Examples

These examples show the same kinds of cleanup in the two supported docstring
styles. Use `--docstring-style numpy` for NumPy-style docstrings and
`--docstring-style google` for Google-style docstrings.

### 2.1. NumPy-style docstrings

NumPy-style docstrings use section titles followed by underline rows. Signature
lines are written as `name : type`, and descriptions are indented under the
signature line.

**Long summaries and descriptions are wrapped.**

```diff
def load_records(path, limit=100):
-    """Load records from disk and normalize every field before returning the resulting table.
+    """
+    Load records from disk and normalize every field before returning the
+    resulting table.

    Parameters
    ----------
-    path : str
-        Path to a CSV file that may be local or remote and may include query parameters that make the line too long.
-    limit : int
-        Maximum number of rows to read before validation and normalization run.
+    path : str
+        Path to a CSV file that may be local or remote and may include query
+        parameters that make the line too long.
+    limit : int
+        Maximum number of rows to read before validation and normalization
+        run.

    Returns
    -------
    list[dict[str, str]]
-        Normalized rows ready for downstream processing or serialization.
+        Normalized rows ready for downstream processing or serialization.
    """
```

**Known section names and signature spacing are canonicalized.**

```diff
def resize(image):
    """
    Resize an image.

-    ParaMEter
-    ---
+    Parameters
+    ----------
    image : ArrayLike
        Input image.

-    ReTurn
-    ----------
+    Returns
+    -------
    ArrayLike
        Resized image.
    """
```

**Default value declarations are standardized.**

```diff
def connect():
    """
    Parameters
    ----------
-    retries : int default 3
+    retries : int, default=3
        Number of attempts.
-    timeout : float, default is 1.5
+    timeout : float, default=1.5
        Timeout in seconds.
    """
```

**Single backticks in prose are converted to rST inline literals.**

```diff
def parse(payload):
    """
-    Parse `payload` into a normalized mapping.
+    Parse ``payload`` into a normalized mapping.

    Parameters
    ----------
    payload : dict
-        Input with `id` and `value` keys.
+        Input with ``id`` and ``value`` keys.
    """
```

**Parameters and returns are synchronized from the real signature.**

```diff
def summarize(name: str, retries: int = 3) -> tuple[int, str]:
    """
    Summarize a job.

    Parameters
    ----------
-    name : object
+    name : str
        Job name.
-    retries : int, optional
+    retries : int, default=3
        Retry count.

    Returns
    -------
-    float
+    int
        Number of processed rows.
    str
        Human-readable status.
    """
```

### 2.2. Google-style docstrings

Google-style docstrings use colon-ended section headers. Signature lines keep
the first description sentence inline as `name (type): description`, and
continuation lines are indented below the description.

**Long summaries and descriptions are wrapped.**

```diff
def load_records(path, limit=100):
-    """Load records from disk and normalize every field before returning the resulting table.
+    """Load records from disk and normalize every field before returning the
+    resulting table.

    Args:
-        path (str): Path to a CSV file that may be local or remote and may include query parameters that make the line too long.
-        limit (int): Maximum number of rows to read before validation and normalization run.
+        path (str): Path to a CSV file that may be local or remote and may
+            include query parameters that make the line too long.
+        limit (int): Maximum number of rows to read before validation and
+            normalization run.

    Returns:
-        list[dict[str, str]]: Normalized rows ready for downstream processing or serialization.
+        list[dict[str, str]]: Normalized rows ready for downstream processing
+            or serialization.
    """
```

**Known section names and signature spacing are canonicalized.**

```diff
def resize(image):
    """
    Resize an image.

-    ParaMEter:
-        image(ArrayLike):Input image.
+    Args:
+        image (ArrayLike): Input image.

-    ReTurn:
-        ArrayLike: Resized image.
+    Returns:
+        ArrayLike: Resized image.
    """
```

**Default value declarations are standardized.**

```diff
def connect():
    """
    Args:
-        retries (int, default 3): Number of attempts.
-        timeout (float, default is 1.5): Timeout in seconds.
+        retries (int, default=3): Number of attempts.
+        timeout (float, default=1.5): Timeout in seconds.
    """
```

**Single backticks in prose are converted to rST inline literals.**

```diff
def parse(payload):
    """
-    Parse `payload` into a normalized mapping.
+    Parse ``payload`` into a normalized mapping.

    Args:
-        payload (dict): Input with `id` and `value` keys.
+        payload (dict): Input with ``id`` and ``value`` keys.
-            Use `strict` mode for validation.
+            Use ``strict`` mode for validation.
    """
```

**Parameters and returns are synchronized from the real signature.**

```diff
def summarize(name: str, retries: int = 3) -> tuple[int, str]:
    """Summarize a job.

    Args:
-        name (object): Job name.
+        name (str): Job name.
-        retries (int, optional): Retry count.
+        retries (int, default=3): Retry count.

    Returns:
-        status (float): Number of processed rows.
-        label (str): Human-readable status.
+        tuple[int, str]: Number of processed rows. label (str):
+            Human-readable status.
    """
```

## 3. Special Formatting Rules

`format-docstring` assumes docstrings are already close to NumPy or Google
style. These examples show the extra rules applied around structure, protected
content, and source-signature sync.

### 3.1. NumPy-style docstrings

**Protected content keeps its shape.** Tables, doctest prompts, fenced code,
literal blocks introduced by `::`, and bullet lists are not reflowed. Prose
around those blocks still wraps normally.

```diff
"""
-Use this formula before processing the records because the surrounding prose is long enough to wrap::
+Use this formula before processing the records because the surrounding prose
+is long enough to wrap::

        total = alpha + beta
        ratio = total / count

Parameters
----------
records : list[dict[str, str]]
    Input records.
"""
```

**Known sections are parsed, and custom sections are kept.** Recognized section
titles such as `Parameters`, `Returns`, `Yields`, `Raises`, `Examples`, and
`Notes` are canonicalized. Unknown underlined sections remain custom sections,
and their prose is wrapped instead of being parsed as parameter signatures.

```diff
def work():
    """
-    argument
-    --------
+    Parameters
+    ----------
    value : int
        Value to process.

-    Todo
-    ----
-    Keep this custom section, but wrap its prose normally when it exceeds the configured line length.
+    Todo
+    ----
+    Keep this custom section, but wrap its prose normally when it exceeds the
+    configured line length.
    """
```

**Tuple returns can stay split across multiple signature lines.** When the
docstring already documents tuple elements as separate return entries, NumPy
formatting syncs each element from the real return annotation.

```diff
def compute() -> tuple[int, str]:
    """
    Returns
    -------
-    float
+    int
        Row count.
    str
        Status message.
    """
```

**`Raises` entries are treated as signatures.** Exception names stay untouched;
only their descriptions wrap.

```diff
"""
Raises
------
ValueError
-    Raised when the payload is missing a required key and the caller asked for strict validation.
+    Raised when the payload is missing a required key and the caller asked for
+    strict validation.
"""
```

**Class attributes can be synchronized too.** Class docstrings can use
annotated assignments and type comments as the source of truth for
`Attributes`.

```diff
class Config:
    """
    Attributes
    ----------
-    retries : int, optional
+    retries : int, default=3
        Retry count.
    """

    retries = 3  # type: int
```

### 3.2. Google-style docstrings

**Protected content keeps its shape.** Tables, doctest prompts, fenced code,
literal blocks introduced by `::`, and Python-like code in `Examples:` are not
reflowed. Prose around those blocks still wraps normally.

```diff
"""
-Use this formula before processing the records because the surrounding prose is long enough to wrap::
+Use this formula before processing the records because the surrounding prose
+is long enough to wrap::

        total = alpha + beta
        ratio = total / count

Args:
    records (list[dict[str, str]]): Input records.
"""
```

**Custom section boundaries are indentation-sensitive.** Known headers such as
`Args:`, `Returns:`, `Raises:`, and `Examples:` are canonicalized. Unknown
peer-level headers after summary content are treated as custom sections, so
their body wraps as prose instead of as argument descriptions.

```diff
def work():
    """
    Do work.

-    Arguments:
+    Args:
        value: Value to process.

    Todo:
-        Keep this custom section, but wrap its prose normally when it exceeds the configured line length.
+        Keep this custom section, but wrap its prose normally when it exceeds
+        the configured line length.
    """
```

If the first content line is an unknown `Name:` header, it is treated as
summary text rather than promoted to a custom section. That protects compact
Google summaries from being misclassified.

**`Examples:` has special boundary rules.** Indented text that looks like a
section header can be doctest output. A real section boundary must return to
the same or lower indentation as the active `Examples:` header.

```python
"""
Examples:
    >>> print("Args:")
    Args:
    >>> print("done")
    done

Args:
    value: Real argument description.
"""
```

**Returns and yields describe one value.** Google style does not split tuple
returns into separate return-variable rows. If a tuple annotation is present,
the formatter syncs the tuple type into one `Returns:` entry and keeps the old
text as description.

```diff
def compute() -> tuple[int, str]:
    """
    Returns:
-        count (float): Row count.
-        status (str): Status message.
+        tuple[int, str]: Row count. status (str): Status message.
    """
```

**Class attributes can be synchronized too.** Google `Attributes:` entries use
the same source-signature policy as `Args:`.

```diff
class Config:
    """
    Attributes:
-        retries (int, optional): Retry count.
+        retries (int, default=3): Retry count.
    """

    retries = 3  # type: int
```

## 4. Installation

```bash
pip install format-docstring
```

## 5. Usage

### 5.1. Command Line Interface

**For Python files:**

```bash
format-docstring path/to/file.py
format-docstring path/to/directory/

# Format Google-style docstrings
format-docstring --docstring-style google path/to/file.py
format-docstring --docstring-style google path/to/directory/
```

**For Jupyter notebooks:**

```bash
format-docstring-jupyter path/to/notebook.ipynb
format-docstring-jupyter path/to/directory/

# Format Google-style docstrings in notebooks
format-docstring-jupyter --docstring-style google path/to/notebook.ipynb
format-docstring-jupyter --docstring-style google path/to/directory/
```

### 5.2. Pre-commit Hook

To use `format-docstring` as a pre-commit hook, add this to your
`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/jsh9/format-docstring
    rev: <LATEST_VERSION>
    hooks:
      - id: format-docstring
        name: Format docstrings in .py files
        args: [--docstring-style=numpy, --line-length=79]
      - id: format-docstring-jupyter
        name: Format docstrings in .ipynb files
        args: [--docstring-style=numpy, --line-length=79]
```

For Google-style docstrings, use `--docstring-style=google` in the hook args.

Then install the pre-commit hook:

```bash
pre-commit install
```

### 5.3. Opting Out of Formatting

Add a comment containing `no-format-docstring` on the same line as the closing
triple quotes to prevent the formatter from touching that docstring:
`""" ... """  # no-format-docstring`.

You can combine this "no-format-docstring" with other directives like "noqa".

Tip: If you only want to keep specific formatter changes inside a docstring,
first run `format-docstring`, accept the parts you like, revert the edits you
dislike, and then add an inline `# no-format-docstring` comment so future runs
leave that docstring untouched.

### 5.4. What Counts as a Docstring

`format-docstring` follows [Python's docstring rule][python-docstring] to find
candidate docstrings: the first statement in a module, class, function, or
method must be a string literal. It intentionally formats only triple-quoted
string literals such as plain, raw, and Unicode-prefixed strings:

```python
"""Formatted."""
r"""Formatted."""
u"""Formatted."""
```

Single-quoted and double-quoted one-character delimiters can be Python
docstrings, but they are outside formatter support and are left unchanged.
Formatted string literals and bytes literals are also left unchanged:

```python
'Not formatted.'
"Not formatted."
f"""Not a docstring."""
rf"""Not a docstring."""
fr"""Not a docstring."""
b"""Not a docstring."""
rb"""Not a docstring."""
br"""Not a docstring."""
```

## 6. Configuration

### 6.1. Command-Line Options

| Option                                  | Default                        | Description                                                                                                                                                                                           |
| --------------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--line-length INTEGER`                 | `79`                           | Maximum line length for wrapping docstrings.                                                                                                                                                          |
| `--docstring-style CHOICE`              | `numpy`                        | Docstring style to target, either `numpy` or `google`. This selects the style to format, not a converter between styles.                                                                              |
| `--fix-rst-backticks BOOL`              | `True`                         | Automatically fix single backticks to double backticks per rST syntax. Pass `False` to disable this.                                                                                                  |
| `--include-arg-types BOOL`              | `True`                         | Include argument type hints in parameter docstrings. Pass `False` to remove them from structured arg and attribute signature lines; defaults must also be disabled.                                   |
| `--include-arg-defaults BOOL`           | `True`                         | Include argument defaults in parameter docstrings. Pass `False` to remove explicit defaults and `optional` markers from structured arg and attribute signature lines. Requires argument types.        |
| `--include-return-and-yield-types BOOL` | `True`                         | Include type hints in `Returns` and `Yields` docstrings. Pass `False` to remove them from Google-style return/yield descriptions. NumPy style does not allow `False`.                                 |
| `--verbose CHOICE`                      | `default`                      | Logging detail level. `default` keeps the existing behaviour; `diff` prints unified diffs when rewrites happen.                                                                                       |
| `--exclude TEXT`                        | `\.git\|\.tox\|\.pytest_cache` | Regex pattern to exclude files/directories.                                                                                                                                                           |
| `--config PATH`                         | None                           | Path to a `pyproject.toml` config file. If not specified, the tool automatically searches for `pyproject.toml` in parent directories. Command-line options take precedence over config file settings. |
| `--version`                             | N/A                            | Show version information.                                                                                                                                                                             |
| `--help`                                | N/A                            | Show help message.                                                                                                                                                                                    |

### 6.2. Usage Examples

```bash
# Format a single file with default settings
format-docstring my_module.py

# Format all Python files in a directory with custom line length
format-docstring --line-length 72 src/

# Format Google-style docstrings
format-docstring --docstring-style google src/

# Format Jupyter notebooks excluding certain directories
format-docstring-jupyter --exclude "\.git|\.venv|__pycache__" notebooks/

# Format Google-style docstrings in notebooks
format-docstring-jupyter --docstring-style google notebooks/

# Preview changes with unified diffs
format-docstring --verbose diff src/

# Use a specific config file
format-docstring --config path/to/pyproject.toml src/

# CLI options override config file settings
format-docstring --config pyproject.toml --line-length 100 src/

# Disable backtick fixing
format-docstring --fix-rst-backticks=False my_module.py

# Omit argument defaults, including optional markers
format-docstring --include-arg-defaults=False src/

# Omit Google-style return/yield type text when annotations carry the types
format-docstring --docstring-style google --include-return-and-yield-types=False src/
```

### 6.3. `pyproject.toml` Configuration

You can configure default values under `[tool.format_docstring]` in
`pyproject.toml`. CLI arguments override these settings. The config loader
accepts either underscore keys, such as `line_length`, or hyphenated keys, such
as `line-length`.

```toml
[tool.format_docstring]
line_length = 79
docstring_style = "numpy"
fix_rst_backticks = true
include_arg_types = true
include_arg_defaults = true
include_return_and_yield_types = true
exclude = "\\.git|\\.venv|__pycache__"
verbose = "default"  # or "diff" to print unified diffs
```

For Google-style docstrings that omit argument types/defaults and return/yield
types:

```toml
[tool.format_docstring]
docstring_style = "google"
line_length = 79
fix_rst_backticks = true
include_arg_types = false
include_arg_defaults = false
include_return_and_yield_types = false
```

**Available options:**

- `line_length` / `line-length` (int): maximum line length for wrapping
  docstrings. Default: `79`.
- `docstring_style` / `docstring-style` (str): target docstring style, either
  `"numpy"` or `"google"`. Default: `"numpy"`.
- `fix_rst_backticks` / `fix-rst-backticks` (bool): whether to convert single
  backticks in prose to double backticks per rST syntax. Default: `true`.
- `include_arg_types` / `include-arg-types` (bool): whether to include argument
  type hints in parameter docstrings. Default: `true`. If this is `false`,
  `include_arg_defaults` must also be `false`.
- `include_arg_defaults` / `include-arg-defaults` (bool): whether to include
  argument defaults in parameter docstrings. Default: `true`. This requires
  `include_arg_types = true`. When set to `false`, explicit defaults and
  `optional` markers are removed from structured signatures, including compact
  or extra-spaced forms such as `,optional` and `,   optional`. For example,
  `x : int, optional` becomes `x : int` and `x (int, optional):` becomes
  `x (int):`.
- `include_return_and_yield_types` / `include-return-and-yield-types` (bool):
  whether to include return and yield type hints in docstrings. Default:
  `true`. Setting this to `false` is supported only with Google style.
- `exclude` (str): regex pattern used to skip files or directories. Default:
  `"\\.git|\\.tox|\\.pytest_cache"`.
- `verbose` (str): logging detail level, either `"default"` or `"diff"`. Use
  `"diff"` to print unified diffs when rewrites happen.

The tool searches for `pyproject.toml` starting from the target file/directory
and walking up the parent directories until one is found.

## 7. Caveat

This tool assumes the docstrings are written in **mostly** the correct format,
because it needs those formatting cues (such as section headers and `------`)
to parse docstrings.

If the docstrings are far from perfectly formatted, it's recommended that you
use AI coding assistants to rewrite the docstrings first.

[black]: https://github.com/psf/black
[docformatter]: https://github.com/PyCQA/docformatter
[pydocstringformatter]: https://github.com/DanielNoord/pydocstringformatter
[python-docstring]: https://docs.python.org/3/glossary.html#term-docstring
[ruff]: https://github.com/astral-sh/ruff
