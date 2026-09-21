import json
import os
import sys


DEFAULTS = {
    "history_file": "history.json",
    "temperature": 0.7,
    "timeout": 60,
    "enable_thinking": True,
    "prompt": "",
    "prompt_file": "",
    "system_prompt": "",
    "system_prompt_file": "",
    "output_file": "",
    "live_display": True,
    "stream": True,
}


def _read_text_file(path: str) -> str | None:
    """Read text file with utf-8, return stripped content or None on failure."""
    if not path or not str(path).strip():
        return None
    p = str(path).strip()
    if not os.path.exists(p):
        print(f"Warning: prompt file '{p}' not found. Falling back to inline value.")
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        # Keep internal whitespace but strip leading/trailing
        if content.strip() == "":
            print(f"Warning: prompt file '{p}' is empty.")
            return None
        return content.strip()
    except OSError as e:
        print(f"Warning: could not read prompt file '{p}': {e}")
        return None


def load_config(path: str) -> dict:
    """Load config.json with validation and defaults.

    Features:
    - api_key is now OPTIONAL (can be empty / missing)
    - enable_thinking controls reasoning toggle
    - prompt can be empty -> asked at runtime
    - prompt_file / system_prompt_file allow loading long prompts from txt
    - max_tokens == 0 means unlimited (no limit sent to API)
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(f"Error: config file '{path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in config: {e}")
        sys.exit(1)

    # Only api_url and model are strictly required now
    required = ["api_url", "model"]
    for key in required:
        if key not in cfg or not str(cfg[key]).strip():
            print(f"Error: missing required key '{key}' in config.")
            sys.exit(1)

    # Apply defaults for optional keys
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)

    # Normalize api_key -> allow empty / missing
    if "api_key" not in cfg or cfg["api_key"] is None:
        cfg["api_key"] = ""
    cfg["api_key"] = str(cfg["api_key"]).strip()

    # Normalize enable_thinking -> bool
    et = cfg.get("enable_thinking", True)
    if isinstance(et, str):
        cfg["enable_thinking"] = et.lower() in ("1", "true", "yes", "on")
    else:
        cfg["enable_thinking"] = bool(et)

    # Normalize prompt and file fields
    if cfg.get("prompt") is None:
        cfg["prompt"] = ""
    cfg["prompt"] = str(cfg["prompt"])

    if cfg.get("prompt_file") is None:
        cfg["prompt_file"] = ""
    cfg["prompt_file"] = str(cfg["prompt_file"]).strip()

    if cfg.get("system_prompt") is None:
        cfg["system_prompt"] = ""
    cfg["system_prompt"] = str(cfg["system_prompt"])

    if cfg.get("system_prompt_file") is None:
        cfg["system_prompt_file"] = ""
    cfg["system_prompt_file"] = str(cfg["system_prompt_file"]).strip()

    if cfg.get("output_file") is None:
        cfg["output_file"] = ""
    cfg["output_file"] = str(cfg["output_file"]).strip()

    # Normalize live_display and stream -> bool
    for bool_key in ("live_display", "stream"):
        if bool_key in cfg:
            val = cfg[bool_key]
            if isinstance(val, str):
                cfg[bool_key] = val.lower() in ("1", "true", "yes", "on")
            else:
                cfg[bool_key] = bool(val)
        else:
            cfg[bool_key] = DEFAULTS[bool_key]

    # Normalize max_tokens: 0 => unlimited (remove limit)
    if "max_tokens" in cfg:
        try:
            cfg["max_tokens"] = int(cfg["max_tokens"])
        except (ValueError, TypeError):
            print("Warning: max_tokens should be int, ignoring.")
            cfg.pop("max_tokens", None)

    # Normalize timeout: 0 or invalid -> default 60
    if "timeout" in cfg:
        try:
            t = int(cfg["timeout"])
            if t <= 0:
                print("Warning: timeout is 0 or negative, using default 60.")
                cfg["timeout"] = 60
            else:
                cfg["timeout"] = t
        except (ValueError, TypeError):
            print("Warning: timeout should be int, using default 60.")
            cfg["timeout"] = 60

    return cfg


def resolve_system_prompt(config: dict) -> str:
    """Resolve system prompt: file takes precedence over inline."""
    # Check file first
    file_content = _read_text_file(config.get("system_prompt_file", ""))
    if file_content is not None:
        return file_content
    # Fallback to inline
    sp = config.get("system_prompt", "")
    if isinstance(sp, str) and sp.strip():
        return sp.strip()
    return ""


def resolve_prompt(config: dict) -> str:
    """Return user prompt: prompt_file > prompt > interactive input."""
    # 1. Try prompt_file
    file_content = _read_text_file(config.get("prompt_file", ""))
    if file_content is not None:
        return file_content

    # 2. Try inline prompt
    prompt = config.get("prompt", "")
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()

    # 3. Config prompt is empty -> ask at runtime
    print("Prompt is empty in config. Please enter your prompt:")
    try:
        user_prompt = input("Prompt > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nNo prompt provided. Exiting.")
        sys.exit(0)

    if not user_prompt:
        print("Error: prompt cannot be empty.")
        sys.exit(1)
    return user_prompt
