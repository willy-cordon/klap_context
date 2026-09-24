"""Built-in evidence providers. More engines can implement AnalysisProvider later."""
from .graphify import GraphifyProvider


def default_provider() -> GraphifyProvider:
    return GraphifyProvider()
