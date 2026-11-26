# Persistent Memory Clone

Coding assistants forget everything between sessions. This tool captures what happened in a session,
turns it into durable memories, and injects the relevant ones into the next session.

```
Capture -> Process -> Store -> Retrieve -> Inject -> Improve
```

## Features
- **Live capture:** `observe` buffers events as they happen (or pipe JSON lines in with `--stdin`); `finish` processes them.
- **Batch capture:** `capture` reads a saved session log (JSON).
- **Process:** removes noise and duplicates, groups file changes, classifies errors, fixes and decisions.
  Optional LLM processing if `ANTHROPIC_API_KEY` is set.
- **Hybrid retrieval:** keyword search (SQLite FTS5 with stemming) combined with vector similarity.
- **Inject:** `context` prints (or writes with `--out`) a block to paste into a new session.
- **Feedback loop:** `useful ID` boosts a memory in later rankings; `forget ID` deletes one.

## Run
No installs needed (Python 3 standard library only).

```
python3 cli.py capture --project myapp --file sample_session.json
python3 cli.py search  --project myapp "jwt decoding failure"
python3 cli.py context --project myapp --query "auth failing again" --out MEMORY_CONTEXT.md
python3 cli.py useful 1
python3 cli.py list --project myapp
```

Live capture:
```
python3 cli.py observe --project myapp --type error "KeyError in parser module"
python3 cli.py observe --project myapp --type fix "Use .get() on the dict"
echo '{"type":"note","text":"We decided to use SQLite"}' | python3 cli.py observe --project myapp --stdin
python3 cli.py finish --project myapp
```

## Tests
```
python3 -m unittest discover -s tests -v
```

## Design notes
- One SQLite file (`memory.db`) holds memories, their vectors and the live event buffer.
- Ranking = 0.6 x vector cosine + 0.4 x normalised BM25 + small bonus for memories marked useful.
- Memories are scoped per `--project`, so projects never leak into each other.

## Limitations (honest)
- The default embedder is an offline **hashing n-gram** model. It handles word forms and typos
  (fail / failing / failure) but not true synonyms (login vs authentication).
  For real semantic search: `pip install sentence-transformers`, then
  `MEMORY_EMBEDDER=sbert python3 cli.py reindex`. (Supported in code, not exercised in the automated tests.)
- Vectors are compared in a Python loop, which is fine for thousands of memories. A vector database
  (Chroma / FAISS / sqlite-vec) would be the next step at larger scale.
- Live capture needs something to send events (a shell alias, editor hook or script). It does not hook
  into an IDE by itself.
