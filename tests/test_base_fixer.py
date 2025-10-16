import difflib

import pytest

from format_docstring.base_fixer import BaseFixer


class DummyFixer(BaseFixer):
    """Minimal fixer to expose BaseFixer internals for testing."""

    def fix_one_file(self, *args, **kwargs):
        raise NotImplementedError


def test_print_diff_noop_when_not_verbose(
        capsys: pytest.CaptureFixture[str],
) -> None:
    # Use CaptureFixture to assert on stderr without polluting test output
    fixer = DummyFixer(path='.', verbose='default')
    fixer._print_diff('file.py', 'before', 'after')

    captured = capsys.readouterr()
    assert captured.err == ''


def test_print_diff_emits_expected_unified_diff(
        capsys: pytest.CaptureFixture[str],
) -> None:
    # CaptureFixture lets us retrieve emitted diff exactly as written to stderr
    fixer = DummyFixer(path='.', verbose='diff')
    before = 'line1\nline2\n'
    after = 'line1\nline2 changed\n'

    fixer._print_diff('file.py', before, after)

    captured = capsys.readouterr()
    diff_text = ''.join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile='file.py (before)',
            tofile='file.py (after)',
            lineterm='',
        )
    )
    expected = diff_text if diff_text.endswith('\n') else f'{diff_text}\n'
    assert captured.err == expected
