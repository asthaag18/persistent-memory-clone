import json
import os
import re
import urllib.request

DECISION_WORDS = re.compile(r"\b(decided|decision|we will use|using|chose|because|switched to)\b", re.I)
ERROR_WORDS = re.compile(r"\b(error|exception|traceback|failed|failure|crash)\b", re.I)


def heuristic_process(events):
    out, files = [], []
    for e in events:
        text = (e.get("text") or "").strip()
        kind = e.get("type", "note")
        if len(text) < 8:
            continue
        if kind == "file_change":
            files.append(text)
        elif kind == "error":
            out.append(("error", text))
        elif kind == "fix":
            out.append(("solution", text))
        elif kind == "command":
            out.append(("tool_use", f"Ran: {text}"))
        elif kind == "note" and DECISION_WORDS.search(text):
            out.append(("decision", text))
        elif kind == "note" and ERROR_WORDS.search(text):
            out.append(("error", text))
        elif kind == "note":
            out.append(("fact", text))
    if files:
        out.append(("code_change", "Files changed: " + ", ".join(sorted(set(files)))))
    seen, unique = set(), []
    for kind, text in out:
        if text.lower() not in seen:
            seen.add(text.lower())
            unique.append((kind, text))
    return unique


def llm_process(events):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    prompt = (
        "From this coding session log, extract durable memories as a JSON list of "
        '{"kind": "decision|error|solution|fact|code_change", "text": "..."}. '
        "Skip noise and duplicates. Return only JSON.\n\n" + json.dumps(events)
    )
    body = json.dumps(
        {"model": model, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]}
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = json.load(r)["content"][0]["text"]
        text = re.sub(r"```json|```", "", text).strip()
        return [(m["kind"], m["text"]) for m in json.loads(text)]
    except Exception as ex:
        print("LLM processing failed, using heuristics:", ex)
        return None


def process(events):
    return llm_process(events) or heuristic_process(events)
