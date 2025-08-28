"""Task runner library extracted from loc-sync.

This module provides the TaskRunner class and related constants for executing
localization tasks defined in configuration files. It supports two execution
modes:

- Registered tasks: Executed via direct import (fast, preferred)
- Unregistered tasks: Executed via subprocess (legacy / Unreal Engine tasks)
"""

import importlib.util
import importlib
from pathlib import Path
from timeit import default_timer as timer
from dataclasses import asdict, fields
from typing import Any
import yaml
from loguru import logger

from libraries.utilities import LocTask

# Tasks module (used to import tasks as {TASKS_MODULE}.{task_name})
TASKS_MODULE = 'tasks'

SCRIPT_DIR = 'scripts'

LOG_TO_SKIP = ['LogLinker: ']

# Task list filtering
CONFIG_NON_TASK_SECTIONS = {'crowdin', 'parameters', 'script-parameters', 'tasks'}

# Configuration keys
CONFIG_KEY_STOP_ON_ERRORS = 'stop-on-errors'
CONFIG_KEY_USE_UNREAL = 'use-unreal'

# User interaction
EXIT_COMMANDS = {'q', 'Q', 'quit', 'Quit', 'Exit', 'exit'}

# Console color codes
COLOR_GREEN = '\033[92m'
COLOR_YELLOW = '\033[93m'
COLOR_DARK_GRAY = '\033[90m'
COLOR_RESET = '\033[0m'

# Default configuration file names
DEFAULT_BASE_CONFIG = 'base.config.yaml'
DEFAULT_SECRET_CONFIG = 'crowdin.config.yaml'


