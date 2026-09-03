"""Set up and validate the project side of the loc tools.

loc-sync.py runs the work; this one looks after the files the project owns:
the configs, the runner batch file, the gitignore and the sync guide.

Usage:
    loc-project.py                -> scaffold a project from the templates, never overwriting
    loc-project.py --check        -> validate the project config, exit 1 on problems
    loc-project.py --upgrade      -> report how the template and the project config differ
    loc-project.py --ensure-crowdin -> install the pinned Crowdin CLI if it is missing
"""

import difflib
import shutil
import subprocess
import tomllib
from dataclasses import fields
from pathlib import Path

import typer
import yaml
from loguru import logger
from typing_extensions import Annotated as A

from libraries.task_runner import (
    DEFAULT_BASE_CONFIG,
    DEFAULT_SECRET_CONFIG,
    TaskRunner,
)
from libraries.utilities import init_logging

TEMPLATE_DIR = Path(__file__).resolve().parent / 'templates'

# Sections under script-parameters that no registered task owns: standalone
# scripts with their own parsers, configured here for convenience.
NON_TASK_SECTIONS = {'targets', 'ue-reimport-assets'}

# winget is the only distribution channel we automate. The CLI ships as a
# portable exe, so winget puts it on PATH without an installer.
CROWDIN_WINGET_ID = 'Crowdin.CrowdinCLI'

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    help='Set up and validate the project side of the loc tools.',
)


def load_yaml(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def do_init(base_path: Path, secret_path: Path) -> int:
    project_dir = base_path.parent
    # template name -> where it lands in the project
    scaffold = {
        'base.config.yaml': base_path,
        'crowdin.config.yaml': secret_path,
        '!loc-sync.bat': project_dir / '!loc-sync.bat',
        'gitignore': project_dir / '.gitignore',
        'sync-guide.md': project_dir / 'sync-guide.md',
    }

    existing = [p for p in scaffold.values() if p.exists()]
    if existing:
        for path in existing:
            logger.error(f'Refusing to overwrite: {path}')
        logger.error('Move or delete it first, or use --upgrade to compare.')
        return 1

    for name, target in scaffold.items():
        template = TEMPLATE_DIR / name
        if not template.exists():
            logger.error(f'Template missing: {template}')
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, target)
        logger.success(f'Created {target}')

    logger.warning(
        f'Fill in your Crowdin token and project ID in {secret_path}, '
        'and keep that file out of version control.'
    )
    logger.info(
        'For Perforce, add the rules in '
        f'{TEMPLATE_DIR / "p4ignore-snippet.txt"} to the .p4ignore.txt at your '
        'workspace root.'
    )
    return 0


def pinned_crowdin_cli_version() -> str | None:
    pyproject = Path(__file__).resolve().parent / 'pyproject.toml'
    if not pyproject.is_file():
        return None
    with open(pyproject, 'rb') as f:
        return (
            tomllib.load(f).get('tool', {}).get('loctools', {})
        ).get('crowdin_cli_version')


