"""
Prompt Template Utilities

Handles rendering and formatting of prompt templates.
"""

from typing import Dict, Any, Optional
from src.config import get_config


class PromptRenderer:
    """Renders prompt templates with context variables."""
    
    def __init__(self, config=None):
        """
        Initialize prompt renderer.
        
        Args:
            config: FailBotConfig instance (uses singleton if None)
        """
        self.config = config or get_config()
    
    def render(self, template: str, **kwargs) -> str:
        """
        Simple template rendering using format().
        
        Args:
            template: Template string with {variable} placeholders
            **kwargs: Values to fill in
        
        Returns:
            Rendered template
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")
    
    def render_from_config(
        self,
        agent_name: str,
        prompt_key: str = "system",
        **kwargs
    ) -> str:
        """
        Render a prompt template from config.
        
        Args:
            agent_name: Agent name (e.g., "log_parser", "triage")
            prompt_key: Prompt key (e.g., "system", "retry_on_parse_fail")
            **kwargs: Context variables to fill in
        
        Returns:
            Rendered prompt
        
        Raises:
            KeyError: If agent or prompt key not found
            ValueError: If template variable not provided
        """
        template = self.config.get_prompt(agent_name, prompt_key)
        return self.render(template, **kwargs)


# Singleton renderer instance
_renderer_instance: Optional[PromptRenderer] = None


def get_prompt_renderer(config=None) -> PromptRenderer:
    """
    Get or create singleton PromptRenderer instance.
    
    Args:
        config: Optional FailBotConfig
    
    Returns:
        PromptRenderer instance
    """
    global _renderer_instance
    
    if _renderer_instance is None:
        _renderer_instance = PromptRenderer(config)
    
    return _renderer_instance


def render_prompt(template: str, **kwargs) -> str:
    """
    Quick function to render a prompt template.
    
    Args:
        template: Template string
        **kwargs: Context variables
    
    Returns:
        Rendered template
    """
    renderer = get_prompt_renderer()
    return renderer.render(template, **kwargs)


def render_agent_prompt(
    agent_name: str,
    prompt_key: str = "system",
    **kwargs
) -> str:
    """
    Quick function to render an agent prompt from config.
    
    Args:
        agent_name: Agent name
        prompt_key: Prompt key
        **kwargs: Context variables
    
    Returns:
        Rendered prompt
    """
    renderer = get_prompt_renderer()
    return renderer.render_from_config(agent_name, prompt_key, **kwargs)


# Test
if __name__ == "__main__":
    renderer = get_prompt_renderer()
    
    # Test simple rendering
    template = "Hello, {name}! The error is: {error}"
    rendered = renderer.render(template, name="Agent", error="TypeError")
    print(f"✓ Rendered: {rendered}")
    
    # Test config-based rendering
    try:
        prompt = render_agent_prompt("log_parser", "system")
        print(f"✓ Loaded log parser prompt ({len(prompt)} chars)")
    except Exception as e:
        print(f"✗ Error: {e}")
