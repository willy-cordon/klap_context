"""Optional Serena MCP adapter.

The package only speaks the public MCP protocol.  It never imports Serena and
is intentionally imported at the provider composition boundary.
"""

from .adapter import SerenaProvider
from .config import SerenaSettings, load_serena_settings, serena_diagnostics

__all__ = ["SerenaProvider", "SerenaSettings", "load_serena_settings", "serena_diagnostics"]
