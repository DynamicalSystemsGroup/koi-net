"""Logging system for all components, lifecycle, and assembly processes."""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from typing import Callable

import structlog
import colorama


shared_log_processors: list[Callable] = [
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.UnicodeDecoder(),
    structlog.processors.CallsiteParameterAdder({
        structlog.processors.CallsiteParameter.MODULE,
        structlog.processors.CallsiteParameter.FUNC_NAME
    }),
    structlog.contextvars.merge_contextvars
]


class PartitionedFileHandler(logging.Handler):
    """Writes logs to partitioned file supporting multiple nodes running
    simultaneously in the same execution environment.

    Intended to be used with :class:`~koi_net.components.logging_context.LoggingContext`
    component, which binds a node's ``root_dir`` to the ``log_dir`` context var. As a result, every
    node in an execution environment should send logs to the log file in
    their own root directory. Oftentimes logs produced by third party
    libraries fall through the cracks and are written to ``dropped_logs.txt``
    instead as a fallback.

    This system is overly complicated and is worth refactoring.
    """
    
    def __init__(
        self,
        log_file_name: str = "log.ndjson",
        max_log_file_size: int = 10 * 1024 ** 2,
        num_log_file_backups: int = 5,
        log_file_encoding: str = "utf-8"
    ):
        self.handlers: dict[str, RotatingFileHandler] = {}
        self.log_file_name = log_file_name
        self.max_log_file_size = max_log_file_size
        self.max_log_file_backups = num_log_file_backups
        self.log_file_encoding = log_file_encoding
        
        self.processor_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_log_processors
        )
        
        self.dropped_log_handler = RotatingFileHandler(
            filename="dropped_logs.txt",
            maxBytes=self.max_log_file_size,
            backupCount=self.max_log_file_backups,
            encoding=self.log_file_encoding,
            delay=True
        )
        
        super().__init__()
        
    def del_handler(self, log_dir: str, wipe_logs: bool = False):
        if log_dir in self.handlers:
            self.handlers[log_dir].close()
            if wipe_logs:
                try:
                    os.remove(self.handlers[log_dir].baseFilename)
                except OSError:
                    pass
            del self.handlers[log_dir]
        
    def get_handler(self, log_dir: str):
        if log_dir not in self.handlers:
            file_handler = RotatingFileHandler(
                filename=Path(log_dir) / Path(self.log_file_name),
                maxBytes=self.max_log_file_size,
                backupCount=self.max_log_file_backups,
                encoding=self.log_file_encoding,
                delay=True
            )
            
            file_handler.setFormatter(self.processor_formatter)
            
            file_handler.setLevel(logging.DEBUG)
            self.handlers[log_dir] = file_handler
        
        return self.handlers[log_dir]
    
    def emit(self, record: logging.LogRecord):
        if record.log_dir is not None:
            log_dir = record.log_dir
            
        elif type(record.msg) is dict and "log_dir" in record.msg:
            log_dir = record.msg["log_dir"]
        
        else:
            self.dropped_log_handler.emit(record)
            return
        
        self.get_handler(str(log_dir)).emit(record)
        

class LogSystem:
    """Configures and initializes the logging system.
    
    Uses two log handlers by default. One prints to the console, the other
    produces NDJSON log files, which can be viewed using LNAV.
    """
    
    use_file_handler: bool
    use_console_handler: bool
    file_handler_log_level: int
    console_handler_log_level: int
    
    _instance = None
    
    def __new__(
        cls,
        use_file_handler: bool = True,
        use_console_handler: bool = True,
        file_handler_log_level: int = logging.DEBUG,
        console_handler_log_level: int = logging.DEBUG
    ):
        """Only instantiable once, other calls will return the first object."""
        if not cls._instance:
            obj = super().__new__(cls)
            obj.use_file_handler = use_file_handler
            obj.use_console_handler = use_console_handler
            obj.file_handler_log_level = file_handler_log_level
            obj.console_handler_log_level = console_handler_log_level
            
            obj.configure()
            cls._instance = obj
            
        return cls._instance
    
    @staticmethod
    def delete_file_handler(log_dir: str, wipe_logs: bool = False):
        for handler in logging.getLogger().handlers:
            if isinstance(handler, PartitionedFileHandler):
                handler.del_handler(log_dir, wipe_logs=wipe_logs)
        
    def configure(self):
        handlers = []
        if self.use_file_handler:
            handlers.append(PartitionedFileHandler())
        if self.use_console_handler:
            handlers.append(self.configure_console_handler())
        
        logging.basicConfig(level=logging.DEBUG, handlers=handlers)
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, *kwargs)
            
            ctx = structlog.contextvars.get_contextvars()
            record.log_dir = ctx.get("log_dir")
            
            return record
        
        logging.setLogRecordFactory(record_factory)
        
        structlog.configure(
            processors=shared_log_processors + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        
    def configure_console_handler(self):
        console_renderer = structlog.dev.ConsoleRenderer(
            columns=[
                # Render the timestamp without the key name in yellow.
                structlog.dev.Column(
                    "timestamp",
                    structlog.dev.KeyValueColumnFormatter(
                        key_style=None,
                        value_style=colorama.Style.DIM,
                        reset_style=colorama.Style.RESET_ALL,
                        value_repr=lambda t: datetime.fromisoformat(t).strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                ),
                structlog.dev.Column(
                    "level",
                    structlog.dev.LogLevelColumnFormatter(
                        level_styles={
                            level: colorama.Style.BRIGHT + color
                            for level, color in {
                                "critical": colorama.Fore.RED,
                                "exception": colorama.Fore.RED,
                                "error": colorama.Fore.RED,
                                "warn": colorama.Fore.YELLOW,
                                "warning": colorama.Fore.YELLOW,
                                "info": colorama.Fore.GREEN,
                                "debug": colorama.Fore.GREEN,
                                "notset": colorama.Back.RED,
                            }.items()
                        },
                        reset_style=colorama.Style.RESET_ALL,
                        width=9
                    )
                ),
                # Render the event without the key name in bright magenta.
                
                # Default formatter for all keys not explicitly mentioned. The key is
                # cyan, the value is green.
                structlog.dev.Column(
                    "path",
                    structlog.dev.KeyValueColumnFormatter(
                        key_style=None,
                        value_style=colorama.Fore.MAGENTA,
                        reset_style=colorama.Style.RESET_ALL,
                        value_repr=str,
                        width=30
                    ),
                ),
                structlog.dev.Column(
                    "event",
                    structlog.dev.KeyValueColumnFormatter(
                        key_style=None,
                        value_style=colorama.Fore.WHITE,
                        reset_style=colorama.Style.RESET_ALL,
                        value_repr=str,
                        width=30
                    ),
                ),
                structlog.dev.Column(
                    "",
                    structlog.dev.KeyValueColumnFormatter(
                        key_style=colorama.Fore.BLUE,
                        value_style=colorama.Fore.GREEN,
                        reset_style=colorama.Style.RESET_ALL,
                        value_repr=str,
                    ),
                )
            ]
        )
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=console_renderer,
                foreign_pre_chain=shared_log_processors
            )
        )
        
        console_handler.setLevel(self.console_handler_log_level)
        return console_handler