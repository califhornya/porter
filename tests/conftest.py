import sys
import types

# Provide a lightweight OpenAI stub for environments without the real package installed.
if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class OpenAI:  # type: ignore
        def __init__(self, *_, **__):
            pass

    openai_stub.OpenAI = OpenAI
    openai_stub.__version__ = "0.0.0"
    sys.modules["openai"] = openai_stub
