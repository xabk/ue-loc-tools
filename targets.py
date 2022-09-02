import argparse
from pathlib import Path
from loguru import logger

from dataclasses import dataclass, field

from libraries.utilities import LocTask
from libraries.uetools import UELocTarget


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

    # This is not intended to be launched from loc-sync.py
    def get_task_list_from_arguments(self):
        return None

    def post_update(self) -> bool:
        super().post_update()

        if self.project_dir:
            self._project_path = Path(self.project_dir).resolve()
        else:
            self._project_path = Path(__file__).parent.parent.parent.resolve()

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

    def _perform_tasks(self, task_name: str, method):
        logger.info(f'Running {task_name} cultures in targets task.')

        if not self._loc_targets:
            logger.error('No targets to modify.')
            return None

        if self._source_target is not None:
            self.locales = self._source_target.get_current_locales()

        if type(self.locales) is not list or len(self.locales) == 0:
            logger.error('No locales specified.')

        logger.info(f'Targets to modify: {self.loc_targets}')
        logger.info(f'Locales to {task_name}: {self.locales}')

        rc = 0
        for target in self._loc_targets:
            rc += target.__getattribute__(method)(self.locales)

        return rc


@dataclass
class ReplaceLocales(LocaleTask):
    def run(self):
        return self._perform_tasks('replace', UELocTarget.replace_all_locales.__name__)


@dataclass
class AddLocales(LocaleTask):
    def run(self):
        return self._perform_tasks('add', UELocTarget.add_locales.__name__)


@dataclass
class DeleteLocales(LocaleTask):
    def run(self):
        return self._perform_tasks('delete', UELocTarget.remove_locales.__name__)


@dataclass
class RenameLocales(LocaleTask):
    def run(self):
        return self._perform_tasks('rename', UELocTarget.rename_locale.__name__)


LOC_TARGET_ACTIONS = {
    'add': AddLocales,
    'replace': ReplaceLocales,
    'delete': DeleteLocales,
    'rename': RenameLocales,
}


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
        help='''Action to perform: `replace`, `add`, `delete`, `rename`\n
        `replace` and `add` require either -source and -targets or -targets and -locales\n
        `delete` requires -targets and -locales\n
        `rename` requires -targets and exactly 2 locales in -locales: old and new name''',
    )

    parser.add_argument(
        '-source',
        '-s',
        default=None,
        type=str,
        help='Source target to use for `replace` and `add` tasks. Defaults to `Game`',
    )

    parser.add_argument(
        '-targets',
        '-t',
        default=None,
        nargs='*',
        help='Loc targets to modify, a space-separated list of target names',
    )

    parser.add_argument(
        '-locales',
        '-l',
        default=None,
        nargs='*',
        help='Locales to add/replace/delete, a space-separated list of locale names',
    )

    args, unknown = parser.parse_known_args()

    if args.action is None or args.action not in LOC_TARGET_ACTIONS:
        logger.error('Argument error: action not supported')
        return None

    if args.targets is None or type(args.targets) is not list or len(args.targets) == 0:
        print(type(args.targets))
        logger.error('Argument error: targets not specified')
        return None

    if args.action == 'delete':
        if (
            args.locales is None
            or type(args.locales) is not list
            or len(args.locales) == 0
        ):
            logger.error('Argument error: no locales for delete action')
            return None

    if args.action == 'rename':
        if (
            args.locales is None
            or type(args.locales) is not list
            or len(args.locales) != 2
        ):
            logger.error(
                'Argument error: no or wrong number of locales for rename action'
            )
            return None

    if args.source is None:
        if (
            args.locales is None
            or type(args.locales) is not list
            or len(args.locales) == 0
        ):
            logger.error(
                'Argument error: no locales and no source for add or replace action'
            )
            return None

    if args.locales is not None and args.source is not None and args.action != 'delete':
        logger.error(
            'Argument error: both source and locales specified, specify only one'
        )
        return None

    logger.info(args)

    return args


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
    if params == None:
        logger.error('No parameters parsed. Aborting.')
        return 1

    task = LOC_TARGET_ACTIONS[params.action](
        params.source, params.targets, params.locales
    )

    task.read_config(Path(__file__).name, logger)

    returncode = task.run()

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
