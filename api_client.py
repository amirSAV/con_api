import json
import re
import time
import requests


# Regex to extract <think>...</think> including variations
_THINK_PATTERNS = [
    re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL | re.IGNORECASE),
]


def extract_thinking(content: str) -> tuple[str, str]:
    """Separate thinking from main content.

    Returns:
        (thinking_text, clean_content)
        thinking_text is "" if no think tags found.
    """
    if not content:
        return "", ""

    thinking_parts = []
    clean = content

    for pat in _THINK_PATTERNS:
        for m in pat.finditer(clean):
            thinking_parts.append(m.group(1).strip())
        # Remove all think blocks from clean
        clean = pat.sub("", clean)

    thinking = "\n\n".join(thinking_parts).strip()
    return thinking, clean.strip()


def _load_file_if_needed(config: dict, file_key: str, text_key: str) -> str:
    """Helper: if file_key points to existing file with content, return file content, else text_key."""
    file_path = config.get(file_key, "")
    if file_path and str(file_path).strip():
        import os
        p = str(file_path).strip()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    return content
            except OSError:
                pass
    # Fallback to inline
    txt = config.get(text_key, "")
    if txt and str(txt).strip():
        return str(txt).strip()
    return ""


def build_messages(config: dict, history: list, user_prompt: str) -> list:
    """Build message list: system + old history (simple format) + new user message."""
    messages = []
    # System prompt can come from file or inline
    sp = _load_file_if_needed(config, "system_prompt_file", "system_prompt")
    if sp and str(sp).strip():
        messages.append({"role": "system", "content": sp})

    # History in new format is list of exchanges; we need to convert to chat messages
    # Support both old format (list of {"role":...}) and new format
    for entry in history:
        if isinstance(entry, dict) and "role" in entry and "content" in entry:
            # Old simple format
            messages.append({"role": entry["role"], "content": entry["content"]})
        elif isinstance(entry, dict) and "user_prompt" in entry:
            # New format: each entry is an exchange
            messages.append({"role": "user", "content": entry["user_prompt"]})
            # assistant content (without thinking) for context
            if entry.get("answer"):
                messages.append({"role": "assistant", "content": entry["answer"]})

    messages.append({"role": "user", "content": user_prompt})
    return messages


def send_request(config: dict, messages: list) -> dict | None:
    """Send request to OpenAI-compatible API.

    Returns dict with keys: content, thinking, usage, raw  or None on error.
    - api_key is optional: Authorization header only if non-empty
    - max_tokens == 0 means unlimited (don't send max_tokens)
    - enable_thinking toggle sent via multiple compatible fields
    """
    headers = {"Content-Type": "application/json"}
    api_key = config.get("api_key", "")
    if api_key and str(api_key).strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": config.get("temperature", 0.7),
    }

    # max_tokens handling: 0 => unlimited, don't send
    max_tokens = config.get("max_tokens")
    if max_tokens is not None:
        try:
            mt = int(max_tokens)
            if mt > 0:
                payload["max_tokens"] = mt
            # if 0 => unlimited, skip
        except (ValueError, TypeError):
            pass

    # enable_thinking handling: support multiple API conventions
    enable_thinking = config.get("enable_thinking", True)
    if enable_thinking is False:
        # For APIs that support explicit toggle:
        # 1) OpenAI-style reasoning_effort
        # 2) Qwen / llama.cpp style enable_thinking
        # 3) chat_template_kwargs
        # We send all to maximize compatibility; unknown fields are ignored by most servers.
        payload["reasoning_effort"] = "none"
        payload["enable_thinking"] = False
        # extra_body style for openai client compatibility (if server respects it)
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    elif enable_thinking is True:
        # Explicitly enable (helps some servers that default to off)
        payload["enable_thinking"] = True
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        # Don't send reasoning_effort when enabled, let model decide
        # Some servers use extra_body
        # We keep payload clean; if server needs extra_body it will also read enable_thinking

    try:
        r = requests.post(
            config["api_url"],
            headers=headers,
            json=payload,
            timeout=config.get("timeout", 60),
        )
    except requests.exceptions.Timeout:
        print("Error: request timed out.")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"Error: could not connect: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None

    if r.status_code != 200:
        print(f"API error (status {r.status_code}): {r.text[:1000]}")
        return None

    try:
        data = r.json()
        message = data["choices"][0]["message"]
        # Some APIs return reasoning_content or thinking separately
        raw_content = message.get("content") or ""
        # Check alternative fields for thinking
        alt_thinking = ""
        for key in ("reasoning_content", "reasoning", "thinking", "thought"):
            if key in message and message[key]:
                alt_thinking = str(message[key]).strip()
                break

        thinking_from_tags, clean_content = extract_thinking(raw_content)
        # Prefer tag-extracted thinking, fallback to alt field
        final_thinking = thinking_from_tags or alt_thinking

        # If thinking was in separate field, clean_content already is final answer
        # If alt_thinking existed and tag thinking empty, use alt
        if alt_thinking and not thinking_from_tags:
            final_thinking = alt_thinking

        usage = data.get("usage", {})  # contains prompt_tokens etc if provided

        return {
            "content": clean_content,
            "thinking": final_thinking,
            "raw_content": raw_content,
            "usage": usage,
            "raw": data,
        }
    except (ValueError, KeyError, IndexError, TypeError) as e:
        print(f"Error parsing server response: {e}")
        try:
            print(f"Raw response: {r.text[:1000]}")
        except Exception:
            pass
        return None


