import sys
import argparse
import subprocess as subp

missing_modules = False

try:
    import yaml
    from pathlib import Path
    from timeit import default_timer as timer
    import re
    from loguru import logger
except Exception as err:
    missing_modules = True

BASE_CFG = 'base.config.yaml'
SECRET_CFG = 'crowdin.config.yaml'


def read_config_files():
    with open(BASE_CFG) as f:
        config = yaml.safe_load(f)
    with open(SECRET_CFG) as f:
        crowdin_cfg = yaml.safe_load(f)

    config['crowdin']['api-token'] = ''
    for key in config['crowdin']:
        if key in crowdin_cfg['crowdin']:
            config['crowdin'][key] = crowdin_cfg['crowdin'][key]

    return config


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='''
    Run a loc sync based on the task list from base.config.yaml
    Example: locsync.py -u'''
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
        '-unattended',
        dest='unattended',
        action='store_true',
        help='Use -unattended to run the script without any input from the user',
    )

    parser.add_argument(
        '-setup',
        dest='setup',
        action='store_true',
        help='Use -setup to install required packages',
    )

    parameters = {}

    parameters['task-list'] = parser.parse_args().tasklist
    parameters['unattended'] = parser.parse_args().unattended
    parameters['setup'] = parser.parse_args().setup

    return parameters


def get_task_list_from_user(config):
    task_lists = [t for t in config if t not in ['crowdin', 'parameters']]
    task_list = ''
    while not task_list:
        print('Available task lists from base.config.yaml:')
        for i, task in enumerate(task_lists, start=1):
            print(f'{i}. {task}')
        name_or_num = input('Enter the number or name of a task list to run: ')
        if name_or_num in task_lists:
            task_list = name_or_num
        else:
            try:
                task_list = task_lists[int(name_or_num) - 1]
            except:
                print('Error. Please enter the task list name or its number.')
    return task_list


def main():
    params = parse_arguments()

    if params['setup']:
        subp.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print('Tried to install required modules.')
        input('Press Enter to quit...')
        return
    if missing_modules and not params['setup']:
        print(
            'Exception during module import. Try running locsync.py -setup to install the needed modules.\n'
            'Exception message:',
            err,
        )
        input('Press Enter to quit...')
        return

    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
    )

    logger.opt(raw=True).info(
        '\n'
        '==========================================\n'
        '---------  Locsync script start  ---------\n'
        '==========================================\n'
    )

    config = read_config_files()

    if params['task-list'] is None and not params['unattended']:
        logger.info('Interactive: getting task list from user in console.')
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

    project_path = Path(__file__).parent.parent.parent.absolute()

    # Trying to find the path to Unreal Build Tool in the .sln file
    with open(next(project_path.glob('*.sln')), mode='r') as f:
        s = f.read()
        engine_path = re.findall(
            r'"UnrealBuildTool", "(.*?)Engine\\Source\\Programs\\UnrealBuildTool\\UnrealBuildTool.csproj"',
            s,
        )

    if len(engine_path) == 0:
        logger.error(
            'Couldn\'t find Engine path in the project solution file. Aborting.'
        )

    ue_cwd = (project_path / engine_path[0]).resolve()

    fpath = (ue_cwd / 'Engine/Binaries/Win64/UE4Editor-cmd.exe').absolute()

    # Finding the .uproject file path
    uproject = next(project_path.glob('*.uproject')).absolute()

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

        if 'unreal' in task and not config['parameters']['use-unreal']:
            skip_task = True
            reason = (
                'Skipped, unreal is turned off in parameters (see base.config.yaml)'
            )

        if 'p4-checkout' in task and not config['parameters']['p4-checkout']:
            skip_task = True
            reason = 'Skipped, P4 checkout is turned off in parameters (see base.config.yaml)'

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
                    f'-script="{py_cwd / task["script"]} {params["task-list"]}"',
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
                    for line in process.stdout:
                        logger.info(f'| UE | {line.strip()}')
                    if process.poll() != None:
                        break
                returncode = process.returncode
        else:
            returncode = subp.run(
                [sys.executable, py_cwd / task['script'], params['task-list']], cwd=py_cwd
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
        logger.info(f'  {task[0]["script"]}: {task[1]} ({task[2]})')
    logger.info(f'Total execution time: {elapsed:.2f} sec.')

    logger.info('--- Loc Sync Script End ---')


if __name__ == '__main__':
    main()
