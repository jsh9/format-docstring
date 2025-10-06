class Alpha:
    """
    Class Alpha performs an operation with a very long explanation meant to
    exceed the configured line length so that we can verify wrapping and
    indentation handling even when the docstring does not begin with a newline
    before the first word.
    """

    CONSTANT_WITH_LONG_VALUE = 'THIS_IS_A_LONG_CONSTANT_VALUE_THAT_SHOULD_NOT_BE_TOUCHED_BY_THE_FORMATTER_EVEN_IF_IT_IS_VERY_LONG'

    def method(self, x, y):
        """
        This method processes the inputs x and y and returns a computed result
        while demonstrating that long lines in docstrings wrap correctly and
        that the closing quotes align on their own line.
        """
        # A very long code line that should not be reformatted by this tool
        some_really_long_variable_name = x + y + 1000000000000000000000000000000000000000000000000000000  # noqa: E501
        return some_really_long_variable_name


def beta(a, b):
    """
    This is a function with a long one-line docstring that intentionally
    exceeds the maximum line length to ensure wrapping occurs and that a
    leading newline is inserted when needed.
    """
    # Another long code line to ensure non-docstring parts are unchanged and definitely far beyond seventy-nine characters to validate we do not touch it
    return (a * b) + (a ** b) + (a - b) + (a / (b if b else 1)) + 12345678901234567890  # noqa: E501


def gamma():
    """
    This function starts with a newline and contains a very long line intended
    to be wrapped across multiple lines while preserving indentation and moving
    the closing quotes to their own properly indented line.
    """
    return None
