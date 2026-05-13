"""
Helpers for parsing LLM responses.
"""
import json
import re


def extract_code_block(text, languages=("python", "py")):
    """
    Extract code from a fenced code block. Falls back to raw text when it
    looks like plain Python code.
    """
    if not text:
        return None

    language_pattern = "|".join(re.escape(lang) for lang in languages)
    fenced = re.search(
        rf"```(?:{language_pattern})?\s*\n(.*?)```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        return fenced.group(1).strip()

    stripped = text.strip()
    python_signals = (
        "import ",
        "from ",
        "df[",
        "df.",
        "plt.",
        "sns.",
        "print(",
        "fig",
    )
    if any(signal in stripped for signal in python_signals):
        return stripped

    return None


def extract_json_object(text):
    """
    Extract and parse a JSON object from a model response.
    """
    if not text:
        raise ValueError("Empty response; cannot parse JSON.")

    stripped = text.strip()

    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start:end + 1])
