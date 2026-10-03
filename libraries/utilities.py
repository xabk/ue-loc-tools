# Holds utility functions used across scripts:
# read and update configs, etc.

import stat
import sys
from datetime import datetime
from pathlib import Path
import yaml
from dataclasses import asdict, dataclass, fields
import argparse
from loguru import logger

BASE_CFG = 'base.config.yaml'
SECRET_CFG = 'crowdin.config.yaml'

BASE_SECTION = 'parameters'
SCRIPT_SECTION = 'script-parameters'

# Paths for default UE folder structure:
# (Engine Root)/[Games]/(GameName)/Content/Python/loc-tools...
# Assuming the scripts are in Python/loc-tools directory where they should be
DEF_CONTENT_PATH = Path('../../')
DEF_PROJECT_PATH = Path('../../../')
DEF_ENGINE_ROOT = Path('../../../../../')
DEF_ENGINE_CMD = DEF_ENGINE_ROOT / 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'  # UE5
DEF_ENGINE_DIR = DEF_ENGINE_ROOT / 'Engine/Binaries/Win64/'


def remove_read_only(func, path, _exc):
    """onexc handler for shutil.rmtree: a Perforce file that is not checked
    out is read-only, and rmtree cannot delete it until the flag is off."""
    Path(path).chmod(stat.S_IWRITE)
    func(path)


LOG_DIR = Path('logs')
LOGS_TO_KEEP = 20


def prune_logs(log_dir: Path, keep: int) -> None:
    """Delete all but the newest `keep` run logs. The names sort by start time.
    A log another run still has open can't be deleted, and stays."""
    logs = sorted(log_dir.glob('locsync_*.log'))
    for old in logs[: max(len(logs) - keep, 0)]:
        try:
            old.unlink()
        except OSError:
            pass


def init_logging(verbose: bool = False) -> Path:
    """One log file per launch, named by its start time, and the newest
    LOGS_TO_KEEP kept. A run's log is never renamed while it is open.
    Returns the path of this launch's log."""
    logger.remove()
    level = 'TRACE' if verbose else 'INFO'
    # Redirected stdout defaults to the locale encoding, and UE logs CJK
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    logger.add(
        sys.stdout,
        format='<green>{time:HH:mm:ss}</green> '
        '<level>{level:1.1}</level> '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line:3d}</cyan> '
        '<level>{message}</level>',
        level=level,
        filter=lambda r: not r['extra'].get('log_only'),
    )
    LOG_DIR.mkdir(exist_ok=True)
    # Room for this launch's file among the ones kept
    prune_logs(LOG_DIR, LOGS_TO_KEEP - 1)
    log_file = LOG_DIR / f'locsync_{datetime.now().astimezone():%Y-%m-%d_%H-%M-%S}.log'
    logger.add(
        str(log_file),
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='TRACE',
        encoding='utf-8',
        filter=lambda r: not r['extra'].get('console_only'),
    )
    return log_file.resolve()


@dataclass
class LocTask:
    # TODO: Add some default parameters? Paths?

    # Secret config
    base_cfg: str = BASE_CFG
    secret_cfg: str = SECRET_CFG

    def post_update(self) -> None:
        """
        Called after you initiate or update the paramaters from config files.

        Override this to recalculate any config values
        that depend on other config values. E.g., if you want
        to format a path based on a base path or
        create regex based on a pattern and other value.
        """
        pass

    # TODO Remove when we switch to imports
    def get_task_list_from_arguments(self) -> str:
        parser = argparse.ArgumentParser(
            description="""
            For defaults: <task_file>.py
            For task-specific settings: <task_file>.py task_list_name
            """
        )

        parser.add_argument(
            'tasklist',
            type=str,
            nargs='?',
            help='Task list to run from base.config.yaml',
        )

        tasklist = ''
        try:
            tasklist = parser.parse_known_args()[0].tasklist
        except Exception:
            ...

        return tasklist

    # TODO Modify to accept config as dict when we switch to imports
    def read_config(
        self,
        script: str,
        base_config: str | None = None,
        secret_config: str | None = None,
        update: bool = True,
    ) -> None:
        if not base_config:
            base_config = self.base_cfg
            logger.info(f'Using default base config: {base_config}')
        if script.endswith('.py'):
            script = script.rpartition('.')[0]

        task_list = self.get_task_list_from_arguments()

        # Use defaults and return if base config does not exist
        if not base_config or not Path(base_config).exists():
            logger.warning('No config found! Working with defaults.')
            return

        with open(base_config, mode='r', encoding='utf-8') as f:
            yaml_config = yaml.safe_load(f)

        # Task modules are named test_lang.py, their config sections test-lang
        if script not in (yaml_config.get(SCRIPT_SECTION) or {}):
            script = script.replace('_', '-')

        # Update config from the base section
        updated = False
        if BASE_SECTION in yaml_config:
            for key, value in yaml_config[BASE_SECTION].items():
                if not key.startswith('_') and key in [
                    field.name for field in fields(self)
                ]:
                    updated = True
                    self.__setattr__(key, value)
            if updated:
                logger.info(
                    f'Updated parameters from the `{BASE_SECTION}` '
                    'section of base.config.yaml.'
                )

        # Update config from the defaults section of base config
        updated = False
        if script in (yaml_config.get(SCRIPT_SECTION) or {}):
            for key, value in (yaml_config[SCRIPT_SECTION][script] or {}).items():
                if not key.startswith('_') and key in [
                    field.name for field in fields(self)
                ]:
                    updated = True
                    self.__setattr__(key, value)
            if updated:
                logger.info(
                    f'Updated parameters from the global `{SCRIPT_SECTION}` '
                    'section of base.config.yaml.'
                )

        # Update config with overrides from the 'task list' section of base config
        updated = False
        if task_list and task_list in yaml_config:
            task_id = [
                i
                for i, val in enumerate(yaml_config[task_list])
                if val['script'] == script
            ]
            if task_id and SCRIPT_SECTION in yaml_config[task_list][task_id[0]]:
                for key, value in yaml_config[task_list][task_id[0]][
                    SCRIPT_SECTION
                ].items():
                    if not key.startswith('_') and key in [
                        field.name for field in fields(self)
                    ]:
                        updated = True
                        self.__setattr__(key, value)
                if updated:
                    logger.info(
                        f'Updated parameters from {task_list} / `{SCRIPT_SECTION}` '
                        'section of base.config.yaml.'
                    )

        if not secret_config:
            secret_config = self.secret_cfg

        # Update Crowdin API config if exists
        if secret_config and Path(secret_config).exists():
            with open(secret_config, mode='r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)

            for key, value in yaml_config['crowdin'].items():
                if not key.startswith('_') and key in [
                    field.name for field in fields(self)
                ]:
                    self.__setattr__(key, value)

        if 'token' in fields(self) and not self.token:
            logger.error('API token parameter exists but not set!')

        # Run post_update to compute derivative parameters, if any
        if update:
            self.post_update()

        cfg_info = asdict(self)
        cfg_info.pop('token', None)
        logger.info(f'Config: {cfg_info}')

        return
