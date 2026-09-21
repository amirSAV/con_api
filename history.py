import json
import os
from datetime import datetime, timezone


def load_history(path: str) -> list:
    """Load history; support both old simple format and new readable format."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        # If file contains single object (unlikely), wrap
        if isinstance(data, dict):
            return [data]
        return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: could not read history ({e}). Starting with empty history.")
        return []


def save_history(path: str, history: list):
    """Save history in pretty, human-readable JSON."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"Warning: failed to save history: {e}")


def build_history_entry(
    config: dict,
    user_prompt: str,
    result: dict,
) -> dict:
    """Build a new highly readable history entry with token usage and thinking separated."""
    now = datetime.now(timezone.utc).astimezone().isoformat()

    usage = result.get("usage", {}) or {}
    # Normalize usage fields
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")

    # Some servers use different names
    if prompt_tokens is None:
        prompt_tokens = usage.get("promptTokenCount") or usage.get("input_tokens")
    if completion_tokens is None:
        completion_tokens = usage.get("completionTokenCount") or usage.get("output_tokens")
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        try:
            total_tokens = int(prompt_tokens) + int(completion_tokens)
        except Exception:
            total_tokens = None

    entry = {
        "timestamp": now,
        "model": config.get("model"),
        "api_url": config.get("api_url"),
        "enable_thinking": config.get("enable_thinking", True),
        "temperature": config.get("temperature"),
        "max_tokens": config.get("max_tokens"),  # 0 means unlimited
        "max_tokens_effective": "unlimited" if config.get("max_tokens") == 0 else config.get("max_tokens"),
        "system_prompt": config.get("system_prompt", ""),
        "system_prompt_file": config.get("system_prompt_file", ""),
        "system_prompt_source": config.get("_system_prompt_source", "inline"),
        "user_prompt": user_prompt,
        "prompt_file": config.get("prompt_file", ""),
        "prompt_source": config.get("_prompt_source", "inline"),
        "thinking": result.get("thinking", "") or "",
        "answer": result.get("content", "") or "",
        "raw_content": result.get("raw_content", "") or "",
        "output_file": config.get("output_file", ""),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "raw": usage,  # keep raw in case of extra fields
        },
    }
    return entry


def format_entry_human(entry: dict) -> str:
    """Return a pretty printed human-readable version for console."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"Time: {entry.get('timestamp')}")
    lines.append(f"Model: {entry.get('model')}  |  URL: {entry.get('api_url')}")
    lines.append(f"Thinking enabled: {entry.get('enable_thinking')}  |  Temp: {entry.get('temperature')}  |  MaxTokens: {entry.get('max_tokens_effective')}")
    lines.append("-" * 60)
    # Show system prompt source if from file
    sp_file = entry.get("system_prompt_file", "")
    sp_source = entry.get("system_prompt_source", "")
    if sp_file:
        lines.append(f"System prompt file: {sp_file} (source: {sp_source})")
        # Don't dump full system prompt in header to keep readable, but show length
        sp = entry.get("system_prompt", "")
        if sp:
            lines.append(f"System prompt chars: {len(sp)}")
        lines.append("-" * 60)
    prompt_file = entry.get("prompt_file", "")
    prompt_source = entry.get("prompt_source", "")
    if prompt_file:
        lines.append(f"User prompt file: {prompt_file} (source: {prompt_source})")
        lines.append("-" * 60)
    lines.append("User Prompt:")
    lines.append(entry.get("user_prompt", ""))
    lines.append("-" * 60)
    thinking = entry.get("thinking", "")
    if thinking:
        lines.append("Thinking (separated):")
        lines.append(thinking)
        lines.append("-" * 60)
    else:
        lines.append("Thinking: (empty / disabled)")
        lines.append("-" * 60)
    lines.append("Answer:")
    lines.append(entry.get("answer", ""))
    lines.append("-" * 60)
    usage = entry.get("usage", {})
    lines.append("Token Usage:")
    lines.append(f"  prompt_tokens: {usage.get('prompt_tokens')}")
    lines.append(f"  completion_tokens: {usage.get('completion_tokens')}")
    lines.append(f"  total_tokens: {usage.get('total_tokens')}")
    if usage.get("raw"):
        # Only show raw if it has extra keys beyond the three
        extra = {k: v for k, v in usage.get("raw", {}).items() if k not in ("prompt_tokens", "completion_tokens", "total_tokens", "promptTokenCount", "completionTokenCount", "input_tokens", "output_tokens")}
        if extra:
            lines.append(f"  raw_extra: {extra}")
    lines.append("=" * 60)
    return "\n".join(lines)
