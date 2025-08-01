import sys
import argparse
import subprocess as subp

from libraries.utilities import init_logging

err = None
# Run with -setup to install required modules
# (based on requirements.txt)
# (generated with pipreqs .)

try:
    import yaml
    from pathlib import Path
    from timeit import default_timer as timer
    import re
    from loguru import logger
except Exception as error:
    err = error


BASE_CFG = 'base.config.yaml'
SECRET_CFG = 'crowdin.config.yaml'

CFG_SECTIONS = ['crowdin', 'parameters', 'script-parameters']

LOG_TO_SKIP = ['LogLinker: ']


def read_config_files(base_cfg=BASE_CFG, secret_cfg=SECRET_CFG):
    """
    Reads the base config file and the secret config file.
    Returns a dict with the config data.

    Always overwrites the base config with the secret config,
    to discourage storing secrets in the base config file.
    """

    if not base_cfg:
        base_cfg = BASE_CFG

    if not secret_cfg:
        secret_cfg = SECRET_CFG

    if not Path(base_cfg).exists():
        logger.error(f'Base config file {base_cfg} not found.')
        raise FileNotFoundError(
            f'Base config file {base_cfg} not found. '
            'Please provide a valid path to the base config file.'
        )
    if not Path(secret_cfg).exists():
        logger.error(f'Secret config file {secret_cfg} not found.')
        raise FileNotFoundError(
            f'Secret config file {secret_cfg} not found. '
            'Please provide a valid path to the secret config file.'
        )

    with open(base_cfg) as f:
        config = yaml.safe_load(f)
    with open(secret_cfg) as f:
        crowdin_cfg = yaml.safe_load(f)

    if 'crowdin' not in config:
        config['crowdin'] = {}

    config['crowdin']['api-token'] = ''
    for key in crowdin_cfg['crowdin']:
        config['crowdin'][key] = crowdin_cfg['crowdin'][key]

    return config


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="""
    Run a loc sync based on the task list from base.config.yaml
    Example: locsync.py -u"""
    )

    parser.add_argument(
        'tasklist',
        type=str,
        nargs='?',
        #                        default='default',
        help='Task list to run from base.config.yaml',
    )

    parser.add_argument(
        '-u',
        '--unattended',
        dest='unattended',
        action='store_true',
        help='Use --unattended to run the script without any input from the user',
    )

    parser.add_argument(
        '--setup',
        dest='setup',
        action='store_true',
        help='Use --setup to install required packages',
    )

    parser.add_argument(
        '-c',
        '--config',
        dest='config',
        type=str,
        nargs='?',
        help='Use -c / --config to specify a secret config file to use instead '
        'of crowdin.config.yaml',
    )

    parser.add_argument(
        '-s',
        '--secret',
        dest='secret',
        type=str,
        nargs='?',
        help='Use -s / --secret to specify a secret config file to use instead '
        'of crowdin.config.yaml',
    )

    parameters = {}

    parameters['task-list'] = parser.parse_args().tasklist
    parameters['unattended'] = parser.parse_args().unattended
    parameters['config'] = parser.parse_args().config or BASE_CFG
    parameters['setup'] = parser.parse_args().setup
    parameters['secret'] = parser.parse_args().config or SECRET_CFG

    return parameters


def get_task_list_from_user(config):
    task_lists = [t for t in config if t not in CFG_SECTIONS]
    task_list = ''
    while not task_list:
        print('\nAvailable task lists from base.config.yaml:')
        for i, task in enumerate(task_lists, start=1):
            print(f'{i}. {task}')
        name_or_num = input('Enter the number or name of a task list to run: ')
        if name_or_num in task_lists:
            task_list = name_or_num
        else:
            try:
                task_list = task_lists[int(name_or_num) - 1]
            except ValueError:
                print('Error. Please enter the task list name or its number.')
        if task_list:
            print(f'\nSelected taks list: {task_list}:')
            update_warning = False
            for task in config[task_list]:
                if 'updates-source' in task:
                    print('\033[93m', task, '\033[0m')
                    update_warning = True
                else:
                    print(task)

            if update_warning:
                print(
                    '\n\033[93mWarning: This task list contains tasks '
                    'that update the source files.\033[0m'
                )

            conf = input(
                f'\nEnter Y to execute task list {task_list}. '
                'Anything else to go back to task list selection... '
            )
            if conf != 'Y' and conf != 'y':
                task_list = None
    return task_list


