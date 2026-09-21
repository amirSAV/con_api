import os
import sys

from config import load_config, resolve_prompt, resolve_system_prompt
from api_client import build_messages, send_request, send_request_stream
from history import load_history, save_history, build_history_entry, format_entry_human


def save_output_file(path: str, content: str):
    """Save only the final answer to txt file, with proper newline handling."""
    if not path or not str(path).strip():
        return
    p = str(path).strip()
    try:
        dir_name = os.path.dirname(p)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        # Handle escaped newlines: convert literal \n to real newlines
        # User requested that \n should become actual line breaks
        processed = content
        if "\\n" in processed:
            try:
                # Decode unicode escapes (\n, \t, etc.)
                processed = processed.encode("utf-8").decode("unicode_escape")
            except Exception:
                processed = processed.replace("\\n", "\n")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(processed)
        print(f"Answer saved to {p} ({len(processed)} chars)")
    except OSError as e:
        print(f"Warning: failed to write output file '{p}': {e}")


CONFIG_FILE = "config.json"


def main():
    config = load_config(CONFIG_FILE)

    # Resolve system prompt from file or inline (file takes precedence)
    resolved_system = resolve_system_prompt(config)
    config["system_prompt"] = resolved_system
    # Optional: keep info about source
    if config.get("system_prompt_file"):
        config["_system_prompt_source"] = f"file:{config['system_prompt_file']}"
    else:
        config["_system_prompt_source"] = "inline"

    history_file = config.get("history_file", "history.json")
    history = load_history(history_file)

    # Single-run mode: get prompt from file / config or ask user
    user_prompt = resolve_prompt(config)
    # Track source for history
    if config.get("prompt_file") and config["prompt_file"].strip():
        # Check if file was actually used (exists and non-empty)
        if os.path.exists(config["prompt_file"].strip()):
            try:
                with open(config["prompt_file"].strip(), "r", encoding="utf-8") as f:
                    if f.read().strip():
                        config["_prompt_source"] = f"file:{config['prompt_file']}"
                    else:
                        config["_prompt_source"] = "inline"
            except OSError:
                config["_prompt_source"] = "inline"
        else:
            config["_prompt_source"] = "inline"
    else:
        config["_prompt_source"] = "inline" if config.get("prompt", "").strip() else "interactive"

    # Build messages (system + history context + new prompt)
    messages = build_messages(config, history, user_prompt)

    live_enabled = config.get("live_display", True) and config.get("stream", True)
    result = None

    if live_enabled:
        # Pretty live display with streaming
        try:
            from live_display import create_live_display

            enable_thinking = config.get("enable_thinking", True)
            model_name = config.get("model", "unknown")

            # Check if we should use rich; create_live_display handles fallback
            with create_live_display(model_name, enable_thinking, use_rich=True) as live:
                result = send_request_stream(config, messages, live_display=live)
                # If streaming failed, fallback to non-streaming
                if result is None:
                    # live will have finished, try non-stream
                    print("\nStreaming failed, falling back to non-streaming...")
                    result = send_request(config, messages)
        except ImportError as e:
            print(f"Live display not available ({e}), using standard request...")
            result = send_request(config, messages)
        except Exception as e:
            print(f"Live display error ({e}), falling back...")
            try:
                result = send_request(config, messages)
            except Exception:
                result = None
    else:
        # Standard non-live request
        print("\nSending request to", config["api_url"], "...")
        print(f"   Model: {config['model']} | Thinking: {config.get('enable_thinking')} | MaxTokens: {'unlimited' if config.get('max_tokens')==0 else config.get('max_tokens')}")
        if resolved_system:
            src = config.get("_system_prompt_source", "inline")
            print(f"   System prompt source: {src} ({len(resolved_system)} chars)")
        if config.get("_prompt_source", "").startswith("file:"):
            print(f"   User prompt source: {config['_prompt_source']} ({len(user_prompt)} chars)")
        print()
        result = send_request(config, messages)

    if result is None:
        # Error already printed in send_request
        sys.exit(1)

    # Build history entry
    entry = build_history_entry(config, user_prompt, result)

    # Append to history and save (full thinking/answer saved in history.json, but not printed to console)
    history.append(entry)
    save_history(history_file, history)

    # Concise final summary (do NOT print full thinking/answer because they may be very long)
    # Live display already showed them streaming; for non-live we also keep output concise
    elapsed = result.get("elapsed", 0)
    usage = result.get("usage", {}) or entry.get("usage", {})
    prompt_t = usage.get("prompt_tokens", "?")
    comp_t = usage.get("completion_tokens", "?")
    total_t = usage.get("total_tokens", "?")
    # Pretty concise summary without full content
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        summary_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1), expand=True)
        summary_table.add_column("Model", justify="center", style="cyan")
        summary_table.add_column("Elapsed", justify="center", style="yellow")
        summary_table.add_column("Prompt", justify="center", style="cyan")
        summary_table.add_column("Completion", justify="center", style="green")
        summary_table.add_column("Total", justify="center", style="bold white")
        summary_table.add_column("History", justify="center", style="dim")
        elapsed_str = f"{elapsed:.2f}s" if isinstance(elapsed, (int, float)) and elapsed else "?"
        summary_table.add_row(
            entry.get("model", "?"),
            elapsed_str,
            str(prompt_t),
            str(comp_t),
            str(total_t),
            f"{len(history)} exchanges",
        )
        console.print(Panel(summary_table, title="[bold green]Done[/bold green]", border_style="green", padding=(0, 1)))
        # Show file locations as markup
        files_info = f"[dim]History:[/dim] [cyan]{history_file}[/cyan]  [dim]Output:[/dim] [green]{config.get('output_file') or '(none)'}[/green]"
        if entry.get("prompt_file"):
            files_info += f"  [dim]Prompt file:[/dim] {entry.get('prompt_file')}"
        console.print(files_info)
    except Exception:
        # Fallback simple
        print(f"\nDone! Model: {entry.get('model')} | Elapsed: {elapsed:.2f}s" if elapsed else f"\nDone! Model: {entry.get('model')}")
        print(f"Token Usage: Prompt {prompt_t} | Completion {comp_t} | Total {total_t}")
        print(f"Saved to {history_file} (total exchanges: {len(history)})")
        if config.get("output_file"):
            print(f"Answer saved to {config.get('output_file')}")

    # Save only final answer to output txt file (no thinking, with proper newlines)
    output_file = config.get("output_file", "")
    if output_file and str(output_file).strip():
        save_output_file(str(output_file).strip(), result.get("content", ""))


if __name__ == "__main__":
    main()
