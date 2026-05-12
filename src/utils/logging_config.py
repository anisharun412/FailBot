"""
Logging Configuration for FailBot

Sets up structured JSON logging with JSONL output.
"""

import logging
import logging.handlers
import json
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid

try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    # Fallback if python-json-logger not installed
    jsonlogger = None


class FailBotJsonFormatter(logging.Formatter):
    """Custom JSON formatter for FailBot logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "run_id"):
            run_id_val: Any = getattr(record, "run_id", None)
            if run_id_val is not None:
                log_data["run_id"] = run_id_val
        if hasattr(record, "node"):
            node_val: Any = getattr(record, "node", None)
            if node_val is not None:
                log_data["node"] = node_val
        if hasattr(record, "event_type"):
            event_type_val: Any = getattr(record, "event_type", None)
            if event_type_val is not None:
                log_data["event_type"] = event_type_val
        if hasattr(record, "data"):
            data_val: Any = getattr(record, "data", None)
            if data_val is not None:
                log_data["data"] = data_val
        if hasattr(record, "duration_ms"):
            duration_val: Any = getattr(record, "duration_ms", None)
            if duration_val is not None:
                log_data["duration_ms"] = duration_val
        
        # Add exception if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_json_logging(
    output_dir: str = "runs",
    level: int = logging.INFO,
    run_id: Optional[str] = None
) -> logging.Logger:
    """
    Set up JSON logging to JSONL file.
    
    Args:
        output_dir: Directory to write log files
        level: Logging level (e.g., logging.INFO)
        run_id: Run ID to include in logs (uses UUID if None)
    
    Returns:
        Configured logger instance
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate run ID if not provided
    if run_id is None:
        run_id = str(uuid.uuid4())[:8]
    
    # Create log file path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = output_path / f"failbot_{timestamp}.jsonl"
    
    # Create logger
    logger = logging.getLogger("failbot")
    logger.setLevel(level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Create file handler
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setLevel(level)
    
    # Use custom JSON formatter
    formatter = FailBotJsonFormatter()
    
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Also add console handler for WARNING level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # Only show warnings/errors on console
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized to {log_file}")
    
    return logger


class LogEventBuffer:
    """Buffers log events for batch writing."""
    
    def __init__(self, logger: logging.Logger, buffer_size: int = 10):
        """
        Initialize event buffer.
        
        Args:
            logger: Logger to write events to
            buffer_size: Number of events to buffer before flushing
        """
        self.logger = logger
        self.buffer_size = buffer_size
        self.buffer: list = []
    
    def add_event(self, event_data: Dict[str, Any]) -> None:
        """
        Add event to buffer.
        
        Args:
            event_data: Event dictionary
        """
        self.buffer.append(event_data)
        
        if len(self.buffer) >= self.buffer_size:
            self.flush()
    
    def flush(self) -> None:
        """Flush buffered events to logger."""
        for event in self.buffer:
            # Create log record with extra fields
            record = logging.LogRecord(
                name="failbot",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=event.get("message", ""),
                args=(),
                exc_info=None
            )
            
            # Add extra fields
            for key, value in event.items():
                setattr(record, key, value)
            
            self.logger.handle(record)
        
        self.buffer = []


def log_event(
    logger: logging.Logger,
    run_id: str,
    node: str,
    event_type: str,
    data: Dict[str, Any],
    duration_ms: Optional[float] = None
) -> None:
    """
    Log a structured event.
    
    Args:
        logger: Logger instance
        run_id: Run ID
        node: Node name
        event_type: Type of event (e.g., "node_start", "llm_call")
        data: Event data dictionary
        duration_ms: Duration in milliseconds (optional)
    """
    record = logging.LogRecord(
        name="failbot",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=event_type,
        args=(),
        exc_info=None
    )
    
    record.run_id = run_id
    record.node = node
    record.event_type = event_type
    record.data = data
    if duration_ms is not None:
        record.duration_ms = duration_ms
    
    logger.handle(record)


# Convenience function
_default_logger: Optional[logging.Logger] = None
_logger_lock = threading.Lock()


def get_logger(output_dir: str = "runs", run_id: Optional[str] = None) -> logging.Logger:
    """
    Get or create default logger instance.
    
    Args:
        output_dir: Output directory
        run_id: Run ID
    
    Returns:
        Logger instance
    """
    global _default_logger
    
    if _default_logger is None:
        with _logger_lock:
            if _default_logger is None:
                _default_logger = setup_json_logging(output_dir, run_id=run_id)
    
    return _default_logger


if __name__ == "__main__":
    logger = setup_json_logging(output_dir="./test_runs")
    
    # Test logging
    log_event(
        logger,
        run_id="test-run-001",
        node="parse_log",
        event_type="llm_call",
        data={
            "model": "gpt-4o-mini",
            "input_tokens": 3420,
            "output_tokens": 210
        },
        duration_ms=1203
    )
    
    log_event(
        logger,
        run_id="test-run-001",
        node="triage",
        event_type="tool_call",
        data={
            "tool": "lookup_known_errors",
            "result_count": 3
        },
        duration_ms=250
    )
    
    print("✓ Logging test completed. Check ./test_runs/ for log files.")
