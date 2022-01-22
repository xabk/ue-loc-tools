from P4 import P4
from configparser import ConfigParser
from pathlib import Path

# TODO: Add config file support
# TODO: Move parameters to config file

assets_to_checkout = [
    'FactoryGame/Interface/UI/DT_Credits_Community.csv',
    'FactoryGame/Interface/UI/DT_Credits_Community.uasset',
]
#              Content/Relative/To/Content


def main():
    cfg = ConfigParser()
    content_path = Path(__file__).parent.parent
    print(
        'Reading P4 config from:',
        content_path.parent / 'Saved/Config/Windows/SourceControlSettings.ini',
    )
    p4 = P4()
    try:
        cfg.read(content_path.parent / 'Saved/Config/Windows/SourceControlSettings.ini')
        p4.port = cfg['PerforceSourceControl.PerforceSourceControlSettings']['Port']
        p4.user = cfg['PerforceSourceControl.PerforceSourceControlSettings']['UserName']
        p4.client = cfg['PerforceSourceControl.PerforceSourceControlSettings'][
            'Workspace'
        ]
    except:
        print(
            'P4 Config Error: check',
            (content_path.parent / 'Saved/Config/Windows/SourceControlSettings.ini'),
        )
        return 1

    p4.connect()
    dir = content_path / 'Localization'
    files = [str(t) for t in dir.glob('**/*') if t.is_file()]
    for asset in assets_to_checkout:
        files += [content_path / asset]

    p4.run('edit', files)
    print(
        'Connected to P4 and checked out the Localization folder and community credits assets.'
    )
    return 0


if __name__ == "__main__":
    main()
