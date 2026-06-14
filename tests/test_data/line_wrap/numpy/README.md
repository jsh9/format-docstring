All the test cases here should be in `tests/test_data/end_to_end/numpy`.

Regression notes:

- `examples_plain_code_after_doctest.txt` and
  `custom_section_after_doctest.txt` mirror the Google regression fixtures so
  the inventory guard keeps both style directories aligned. They also confirm
  the shared doctest helpers keep NumPy behavior unchanged.
