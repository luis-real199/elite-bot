"""One way to ask the language model for JSON, whichever provider persona.yaml picks.

- groq / gemini: free tiers through their OpenAI-compatible chat endpoints (HTTP, no SDK)
- claude: Anthropic's API through the official SDK (paid, strongest)
"""

import json
import re
import time

import requests

PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        # Llama 3.3 70B and Llama 4 Scout left the free tier in Jul/Aug 2026; these are Groq's replacements.
        "model": "openai/gpt-oss-120b",
        "vision_model": "qwen/qwen3.8-27b",  # preview model: max 3 images per request
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-flash-latest",
        "vision_model": "gemini-flash-latest",
    },
}
PROVIDERS = ("claude", *PRESETS)


class LLMError(Exception):
    pass


class LLMRefusal(LLMError):
    """The model declined; callers decide what that means (escalate, fail QC, stop the plan)."""


class LLMBadOutput(LLMError):
    """The model answered, but not with usable JSON (invalid or cut off). Asking for less usually works."""


def settings(cfg):
    """The resolved provider settings for this persona."""
    raw = cfg.models.get("llm") or {}
    provider = raw.get("provider") or "claude"
    if provider not in PROVIDERS:
        raise LLMError(f"models.llm.provider πρέπει να είναι ένα από {PROVIDERS}")
    preset = PRESETS.get(provider, {})
    return {
        "provider": provider,
        "base_url": raw.get("base_url") or preset.get("base_url"),
        "key_env": preset.get("key_env"),
        "model": raw.get("model") or preset.get("model") or cfg.models["claude"],
        "vision_model": raw.get("vision_model") or preset.get("vision_model") or raw.get("model") or preset.get("model"),
        "plan_chunk": int(raw.get("plan_chunk") or 5),
        "usd_per_mtok": raw.get("usd_per_mtok") or {"input": 0.0, "output": 0.0},
    }


def ask_json(app, *, system, content, schema, kind, effort="medium", max_tokens=16000,
             cached_system=None, stream=False):
    """Ask for one JSON object matching `schema`. `content` is a string or Claude-style content blocks
    (text and {"type": "image", "source": {"type": "url", ...}}). Records the cost under `kind`."""
    s = settings(app.cfg)
    if s["provider"] == "claude":
        return _ask_claude(app, system, content, schema, kind, effort, max_tokens, cached_system, stream)
    return _ask_openai_compatible(app, s, system, content, schema, kind, cached_system)


# ---------- Claude ----------

def _ask_claude(app, system, content, schema, kind, effort, max_tokens, cached_system, stream):
    cfg = app.cfg
    if cached_system:
        system_param = [{"type": "text", "text": cached_system, "cache_control": {"type": "ephemeral"}}]
        if system:
            system_param.append({"type": "text", "text": system})
    else:
        system_param = system
    request = dict(
        model=cfg.models["claude"],
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
    )
    if system_param:
        request["system"] = system_param
    if stream:
        with app.claude.beta.messages.stream(**request) as s:
            response = s.get_final_message()
    else:
        response = app.claude.beta.messages.create(**request)

    price = cfg.models["claude_usd_per_mtok"]
    usage = response.usage
    app.db.add_cost(kind, (usage.input_tokens * price["input"] + usage.output_tokens * price["output"]) / 1_000_000)
    if response.stop_reason == "refusal":
        raise LLMRefusal("Το Claude αρνήθηκε")
    if response.stop_reason == "max_tokens":
        raise LLMBadOutput("Η απάντηση κόπηκε (max_tokens)")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except ValueError as e:
        raise LLMBadOutput(f"Μη έγκυρο JSON από το Claude: {e}")


# ---------- Groq / Gemini (OpenAI-compatible) ----------

def _to_openai_content(content):
    if isinstance(content, str):
        return content, False
    parts, has_image = [], False
    for block in content:
        if block["type"] == "text":
            parts.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            parts.append({"type": "image_url", "image_url": {"url": block["source"]["url"]}})
            has_image = True
    return parts, has_image


def _parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    return json.loads(text[start:end + 1])


def _error(r):
    """(code, message) from an OpenAI-style error body, without echoing the whole response."""
    try:
        err = r.json().get("error") or {}
        return err.get("code") or "", (err.get("message") or "")[:200]
    except (ValueError, AttributeError, TypeError):
        return "", (getattr(r, "text", "") or "")[:200]


def _post(app, url, key, body, attempts=3):
    for attempt in range(attempts):
        try:
            r = app.llm_http.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=180)
        except requests.RequestException as e:
            raise LLMError(f"{type(e).__name__}") from None
        if r.status_code == 429 and attempt < attempts - 1:
            try:
                wait = float(r.headers.get("retry-after") or 20)
            except ValueError:
                wait = 20
            app.sleep(min(wait, 60))
            continue
        if r.status_code >= 300:
            code, message = _error(r)
            if code == "json_validate_failed":  # Groq checked the output and it was not valid JSON
                raise LLMBadOutput("το μοντέλο έβγαλε άκυρο JSON")
            raise LLMError(f"HTTP {r.status_code} {code}: {message}".replace("  ", " "))
        return r.json()
    raise LLMError("Όριο αιτημάτων του δωρεάν API (429). Ξαναδοκιμάζει αργότερα.")


def _ask_openai_compatible(app, s, system, content, schema, kind, cached_system):
    key = app.cfg.secret(s["key_env"])
    if not key:
        raise LLMError(f"Λείπει το {s['key_env']} στο .env")
    user, has_image = _to_openai_content(content)
    instructions = "\n\n".join(x for x in (cached_system, system) if x)
    instructions += (
        "\n\nReply with one JSON object only, no other text. It must match this JSON schema:\n"
        + json.dumps(schema)
    )
    messages = [{"role": "system", "content": instructions.strip()}, {"role": "user", "content": user}]
    body = {
        "model": s["vision_model"] if has_image else s["model"],
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.8 if kind in ("claude", "plan") else 0.4,
        # gpt-oss and qwen3 reason before answering; those tokens count against the limit and the free quota
        "max_completion_tokens": 8192,
    }
    if body["model"].startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    url = s["base_url"].rstrip("/") + "/chat/completions"
    for attempt in range(2):
        try:
            result = _post(app, url, key, body)
        except LLMBadOutput:
            if attempt:
                raise
            body["temperature"] = min(body["temperature"], 0.5)  # a calmer second try usually validates
            continue
        usage = result.get("usage") or {}
        price = s["usd_per_mtok"]
        app.db.add_cost(kind, (usage.get("prompt_tokens", 0) * price["input"]
                               + usage.get("completion_tokens", 0) * price["output"]) / 1_000_000)
        choice = (result.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "content_filter":
            raise LLMRefusal("Το μοντέλο αρνήθηκε (content filter)")
        if choice.get("finish_reason") == "length":
            raise LLMBadOutput("Η απάντηση κόπηκε (max_completion_tokens)")
        try:
            data = _parse_json((choice.get("message") or {}).get("content"))
        except ValueError:
            data = None
        if isinstance(data, dict) and all(k in data for k in schema.get("required", [])):
            return data
        body["messages"] = messages + [{"role": "user", "content": "That was not valid JSON for the schema. Reply with the JSON object only."}]
    raise LLMBadOutput("Το μοντέλο δεν έδωσε έγκυρο JSON")
