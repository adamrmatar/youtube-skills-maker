from src.adapters.antigravity import AntigravityAdapter
from src.adapters.cursor import CursorAdapter
from src.adapters.claude import ClaudeAdapter
from src.adapters.copilot import CopilotAdapter
from src.adapters.windsurf import WindsurfAdapter

ALL_ADAPTERS = {
    "antigravity": AntigravityAdapter(),
    "cursor": CursorAdapter(),
    "claude": ClaudeAdapter(),
    "copilot": CopilotAdapter(),
    "windsurf": WindsurfAdapter()
}

def get_adapters(enabled_names=None):
    """
    Returns instances of adapters matching enabled_names.
    If enabled_names is None, returns all adapters.
    """
    if enabled_names is None:
        return list(ALL_ADAPTERS.values())
        
    adapters = []
    for name in enabled_names:
        if name in ALL_ADAPTERS:
            adapters.append(ALL_ADAPTERS[name])
        else:
            print(f"[Adapters] Warning: Unknown adapter '{name}' requested.")
    return adapters
