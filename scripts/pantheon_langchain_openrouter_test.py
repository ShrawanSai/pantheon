#!/usr/bin/env python3
import argparse
import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pantheon_llm.openrouter_langchain import SUPPORTED_LLMS, ainvoke_text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pantheon LangChain+OpenRouter smoke test using shortlisted MVP models."
    )
    parser.add_argument(
        "--model",
        default="deepseek",
        choices=sorted(SUPPORTED_LLMS.keys()),
        help="Model alias to test.",
    )
    parser.add_argument(
        "--prompt",
        default="Say hello in exactly one word.",
        help="Prompt to run.",
    )
    args = parser.parse_args()

    try:
        output = asyncio.run(ainvoke_text(alias=args.model, prompt=args.prompt))
        print(output)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
