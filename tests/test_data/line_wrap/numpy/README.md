All the test cases here should be in `tests/test_data/end_to_end/numpy`.

Regression notes:

- `examples_plain_code_after_doctest.txt` and
  `custom_section_after_doctest.txt` mirror the Google regression fixtures so
  the inventory guard keeps both style directories aligned. They also confirm
  the shared doctest helpers keep NumPy behavior unchanged.
- `arg_description_starts_with_bulleted_list.txt` and
  `arg_description_starts_with_table.txt` mirror the Google indentation
  regression fixtures. They keep the inventory guard aligned and confirm the
  new Google-only fix does not change NumPy protected-block behavior.
