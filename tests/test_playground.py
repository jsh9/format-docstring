from pathlib import Path

from format_docstring import docstring_rewriter


def test_playground_empty_file_formats_to_empty() -> None:
    """Test playground."""
    before_path = Path(__file__).parent / 'test_data' / 'playground.py'
    src = before_path.read_text()

    # Run the formatter on the playground file
    formatted = docstring_rewriter.fix_src(
        src,
        line_length=10,
        docstring_style='google',
    )

    # For this test suite, the expected output is an empty string
    assert formatted == ''
