"""uv resolves the environment from pyproject.toml and .python-version, and
both have to sit together at the repo root for a nested checkout to work."""

import tomllib


def test_python_version_sits_next_to_pyproject(repo_root):
    assert (repo_root / 'pyproject.toml').is_file()
    assert (repo_root / '.python-version').is_file()


def test_pinned_python_is_within_requires_python(repo_root):
    pinned = (repo_root / '.python-version').read_text(encoding='utf-8').strip()
    requires = tomllib.loads(
        (repo_root / 'pyproject.toml').read_text(encoding='utf-8')
    )['project']['requires-python']

    major, minor = (int(part) for part in pinned.split('.')[:2])
    floor = requires.split('>=')[1].split(',')[0].strip()
    ceiling = requires.split('<')[-1].strip()

    assert (major, minor) >= tuple(int(p) for p in floor.split('.')[:2])
    assert (major, minor) < tuple(int(p) for p in ceiling.split('.')[:2])


def test_requires_python_has_an_upper_bound(repo_root):
    """The locked dep set has no wheels for 3.14; an open-ended floor let uv
    pick it and the sync failed."""
    requires = tomllib.loads(
        (repo_root / 'pyproject.toml').read_text(encoding='utf-8')
    )['project']['requires-python']
    assert '<' in requires, f'requires-python has no ceiling: {requires}'


def test_lockfile_is_present(repo_root):
    assert (repo_root / 'uv.lock').is_file()
