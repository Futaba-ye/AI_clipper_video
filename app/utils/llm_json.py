import re
import json


def parse_llm_json(raw: str):
    """Strip markdown code fences around JSON from LLM response, then parse.

    Many LLMs (especially Qwen via DashScope) wrap JSON output in ```json ... ```
    despite prompts instructing otherwise. This handles:
      - ```json\\n{...}\\n```
      - ```\\n{...}\\n```
      - plain { ... }
    """
    text = raw.strip()
    # Strip leading ```json or ``` fence
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    # Strip trailing ``` fence
    text = re.sub(r'\n?```\s*$', '', text)
    return json.loads(text)
