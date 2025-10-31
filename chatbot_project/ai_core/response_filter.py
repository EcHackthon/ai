
from __future__ import annotations
import re
import json
from typing import Optional, Tuple, Any, Dict

JSON_BLOCK_RE = re.compile(
    r"(?:```json\s*)(\{[\s\S]*?\})(?:\s*```)|(\{[\s\S]*\})",
    re.IGNORECASE
)

def extract_json_block(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    m = JSON_BLOCK_RE.search(text)
    if not m:
        return None
    block = m.group(1) or m.group(2)
    # Trim trailing junk after the last balanced brace
    # Find the last closing brace that balances
    depth = 0
    last_idx = None
    for i, ch in enumerate(block):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                last_idx = i
    if last_idx is not None:
        block = block[:last_idx+1]
    return block

def parse_json_safely(text: str) -> Optional[Dict[str, Any]]:
    blk = extract_json_block(text)
    if not blk:
        return None
    try:
        return json.loads(blk)
    except Exception:
        # Try to relax JSON by removing trailing commas
        blk2 = re.sub(r",\s*([}\]])", r"\1", blk)
        try:
            return json.loads(blk2)
        except Exception:
            return None

def sanitize_to_json_only(text: str) -> Optional[str]:
    blk = extract_json_block(text)
    if not blk:
        return None
    return "```json\n" + blk + "\n```"
