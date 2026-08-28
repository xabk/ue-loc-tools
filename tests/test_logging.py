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


def test_cjk_survives_a_redirected_stdout(repo_root):
    """stdout is a pipe here, so Python picks the locale encoding for it.
    PYTHONIOENCODING pins that to cp1252, which is what a Windows console
    gives you and what UE output then fails to encode into."""
    env = dict(os.environ, PYTHONIOENCODING='cp1252')

    result = subprocess.run(
        [sys.executable, '-c', SNIPPET],
        cwd=repo_root,
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
