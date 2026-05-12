"""
Configuration Management for FailBot

Loads and manages configuration from prompts.yaml and environment variables.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
import yaml

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


@dataclass
class FailBotConfig:
    """Configuration object for FailBot pipeline."""
    
    models: Dict[str, str] = field(default_factory=dict)
    temperature: float = 0.7
    max_tokens_per_call: int = 2000
    
    token_limits: Dict[str, int] = field(default_factory=dict)
    fuzzy_match: Dict[str, Any] = field(default_factory=dict)
    retry: Dict[str, Any] = field(default_factory=dict)
    
    prompts: Dict[str, Dict[str, str]] = field(default_factory=dict)
    error_messages: Dict[str, str] = field(default_factory=dict)
    logging: Dict[str, str] = field(default_factory=dict)
    
    _config_path: Optional[Path] = None
    
    def get_prompt(self, agent_name: str, prompt_key: str) -> str:
        """
        Get a prompt template for an agent.
        
        Args:
            agent_name: Name of the agent (e.g., "log_parser", "triage")
            prompt_key: Key within the agent's prompts (e.g., "system", "retry_on_parse_fail")
        
        Returns:
            The prompt template string
        
        Raises:
            KeyError: If agent_name or prompt_key not found
        """
        if agent_name not in self.prompts:
            raise KeyError(f"Agent '{agent_name}' not found in config")
        
        if prompt_key not in self.prompts[agent_name]:
            raise KeyError(f"Prompt key '{prompt_key}' not found for agent '{agent_name}'")
        
        return self.prompts[agent_name][prompt_key]
    
    def get_model(self, role: str) -> str:
        """
        Get the model name for a specific role.
        
        Args:
            role: Role name (e.g., "parser", "triage", "test_suggester")
        
        Returns:
            Model name (e.g., "gpt-4o-mini")
        
        Raises:
            KeyError: If role not found
        """
        if role not in self.models:
            raise KeyError(f"Model role '{role}' not found in config")
        return self.models[role]
    
    def get_token_limit(self, node_name: str) -> int:
        """
        Get token limit for a specific node.
        
        Args:
            node_name: Node name (e.g., "ingest", "parse_log", "triage")
        
        Returns:
            Token limit (default: max_tokens_per_call if not specified)
        """
        return self.token_limits.get(node_name, self.max_tokens_per_call)


def load_config(config_path: Optional[str] = None) -> FailBotConfig:
    """
    Load FailBot configuration from YAML file and environment variables.
    
    Args:
        config_path: Path to prompts.yaml. If None, searches in:
            1. FAILBOT_CONFIG env var
            2. ./config/prompts.yaml
            3. ../config/prompts.yaml (for scripts in subdirectories)
    
    Returns:
        Loaded FailBotConfig object
    
    Raises:
        FileNotFoundError: If config file not found
        yaml.YAMLError: If YAML is malformed
    """
    
    if load_dotenv is not None:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)

    # Determine config path
    resolved_path: Optional[str] = config_path
    if resolved_path is None:
        # Check environment variable
        env_config = os.getenv("FAILBOT_CONFIG")
        if env_config is not None:
            resolved_path = env_config
        
        if resolved_path is None:
            # Search in common locations
            for potential_path in [
                Path("config/prompts.yaml"),
                Path(__file__).parent.parent / "config" / "prompts.yaml",
                Path(__file__).parent / ".." / ".." / "config" / "prompts.yaml",
            ]:
                if potential_path.exists():
                    resolved_path = str(potential_path)
                    break
            
            if resolved_path is None:
                raise FileNotFoundError(
                    "config/prompts.yaml not found. Set FAILBOT_CONFIG env var or place file in config/ directory"
                )
    
    # At this point, resolved_path is guaranteed to be a string
    config_path_obj: Path = Path(resolved_path)
    if not config_path_obj.exists():
        raise FileNotFoundError(f"Config file not found: {config_path_obj}")
    
    # Load YAML
    with open(config_path_obj, 'r') as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}
    
    # Override with environment variables
    models: Dict[str, str] = data.get("models", {})
    
    parser_model = os.getenv("FAILBOT_PARSER_MODEL") or os.getenv("PARSER_MODEL") or os.getenv("MODEL_NAME")
    if parser_model is not None:
        models["parser"] = parser_model

    triage_model = os.getenv("FAILBOT_TRIAGE_MODEL") or os.getenv("TRIAGE_MODEL") or os.getenv("MODEL_NAME")
    if triage_model is not None:
        models["triage"] = triage_model

    test_model = os.getenv("FAILBOT_TEST_MODEL") or os.getenv("TEST_MODEL") or os.getenv("MODEL_NAME")
    if test_model is not None:
        models["test_suggester"] = test_model

    temp_env = os.getenv("FAILBOT_TEMPERATURE") or os.getenv("TEMPERATURE")
    if temp_env is not None:
        try:
            data["temperature"] = float(temp_env)
        except ValueError as exc:
            raise ValueError(
                f"Invalid FAILBOT_TEMPERATURE value: {temp_env!r} (must be a number)"
            ) from exc

    max_tokens_env = os.getenv("FAILBOT_MAX_TOKENS_PER_CALL") or os.getenv("MAX_TOKENS_PER_CALL")
    if max_tokens_env is not None:
        try:
            data["max_tokens_per_call"] = int(max_tokens_env)
        except ValueError as exc:
            raise ValueError(
                f"Invalid FAILBOT_MAX_TOKENS_PER_CALL value: {max_tokens_env!r} (must be an integer)"
            ) from exc
    
    # Create config object
    config = FailBotConfig(
        models=models or {},
        temperature=data.get("temperature", 0.7),
        max_tokens_per_call=data.get("max_tokens_per_call", 2000),
        token_limits=data.get("token_limits", {}),
        fuzzy_match=data.get("fuzzy_match", {}),
        retry=data.get("retry", {}),
        prompts=data.get("prompts", {}),
        error_messages=data.get("error_messages", {}),
        logging=data.get("logging", {}),
        _config_path=config_path_obj,
    )
    
    # Validate required fields
    _validate_config(config)
    
    return config


def _validate_config(config: FailBotConfig) -> None:
    """
    Validate that config has all required fields.
    
    Args:
        config: FailBotConfig to validate
    
    Raises:
        ValueError: If required fields are missing
    """
    required_agents = ["parser", "triage", "test_suggester"]
    for agent in required_agents:
        if agent not in config.models:
            raise ValueError(f"Missing model configuration for agent: {agent}")
    
    required_prompts = ["log_parser", "triage", "test_suggester"]
    for prompt_agent in required_prompts:
        if prompt_agent not in config.prompts:
            raise ValueError(f"Missing prompt configuration for agent: {prompt_agent}")
        
        if "system" not in config.prompts[prompt_agent]:
            raise ValueError(f"Missing 'system' prompt for agent: {prompt_agent}")


# Singleton config instance
_config_instance: Optional[FailBotConfig] = None


def get_config(reload: bool = False, config_path: Optional[str] = None) -> FailBotConfig:
    """
    Get or create singleton FailBotConfig instance.
    
    Args:
        reload: If True, reload config from disk
        config_path: If provided, load from this path
    
    Returns:
        FailBotConfig instance
    """
    global _config_instance
    
    if _config_instance is None or reload:
        _config_instance = load_config(config_path)
    
    return _config_instance


if __name__ == "__main__":
    # Test config loading
    try:
        cfg = load_config()
        print(f"✓ Config loaded successfully")
        print(f"  Models: {cfg.models}")
        print(f"  Temperature: {cfg.temperature}")
        print(f"  Log Parser Model: {cfg.get_model('parser')}")
        print(f"  Sample Prompt (first 100 chars): {cfg.get_prompt('log_parser', 'system')[:100]}...")
    except Exception as e:
        print(f"✗ Error loading config: {e}")
