#!/usr/bin/env python3
import json
import os
import sys
import urllib.request


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def main() -> int:
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    if not api_key:
        print("OPENROUTER_API_KEY not found", file=sys.stderr)
        return 1

    body = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Say hello. Output only: hello"}],
        "max_tokens": 5,
        "temperature": 0,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url=f"{base_url}/chat/completions",
        method="POST",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://pantheon.local",
            "X-Title": "Pantheon Hello Test",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        print((payload["choices"][0]["message"]["content"] or "").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
