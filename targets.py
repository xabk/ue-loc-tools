import argparse
from pathlib import Path
from typing import NamedTuple
from loguru import logger

from dataclasses import dataclass, field

from libraries.utilities import LocTask
from libraries.uetools import UELocTarget

LOC_TARGET_ACTIONS = ['add', 'replace', 'delete']


class LocTargetParameters(NamedTuple):
    action: str
    source: str
    targets: list[str]
    locales: list[str]


@dataclass
class LocaleTask(LocTask):
    '''
    Class to represent loc target related tasks

    ...

    Attributes
    ----------
    source_target
        Target to use as source (e.g., to add/copy locales from)
    loc_targets
        List of targets or a target to modify (add/remove/replace locales)
        Defaults to None to prevent unintentional modifications
    project_dir
        Project directory
        Defaults to ../../ based on the scripts being in Content/Python
    '''

    source_target: str = None

    loc_targets: list[str] or str = None

    locales: list[str] = None

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    project_dir: str = '../../'

    _source_target: UELocTarget = None
    _loc_targets: list[UELocTarget] = None

    _project_path: Path = None

    def post_update(self) -> bool:
        super().post_update()

        if self.project_dir:
            self._project_path = Path(self.project_dir).resolve()
        else:
            self._project_path = self._project_path.parent.resolve()

        if not (
            (self._project_path / 'Content').exists()
            and (self._project_path / 'Config').exists()
        ):
            logger.error(
                f'{self._project_path} doesn\'t '
                'look like an Unreal project directory'
            )

        logger.info(f'Project path: {self._project_path}.')

        if self.source_target is not None:
            self._source_target = UELocTarget(self._project_path, self.source_target)
            logger.info(f'Source target: {self.source_target}.')
        else:
            logger.info(f'No source target specified.')

        if type(self.loc_targets) is str:
            self.loc_targets = [self.loc_targets]

        if type(self.loc_targets) is list and len(self.loc_targets) > 0:
            self._loc_targets = [
                UELocTarget(self._project_path, target) for target in self.loc_targets
            ]
            logger.info(f'Loc targets to modify: {self.loc_targets}.')
        else:
            logger.error(f'No loc targets to modify specified.')

        return True

    def run(self):
        pass


@dataclass
class ReplaceLocales(LocaleTask):
    pass


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='''
    Run loc target-related actions. Reads config from base.config.yaml and command line.
    Examples: targets.py replace source=Game target=Audio
              targets.py add source=Game target=Audio
              targets.py delete target=Audio locale=io
              targets.py add target=Audio locale=io'''
    )

    parser.add_argument(
        'action',
        nargs='?',
        choices=LOC_TARGET_ACTIONS,
        help='''Action to perform: `replace`, `add`, or `delete`
        Replace and add require either -source and -targets or -targets and -locales
        Delete accepts -targets and -locales''',
    )

    parser.add_argument(
        '-source',
        default=None,
        nargs=1,
        help='Source target to use for `replace` and `add` tasks. Defaults to `Game`',
    )

    parser.add_argument(
        '-targets',
        default=None,
        nargs='*',
        help='Loc targets to modify, a space-separated list of target names',
    )

    parser.add_argument(
        '-locales',
        default=None,
        nargs='*',
        help='Locales to add/replace/delete, a space-separated list of locale names',
    )

    args, unknown = parser.parse_known_args()

    print(args)

    if args.action is None or args.action not in LOC_TARGET_ACTIONS:
        logger.error('Argument error: action not supported')
        return None

    if args.targets is None or type(args.targets) is not list:
        print(type(args.targets))
        logger.error('Argument error: targets not specified')
        return None

    if args.action == 'delete':
        if args.locales is None or type(args.locales) is not list:
            logger.error('Argument error: no locales or error for delete action')
            return None

    if args.source is None:
        if args.locales is None or type(args.locales) is not list:
            logger.error(
                'Argument error: no locales and no source for add or replace action'
            )
            return None

    if args.locales is not None and args.source is not None and args.action != 'delete':
        logger.error(
            'Argument error: both source and locales specified, specify only one'
        )
        return None

    parameters = LocTargetParameters(
        args.action, args.source, args.targets, args.locales
    )

    logger.info(parameters)

    return parameters


def main():

    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
    )

    logger.info('')
    logger.info('--- Unreal gather text commandlet script ---')
    logger.info('')

    params = parse_arguments()

    task = LocaleTask('Game', 'Audio')
    task.read_config(Path(__file__).name, logger)

    returncode = 0  # task.run_tasks()

    if returncode == 0:
        logger.info('')
        logger.info('--- Unreal gather text commandlet script end ---')
        logger.info('')
        return 0

    logger.error('Error occured, please see the Content/Python/Logs/locsync.log')
    return 1


# Run the script if the isn't imported
if __name__ == "__main__":
    main()
