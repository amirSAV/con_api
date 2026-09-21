import time
from typing import Optional

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.align import Align
    from rich.progress import SpinnerColumn, Progress, TextColumn, BarColumn, TaskProgressColumn
    from rich.spinner import Spinner
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None
    Live = None


# Fallback ANSI colors
ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "cyan": "\033[96m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "magenta": "\033[95m",
    "blue": "\033[94m",
    "red": "\033[91m",
    "dim": "\033[2m",
    "white": "\033[97m",
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class SimpleLiveDisplay:
    """Fallback live display without rich - uses ANSI and simple updates."""

    def __init__(self, model: str, enable_thinking: bool):
        self.model = model
        self.enable_thinking = enable_thinking
        self.start_time = time.time()
        self.state = "CONNECTING"
        self.thinking = ""
        self.answer = ""
        self.prompt_tokens = 0
        self.completion_estimate = 0
        self.usage = {}

    def __enter__(self):
        print(f"{ANSI['cyan']}{ANSI['bold']}┌─ Live Model Status ─────────────────────────────────────{ANSI['reset']}")
        print(f"{ANSI['yellow']}◐ Connecting to {self.model}...{ANSI['reset']}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def update(self, state: str = None, thinking: str = None, answer: str = None, prompt_tokens: int = None, usage: dict = None):
        if state:
            self.state = state
        if thinking is not None:
            self.thinking = thinking
        if answer is not None:
            self.answer = answer
        if prompt_tokens is not None:
            self.prompt_tokens = prompt_tokens
        if usage is not None:
            self.usage = usage
        # For simple, we don't re-render every time to avoid flood, just occasional
        # The caller throttles, so we can print status every update
        self._render_simple()

    def _render_simple(self):
        elapsed = time.time() - self.start_time
        state_color = {
            "CONNECTING": ANSI["yellow"],
            "THINKING": ANSI["magenta"],
            "WRITING": ANSI["green"],
            "FINISHED": ANSI["cyan"],
        }.get(self.state, ANSI["white"])
        comp_est = estimate_tokens(self.thinking + self.answer)
        # Clear line and print status
        # Use carriage return for live update
        status = f"\r{state_color}State: {self.state}{ANSI['reset']} | Elapsed: {elapsed:.1f}s | Prompt: {self.prompt_tokens} | Completion: {comp_est} | Thinking: {len(self.thinking)} chars | Answer: {len(self.answer)} chars   "
        # Print without newline, flush
        try:
            print(status, end="", flush=True)
        except Exception:
            pass

    def finish(self, usage: dict = None):
        self.state = "FINISHED"
        if usage:
            self.usage = usage
            self.prompt_tokens = usage.get("prompt_tokens", self.prompt_tokens)
        # Print final newline and summary
        print()  # newline after live updates
        elapsed = time.time() - self.start_time
        if self.usage:
            prompt_t = self.usage.get("prompt_tokens", "?")
            comp_t = self.usage.get("completion_tokens", estimate_tokens(self.thinking + self.answer))
            total_t = self.usage.get("total_tokens", "?")
            speed = comp_t / elapsed if isinstance(comp_t, int) and elapsed > 0 else 0
            print(f"{ANSI['bold']}{ANSI['green']}✓ Finished{ANSI['reset']} | Elapsed: {elapsed:.2f}s | Speed: {speed:.1f} tok/s")
            print(f"{ANSI['cyan']}Prompt: {prompt_t} | Completion: {comp_t} | Total: {total_t}{ANSI['reset']}")
        if self.enable_thinking and self.thinking:
            print(f"{ANSI['magenta']}Thinking: {len(self.thinking)} chars{ANSI['reset']}")
        if self.answer:
            print(f"{ANSI['green']}Answer: {len(self.answer)} chars{ANSI['reset']}")
        print(f"{ANSI['bold']}└──────────────────────────────────────────────────────{ANSI['reset']}")


class RichLiveDisplay:
    """Pretty live display using rich with panels, tables, spinners."""

    def __init__(self, model: str, enable_thinking: bool, console: Optional[Console] = None):
        self.model = model
        self.enable_thinking = enable_thinking
        self.console = console or Console()
        self.start_time = time.time()
        self.state = "CONNECTING"
        self.thinking = ""
        self.answer = ""
        self.prompt_tokens = 0
        self.usage = {}
        self.live: Optional[Live] = None

    def __enter__(self):
        self.live = Live(self._build_layout(), console=self.console, refresh_per_second=12, transient=False)
        self.live.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.live:
            self.live.__exit__(exc_type, exc_val, exc_tb)

    def update(self, state: str = None, thinking: str = None, answer: str = None, prompt_tokens: int = None, usage: dict = None):
        if state:
            self.state = state
        if thinking is not None:
            self.thinking = thinking
        if answer is not None:
            self.answer = answer
        if prompt_tokens is not None:
            self.prompt_tokens = prompt_tokens
        if usage is not None:
            self.usage = usage
        if self.live:
            self.live.update(self._build_layout())

    def _build_layout(self):
        elapsed = time.time() - self.start_time

        # State with spinner and color
        state_config = {
            "CONNECTING": ("yellow", "dots", "Connecting"),
            "THINKING": ("magenta", "dots2", "Thinking"),
            "WRITING": ("green", "dots3", "Writing"),
            "FINISHED": ("cyan", "star", "Finished"),
        }
        color, spinner_name, label = state_config.get(self.state, ("white", "dots", self.state))

        # Create spinner text for current state
        if self.state in ("THINKING", "WRITING", "CONNECTING"):
            try:
                spinner = Spinner(spinner_name, text=f"[{color}]{label}[/{color}]", style=color)
                # Render spinner as text for table
                state_display = f"[{color}]{label}[/{color}]"
            except Exception:
                state_display = f"[{color}]{label}[/{color}]"
        else:
            state_display = f"[{color}]✓ {label}[/{color}]"

        # Header table with model, state, elapsed
        header_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        header_table.add_column("left", justify="left", ratio=2)
        header_table.add_column("center", justify="center", ratio=1)
        header_table.add_column("right", justify="right", ratio=1)
        header_table.add_row(
            f"[bold cyan]Model:[/bold cyan] [white]{self.model}[/white]",
            state_display,
            f"[dim]⏱ Elapsed: {elapsed:.1f}s[/dim]",
        )

        # Token info with pretty table
        comp_est = estimate_tokens(self.thinking + self.answer)
        total_est = self.prompt_tokens + comp_est if self.prompt_tokens else comp_est

        # Build token table
        token_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1), expand=True)
        token_table.add_column("Prompt", justify="center", style="cyan")
        token_table.add_column("Completion", justify="center", style="green")
        token_table.add_column("Total", justify="center", style="bold white")
        token_table.add_column("Speed", justify="center", style="yellow")
        token_table.add_column("Thinking", justify="center", style="magenta")
        token_table.add_column("Answer", justify="center", style="green")

        if self.usage and self.usage.get("prompt_tokens") is not None:
            prompt_t = self.usage.get("prompt_tokens", self.prompt_tokens)
            comp_t = self.usage.get("completion_tokens", comp_est)
            total_t = self.usage.get("total_tokens", prompt_t + comp_t if isinstance(prompt_t, int) and isinstance(comp_t, int) else "?")
            speed = comp_t / elapsed if isinstance(comp_t, int) and elapsed > 0 else 0
            th_chars = len(self.thinking)
            ans_chars = len(self.answer)
            token_table.add_row(
                str(prompt_t),
                str(comp_t),
                str(total_t),
                f"{speed:.1f} tok/s",
                f"{th_chars} chars",
                f"{ans_chars} chars",
            )
        else:
            prompt_disp = str(self.prompt_tokens) if self.prompt_tokens else "?"
            th_chars = len(self.thinking)
            ans_chars = len(self.answer)
            speed_est = comp_est / elapsed if elapsed > 0 and comp_est else 0
            token_table.add_row(
                prompt_disp,
                f"~{comp_est}",
                f"~{total_est}",
                f"{speed_est:.1f} tok/s",
                f"{th_chars} chars",
                f"{ans_chars} chars",
            )

        # Build panels
        panels = []
        # Header panel with status
        panels.append(Panel(header_table, title="[bold blue]● Live Model Status[/bold blue]", border_style="blue", padding=(0, 1)))

        # Thinking panel
        if self.enable_thinking:
            if self.thinking:
                # Show thinking with syntax highlighting-like, last 1000 chars
                thinking_preview = self.thinking[-1000:] if len(self.thinking) > 1000 else self.thinking
                # Use Text with magenta, add icon
                thinking_text = Text(thinking_preview, style="magenta")
                th_tokens = estimate_tokens(self.thinking)
                panels.append(
                    Panel(
                        thinking_text,
                        title=f"[magenta]🧠 Thinking[/magenta] [dim]({len(self.thinking)} chars / ~{th_tokens} tokens) ─ {self.state}[/dim]",
                        border_style="magenta",
                        padding=(0, 1),
                    )
                )
            else:
                if self.state == "THINKING":
                    panels.append(
                        Panel(
                            Align.center(Text("Thinking in progress...", style="dim magenta")),
                            title="[magenta]🧠 Thinking[/magenta] [yellow](active)[/yellow]",
                            border_style="magenta",
                        )
                    )
                elif self.state == "CONNECTING":
                    panels.append(
                        Panel(
                            Align.center(Text("Waiting for model...", style="dim")),
                            title="[magenta]🧠 Thinking[/magenta] [dim](waiting)[/dim]",
                            border_style="dim",
                        )
                    )
                else:
                    # When thinking disabled or no thinking yet but writing
                    if not self.enable_thinking:
                        panels.append(
                            Panel(
                                Align.center(Text("Thinking disabled", style="dim")),
                                title="[magenta]🧠 Thinking[/magenta] [dim](disabled)[/dim]",
                                border_style="dim",
                            )
                        )
                    else:
                        panels.append(
                            Panel(
                                Align.center(Text("No thinking yet", style="dim")),
                                title="[magenta]🧠 Thinking[/magenta] [dim](empty)[/dim]",
                                border_style="dim",
                            )
                        )

        # Answer panel
        if self.answer:
            ans_preview = self.answer[-1500:] if len(self.answer) > 1500 else self.answer
            ans_text = Text(ans_preview, style="green")
            ans_tokens = estimate_tokens(self.answer)
            # Determine if answer is complete or streaming
            status_icon = "✍️" if self.state == "WRITING" else "✅" if self.state == "FINISHED" else "📝"
            panels.append(
                Panel(
                    ans_text,
                    title=f"[green]{status_icon} Answer[/green] [dim]({len(self.answer)} chars / ~{ans_tokens} tokens)[/dim]",
                    border_style="green",
                    padding=(0, 1),
                )
            )
        else:
            if self.state == "WRITING":
                panels.append(
                    Panel(
                        Align.center(Text("Generating answer...", style="dim green")),
                        title="[green]✍️ Answer[/green] [yellow](generating)[/yellow]",
                        border_style="green",
                    )
                )
            elif self.state == "FINISHED":
                panels.append(
                    Panel(
                        Align.center(Text("No answer", style="dim")),
                        title="[green]Answer[/green] [dim](empty)[/dim]",
                        border_style="dim",
                    )
                )
            else:
                panels.append(
                    Panel(
                        Align.center(Text("Waiting for answer...", style="dim")),
                        title="[green]Answer[/green] [dim](waiting)[/dim]",
                        border_style="dim",
                    )
                )

        # Footer with token table
        panels.append(Panel(token_table, title="[bold cyan]📊 Token Usage[/bold cyan]", border_style="cyan", padding=(0, 1)))

        # Combine
        group = Group(*panels)
        return group

    def finish(self, usage: dict = None):
        self.state = "FINISHED"
        if usage:
            self.usage = usage
        if self.live:
            self.live.update(self._build_layout())
            time.sleep(0.3)


def create_live_display(model: str, enable_thinking: bool, use_rich: bool = True):
    """Factory to create appropriate live display."""
    if use_rich and RICH_AVAILABLE:
        return RichLiveDisplay(model, enable_thinking)
    else:
        return SimpleLiveDisplay(model, enable_thinking)