def send_request_stream(config: dict, messages: list, live_display=None) -> dict | None:
    """Streaming version with live display support.

    - Sends request with stream=True
    - Updates live_display with thinking/writing state and token estimates
    - Returns same dict as send_request (content, thinking, usage, raw)
    - Respects enable_thinking: if False, ignores reasoning_content
    """
    headers = {"Content-Type": "application/json"}
    api_key = config.get("api_key", "")
    if api_key and str(api_key).strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": config.get("temperature", 0.7),
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    max_tokens = config.get("max_tokens")
    if max_tokens is not None:
        try:
            mt = int(max_tokens)
            if mt > 0:
                payload["max_tokens"] = mt
        except (ValueError, TypeError):
            pass

    enable_thinking = config.get("enable_thinking", True)
    if enable_thinking is False:
        payload["reasoning_effort"] = "none"
        payload["enable_thinking"] = False
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    elif enable_thinking is True:
        payload["enable_thinking"] = True
        payload["chat_template_kwargs"] = {"enable_thinking": True}

    # Estimate prompt tokens for live display
    def estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    prompt_text = " ".join([m.get("content", "") for m in messages])
    prompt_tokens_est = estimate_tokens(prompt_text)

    thinking_buffer = ""
    answer_buffer = ""
    raw_content_buffer = ""
    usage = {}
    raw_data = {}
    state = "CONNECTING"
    start_time = time.time()
    last_update = 0

    if live_display:
        try:
            live_display.update(state=state, thinking=thinking_buffer, answer=answer_buffer, prompt_tokens=prompt_tokens_est)
        except Exception:
            pass

    try:
        r = requests.post(
            config["api_url"],
            headers=headers,
            json=payload,
            timeout=config.get("timeout", 60),
            stream=True,
        )
    except requests.exceptions.Timeout:
        print("Error: request timed out.")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"Error: could not connect: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None

    if r.status_code != 200:
        print(f"API error (status {r.status_code}): {r.text[:1000] if hasattr(r, 'text') else ''}")
        return None

    try:
        # Ensure correct encoding for streaming
        r.encoding = "utf-8"
        # Use iter_lines with manual decode to handle utf-8 correctly (emoji etc.)
        for raw_line in r.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            try:
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
            except Exception:
                line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Save raw for final
            raw_data = data

            # Check for usage in streaming (some servers send it at end, sometimes with no choices)
            has_usage = False
            if "usage" in data and data["usage"]:
                usage = data["usage"]
                has_usage = True
                # Also try to get usage from stream_options include_usage: it may be in data["usage"]
                # Update live display even if no choices
                if live_display and has_usage:
                    try:
                        live_display.update(state=state, thinking=thinking_buffer, answer=answer_buffer, prompt_tokens=usage.get("prompt_tokens", prompt_tokens_est), usage=usage)
                    except Exception:
                        pass
            if "timings" in data and data["timings"]:
                # llama.cpp timings can be used to estimate
                timings = data["timings"]
                # Try to extract predicted_n as completion tokens
                if "predicted_n" in timings and not usage.get("completion_tokens"):
                    usage["completion_tokens"] = timings.get("predicted_n")
                    has_usage = True
                if "prompt_n" in timings and not usage.get("prompt_tokens"):
                    usage["prompt_tokens"] = timings.get("prompt_n")
                    has_usage = True
                if has_usage and live_display:
                    try:
                        live_display.update(state=state, thinking=thinking_buffer, answer=answer_buffer, prompt_tokens=usage.get("prompt_tokens", prompt_tokens_est), usage=usage)
                    except Exception:
                        pass

            choices = data.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # Check reasoning_content / thinking
            has_thinking = False
            for key in ("reasoning_content", "reasoning", "thinking", "thought"):
                if key in delta and delta[key]:
                    has_thinking = True
                    chunk = str(delta[key])
                    # Respect enable_thinking flag
                    if enable_thinking:
                        thinking_buffer += chunk
                        raw_content_buffer += chunk
                        state = "THINKING"
                    else:
                        # If thinking disabled, ignore reasoning but still track for raw?
                        # Do not add to thinking_buffer when disabled
                        pass
                    break

            # Check content
            has_content = False
            if "content" in delta and delta["content"] is not None:
                chunk = delta["content"]
                if chunk:
                    has_content = True
                    # Handle <think> tags inside content for non-separated models
                    # We will buffer raw and later extract, but for live we need to detect
                    raw_content_buffer += chunk
                    # If content contains think tags, we need to separate live
                    # Simple: if enable_thinking and "<think>" in chunk, treat as thinking
                    # But we already handle reasoning_content separately
                    # For <think> tags, we do live extraction
                    if enable_thinking and ("<think>" in chunk or "<thinking>" in chunk or "<reasoning>" in chunk):
                        # Will be handled via extract at end, but for live we can try to detect
                        # For now, just treat as thinking until closing tag
                        # Simplify: add to thinking if inside tags, else answer
                        # We will do final extraction, but live we append to answer and later re-evaluate
                        # To keep live accurate, we append to answer but also track
                        pass
                    answer_buffer += chunk
                    if not has_thinking:
                        state = "WRITING"

            # Update live display throttled
            now = time.time()
            if live_display and (now - last_update > 0.05 or has_thinking or has_content or finish_reason):
                last_update = now
                elapsed = now - start_time
                # Estimate tokens for live
                try:
                    live_display.update(
                        state=state,
                        thinking=thinking_buffer,
                        answer=answer_buffer,
                        prompt_tokens=prompt_tokens_est,
                        usage=usage if usage else None,
                    )
                except Exception:
                    pass

            if finish_reason:
                # Finished
                if finish_reason in ("stop", "length", "tool_calls"):
                    state = "FINISHED"
                    break

        # After streaming, handle final processing
        # If answer_buffer contains <think> tags, extract
        final_thinking = thinking_buffer
        final_answer = answer_buffer
        # If we have raw_content_buffer that may contain tags and we didn't separate, try extract
        if raw_content_buffer and not thinking_buffer:
            # Try to extract from raw_content_buffer if it has tags
            th, clean = extract_thinking(raw_content_buffer)
            if th:
                final_thinking = th
                final_answer = clean
            else:
                # Check answer_buffer
                th2, clean2 = extract_thinking(answer_buffer)
                if th2:
                    final_thinking = th2
                    final_answer = clean2
        elif raw_content_buffer and thinking_buffer:
            # If we have both, ensure answer is clean (remove any think tags that slipped into answer)
            th_extra, clean_extra = extract_thinking(answer_buffer)
            if th_extra:
                final_thinking = (final_thinking + "\n\n" + th_extra).strip()
                final_answer = clean_extra

        # If thinking disabled, ensure thinking is empty
        if not enable_thinking:
            final_thinking = ""

        # Final thinking/answer stripping
        final_thinking = final_thinking.strip()
        final_answer = final_answer.strip()

        # If usage still empty, estimate
        if not usage or not usage.get("prompt_tokens"):
            usage = usage or {}
            if not usage.get("prompt_tokens"):
                usage["prompt_tokens"] = prompt_tokens_est
            if not usage.get("completion_tokens"):
                usage["completion_tokens"] = estimate_tokens(final_thinking + final_answer)
            if not usage.get("total_tokens"):
                try:
                    usage["total_tokens"] = int(usage["prompt_tokens"]) + int(usage["completion_tokens"])
                except Exception:
                    usage["total_tokens"] = estimate_tokens(prompt_text + final_thinking + final_answer)

        elapsed = time.time() - start_time
        # Final live update
        if live_display:
            try:
                live_display.update(state="FINISHED", thinking=final_thinking, answer=final_answer, prompt_tokens=usage.get("prompt_tokens"), usage=usage)
                live_display.finish(usage)
            except Exception:
                pass

        return {
            "content": final_answer,
            "thinking": final_thinking,
            "raw_content": raw_content_buffer or final_answer,
            "usage": usage,
            "raw": raw_data,
            "elapsed": elapsed,
        }

    except Exception as e:
        print(f"Error during streaming: {e}")
        # Fallback to non-streaming
        if live_display:
            try:
                live_display.finish({})
            except Exception:
                pass
        return None
