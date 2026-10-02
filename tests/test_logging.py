"""UE logs CJK, and a redirected stdout defaults to the locale encoding."""

import os
import subprocess
import sys

from loguru import logger

CJK = '每日任务'

SNIPPET = (
    'from libraries.utilities import init_logging\n'
    'from loguru import logger\n'
    'init_logging()\n'
    f'logger.info("| UE | Loading package: {CJK}")\n'
)


def test_cjk_survives_a_redirected_stdout(repo_root, tmp_path):
    """stdout is a pipe here, so Python picks the locale encoding for it.
    PYTHONIOENCODING pins that to cp1252, which is what a Windows console
    gives you and what UE output then fails to encode into.

    Runs from tmp_path because init_logging() opens its file sink relative
    to the working directory: from the repo root this test wrote a real
    logs/locsync.log into the checkout on every run."""
    env = dict(
        os.environ, PYTHONIOENCODING='cp1252', PYTHONPATH=str(repo_root)
    )

    result = subprocess.run(
        [sys.executable, '-c', SNIPPET],
        cwd=tmp_path,
        env=env,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
    assert 'Logging error' not in result.stderr.decode('utf-8', 'replace')
    assert CJK in result.stdout.decode('utf-8', 'replace')


def test_the_file_sink_keeps_the_characters(tmp_path):
    log = tmp_path / 'locsync.log'
    logger.remove()
    logger.add(str(log), format='{message}', encoding='utf-8')
    logger.info(CJK)
    logger.remove()

    assert CJK in log.read_text(encoding='utf-8')


def test_token_never_reaches_the_log(tmp_path, monkeypatch):
    """read_config drops the token before logging the config dict."""
    from tasks.build_and_download import BuildAndDownloadTranslations

    log = tmp_path / 'locsync.log'
    logger.remove()
    logger.add(str(log), format='{message}', level='TRACE')

    monkeypatch.setattr('sys.argv', ['build_and_download.py'])
    task = BuildAndDownloadTranslations()
    task.token = 'super-secret-token-value'
    task.read_config('build_and_download.py', str(tmp_path / 'missing.yaml'))

    logger.remove()
    assert 'super-secret-token-value' not in log.read_text(encoding='utf-8')


# ------------------------- one log file per launch ------------------------- #


def test_each_launch_logs_to_its_own_file(tmp_path, monkeypatch):
    """Rotating by size renamed the log mid-run, which fails on Windows while
    another run still has it open. A file per launch is never renamed."""
    from libraries.utilities import init_logging

    monkeypatch.chdir(tmp_path)
    log_file = init_logging()
    logger.info('this launch')
    logger.remove()

    assert log_file.parent == (tmp_path / 'logs').resolve()
    assert log_file.name.startswith('locsync_')
    assert 'this launch' in log_file.read_text(encoding='utf-8')


def test_only_the_newest_logs_are_kept(tmp_path):
    from libraries.utilities import prune_logs

    for day in range(1, 26):
        (tmp_path / f'locsync_2026-10-{day:02d}_09-00-00.log').write_text('')
    (tmp_path / 'locsync.log').write_text('')  # the old single file is not ours

    prune_logs(tmp_path, 20)

    kept = sorted(p.name for p in tmp_path.glob('locsync_*.log'))
    assert len(kept) == 20
    assert kept[0] == 'locsync_2026-10-06_09-00-00.log'
    assert (tmp_path / 'locsync.log').exists()


def test_a_launch_leaves_twenty_logs_including_its_own(tmp_path, monkeypatch):
    from libraries.utilities import LOGS_TO_KEEP, init_logging

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'logs').mkdir()
    for day in range(1, 26):
        (tmp_path / 'logs' / f'locsync_2000-01-{day:02d}_09-00-00.log').write_text('')

    log_file = init_logging()
    logger.remove()

    logs = list((tmp_path / 'logs').glob('locsync_*.log'))
    assert len(logs) == LOGS_TO_KEEP == 20
    assert log_file in [p.resolve() for p in logs]
