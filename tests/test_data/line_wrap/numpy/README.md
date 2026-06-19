All the test cases here should be in `tests/test_data/end_to_end/numpy`.

Regression notes:

- `examples_plain_code_after_doctest.txt` and
  `custom_section_after_doctest.txt` mirror the Google regression fixtures so
  the inventory guard keeps both style directories aligned. They also confirm
  the shared doctest helpers keep NumPy behavior unchanged.
- `doctest_output_section_headers_are_preserved.txt` mirrors the Google
  doctest-boundary regression and confirms NumPy still exits doctest output at
  a real underlined `Parameters` section.
- `examples_leading_comment_is_preserved.txt` and
  `examples_plain_output_after_code_is_preserved.txt` verify the shared
  example-code scanner preserves Python comments and plain output lines before
  the prose wrapper or rST backtick fixer can rewrite them.
- `arg_description_starts_with_bulleted_list.txt` and
  `arg_description_starts_with_table.txt` mirror the Google indentation
  regression fixtures. They keep the inventory guard aligned and confirm the
  new Google-only fix does not change NumPy protected-block behavior.
