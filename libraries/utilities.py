# Holds utility functions used across scripts:
# read and update configs, etc.

from pathlib import Path
import yaml
from dataclasses import asdict, dataclass, fields
import argparse

BASE_CFG = 'base.config.yaml'
SECRET_CFG = 'crowdin.config.yaml'

# Paths for default UE folder structure:
# (Engine Root)/Games/(GameName)/Content/Python/...
# Assuming the scripts are in Python directory where they should be
DEF_CONTENT_PATH = Path('../')
DEF_PROJECT_PATH = Path('../../')
DEF_ENGINE_ROOT = Path('../../../../')
DEF_ENGINE_CMD = DEF_ENGINE_ROOT / 'Engine/Binaries/Win64/UE4Editor-cmd.exe'
DEF_ENGINE_DIR = DEF_ENGINE_ROOT / 'Engine/Binaries/Win64/'


@dataclass
class LocTask:

    # TODO: Add some default parameters? Paths?

    def post_update(self):
        '''
        Called after you initiate or update the paramaters from config files.

        Override this to recalculate any config values
        that depend on other config values. E.g., if you want
        to format a path based on a base path or
        create regex based on a pattern and other value.
        '''
        pass

    def get_task_list_from_arguments(self):
        parser = argparse.ArgumentParser(
            description='''
            Create a debug ID locale using settings in base.config.yaml
            For defaults: test_lang.py
            For task-specific settings: test_lang.py task_list_name
            '''
        )

        parser.add_argument(
            'tasklist',
            type=str,
            nargs='?',
            help='Task list to run from base.config.yaml',
        )

        return parser.parse_args().tasklist

    def read_config(
        self,
        script: str,
        logger,
        base_config: str = BASE_CFG,
        secret_config: str = SECRET_CFG,
    ):

        if script.endswith('.py'):
            script = script.rpartition('.')[0]

        task_list = self.get_task_list_from_arguments()

        # Update Crowdin API config if exists
        if secret_config and Path(secret_config).exists():
            with open(secret_config, mode='r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)

            for key, value in yaml_config['crowdin'].items():
                if not key.startswith('_') and key in [
                    field.name for field in fields(self)
                ]:
                    self.__setattr__(key, value)

        # Use defaults and return if base config does not exist
        if not base_config or not Path(base_config).exists():
            logger.info('No config found. Using default parameters.')
            if 'token' in fields(self) and not self.token:
                logger.warning('API token parameter exists but not set!')
            self.post_update()
            cfg_info = asdict(self)
            cfg_info.pop('token', None)
            logger.info(f'{cfg_info}')
            return

        with open(base_config, mode='r', encoding='utf-8') as f:
            yaml_config = yaml.safe_load(f)

        # Update config from the defaults section of base config
        updated = False
        if script in yaml_config['script-parameters']:
            for key, value in yaml_config['script-parameters'][script].items():
                if not key.startswith('_') and key in [
                    field.name for field in fields(self)
                ]:
                    updated = True
                    self.__setattr__(key, value)
            if updated:
                logger.info(
                    'Updated parameters from global section of base.config.yaml.'
                )

        # Update config with overrides from the 'task list' section of base config
        updated = False
        if task_list and task_list in yaml_config:
            task_id = [
                i
                for i, val in enumerate(yaml_config[task_list])
                if val['script'] == script
            ]
            if task_id and 'script-parameters' in yaml_config[task_list][task_id[0]]:
                logger.info(
                    'Updated parameters from global section of base.config.yaml.'
                )
                for key, value in yaml_config[task_list][task_id[0]][
                    'script-parameters'
                ].items():
                    if not key.startswith('_') and key in [
                        field.name for field in fields(self)
                    ]:
                        updated = True
                        self.__setattr__(key, value)
                if updated:
                    logger.info(
                        f'Updated parameters from {task_list} section of base.config.yaml.'
                    )

        if 'token' in fields(self) and not self.token:
            logger.error('API token parameter exists but not set!')

        # Run post_update to compute derivative parameters, if any
        self.post_update()

        cfg_info = asdict(self)
        cfg_info.pop('token', None)
        logger.info(f'{cfg_info}')

        return