def installed_crowdin_cli_version() -> str | None:
    try:
        result = subprocess.run(
            ['crowdin', '--version'],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
            shell=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().splitlines()[0].strip() if result.stdout else None


def winget_has_crowdin_cli() -> bool:
    """winget list exits 0 when the package is installed, 20 when it is not.
    Asks winget rather than PATH, which this process cannot see updates to."""
    try:
        result = subprocess.run(
            [
                'winget',
                'list',
                '--id',
                CROWDIN_WINGET_ID,
                '-e',
                '--accept-source-agreements',
                '--disable-interactivity',
            ],
            capture_output=True,
            text=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
            shell=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def install_crowdin_cli(version: str) -> bool:
    """Installs the pinned version with winget. Installing anything other than
    the pin would defeat the point, so a pin winget cannot supply is reported
    rather than substituted."""
    if not shutil.which('winget'):
        logger.error(
            'winget is not available, so the Crowdin CLI cannot be installed '
            f'automatically. Install {version} by hand: '
            'https://crowdin.github.io/crowdin-cli'
        )
        return False

    logger.info(
        f'Installing Crowdin CLI {version} with winget. This downloads from '
        'the internet and can take a minute.'
    )
    try:
        result = subprocess.run(
            [
                'winget',
                'install',
                '--id',
                CROWDIN_WINGET_ID,
                '-e',
                '--version',
                version,
                '--accept-source-agreements',
                '--accept-package-agreements',
                '--disable-interactivity',
            ],
            timeout=1800,
            stdin=subprocess.DEVNULL,
            shell=True,
        )
    except subprocess.SubprocessError as err:
        logger.error(
            f'winget did not finish installing the Crowdin CLI: {err}. It may '
            'have been left half-installed, so check with: '
            f'winget list --id {CROWDIN_WINGET_ID} -e'
        )
        return False

    if result.returncode != 0:
        # Most often winget declining to reinstall something it already has.
        if winget_has_crowdin_cli():
            logger.warning(
                'winget reports the Crowdin CLI as installed, but it is not '
                'on PATH in this shell. Open a new terminal and run this again.'
            )
            return False

        logger.error(f'winget could not install Crowdin CLI {version}.')
        logger.error(
            'Run this by hand to see what it is asking for: '
            f'winget install --id {CROWDIN_WINGET_ID} -e --version {version}'
        )
        logger.error(
            'If that version is not published, bump crowdin_cli_version in '
            'pyproject.toml and re-run the tests. Published versions: '
            f'winget show --id {CROWDIN_WINGET_ID} -e --versions'
        )
        return False

    if installed_crowdin_cli_version() == version:
        logger.success(f'Installed Crowdin CLI {version}.')
        return True

    # winget puts the exe on the user PATH in the registry, which this
    # process cannot see: it inherited PATH when it started.
    logger.success(
        f'Installed Crowdin CLI {version}. It is not visible in this shell '
        'yet, so the checks below may not see it either.'
    )
    return True


def check_crowdin_cli(install_missing: bool = False) -> bool:
    """A version mismatch warns rather than blocks: the CLI is only used for
    uploads, and most task lists never touch it. Returns False only when
    there is no usable CLI at all."""
    pinned = pinned_crowdin_cli_version()
    if not pinned:
        return True

    installed = installed_crowdin_cli_version()
    if installed is None:
        if install_missing:
            return install_crowdin_cli(pinned)
        logger.warning(
            f'Crowdin CLI not found on PATH. Source uploads need it, pinned at '
            f'{pinned}. Run update-loc-tools.bat to install it.'
        )
        return False

    if installed != pinned:
        logger.warning(
            f'Crowdin CLI is {installed}, this release is tested against '
            f'{pinned}. Uploads may behave differently. Either install {pinned} '
            'or bump crowdin_cli_version in pyproject.toml and re-run the tests.'
        )
        return True

    logger.success(f'Crowdin CLI {installed} matches the pinned version.')
    return True


def do_check(base_path: Path, secret_path: Path) -> int:
    if not base_path.exists():
        logger.error(f'No config to check: {base_path}')
        return 1

    if not secret_path.exists():
        logger.warning(
            f'No {secret_path.name}, checking against the template instead. '
            'Crowdin credentials are not validated.'
        )
        secret_path = TEMPLATE_DIR / 'crowdin.config.yaml'

    runner = TaskRunner()
    runner.unattended = True
    try:
        config = runner.load_config(str(base_path), str(secret_path))
    except Exception as err:
        logger.error(f'Config does not load: {err}')
        return 1

    problems = 0

    for name, params in (config.get('script-parameters') or {}).items():
        if name in NON_TASK_SECTIONS:
            continue
        task_class = runner._task_registry.get(name)
        if task_class is None:
            logger.error(f'script-parameters section "{name}" matches no task')
            problems += 1
            continue
        known = {f.name for f in fields(task_class())}
        for key in sorted(k for k in (params or {}) if k not in known):
            suggestion = difflib.get_close_matches(key, known, n=1)
            hint = f' (did you mean "{suggestion[0]}"?)' if suggestion else ''
            logger.error(f'{name}: "{key}" matches no field and is ignored{hint}')
            problems += 1

    for list_name, tasks in config.items():
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            script = task.get('script')
            if script not in runner._task_registry:
                logger.error(f'"{list_name}": unknown task "{script}"')
                problems += 1
                continue
            try:
                runner.create_task_instance(script, task)
            except Exception as err:
                logger.error(f'"{list_name}" -> {script}: {type(err).__name__}: {err}')
                problems += 1

    if problems:
        logger.error(f'{problems} problem(s) found in {base_path}')
        return 1

    logger.success(f'{base_path} is valid.')
    check_crowdin_cli()
    return 0


def section_keys(config: dict) -> dict[str, set]:
    sections = {'parameters': set((config.get('parameters') or {}).keys())}
    for name, params in (config.get('script-parameters') or {}).items():
        sections[f'script-parameters/{name}'] = set((params or {}).keys())
    return sections


def do_upgrade(base_path: Path) -> int:
    if not base_path.exists():
        logger.error(f'No config to compare: {base_path}')
        return 1

    template = section_keys(load_yaml(TEMPLATE_DIR / 'base.config.yaml'))
    project = section_keys(load_yaml(base_path))

    for name in sorted(set(template) - set(project)):
        logger.info(f'Section only in the template: {name}')
    for name in sorted(set(project) - set(template)):
        logger.info(f'Section only in your config: {name}')

    changes = 0
    for name in sorted(set(template) & set(project)):
        added = sorted(template[name] - project[name])
        removed = sorted(project[name] - template[name])

        renamed = []
        for key in list(removed):
            match = difflib.get_close_matches(key, added, n=1, cutoff=0.7)
            if match:
                renamed.append((key, match[0]))
                removed.remove(key)
                added.remove(match[0])

        for old, new in renamed:
            logger.warning(f'{name}: "{old}" looks renamed to "{new}"')
        for key in added:
            logger.info(f'{name}: new in the template: "{key}"')
        for key in removed:
            logger.info(f'{name}: only in your config: "{key}"')
        changes += len(renamed) + len(added) + len(removed)

    if changes:
        logger.warning(
            f'{changes} difference(s). Nothing was modified: a config is '
            'judgment, not data. Apply what you want by hand, then --check.'
        )
    else:
        logger.success('Your config and the template agree on every key.')
    return 0


@app.command()
def run(
    check: A[
        bool, typer.Option('--check', help='Validate the project config')
    ] = False,
    upgrade: A[
        bool,
        typer.Option('--upgrade', help='Report template/config differences'),
    ] = False,
    ensure_crowdin: A[
        bool,
        typer.Option(
            '--ensure-crowdin',
            help='Install the pinned Crowdin CLI if it is missing',
        ),
    ] = False,
    config: A[str, typer.Option('--config', '-c', help='Base config file')] = (
        DEFAULT_BASE_CONFIG
    ),
    secret: A[str, typer.Option('--secret', '-s', help='Secret config file')] = (
        DEFAULT_SECRET_CONFIG
    ),
    debug: A[bool, typer.Option('--debug', help='Enable debug logging')] = False,
):
    init_logging(debug)

    if ensure_crowdin:
        ok = check_crowdin_cli(install_missing=True)
        raise typer.Exit(code=0 if ok else 1)

    if check and upgrade:
        logger.error('Use either --check or --upgrade, not both.')
        raise typer.Exit(code=2)

    base_path = Path(config)
    secret_path = Path(secret)

    if check:
        raise typer.Exit(code=do_check(base_path, secret_path))
    if upgrade:
        raise typer.Exit(code=do_upgrade(base_path))
    raise typer.Exit(code=do_init(base_path, secret_path))


if __name__ == '__main__':
    app()
