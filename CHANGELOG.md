# Change Log

All notable changes to this project will be documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.3] - 2026-10-04

- Fixed
  - NumPy style no longer reflows `::` literal blocks after their first
    paragraph. Paragraphs after a blank line inside the block were wrapped as
    prose; the whole block is now kept until the text dedents.
  - A `::` literal block whose first line is a list item or table row is now
    kept whole in both styles. Only the list or table was kept before, and the
    block's later paragraphs were wrapped as prose.
  - NumPy style no longer reflows the body of code directives that take an
    argument, such as `.. code-block:: python`, `.. code:: python`, and
    `.. sourcecode:: python`. Their code lines were joined like prose.
  - In NumPy style, when a list item's `::` block is indented past the item's
    text, the item's next paragraph now gets its single backticks fixed. It was
    already wrapped as prose, but its backticks were left alone as if it were
    part of the block.
  - A `::` literal block no longer ends at a line inside it that looks like a
    section header, such as `Arguments:` in a CLI help sample or a
    `parameters:` key in YAML. The rest of the block was reflowed as prose and
    got its single backticks doubled, in both styles. Only indentation ends a
    block now, as in rST. For a Google compact summary (`"""Summary::` beside
    the opening quotes), the block is measured from the docstring margin, so it
    still ends at the next section, and now also at the next paragraph at the
    margin, which it used to swallow.
  - The bodies of IPython's `.. ipython::` directive, the `sphinx.ext.doctest`
    directives (`.. doctest::`, `.. testcode::`, `.. testoutput::`,
    `.. testsetup::`, `.. testcleanup::`) and sphinx-prompt's `.. prompt::` are
    now kept as is when the directive takes an argument, such as
    `.. ipython:: python` or `.. doctest:: grouped`, like
    `.. code-block:: python`. Their lines were joined like prose (in Google
    style, `.. ipython:: python` bodies were also dedented). Code directives
    written with a space before the `::` (`.. code-block :: python`), which
    docutils accepts, are recognized too.
  - A section heading inside an rST code directive or a `::` literal block
    (such as an rST or NumPy sample with `Returns` over `-------`) no longer
    switches the section the text after the block is parsed in. In NumPy style,
    prose after such a block was read as a return signature and replaced by the
    synced type, and parameters after a block in a parameter description lost
    their signature sync. In Google style, a header line inside a block was
    renamed (`Arguments:` became `Args:`) and the prose after the block was
    parsed as section content. Both wrappers now pass these blocks through
    before section parsing, ahead of code fences, so a `~~~~` line inside a
    block is no longer read as an unclosed fence that hides the rest of the
    docstring.
- Changed
  - In NumPy style, the whole body of a directive whose line ends with `::`,
    such as `.. note::`, is now left as is, like a literal block. Previously
    only its first paragraph was kept and later paragraphs were rewrapped.
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.4.2...0.4.3

## [0.4.2] - 2026-10-04

- Fixed
  - Line wrapping no longer breaks inside rST inline literals
    (``` ``...`` ```). Breaking there dropped the whitespace at the break, so a
    literal such as ``` ``'  '`` ``` lost its spaces. Each inline literal now
    wraps as one unbreakable word, overflowing like other long words when it is
    longer than the line. Re-running the formatter rejoins literals that
    earlier versions split across lines. Tabs and other Unicode whitespace
    inside a literal are preserved as well, instead of being expanded or
    collapsed.
  - Google-style compact first lines no longer collapse runs of spaces inside
    inline literals.
  - Google-style prose lines that start with an inline literal containing a
    colon (such as ``` ``key:value`` ```) are no longer mistaken for signature
    lines, which rewrote the literal's content on a second pass.
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.4.1...0.4.2

## [0.4.1] - 2026-06-30

- Fixed
  - Google-style compact docstring wrapping now reserves the opening literal
    width from the source, so plain triple-quoted summaries keep the correct
    first-line budget while raw and Unicode prefixes still account for their
    extra prefix column.
  - One-character quoted docstring literals and adjacent string-token
    docstrings are skipped as unsupported formatter targets, so long strings
    are not wrapped into invalid multi-line source.
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.4.0...0.4.1

## [0.4.0] - 2026-06-29

- Added
  - CLI and `pyproject.toml` options to control whether argument types,
    argument defaults, and Google return/yield types are included in docstring
    signature lines for Python files and Jupyter notebooks.
- Fixed
  - Google-style argument signature synchronization preserves existing
    `required` metadata when source annotations replace stale docstring type
    text.
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.3.0...0.4.0