class TaskRunner:
    """Unified task runner with dual execution modes: import and subprocess.

    Responsibilities:
    - Load and merge configuration files
    - Discover and register available tasks
    - Create configured task instances
    - Execute tasks sequentially with summary output
    - Provide interactive task list selection unless unattended
    """

    def __init__(self):
        self.config: dict[str, dict] = {}
        self.base_config_path: str | None = None
        self.secret_config_path: str | None = None
        self.task_list_name: str | None = None
        self.unattended: bool = False
        self.debug: bool = False
        self._task_registry: dict[str, type[LocTask]] = {}

    # -------------------- Configuration & Registration -------------------- #
    def _register_available_tasks(self):
        if not self.config or 'tasks' not in self.config:
            logger.warning('No tasks configured - task registry will be empty')
            return
        task_config = self.config['tasks']
        logger.info(f'Discovering {len(task_config)} configured tasks...')
        for task_name, task_info in task_config.items():
            if not self._validate_task_config(task_name, task_info):
                continue
            try:
                module_name = task_info['module']
                class_name = task_info['class']
                logger.debug(
                    f'Processing task {task_name}: module={module_name}, class={class_name}'
                )
                # Import logic: prefer package modules under tasks.
                if module_name.startswith(f'{TASKS_MODULE}.'):
                    module = importlib.import_module(module_name)
                    logger.debug(f'Imported module: {module_name}')
                else:
                    file_path = task_info.get('file', f'{module_name}.py')
                    logger.debug(
                        f'Using legacy file-based import for {module_name} from {file_path}'
                    )
                    spec = importlib.util.spec_from_file_location(
                        module_name, file_path
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)  # type: ignore[attr-defined]
                        logger.debug(
                            f'Imported legacy module: {module_name} from {file_path}'
                        )
                    else:
                        raise ImportError(f'Could not load spec for {file_path}')
                if hasattr(module, class_name):
                    task_class = getattr(module, class_name)
                    if not issubclass(task_class, LocTask):
                        logger.warning(
                            f'Task class {class_name} is not a LocTask subclass'
                        )
                        continue
                    self._task_registry[task_name] = task_class
                    logger.debug(
                        f'Registered task: {task_name} -> {module_name}.{class_name}'
                    )
                else:
                    logger.warning(
                        f'Class {class_name} not found in module {module_name}'
                    )
            except Exception as e:
                logger.warning(f'Could not import task {task_name}: {e}')

        if len(self._task_registry) == len(task_config):
            logger.success(
                f'All tasks ({len(self._task_registry)}) registered successfully'
            )
        else:
            logger.warning(
                f'Registered only {len(self._task_registry)}/{len(task_config)} tasks'
            )

    def _validate_task_config(self, task_name: str, task_info: dict[str, Any]) -> bool:
        for field in ['module', 'class']:
            if field not in task_info:
                logger.error(f'Task {task_name} missing required field: {field}')
                return False
        return True

    def load_config(
        self,
        base_config: str = DEFAULT_BASE_CONFIG,
        secret_config: str = DEFAULT_SECRET_CONFIG,
    ) -> dict[str, Any]:
        self.base_config_path = base_config
        self.secret_config_path = secret_config

        if not Path(base_config).exists():
            raise FileNotFoundError(f'Base config file {base_config} not found')

        with open(base_config, 'r', encoding='utf-8') as f:
            config: dict[str, dict] = yaml.safe_load(f)

        if not Path(secret_config).exists():
            raise FileNotFoundError(f'Secret config file {secret_config} not found')

        with open(secret_config, 'r', encoding='utf-8') as f:
            secret_cfg = yaml.safe_load(f)

        if 'crowdin' in secret_cfg:
            config.setdefault('crowdin', {}).update(secret_cfg['crowdin'])

        self.config = config
        self._task_registry.clear()
        self._register_available_tasks()

        return config

    # -------------------- Task Creation & Metadata -------------------- #
    def _apply_config_to_task(self, task: LocTask, config_dict: dict[str, Any]):
        task_fields = {f.name for f in fields(task)}
        for key, value in config_dict.items():
            if not key.startswith('_') and key in task_fields:
                setattr(task, key, value)

    def create_task_instance(
        self, script_name: str, task_config: dict[str, Any]
    ) -> LocTask:
        task_class = self._task_registry.get(script_name)
        if not task_class:
            raise ValueError(f"Task '{script_name}' not found in registry")
        task = task_class()
        if 'crowdin' in self.config:
            self._apply_config_to_task(task, self.config['crowdin'])
        if 'parameters' in self.config:
            self._apply_config_to_task(task, self.config['parameters'])
        if (
            'script-parameters' in self.config
            and script_name in self.config['script-parameters']
        ):
            self._apply_config_to_task(
                task, self.config['script-parameters'][script_name]
            )
        if 'script-parameters' in task_config:
            self._apply_config_to_task(task, task_config['script-parameters'])
        task.post_update()
        return task

    def get_task_metadata(self, script_name: str) -> tuple[str, str]:
        """Get metadata for a specific task."""
        task_class = self._task_registry.get(script_name)
        if not task_class:
            return script_name, f'Unknown task: {script_name}'
        temp_task = task_class()
        name = getattr(temp_task, 'name', script_name)
        description = getattr(temp_task, 'description', f'Task: {script_name}')
        return name, description

    def list_task_metadata(self, *, sort: bool = True) -> list[tuple[str, str, str]]:
        """Return metadata for all registered tasks.

        Each tuple contains: (script_name, task_name, task_description).

        Parameters:
            sort: Whether to sort results by script_name (default True).
        """
        items: list[tuple[str, str, str]] = []
        for script_name in self._task_registry.keys():
            task_name, task_description = self.get_task_metadata(script_name)
            items.append((script_name, task_name, task_description))
        if sort:
            items.sort(key=lambda t: t[0])
        return items

    # -------------------- Execution -------------------- #
    def execute_task(self, task_config: dict[str, Any]) -> tuple[bool, float, str]:
        script_name = task_config['script']

        start_time = timer()

        if script_name in self._task_registry:
            try:
                logger.info(f'Executing {script_name} via import')
                task = self.create_task_instance(script_name, task_config)
                cfg_info = asdict(task)
                cfg_info.pop('token', None)
                logger.info(f'Config: {cfg_info}')
                success = task.run()
                duration = timer() - start_time
                return success, duration, 'Import execution'
            except Exception as e:
                duration = timer() - start_time
                logger.error(f'Import execution failed for {script_name}: {e}')
                if self.debug:
                    raise e
                return False, duration, f'Import execution failed: {e}'

        # Task not in registry, executing the old way, via subprocess
        logger.info(f'Executing unregistered task {script_name} via subprocess')
        return self._execute_via_subprocess(task_config, start_time)

    def _execute_via_subprocess(
        self, task_config: dict[str, Any], start_time: float
    ) -> tuple[bool, float, str]:
        import subprocess as subp

        script_name = f'{SCRIPT_DIR}/{task_config["script"]}.py'
        if task_config.get('unreal'):
            return self._execute_ue_task(task_config, start_time)

        try:
            result = subp.run(
                ['uv', 'run', script_name, self.task_list_name or ''],
                capture_output=True,
                text=True,
            )
            duration = timer() - start_time
            success = result.returncode == 0
            if not success:
                logger.error(f'Subprocess stderr: {result.stderr}')
            return success, duration, f'Subprocess return code: {result.returncode}'
        except Exception as e:
            duration = timer() - start_time
            if self.debug:
                raise e
            return False, duration, f'Subprocess execution failed: {e}'

    def _execute_ue_task(
        self, task_config: dict[str, Any], start_time: float
    ) -> tuple[bool, float, str]:
        import subprocess as subp

        try:
            ue_params = self.config.get('parameters', {})

            ue_cwd = Path(ue_params['engine_dir']).resolve().absolute()

            project_path = Path(ue_params.get('project_dir')).resolve().absolute()

            script_path = Path().absolute()

            uprojects = project_path.glob('*.uproject')
            if uprojects:
                project_path = next(uprojects)
            else:
                uprojects = ue_cwd.glob('*.uproject')
                if uprojects:
                    project_path = next(uprojects)

            ue_executable = ue_cwd / ue_params['unreal_binary']

            if not ue_executable.is_file() and not ue_executable.exists():
                raise ValueError(
                    f"UE editor path does not exist or isn't a file: {ue_cwd}"
                )

            if not project_path.is_file() and not project_path.exists():
                raise ValueError(
                    f"Project path does not exist or isn't a file: {project_path}"
                )

            ue_script = script_path / f'{SCRIPT_DIR}/{task_config["script"]}.py'
            ue_script = ue_script.as_posix()

            cmd = [
                ue_executable,
                project_path,
                f'-run="{ue_script}"',
                '-unattended',
                '-stdout',
                '-NullRHI',
            ]

            logger.info('Running UE command: ' + ' '.join(str(x) for x in cmd))

            with subp.Popen(
                [
                    ue_executable,
                    project_path,
                    '-run=pythonscript',
                    f'-script="{ue_script}"',
                    '-SCCProvider=None',
                    '-Unattended',
                    '-Log="LocSync.log"',
                ],
                stdout=subp.PIPE,
                stderr=subp.STDOUT,
                cwd=ue_cwd,
                universal_newlines=True,
            ) as process:
                while True:
                    if not process.stdout:
                        break
                    for line in process.stdout:
                        skip = False
                        for item in LOG_TO_SKIP:
                            if item in line:
                                skip = True
                                break

                        if skip:
                            continue

                        if 'Error: ' in line:
                            logger.error(f'| UE | {line.strip()}')
                        elif 'Warning: ' in line:
                            logger.warning(f'| UE | {line.strip()}')
                        else:
                            logger.info(f'| UE | {line.strip()}')
                    if process.poll() is not None:
                        break
                returncode = process.returncode

            duration = timer() - start_time
            success = returncode == 0
            if not success:
                logger.error(f'UE commandlet returned an error! {returncode}')
            return success, duration, f'UE commandlet return code: {returncode}'
        except Exception as e:
            duration = timer() - start_time
            if self.debug:
                raise e
            return False, duration, f'UE task execution failed: {e}'

    # -------------------- Helpers -------------------- #
    def _should_skip_task(self, task_config: dict[str, Any]) -> bool:
        if task_config.get('skip', False):
            return True
        if task_config.get('unreal', False):
            if not self.config['parameters'].get(CONFIG_KEY_USE_UNREAL, False):
                logger.info(
                    f"Skipping Unreal Engine task '{task_config['script']}' because Unreal Engine is not enabled in configuration."
                )
                return True
            return False
        return False

    def get_task_list_from_user(self) -> str:
        task_lists = [t for t in self.config if t not in CONFIG_NON_TASK_SECTIONS]
        if not task_lists:
            raise ValueError('No task lists found in configuration')
        if self.unattended:
            raise ValueError('Task list must be specified in unattended mode')
        task_list = ''
        print('\nAvailable task lists from base.config.yaml:\n')
        for i, task in enumerate(task_lists, start=1):
            lines = task.split('\n')
            print(f'{COLOR_GREEN}{i:>2d}.{COLOR_RESET} {lines[0]}')
            for line in lines[1:]:
                print(f'\t{COLOR_DARK_GRAY}{line}{COLOR_RESET}')
        while not task_list:
            choice = ''
            try:
                choice = input('Select task list (number or name): ').strip()
                if choice in task_lists:
                    task_list = choice
                idx = int(choice) - 1
                if 0 <= idx < len(task_lists):
                    task_list = task_lists[idx]
            except ValueError:
                if choice in EXIT_COMMANDS:
                    print('\nTask selection cancelled by user.')
                    quit(0)
                print('Invalid input. Please try again.')
            except KeyboardInterrupt:
                print('\nTask selection cancelled by user.')
                quit(0)
        if task_list:
            print(f'\nSelected task list: {COLOR_GREEN}{task_list}{COLOR_RESET}:')
            update_warning = False
            for task in self.config[task_list]:
                if 'updates-source' in task:
                    print(f'{COLOR_YELLOW}{task}{COLOR_RESET}')
                    update_warning = True
                else:
                    print(task)
            if update_warning:
                print(
                    f'\n{COLOR_YELLOW}Warning: This task list contains tasks that update the source files.{COLOR_RESET}'
                )
            conf = input(
                f'\nEnter Y to execute task list {task_list.splitlines()[0].strip()}. Anything else to go back to task list selection... '
            )
            if conf != 'Y' and conf != 'y':
                task_list = None
        return task_list

    # -------------------- Orchestration -------------------- #
    def run_task_list(
        self, tasks: list[dict[str, Any]]
    ) -> list[tuple[dict[str, Any], str, str]]:
        results: list[tuple[dict[str, Any], str, str]] = []
        for i, task_config in enumerate(tasks, 1):
            script_name = task_config['script']
            task_name, task_description = self.get_task_metadata(script_name)
            logger.info(f'Task {i}/{len(tasks)}: {task_name}')
            logger.info(f'  Description: {task_description}')
            logger.info(f'  Script: {script_name}')
            if self._should_skip_task(task_config):
                results.append((task_config, 'Skipped', '—'))
                continue
            success, duration, _ = self.execute_task(task_config)
            status = 'Success' if success else 'Failed'
            results.append((task_config, f'{duration:.2f}s', status))
            if not success and self.config.get('parameters', {}).get(
                CONFIG_KEY_STOP_ON_ERRORS, True
            ):
                logger.error(f'Stopping due to error in task {i}')
                break
        return results

    def summarize(
        self, results: list[tuple[dict[str, Any], str, str]], total_duration: float
    ) -> int:
        logger.info(f'\nTask execution summary (Total: {total_duration:.2f}s):')
        for task_config, duration, status in results:
            script_name = task_config['script']
            task_name, _ = self.get_task_metadata(script_name)
            logger.info(f'  {task_name} ({script_name}): {duration} - {status}')
        return 0 if all(r[2] in ['Success', 'Skipped'] for r in results) else 1


__all__ = [
    'TaskRunner',
    'CONFIG_NON_TASK_SECTIONS',
    'EXIT_COMMANDS',
    'COLOR_GREEN',
    'COLOR_YELLOW',
    'COLOR_DARK_GRAY',
    'COLOR_RESET',
    'DEFAULT_BASE_CONFIG',
    'DEFAULT_SECRET_CONFIG',
    'CONFIG_KEY_STOP_ON_ERRORS',
    'CONFIG_KEY_USE_UNREAL',
]
