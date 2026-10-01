"""Model-independent routing seam; identity, memory, and tools stay outside it."""
DEFAULT_MODEL = 'qwen3:8b'
ALLOWLIST = (DEFAULT_MODEL,)

def choose(requested=None):
    """Return an installed/approved model name, failing closed to the default."""
    return requested if isinstance(requested, str) and requested in ALLOWLIST else DEFAULT_MODEL

def describe():
    return {'default': DEFAULT_MODEL, 'allowlist': list(ALLOWLIST),
            'future_slots': ['coding', 'deep_reasoning'], 'downloads_enabled': False}
