"""
LangGraph Callbacks for FailBot

Implements callbacks for LangGraph to capture and log events.
"""

import time
import logging
from typing import Any, Dict, List, Optional, Union
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class FailBotEventLogger(BaseCallbackHandler):
    """
    LangGraph callback handler that logs all events to a logger.
    
    Captures LLM calls, tool calls, and other events with full context.
    """
    
    def __init__(self, logger: logging.Logger, run_id: str):
        """
        Initialize event logger callback.
        
        Args:
            logger: Logger instance to write events to
            run_id: Run ID for this execution
        """
        super().__init__()
        self.logger = logger
        self.run_id = run_id
        self.start_times: Dict[str, float] = {}
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any
    ) -> None:
        """Called when an LLM is about to start."""
        node_name = kwargs.get("node_name", "unknown")
        self.start_times[node_name] = time.time()
        
        # Log LLM call start
        record = logging.LogRecord(
            name="failbot",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="LLM call started",
            args=(),
            exc_info=None
        )
        
        record.run_id = self.run_id
        record.node = node_name
        record.event_type = "llm_start"
        record.data = {
            "model": serialized.get("name", "unknown"),
            "num_prompts": len(prompts),
            "first_prompt_length": len(prompts[0]) if prompts else 0,
        }
        
        self.logger.handle(record)
    
    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any
    ) -> None:
        """Called when an LLM finishes."""
        node_name = kwargs.get("node_name", "unknown")
        start_time = self.start_times.pop(node_name, None)
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        
        # Count tokens
        total_input_tokens = 0
        total_output_tokens = 0
        
        if hasattr(response, 'llm_output'):
            llm_output = response.llm_output or {}
            if isinstance(llm_output, dict):
                usage = llm_output.get('usage', {})
                total_input_tokens = usage.get('prompt_tokens', 0)
                total_output_tokens = usage.get('completion_tokens', 0)
        
        # Log LLM call end
        record = logging.LogRecord(
            name="failbot",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="LLM call completed",
            args=(),
            exc_info=None
        )
        
        record.run_id = self.run_id
        record.node = node_name
        record.event_type = "llm_end"
        record.duration_ms = duration_ms
        record.data = {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "generations": len(response.generations) if response.generations else 0,
        }
        
        self.logger.handle(record)
    
    def on_llm_error(
        self,
        error: BaseException,
        **kwargs: Any
    ) -> None:
        """Called when an LLM call errors."""
        node_name = kwargs.get("node_name", "unknown")
        start_time = self.start_times.pop(node_name, None)
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        
        record = logging.LogRecord(
            name="failbot",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="LLM call failed",
            args=(),
            exc_info=None
        )
        
        record.run_id = self.run_id
        record.node = node_name
        record.event_type = "llm_error"
        record.duration_ms = duration_ms
        record.data = {
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        
        self.logger.handle(record)
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool is about to run."""
        node_name = kwargs.get("node_name", "unknown")
        tool_name = serialized.get("name", "unknown")
        self.start_times[f"{node_name}_tool"] = time.time()
        
        record = logging.LogRecord(
            name="failbot",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Tool call started",
            args=(),
            exc_info=None
        )
        
        record.run_id = self.run_id
        record.node = node_name
        record.event_type = "tool_start"
        record.data = {
            "tool_name": tool_name,
            "input_length": len(input_str),
        }
        
        self.logger.handle(record)
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool finishes."""
        node_name = kwargs.get("node_name", "unknown")
        start_time = self.start_times.pop(f"{node_name}_tool", None)
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        
        record = logging.LogRecord(
            name="failbot",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Tool call completed",
            args=(),
            exc_info=None
        )
        
        output_length = 0
        if isinstance(output, str):
            output_length = len(output)
        elif hasattr(output, "content"):
            try:
                output_length = len(output.content)
            except TypeError:
                output_length = len(str(output.content))
        else:
            try:
                output_length = len(output)
            except TypeError:
                output_length = len(str(output))

        record.run_id = self.run_id
        record.node = node_name
        record.event_type = "tool_end"
        record.duration_ms = duration_ms
        record.data = {
            "output_length": output_length,
            "success": True,
        }
        
        self.logger.handle(record)
    
    def on_tool_error(
        self,
        error: BaseException,
        **kwargs: Any
    ) -> None:
        """Called when a tool errors."""
        node_name = kwargs.get("node_name", "unknown")
        start_time = self.start_times.pop(f"{node_name}_tool", None)
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        
        record = logging.LogRecord(
            name="failbot",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Tool call failed",
            args=(),
            exc_info=None
        )
        
        record.run_id = self.run_id
        record.node = node_name
        record.event_type = "tool_error"
        record.duration_ms = duration_ms
        record.data = {
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        
        self.logger.handle(record)