## [0.3.0] - 2026-06-19

- Added
  - Google-style docstring formatting for Python files and Jupyter notebooks
    via `--docstring-style google` or `docstring_style = "google"` under
    `[tool.format_docstring]`
  - Google `Args:`, `Attributes:`, `Returns:`, and `Yields:` signature
    synchronization from source annotations, defaults, class attributes, and
    generator yield annotations
  - Fixture coverage for Google line wrapping, end-to-end rewrites, notebook
    rewrites, protected blocks, custom sections, and signature synchronization
- Changed
  - Shared section and protected-block parsing so NumPy and Google formatting
    preserve doctests, Python example code, fenced code, rST code blocks,
    literal blocks, tables, and bullet lists more consistently
  - README examples and configuration docs now describe NumPy and Google
    behavior separately
  - Development type checking now uses `ty` instead of `mypy`
- Fixed
  - CLI config discovery now applies `pyproject.toml` settings found by walking
    up from the target file or directory
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.7...0.3.0

## [0.2.7] - 2025-12-04

- Fixed
  - Bug where non-ASCII characters would mess up auto formatting
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.6...0.2.7

## [0.2.6] - 2025-11-21

- Fixed
  - Multiline annotations now normalize without inserting spaces inside
    `Literal[...]` or other bracketed signatures, even when they span several
    lines.
  - A bug where bare `*args`/`**kwargs` signature lines (typed or untyped)
    would be merged into previous descriptions
  - NumPy signature syncing left the `:class:` / `:meth:` role prefixes behind,
    producing mismatched annotations like ` : MyClass`
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.5...0.2.6

## [0.2.5] - 2025-11-20

- Fixed
  - A bug where `Generator[XXX, YYY, ZZZ]` in the return type annotation is not
    parsed correctly (the Yields section should have been XXX)
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.4...0.2.5

## [0.2.4] - 2025-10-27

- Fixed
  - A bug where 2nd pair of backticks can't be added for dunder names (such as
    `__init__`)
  - A bug where input args named `default` would get treated incorrectly (the
    tool would confuse it with the default values)
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.3...0.2.4

## [0.2.3] - 2025-10-22

- Added
  - A lot more linters
  - Formatters for TOML and INI config files
- Changed
  - A lot of code changes to pass the linter checks
- Removed
  - Unnecessary pre-commit hooks
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.2...0.2.3

## [0.2.2] - 2025-10-20

- Added
  - Formatting support for type hints and default values in class docstrings
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.1...0.2.2

## [0.2.1] - 2025-10-20

- Fixed
  - A bug where raised exceptions in docstrings are incorrectly changed
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.2.0...0.2.1

## [0.2.0] - 2025-10-20

- Added
  - AST-driven synchronization of NumPy `Parameters` and `Returns` signature
    lines with the function signature, including tuple element expansion for
    multi-line return blocks
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.9...0.2.0

## [0.1.9] - 2025-10-16

- Added
  - A "`# no-format-docstring`" directive to ignore certain docstring
  - Verbose diff output via `--verbose diff` and
    `[tool.format_docstring] verbose`
  - Normalize NumPy section headings that include trailing colons (e.g.,
    `Parameters:`); also, fix Google-style "Arg" header into "Parameters"
- Changed
  - Added "self format" pre-commit hook to format docstrings within this repo
    with its own formatting logic
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.8...0.1.9

## [0.1.8] - 2025-10-14

- Fixed
  - Bug in `_fix_rst_backticks()` where backtick pairs spanning multiple lines
    (e.g., multi-line external links) were incorrectly processed
  - Added `(?!_)` lookahead to regex pattern to prevent matching trailing
    backticks from cross-references (e.g., `` `text`_ ``)
- Changed
  - Moved backtick fixing from line-by-line processing to whole-docstring
    processing to correctly handle multi-line constructs
  - REPL lines (starting with `>>> ` or `... `) are now protected with
    placeholders during backtick fixing to preserve backticks in Python
    examples
- Added
  - Test cases for multi-line external links in
    `test_fix_rst_backticks_cases()`
  - Test cases for REPL lines with backticks in
    `test_fix_rst_backticks_cases()`
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.7...0.1.8

## [0.1.7] - 2025-10-14

- Fixed
  - Backtick fixing logic to properly distinguish between inline literals and
    external links (e.g., `` `Python <https://example.org>`_ ``)
  - Refactored `_fix_rst_backticks()` to use pre-compiled regex pattern for
    better performance
- Full diff
  - https://github.com/jsh9/format-docstring/compare/0.1.6...0.1.7

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
