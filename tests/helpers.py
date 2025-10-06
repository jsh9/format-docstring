from __future__ import annotations

from pathlib import Path

SEPARATOR = '**********'


def load_cases_from_dir(data_dir: Path) -> list[tuple[str, int, str, str]]:
    """Load line-wrap test cases from text files in a directory.

    Each file format:
    - First line: ``LINE_LENGTH: <int>``
    - Body contains BEFORE content, a line with ``**********`` as separator,
      followed by AFTER content. Optional blank lines around the separator are
      allowed.
    """
    cases: list[tuple[str, int, str, str]] = []
    for filename in sorted(data_dir.glob('*.txt')):
        case: tuple[str, int, str, str] = load_case_from_file(filename)
        cases.append(case)

    return cases


def load_case_from_file(filename: Path) -> tuple[str, int, str, str]:
    raw = filename.read_text()
    first_nl = raw.find('\n')
    if first_nl == -1:
        raise AssertionError(f'Malformed test file (no newline): {filename}')

    header = raw[:first_nl].strip()
    if not header.lower().startswith('line_length:'):
        raise AssertionError(f'Malformed header in {filename}: {header!r}')

    try:
        line_length = int(header.split(':', 1)[1].strip())
    except Exception as e:  # pragma: no cover - error path
        raise AssertionError(
            f'Invalid line length in {filename}: {header!r}'
        ) from e

    body = raw[first_nl + 1 :].lstrip('\n')
    # Accept an optional leading separator line
    if body.startswith(SEPARATOR):
        body = body[len(SEPARATOR) :].lstrip('\n')

    if SEPARATOR not in body:
        raise AssertionError(f'Missing separator in {filename}')

    parts = body.split(SEPARATOR)
    before = parts[0].strip('\n')
    after = SEPARATOR.join(parts[1:]).strip('\n')

    return filename.name, line_length, before, after
