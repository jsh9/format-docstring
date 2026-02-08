def func1():
    def func2():
        def func3():
            def func4():
                """
                This paragraph is indented by sixteen spaces. With a
                small line-length, the available width after indentation
                is tiny, so wrapping becomes very aggressive. The indent
                is always preserved; words wrap as needed without mid-word
                splitting.
                """
                pass
