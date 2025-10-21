from format_docstring.line_wrap_utils import ParameterMetadata


def wrap_docstring_google(
        docstring: str,  # noqa: ARG001
        *,
        line_length: int,  # noqa: ARG001
        leading_indent: int | None = None,  # noqa: ARG001
        fix_rst_backticks: bool = True,  # noqa: ARG001
        parameter_metadata: ParameterMetadata | None = None,  # noqa: ARG001
        return_annotation: str | None = None,  # noqa: ARG001
        attribute_metadata: ParameterMetadata | None = None,  # noqa: ARG001
) -> str:
    """A placeholder for now."""  # noqa: D401
    return ''
