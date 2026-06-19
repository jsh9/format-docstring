All the test cases here should be in `tests/test_data/end_to_end/google`.

Regression notes:

- `examples_plain_code_after_doctest.txt` verifies that plain Python code in
  `Examples:` keeps its physical line breaks after a preceding doctest block.
  This is needed because doctests split the wrapper into separate segments.
- `custom_section_after_doctest.txt` verifies that a peer custom section after
  doctest output resumes normal prose wrapping instead of being preserved as
  doctest output.
- `doctest_output_section_headers_are_preserved.txt` verifies that indented
  doctest output such as `Args:`, `Returns:`, and custom `Todo:` remains
  output, while a peer `Args:` after the example starts a real section.
- `examples_leading_comment_is_preserved.txt` verifies that a leading Python
  comment in `Examples:` is preserved byte-for-byte. This is needed because the
  backtick fixer and prose wrapper otherwise treat the comment as normal prose.
- `examples_plain_output_after_code_is_preserved.txt` verifies that plain
  repr-like output after example code keeps its original line break. This
  guards the code/output span scanner from handing output to prose wrapping.
- `arg_description_starts_with_bulleted_list.txt` and
  `arg_description_starts_with_table.txt` verify that an `Args:` entry whose
  description starts on the next line keeps protected block indentation. This
  guards the pass-one handoff where inline descriptions are already dedented
  but following block lines still carry source indentation.
