from pathlib import Path
from loguru import logger

import typer
from typing_extensions import Annotated as A
from typing import Callable, Union

from dataclasses import dataclass

from libraries.utilities import LocTask
from libraries.uetools import UELocTarget, UEProject, init_logging

# Run loc target-related actions. Reads config from base.config.yaml and command line.
#    Examples: targets.py replace source=Game target=Audio
#              targets.py add source=Game target=Audio
#              targets.py delete target=Audio locale=io
#              targets.py add target=Audio locale=io


@dataclass
class LocaleTask(LocTask):
    """
    Class to represent loc target related tasks

    Attributes
    ----------
    source_target
        Target to use as source (to add/copy locales from)
    loc_targets
        List of targets or a target to modify (add/remove/replace locales)
        Defaults to None to prevent unintentional modifications
    locales
        List of locales to use
    project_dir
        Project directory
        Defaults to ../../ based on the scripts being in Content/Python
    """

    source_target: str | None = None

    loc_targets: list[str] | str | None = None

    locales: list[str] | None = None

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    project_dir: str = '../../../'  # Absolute or relative to cwd
    engine_dir: str | None = None  # Absolute or relative to project_dir

    _ue_project: UEProject | None = None

    _source_target: UELocTarget | None = None
    _loc_targets: list[UELocTarget] | None = None

    _project_path: Path | None = None

    def available_targets(self) -> list[str]:
        if self._ue_project is None:
            logger.error('UEProject is not initialized.')
            return []

        return list(self._ue_project.loc_targets.keys())

    def available_locales(self, target: str) -> list[str]:
        if self._loc_targets is None:
            logger.error('UELocTargets are not initialized.')
            return []

        for t in self._loc_targets:
            if t.name == target:
                return sorted(t.get_current_locales())
        return []

    # This is not intended to be launched from loc-sync.py
    def get_task_list_from_arguments(self):
        return None

    def post_update(self) -> bool:
        super().post_update()

        if not self._ue_project:
            self._ue_project = UEProject(
                project_path=self.project_dir, engine_path=self.engine_dir
            )

        if self.source_target is not None:
            self._source_target = UELocTarget(
                self._ue_project.project_path, self.source_target
            )

        if isinstance(self.loc_targets, str):
            self.loc_targets = [self.loc_targets]

        if isinstance(self.loc_targets, list) and len(self.loc_targets) > 0:
            self._loc_targets = [
                UELocTarget(self._ue_project.project_path, target)
                for target in self.loc_targets
                if target in self.available_targets()
            ]

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

        if not isinstance(self.locales, list) or len(self.locales) == 0:
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


@dataclass
class ListTargets(LocaleTask):
    def run(self):
        if self.loc_targets is not None and len(self.loc_targets) > 0:
            logger.success(
                f'Locales for {self.loc_targets[0]}: {self.available_locales(self.loc_targets[0])}'
            )
            return True

        available_targets = self.available_targets()
        logger.success(f'Available targets: {", ".join(available_targets)}')
        return True


###############################################################
############################# CLI #############################
###############################################################

app = typer.Typer(
    rich_markup_mode='rich',
    add_completion=False,
    help="""
    Tool to manipulate locales across multiple localization targets in an Unreal project.
    Reads config from [blue]base.config.yaml[/] and overrides with command line parameters.

    [red]Notes:[/red]
    - If you [green]rename[/] a locale, import in UE first to preserve translations.
    - The tool does [blue]not[/] modify the [green].locmeta[/] files and does [blue]not[/] create or delete locale folders or files.
    - Remember to add and delete the relevant locale directories in Perforce as needed.
    """,
)


def check_and_split_comma_separated_list(
    number: int = 0,
) -> Callable[[str], list[str]]:
    """
    Parse the locales string into a tuple of (from_locale, to_locale).
    """

    def f(locales: str) -> list[str]:
        """
        Callback function to validate and parse the locales string.
        """
        parts: list[str] = [s.strip() for s in locales.split(',')]
        if number > 0 and len(parts) != number:
            raise typer.BadParameter(
                'Invalid locales format or quantity. '
                'Expected a comma-separated list (e.g., `en,de,...`) '
                f'of exactly {number} locales.',
            )
        return parts

    return f


