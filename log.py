import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from paths import DATA_DIR

def setup_logging(verbose: bool = False):
    """Sets up application-wide logging to file and (optionally) console."""
    log_dir = DATA_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ai_dj.log"

    # Use a rotating file handler to prevent log files from growing indefinitely
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024 * 5,  # 5 MB
        backupCount=2,             # Keep 2 old log files
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Capture all levels

    # Clear existing handlers to prevent duplicate output if called multiple times
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)

    logger.addHandler(file_handler)

    # Always add console handler in verbose mode
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter("%(levelname)s - %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # Log any uncaught exceptions to the log file
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Don't log KeyboardInterrupts
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Unhandled exception caught by excepthook",
                        exc_info=(exc_type, exc_value, exc_traceback))
        # Call the default exception handler
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

    logger.info("Logging initialized.")

# Call setup_logging once when this module is imported
if __name__ == '__main__':
    setup_logging(verbose=True)
    logging.info("This is an info message.")
    logging.debug("This is a debug message.")
    try:
        1 / 0
    except ZeroDivisionError:
        logging.error("A division by zero error occurred.")
