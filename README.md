# CON API Agent

A powerful command-line interface (CLI) agent framework designed to interact with large language models (LLMs) via API. It manages conversation history, system prompts, and provides detailed, real-time streaming output of the AI's thought process and final response.

## ✨ Features

- **API Integration**: Seamless communication with OpenAI-compatible LLMs.
- **Live Streaming Display**: Real-time visualization of the model's status, thinking process, and generated response using the `rich` library.
- **State Management**: Tracks the agent's state (Connecting, Thinking, Writing, Finished) and token usage throughout the session.
- **History Persistence**: Automatically saves and loads conversation history.
- **Flexible Input**: Supports defining prompts and system messages both inline and via external configuration files.
- **Detailed Metrics**: Provides a concise summary upon completion, including elapsed time, prompt tokens, completion tokens, and total tokens.
- **Thinking Mechanism**: Supports explicit reasoning/thinking blocks, which can be separated from the final answer for clearer output.

## 📋 Prerequisites

- Python 3.10 or higher
- `pip` (Python package installer)

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/amirSAV/con_api.git
   cd con_api
   ```

2. **Set up a virtual environment** (recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## ⚙️ Configuration

Create a `config.json` file in the project root. You can copy the example below and adjust the values.

### Example `config.json`

```json
{
  "api_url": "https://api.openai.com/v1/chat/completions",
  "api_key": "your-api-key-here",
  "model": "gpt-4o-mini",
  "system_prompt": "You are a helpful assistant.",
  "system_prompt_file": "",
  "prompt": "Hello!",
  "prompt_file": "",
  "enable_thinking": false,
  "history_file": "history.json",
  "output_file": "output.txt",
  "live_display": true,
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 0,
  "timeout": 60
}
```

### Configuration Fields

| Field                  | Description                                                                                     | Default       |
|------------------------|-------------------------------------------------------------------------------------------------|---------------|
| `api_url`              | Full URL of the chat completions endpoint (e.g., `https://api.openai.com/v1/chat/completions`). | —             |
| `api_key`              | Your secret API key.                                                                            | —             |
| `model`                | The name of the model to use (e.g., `gpt-4o-mini`, `deepseek-chat`).                            | —             |
| `system_prompt`        | Inline system prompt. If empty, `system_prompt_file` is used.                                   | `""`          |
| `system_prompt_file`   | Path to a file containing the system prompt. Ignored if `system_prompt` is set.                 | `""`          |
| `prompt`               | Inline user prompt. If empty, `prompt_file` is used.                                            | `""`          |
| `prompt_file`          | Path to a file containing the user prompt. Ignored if `prompt` is set.                          | `""`          |
| `enable_thinking`      | Enable explicit reasoning/thinking blocks (only for models that support it, e.g., DeepSeek-R1). | `false`       |
| `history_file`         | Path to the file where conversation history is saved.                                           | `history.json`|
| `output_file` | Path to the file where **only the model's final answer** is saved, with no extra text, metadata, or formatting. | `output.txt` |
| `live_display`         | Show real-time streaming output in the terminal.                                                | `true`        |
| `stream`               | Use streaming API responses.                                                                    | `true`        |
| `temperature`          | Sampling temperature (0.0 to 2.0).                                                              | `0.7`         |
| `max_tokens`           | Maximum number of tokens to generate. **Set to `0` for unlimited.**                             | `0`           |
| `timeout`              | Request timeout in **seconds**.                                                                 | `60`          |

> **Note:** The `api_url` must point to the full endpoint (including `/v1/chat/completions`). For OpenAI-compatible providers, this is typically `<base_url>/v1/chat/completions`.

## 🕹️ Usage

After configuring `config.json`, run the agent:

```bash
python main.py
```

The agent will connect to the API, display live streaming output, and save the conversation history and final output to the specified files.

Note: The output_file contains only the model's final response — no timestamps, no status lines, no metrics, and no thinking/reasoning blocks. Everything else (state changes, thinking, token counts, elapsed time) is shown only in the terminal via the live display.
### Example Output

```
[Connecting] ...
[Thinking] ...
[Writing] Hello! How can I help you today?
[Finished]
Elapsed: 2.34s | Prompt tokens: 12 | Completion tokens: 9 | Total tokens: 21
```

## 📁 Project Structure

```
con_api/
├── main.py              # Entry point; orchestrates the entire process.
├── api_client.py        # Handles API communication: request building and response parsing.
├── live_display.py      # Manages real-time visual output in the terminal.
├── config.json          # User-specific settings and operational parameters.
├── requirements.txt     # Python dependencies.
├── README.md            # English documentation (this file).
├── README_FA.md         # Persian documentation.
└── LICENSE              # MIT License.
```

## 🇮🇷 Persian Users

If your preferred language is Persian, please refer to the dedicated Farsi version of the documentation at [README_FA.md](README_FA.md).

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.