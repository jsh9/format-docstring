All the test cases in `tests/test_data/line_wrap/numpy` should be here, but not
all the test cases here are over there.

Regression notes:

- `examples_plain_code_after_doctest.txt` and
  `custom_section_after_doctest.txt` are NumPy counterparts for Google
  regression fixtures. They ensure shared helper changes do not alter NumPy
  full-source rewrites.
