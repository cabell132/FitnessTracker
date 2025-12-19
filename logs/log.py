import logging
from pathlib import Path
from typing import Optional


def get_logger(
    name: str = __name__,
    log_level: int = logging.INFO,
    log_file_name: Optional[str] = None,
    log_sub_dir: str = "logs",
) -> logging.Logger:
    """
    Set up the logging configuration.

    Args:
        name (str): Name of the logger.
        log_level (int): Logging level (e.g., logging.INFO, logging.DEBUG).
        log_file_name (str): Name of the log file. If None, logs are printed to the console.
        log_sub_dir (str): Subdirectory where the log file is saved.
    """

    # Create logger
    logger = logging.getLogger(name)

    if logger.hasHandlers():
        return logger
    

    logger.propagate = False
    
    logger.setLevel(log_level)

    # Create formatter
    formatter = CustomFormatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    # Remove previous handlers
    while logger.handlers:
        logger.removeHandler(logger.handlers[0])

    # Create and add handlers
    if log_file_name:
        # Create log directory if it does not exist
        log_dir = Path(log_sub_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create file handler
        log_file = log_dir / f"{str(log_file_name)}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Always add the stream (console) handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Return logger object
    return logger

class CustomFormatter(logging.Formatter):
    """ Custom Formatter does these 2 things:
    1. Overrides 'funcName' with the value of 'func_name_override', if it exists.
    2. Overrides 'filename' with the value of 'file_name_override', if it exists.
    """
    def format(self, record: logging.LogRecord):
        if hasattr(record, 'name_override'):
            record.name = getattr(record,"name_override")
        if hasattr(record, 'func_name_override'):
            record.filename = getattr(record,"func_name_override")
        if hasattr(record, 'file_name_override'):
            record.filename = getattr(record,"file_name_override")
        return super(CustomFormatter, self).format(record)