def main():
    params = parse_arguments()

    if params['setup']:
        subp.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print('Tried to install required modules.')
        input('Press Enter to quit...')
        return
    if err is not None and not params['setup']:
        print(
            'Exception during module import. Try running locsync.py --setup '
            'to install the needed modules.\n'
            'Exception message:',
            err,
        )
        input('Press Enter to quit...')
        return

    init_logging()

    logger.opt(raw=True).info(
        '\n'
        '==========================================\n'
        '---------  Locsync script start  ---------\n'
        '==========================================\n'
    )

    config = read_config_files(base_cfg=params['config'], secret_cfg=params['secret'])

    if params['task-list'] is None and not params['unattended']:
        logger.info('Interactive: getting task list from user in console.')
        logger.info(
            f'Crowdin organization: {config["crowdin"]["organization"]}. '
            f'Project: {config["crowdin"]["project_id"]}.'
        )
        params['task-list'] = get_task_list_from_user(config)

    if not params['task-list']:
        logger.error(
            'No task list specified. Provide task list name as one of the arguments. '
            'See base.config.yaml for available task lists.'
        )
        return 1

    logger.info(f'Executing task list: {params["task-list"]}')

    tasks_done = []

    all_tasks_start = timer()

    # TODO: Extract project path and engine path search to a module

    project_path = None
    if 'project_dir' in config['parameters']:
        project_path = Path(config['parameters']['project_dir']).resolve().absolute()

    if project_path is None or not project_path.exists():
        logger.info(
            'No project_dir specified in parameters. Trying default: {script_dir}/../../../../'
        )
        project_path = (Path(__file__).parent.parent.parent.parent).resolve().absolute()

    logger.info(f'Project directory: {project_path}')

    if 'engine_dir' in config['parameters']:
        ue_cwd = Path(config['parameters']['engine_dir']).resolve().absolute()

    if ue_cwd is None or not ue_cwd.exists():
        logger.info(
            'No engine_dir specified in parameters, trying default: {project_dir}/../).'
        )
        ue_cwd = (project_path / '../').resolve()

    logger.info(f'Engine directory: {ue_cwd}')

    fname = config['parameters'].get('unreal_binary', None)
    if fname is None:
        logger.info('No engine_executable specified in parameters, using default.')
        # Default Unreal Engine executable name
        fname = 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'  # UE5
        # fname = 'Engine/Binaries/Win64/UE4Editor-Cmd.exe'  # UE4

    fpath = (ue_cwd / fname).absolute()

    logger.info(f'Engine executable: {fpath}')

    if not fpath.exists():
        logger.error(
            f'Engine executable {fpath} does not exist. '
            'Please configure the engine directory in base.config.yaml.\n'
            'For now, Unreal Engine tasks will be skipped.'
        )
        fpath = None

    # Finding the .uproject file path
    uproject = None
    project_files = list(project_path.glob('*.uproject'))
    if not project_files or len(project_files) != 1:
        logger.error(
            'None or more than one .uproject file found in the project directory. '
            'Please configure the project directory in base.config.yamL\n'
            f'Found: {project_files if project_files else "None"}\n'
            'For now, Unreal Engine tasks will be skipped.'
        )
        uproject = None
    else:
        uproject = project_files[0]

    py_cwd = Path(__file__).parent.absolute()

    tasks = config[params['task-list']]
    cur_task_num = 0
    num_tasks = len(tasks)

    for task in tasks:
        cur_task_num += 1

        task_start = timer()

        logger.info(
            f'\n--- Task {cur_task_num} of {num_tasks} ---\n{task["description"]}'
        )

        skip_task = False
        reason = '(This should not appear in the logs)'

        if 'unreal' in task and not config['parameters']['use-unreal']:
            skip_task = True
            reason = (
                'Skipped, unreal is turned off in parameters (see base.config.yaml)'
            )

        if 'unreal' in task and fpath is None:
            skip_task = True
            reason = (
                'Skipped, Unreal executable not found. '
                'Please configure the paths in base.config.yaml.'
            )

        if 'unreal' in task and uproject is None:
            skip_task = True
            reason = (
                'Skipped, uproject file not found. '
                'Please configure the paths in base.config.yaml.'
            )

        if 'p4-checkout' in task and not config['parameters']['p4-checkout']:
            skip_task = True
            reason = (
                'Skipped, P4 checkout is turned off in parameters '
                '(see base.config.yaml)'
            )

        if 'p4-checkin' in task and not config['parameters']['p4-checkin']:
            skip_task = True
            reason = (
                'Skipped, P4 checkin is turned off in parameters (see base.config.yaml)'
            )

        if skip_task:
            logger.info(reason)
            tasks_done += [[task, reason, '—']]
            continue

        if 'unreal' in task:
            with subp.Popen(
                [
                    fpath,
                    uproject,
                    '-run=pythonscript',
                    f'-script="{task["script"]}.py"',
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
        else:
            returncode = subp.run(
                [
                    sys.executable,
                    py_cwd / (task['script'] + '.py'),
                    params['task-list'],
                ],
                cwd=py_cwd,
            ).returncode

        task_elapsed = timer() - task_start

        tasks_done += [[task, f'{task_elapsed:.2f} sec.', f'Return code: {returncode}']]

        logger.info(f'Execution time: {task_elapsed:.2f} sec.')

        if returncode != 0 and config['parameters']['stop-on-errors']:
            logger.error(f'Error in task #{cur_task_num}.')
            break

    elapsed = timer() - all_tasks_start
    logger.info('\n---\nTasks performed:')
    for task in tasks_done:
        logger.info(f'- {task[0]["description"]}:')
        if task[2] == 'Return code: 0':
            logger.success(f'  Success! {task[0]["script"]}: {task[1]}')
        else:
            logger.warning(
                f'  Something went wrong! {task[0]["script"]}: {task[1]} ({task[2]})'
            )
    logger.info(f'Total execution time: {elapsed:.2f} sec.')

    logger.info('--- Loc Sync Script End ---')


if __name__ == '__main__':
    main()
