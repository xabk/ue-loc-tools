# Holds utility functions used across scripts:
# read and update configs, etc.

from pathlib import Path
import yaml
from dataclasses import dataclass, fields

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
class Parameters:
    def post_update(self):
        pass

    # ---------------------------------------------------------------------------------

    def read_config(
        self,
        script,
        logger,
        base_config: str = BASE_CFG,
        secret_config: str = SECRET_CFG,
        task_list: str = None,
    ):

        if not Path(base_config).exists():
            logger.info('No config found. Using default parameters.')
            if 'token' in self and not self.token:
                logger.warning('Token parameter exists but not set!')
            self.post_update()
            logger.info(f'{self}')
            return

        with open(base_config, mode='r', encoding='utf-8') as f:
            yaml_config = yaml.safe_load(f)

        updated = False
        if script in yaml_config['script-parameters']:
            for key, value in yaml_config['script-parameters'][script].items():
                if key in [field.name for field in fields(self)]:
                    updated = True
                    self.__setattr__(key, value)
            if updated:
                logger.info(
                    'Updated parameters from global section of base.config.yaml.'
                )

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
                    if key in [field.name for field in fields(self)]:
                        updated = True
                        self.__setattr__(key, value)
                if updated:
                    logger.info(
                        f'Updated parameters from {task_list} section of base.config.yaml.'
                    )

        self.post_update()

        logger.info(f'{self}')

        return
