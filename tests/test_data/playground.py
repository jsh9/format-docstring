def func1():
    """Below is a formula that should not be wrapped. Here are some more
    contents that are arbitrary just to make the line length quite long so that
    we can test how it can be wrapped. This paragraph would end with two colons
    to signal that the contents below should not be wrapped

    Args:
        arg1 (int): Below is a formula

            where:
                + x     = Something
                + alpha = Something else
                + beta  = Something beta
                + a     = A thing
                + gamma = The gamma

        arg2 (bool): Here is a table, and it should not be wrapped.

            +------------+--------+------------+-------------+-------------+--------+-----+
            | strain [%] | G/Gmax | strain [%] | damping [%] |  strain [%] | G/Gmax | ... |
            +============+========+============+=============+=============+========+=====+
            |    ...     |  ...   |    ...     |    ...      |    ...      |  ...   | ... |
            +------------+--------+------------+-------------+-------------+--------+-----+
    """
    pass
