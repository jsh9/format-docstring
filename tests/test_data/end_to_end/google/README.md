All the test cases in `tests/test_data/line_wrap/google` should be here, but not
all the test cases here are over there.

Regression notes:

- `examples_plain_code_after_doctest.txt` verifies the full-source rewrite for
  plain Python examples following doctest output. This catches quote/indent
  interactions that the line-wrap-only fixture cannot exercise.
- `custom_section_after_doctest.txt` verifies that a custom section after
  doctest output is wrapped as prose in a rebuilt Python docstring.