@app.command('list')
def list_targets(
    target: A[
        Union[str, None],
        typer.Argument(
            help='Specify a target to list its locales, omit to list available targets instead.',
        ),
    ] = None,
):
    """
    List available localization targets or list locales for a specific target with [bold turquoise2]list <target>[/].
    """

    task = ListTargets()
    task.read_config(script=Path(__file__).name, logger=logger)
    task.loc_targets = target
    task.post_update()
    task.run()


@app.command()
def add(
    targets: A[
        str,
        typer.Option(
            '--targets',
            '-t',
            help='Target(s) to modify. Comma-separated list, e.g.: [green]Game,Data,Subtitles[/green]',
            show_default=False,
            callback=check_and_split_comma_separated_list(),
        ),
    ],
    locales: A[
        str,
        typer.Option(
            '--locales',
            '-l',
            help='Locale(s) to add. Comma-separated list, e.g.: [green]es,de,pt-BR[/green]',
            show_default=False,
            callback=check_and_split_comma_separated_list(),
        ),
    ],
):
    """
    Add locales to the specified targets.
    Note: Does [blue italic]not[/blue italic] create any locale directories.
    """
    task = AddLocales()
    task.read_config(script=Path(__file__).name, logger=logger)
    task.loc_targets = list(targets)
    task.locales = list(locales)
    task.post_update()
    task.run()

    logger.success('Locales added successfully.')


@app.command()
def delete(
    targets: A[
        str,
        typer.Option(
            '--targets',
            '-t',
            help='Target(s) to modify. Comma-separated list, e.g.: [green]Game,Data,Subtitles[/green]',
            show_default=False,
            callback=check_and_split_comma_separated_list(),
        ),
    ],
    locales: A[
        str,
        typer.Option(
            '--locales',
            '-l',
            help='Locale(s) to delete. Comma-separated list, e.g.: [green]es,de,pt-BR[/green]',
            show_default=False,
            callback=check_and_split_comma_separated_list(),
        ),
    ],
):
    """
    Delete locales from the specified targets.
    Note: Does [blue italic]not[/blue italic] delete any locale directories.
    """

    task = DeleteLocales()
    task.read_config(script=Path(__file__).name, logger=logger)
    task.loc_targets = list(targets)
    task.locales = list(locales)
    task.post_update()
    task.run()

    logger.success('Locales deleted successfully.')


@app.command()
def replace(
    source: A[
        str,
        typer.Option(
            '--source',
            '-s',
            help='Source target to copy locales from, e.g. [green]Game[/green]',
            show_default=False,
        ),
    ],
    targets: A[
        str,
        typer.Option(
            '--targets',
            '-t',
            help='Target(s) to replace the locales. Comma-separated list, e.g.: [green]Game,Data,Subtitles[/green]',
            show_default=False,
            callback=check_and_split_comma_separated_list(),
        ),
    ],
):
    """
    Replace locales in the specified target(s) with the locales from the source target.
    Note: Does [blue italic]not[/blue italic] create or delete any locale directories.
    """

    task = ReplaceLocales(loc_targets=targets)
    task.read_config(script=Path(__file__).name, logger=logger)
    task.source_target = source
    task.loc_targets = list(targets)
    task.post_update()
    task.run()


@app.command()
def rename(
    targets: A[
        str,
        typer.Option(
            '--targets',
            '-t',
            help='Target(s) to modify. Comma-separated list, e.g.: [green]Game,Data,Subtitles[/green]',
            show_default=False,
            callback=check_and_split_comma_separated_list(),
        ),
    ],
    locales: A[
        str,
        typer.Option(
            '--locales',
            '-l',
            help='Locale to rename and its new name, separated by a comma, e.g.: '
            '[green]pt-PT,pt-BR[/green] or [green]en-US,en[/green]',
            show_default=False,
            callback=check_and_split_comma_separated_list(2),
        ),
    ],
):
    """
    Rename a locale in the specified targets.
    Also renames the locale directory in the target folder(s) to preserve translations.
    [red]Important:[/red] Import translations in UE to preserve translations. Do not export or gather before that.
    """

    task = RenameLocales()
    task.read_config(script=Path(__file__).name, logger=logger)
    task.loc_targets = list(targets)
    task.locales = list(locales)
    task.post_update()
    task.run()

    logger.success('Locales renamed successfully.')


if __name__ == '__main__':
    app()
