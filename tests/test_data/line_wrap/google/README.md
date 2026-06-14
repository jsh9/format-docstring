All the test cases here should be in `tests/test_data/end_to_end/google`.

Regression notes:

- `examples_plain_code_after_doctest.txt` verifies that plain Python code in
  `Examples:` keeps its physical line breaks after a preceding doctest block.
  This is needed because doctests split the wrapper into separate segments.
- `custom_section_after_doctest.txt` verifies that a peer custom section after
  doctest output resumes normal prose wrapping instead of being preserved as
  doctest output.
