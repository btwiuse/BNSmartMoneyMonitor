from __future__ import annotations

import logging
import sys
from pathlib import Path

from smart_signal.logging_utils import configure_logging, install_exception_logging


def test_configure_logging_creates_logfile_and_writes(tmp_path: Path) -> None:
    logfile = configure_logging(
        log_level="DEBUG",
        log_dir=tmp_path,
        log_filename="test.log",
        backup_count=3,
    )
    logger = logging.getLogger("smart_signal.test")
    logger.info("hello")

    assert logfile == tmp_path / "test.log"
    assert logfile.exists()
    assert "hello" in logfile.read_text(encoding="utf-8")


def test_install_exception_logging_sets_sys_hook(tmp_path: Path) -> None:
    configure_logging(log_dir=tmp_path, log_filename="test.log")
    install_exception_logging("smart_signal.test")
    assert sys.excepthook is not sys.__excepthook__
