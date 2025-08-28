"""Typer-based CLI replicating prior argparse interface for loc-sync.

Usage:
    uv run loc-sync.py                 -> interactive task list selection
    uv run loc-sync.py MYLIST          -> run task list MYLIST
    uv run loc-sync.py -u MYLIST       -> unattended run
    uv run loc-sync.py --list-tasks    -> list registered tasks
"""

import typer
from typing import Any, Optional, cast
from typing_extensions import Annotated as A
from timeit import default_timer as timer
from loguru import logger

from libraries.utilities import init_logging
from libraries.task_runner import (
    TaskRunner,
    DEFAULT_BASE_CONFIG,
    DEFAULT_SECRET_CONFIG,
)

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    help='Run localization synchronization tasks.',
)


def _build_runner(
    base_cfg: str, secret_cfg: str, unattended: bool, debug: bool
) -> TaskRunner:
    runner = TaskRunner()
    runner.unattended = unattended
    runner.debug = debug
    runner.load_config(base_cfg, secret_cfg)
    return runner


@app.command()
def run(
    tasklist: A[
        Optional[str], typer.Argument(help='Task list to run.', show_default=False)
    ] = None,
    unattended: A[
        bool,
        typer.Option('--unattended', '-u', help='Run without prompts', is_flag=True),
    ] = False,
    config: A[
        str, typer.Option('--config', '-c', help='Base config file')
    ] = DEFAULT_BASE_CONFIG,
    secret: A[
        str, typer.Option('--secret', '-s', help='Secret config file')
    ] = DEFAULT_SECRET_CONFIG,
    list_tasks: A[
        bool, typer.Option('--list-tasks', help='List available tasks', is_flag=True)
    ] = False,
    debug: A[
        bool, typer.Option('--debug', help='Enable debug logging', is_flag=True)
    ] = False,
):
    """Primary entry point (no subcommand). Future subcommands can be added without changing usage."""
    init_logging(debug)
    try:
        runner = _build_runner(config, secret, unattended, debug)
    except FileNotFoundError as e:
        logger.error(str(e))
        raise typer.Exit(code=1)

    if list_tasks:
        logger.info('Available tasks:')
        items = runner.list_task_metadata()
        if not items:
            logger.warning('No tasks available - check configuration')
            raise typer.Exit(code=1)
        for script_name, task_name, task_description in items:
            logger.info(f'  {script_name}')
            logger.info(f'    Name: {task_name}')
            logger.info(f'    Description: {task_description}')
            logger.info('')
        raise typer.Exit(code=0)

    if tasklist:
        runner.task_list_name = tasklist
    else:
        try:
            runner.task_list_name = runner.get_task_list_from_user()
        except (ValueError, KeyboardInterrupt) as e:
            logger.error(str(e))
            raise typer.Exit(code=1)

    if runner.task_list_name not in runner.config:
        logger.error(f"Task list '{runner.task_list_name}' not found in configuration")
        raise typer.Exit(code=1)

    tasks = cast(list[dict[str, Any]], runner.config[runner.task_list_name])
    logger.info(f'Executing task list: {runner.task_list_name}')
    total_start = timer()
    results = runner.run_task_list(tasks)
    total_duration = timer() - total_start
    code = runner.summarize(results, total_duration)
    raise typer.Exit(code=code)


def main():  # external entry point if imported
    app()


if __name__ == '__main__':
    app()
