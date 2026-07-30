"""Second Claude pass: approves or rejects today's caption before it can publish."""
import json
import os
import sys

from anthropic import Anthropic

from brand_voice import GUARDRAIL_PROMPT


def check(caption: str) -> dict:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=256,
        system=GUARDRAIL_PROMPT,
        messages=[{"role": "user", "content": caption}],
    )

    return json.loads(message.content[0].text.strip())


def main():
    post = json.loads(sys.stdin.read())
    result = check(post["caption"])

    if not result["approved"]:
        print(f"REJECTED: {result['reason']}", file=sys.stderr)
        sys.exit(1)

    print("APPROVED", file=sys.stderr)


if __name__ == "__main__":
    main()
