"""CLI entry point for localization task synchronization.

This file now delegates all task running logic to `libraries.task_runner` in
order to keep the script lean. Existing imports / usage of TaskRunner should
continue to work (TaskRunner symbol is re-exported for backwards compatibility).
"""

import sys
import argparse
from typing import Any, cast
from timeit import default_timer as timer
from loguru import logger

from libraries.utilities import init_logging
from libraries.task_runner import (
    TaskRunner,
    DEFAULT_BASE_CONFIG,
    DEFAULT_SECRET_CONFIG,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="""
        Run localization tasks based on configuration
        Example: uv run loc-sync.py"""
    )
    parser.add_argument(
        'tasklist', type=str, nargs='?', help='Task list to run from base.config.yaml'
    )
    parser.add_argument(
        '-u', '--unattended', action='store_true', help='Run without user interaction'
    )
    parser.add_argument(
        '-c',
        '--config',
        type=str,
        help=f'Base config file path (default: {DEFAULT_BASE_CONFIG})',
    )
    parser.add_argument(
        '-s',
        '--secret',
        type=str,
        help=f'Secret config file path (default: {DEFAULT_SECRET_CONFIG})',
    )
    parser.add_argument(
        '--list-tasks', action='store_true', help='List available tasks with metadata'
    )
    parser.add_argument(
        '--debug', action='store_true', help='Enable debug logging and exceptions'
    )
    return parser.parse_args()


def main():
    init_logging()

    args = parse_arguments()

    runner = TaskRunner()

    # Load config early for discovery
    try:
        runner.load_config(
            args.config or DEFAULT_BASE_CONFIG, args.secret or DEFAULT_SECRET_CONFIG
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    if args.list_tasks:
        logger.info('Available tasks:')
        task_items = runner.list_task_metadata()
        if not task_items:
            logger.warning('No tasks available - check your configuration')
            return 1
        for script_name, task_name, task_description in task_items:
            logger.info(f'  {script_name}')
            logger.info(f'    Name: {task_name}')
            logger.info(f'    Description: {task_description}')
            logger.info('')
        return 0

    runner.unattended = args.unattended
    runner.debug = args.debug

    if args.tasklist:
        runner.task_list_name = args.tasklist
    else:
        try:
            runner.task_list_name = runner.get_task_list_from_user()
        except (ValueError, KeyboardInterrupt) as e:
            logger.error(str(e))
            return 1

    if runner.task_list_name not in runner.config:
        logger.error(f"Task list '{runner.task_list_name}' not found in configuration")
        return 1

    tasks = cast(list[dict[str, Any]], runner.config[runner.task_list_name])

    logger.info(f'Executing task list: {runner.task_list_name}')
    total_start = timer()
    results = runner.run_task_list(tasks)
    total_duration = timer() - total_start

    return runner.summarize(results, total_duration)


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
