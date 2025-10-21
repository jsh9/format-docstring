# format-docstring

A Python formatter to automatically format numpy-style docstrings.

<!--TOC-->

______________________________________________________________________

**Table of Contents**

- [1. Overview](#1-overview)
- [2. Before vs After Examples](#2-before-vs-after-examples)
  - [2.1. Long lines are wrapped to fit line length limit](#21-long-lines-are-wrapped-to-fit-line-length-limit)
  - [2.2. One-line summaries are formatted to fit line length limit](#22-one-line-summaries-are-formatted-to-fit-line-length-limit)
  - [2.3. Minor typos can be automatically fixed](#23-minor-typos-can-be-automatically-fixed)
  - [2.4. Default value declarations are standardized](#24-default-value-declarations-are-standardized)
  - [2.5. Single backticks are converted to double backticks (rST syntax)](#25-single-backticks-are-converted-to-double-backticks-rst-syntax)
  - [2.6. Docstring parameters and returns stay in sync with signatures](#26-docstring-parameters-and-returns-stay-in-sync-with-signatures)
- [3. Installation](#3-installation)
- [4. Usage](#4-usage)
  - [4.1. Command Line Interface](#41-command-line-interface)
  - [4.2. Pre-commit Hook](#42-pre-commit-hook)
  - [4.3. Opting Out of Formatting](#43-opting-out-of-formatting)
- [5. Configuration](#5-configuration)
  - [5.1. Command-Line Options](#51-command-line-options)
  - [5.2. Usage Examples](#52-usage-examples)
  - [5.3. `pyproject.toml` Configuration](#53-pyprojecttoml-configuration)
- [6. Caveat](#6-caveat)

______________________________________________________________________

<!--TOC-->

## 1. Overview

`format-docstring` is a tool that automatically formats and wraps docstring
content in Python files and Jupyter notebooks.

Baseline reflow corresponds to the common docstring cleanups offered by
general-purpose formatters: splitting one-line docstrings into the canonical
multi-line layout (triple quotes, blank line, summary), normalizing
indentation, and wrapping text at a fixed column width without applying extra
heuristics.

| Feature                                   | `format-docstring` | [docformatter] | [pydocstringformatter] | [Ruff] | [Black] |
| ----------------------------------------- | ------------------ | -------------- | ---------------------- | ------ | ------- |
| Docstring wrapping                        | ✅                 | ❌             | ❌                     | ❌     | ❌      |
| Compatible with line length linter (E501) | ✅                 | ❌             | ❌                     | N/A    | N/A     |
| Fixes common docstring typos              | ✅                 | ❌             | ❌                     | ❌     | ❌      |

## 2. Before vs After Examples

### 2.1. Long lines are wrapped to fit line length limit

```diff
def example_function(param1, param2, option='default'):
-    """This summary line is intentionally very long and exceeds the line length limit to demonstrate that format-docstring will automatically wrap it across multiple lines while preserving code structure.
+    """
+    This summary line is intentionally very long and exceeds the line length
+    limit to demonstrate that format-docstring will automatically wrap it
+    across multiple lines while preserving code structure.

    Parameters
    ----------
-    param1 : str
-        This parameter description is also intentionally long to show how parameter descriptions get wrapped when they exceed the configured line length limit
-    param2 : int
-        Another long parameter description that demonstrates the wrapping behavior for parameter documentation in NumPy-style docstrings
+    param1 : str
+        This parameter description is also intentionally long to show how
+        parameter descriptions get wrapped when they exceed the configured
+        line length limit
+    param2 : int
+        Another long parameter description that demonstrates the wrapping
+        behavior for parameter documentation in NumPy-style docstrings
    option : str, optional
        Short description (not wrapped)

    Returns
    -------
    dict
-        The return value wrapped, because it is a very long line that exceeds line length limit by a lot.
+        The return value wrapped, because it is a very long line that exceeds
+        line length limit by a lot.

    Examples
    --------
    Within the "Examples" section, code with >>> prompts are preserved without
    wrapping:

    >>> result = example_function('test', 42, option='custom_value_with_a_very_long_name_that_exceeds_line_length')
    >>> print(result)
    {'status': 'success'}

    rST tables are preserved without wrapping:

    ===========  ==================  ===============================
    Format       Wrapped             Preserved
    ===========  ==================  ===============================
    Text         Yes                 No (in tables, code, lists)
    Params       Yes                 Signature lines preserved
    ===========  ==================  ===============================

    Contents following double colons (`::`) are preserved::

                  P(B|A) P(A)
        P(A|B) = -------------
                      P(B)

    Even if there isn't an extra blank line after `::`, the contents are still
    preserved::
            _______
       σ = √ Var(X)

    Regular bullet lists are also preserved:

    - First bullet point that is intentionally long but not wrapped
    - Second point also stays on one line regardless of length
    """
```

### 2.2. One-line summaries are formatted to fit line length limit

```diff
def my_function():
-    """Contents are short, but with quotation marks this exceeds length limit."""
+    """
+    Contents are short, but with quotation marks this exceeds length limit.
+    """
    pass
```

### 2.3. Minor typos can be automatically fixed

```diff
def mu_function():
    """
    Minor typos in section titles or "signatures" can be fixed.

-    Parameter
-    ----
+    Parameters
+    ----------
    arg1 : str
        Arg 1
    arg2 : bool
        Arg 2
-    arg3: int
+    arg3 : int
        Arg 3
-    arg4    : int
+    arg4 : int
        Arg 4

-    ReTurn
-    ----------
+    Returns
+    -------
    int
        The return value
    """
    pass
```

or, Google-style section headers can be fixed:

```diff
def my_function():
    """
    My function

-    Args:
-    ----
+    Parameters
+    ----------
    arg1 : str
        Arg 1

    ...
    """
    pass
```

### 2.4. Default value declarations are standardized

```diff
def example_function(arg1, arg2, arg3, arg4):
    """
    Parameters
    ----------
-    arg1 : int default 10
+    arg1 : int, default=10
        First argument
-    arg2 : str, default "hello"
+    arg2 : str, default="hello"
        Second argument
-    arg3 : bool, default is True
+    arg3 : bool, default=True
        Third argument
-    arg4 : float default: 3.14
+    arg4 : float, default=3.14
        Fourth argument
    """
    pass
```

### 2.5. Single backticks are converted to double backticks (rST syntax)

```diff
def process_data(data):
    """
-    Process data using the `transform` function.
+    Process data using the ``transform`` function.

    Parameters
    ----------
    data : dict
-        Input data with keys `id`, `value`, and `timestamp`.
+        Input data with keys ``id``, ``value``, and ``timestamp``.

    Returns
    -------
    dict
-        Processed data with key `result`.
+        Processed data with key ``result``.
    """
```

### 2.6. Docstring parameters and returns stay in sync with signatures

```diff
from typing import List, Optional


def create_user(
        user: Optional[str] = None,
        roles: List["Role"] | None = None,
        retries: int = 0,
        serializer: "Serializer" | None = None,
        something_else: tuple[int, ...] = (
            "1",
            '2',
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
        ),
) -> None:
    """
    Parameters
    ----------
-    user : str
+    user : Optional[str], default=None
        Login name.
-    roles : list
+    roles : List["Role"] | None, default=None
        Assigned roles.
-    retries : int
+    retries : int, default=0
        Number of retry attempts.
-    serializer : Serializer, optional
+    serializer : "Serializer" | None, default=None
        Custom serializer instance.
-    something_else : tuple[int, ...]
+    something_else : tuple[int, ...], default=("1", '2', 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    """
    pass
```

And return type hint:

```diff
def build_mapping() -> dict[str, str]:
    """
    Returns
    -------
-    str
+    dict[str, str]
        Mapping of values.
    """
```

For tuple return annotations, tuple elements are split across multiple
signature lines only when the docstring already adopted that layout:

```diff
def compute_values() -> tuple[int, str, list[str]]:
    """
    Returns
    -------
-    float
+    int
        First element.
-    str
+    str
        Second element.
-    List[str]
+    list[str]
        Third element.
    """
```

Annotations and defaults are extracted from the actual function signature, so
docstring signature lines reflect the ground truth. Defaulted parameters omit
redundant `, optional`, forward references keep their original quoting, and
return signatures track tuple splitting conventions already present in the
docstring.

## 3. Installation

```bash
pip install format-docstring
```

## 4. Usage

### 4.1. Command Line Interface

**For Python files:**

```bash
format-docstring path/to/file.py
format-docstring path/to/directory/
```

**For Jupyter notebooks:**

```bash
format-docstring-jupyter path/to/notebook.ipynb
format-docstring-jupyter path/to/directory/
```

### 4.2. Pre-commit Hook

To use `format-docstring` as a pre-commit hook, add this to your
`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/jsh9/format-docstring
    rev: <LATEST_VERSION>
    hooks:
      - id: format-docstring
        name: Format docstrings in .py files
        args: [--line-length=79]
      - id: format-docstring-jupyter
        name: Format docstrings in .ipynb files
        args: [--line-length=79]
```

Then install the pre-commit hook:

```bash
pre-commit install
```

### 4.3. Opting Out of Formatting

Add a comment containing `no-format-docstring` on the same line as the closing
triple quotes to prevent the formatter from touching that docstring:
`""" ... """  # no-format-docstring`.

You can combine this "no-format-docstring" with other directives like "noqa".

Tip: If you only want to keep specific formatter changes inside a docstring,
first run `format-docstring`, accept the parts you like, revert the edits you
dislike, and then add an inline `# no-format-docstring` comment so future runs
leave that docstring untouched.

## 5. Configuration

### 5.1. Command-Line Options

- `--line-length INTEGER`: Maximum line length for wrapping docstrings
  (default: 79)
- `--docstring-style CHOICE`: Docstring style to target (`numpy` or `google`,
  default: `numpy`). Note: Currently only `numpy` style is fully supported.
- `--fix-rst-backticks BOOL`: Automatically fix single backticks to double
  backticks per rST syntax (default: True)
- `--verbose CHOICE`: Logging detail level (`default` keeps the existing
  behaviour, `diff` prints unified diffs when rewrites happen)
- `--exclude TEXT`: Regex pattern to exclude files/directories (default:
  `\.git|\.tox|\.pytest_cache`)
- `--config PATH`: Path to a `pyproject.toml` config file. If not specified,
  the tool automatically searches for `pyproject.toml` in parent directories.
  Command-line options take precedence over config file settings.
- `--version`: Show version information
- `--help`: Show help message

### 5.2. Usage Examples

```bash
# Format a single file with default settings
format-docstring my_module.py

# Format all Python files in a directory with custom line length
format-docstring --line-length 72 src/

# Format Jupyter notebooks excluding certain directories
format-docstring-jupyter --exclude "\.git|\.venv|__pycache__" notebooks/

# Preview changes with unified diffs
format-docstring --verbose diff src/

# Use a specific config file
format-docstring --config path/to/pyproject.toml src/

# CLI options override config file settings
format-docstring --config pyproject.toml --line-length 100 src/

# Disable backtick fixing
format-docstring --fix-rst-backticks=False my_module.py
```

### 5.3. `pyproject.toml` Configuration

You can configure default values in your `pyproject.toml`. CLI arguments will
override these settings:

```toml
[tool.format_docstring]
line_length = 79
docstring_style = "numpy"
fix_rst_backticks = true
exclude = "\\.git|\\.venv|__pycache__"
verbose = "default"  # or "diff" to print unified diffs
```

**Available options:**

- `line_length` (int): Maximum line length for wrapping docstrings (default:
  79\)
- `docstring_style` (str): Docstring style, either `"numpy"` or `"google"`
  (default: `"numpy"`)
- `fix_rst_backticks` (bool): Automatically fix single backticks to double
  backticks per rST syntax (default: `true`)
- `exclude` (str): Regex pattern to exclude files/directories (default:
  `"\\.git|\\.tox|\\.pytest_cache"`)
- `verbose` (str): Logging detail level (`"default"` or `"diff"`)

The tool searches for `pyproject.toml` starting from the target file/directory
and walking up the parent directories until one is found.

## 6. Caveat

This tool assumes the docstrings are written in **mostly** the correct format,
because it needs those formatting cues (such as section headers and `------`)
to parse docstrings.

If the docstrings are far from perfectly formatted, it's recommended that you
use AI coding assistants to rewrite the docstrings first.

[black]: https://github.com/psf/black
[docformatter]: https://github.com/PyCQA/docformatter
[pydocstringformatter]: https://github.com/DanielNoord/pydocstringformatter
[ruff]: https://github.com/astral-sh/ruff
