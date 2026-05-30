import json
import os

_PROMPT_CACHE = None


def _prompt_path():
    return os.path.join(os.path.dirname(__file__), "prompt.json")


def load_prompts():
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        path = _prompt_path()
        with open(path, "r", encoding="utf-8") as f:
            _PROMPT_CACHE = json.load(f)
    return _PROMPT_CACHE


def render_prompt(template, **kwargs):
    rendered = template
    for key, value in kwargs.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return rendered
