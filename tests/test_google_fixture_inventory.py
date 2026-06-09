"""
Guard Google fixture coverage against drifting from the NumPy gold standard.

The NumPy line-wrap and end-to-end fixture folders are the canonical coverage
set for docstring formatting behavior. Google fixtures should keep matching
that inventory so a new NumPy regression case prompts an equivalent Google
case. The only expected omissions are the underline-mismatch fixtures, because
those exercise NumPy section-underlining syntax that Google docstrings do not
use.
"""

from pathlib import Path


TEST_DATA_DIR = Path(__file__).parent / 'test_data'

NUMPY_ONLY_FIXTURES = {
    'mismatched_underlines.txt',
    'mismatched_underlines_one_dash.txt',
    'mismatched_underlines_two_dashes.txt',
}


def _fixture_names(path: Path) -> set[str]:
    return {fixture.name for fixture in path.glob('*.txt')}


def test_google_fixture_inventory_matches_numpy_gold_standard() -> None:
    """Google fixtures should track NumPy coverage except NumPy syntax cases."""
    for fixture_group in ('line_wrap', 'end_to_end'):
        numpy_names = _fixture_names(TEST_DATA_DIR / fixture_group / 'numpy')
        google_names = _fixture_names(TEST_DATA_DIR / fixture_group / 'google')

        assert numpy_names - google_names == NUMPY_ONLY_FIXTURES
        assert not google_names - numpy_names
