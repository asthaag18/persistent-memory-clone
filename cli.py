import argparse
import json
import sys

from processor import process
from store import MemoryStore


def build_parser():
    p = argparse.ArgumentParser(description="Persistent memory for coding sessions")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="process a saved session log (JSON) into memories")
    c.add_argument("--project", required=True)
    c.add_argument("--file", required=True)

    o = sub.add_parser("observe", help="record one live event as it happens")
    o.add_argument("--project", required=True)
    o.add_argument("--type", default="note", help="note|error|fix|command|file_change")
    o.add_argument("--stdin", action="store_true", help='read JSON lines {"type","text"} from stdin')
    o.add_argument("text", nargs="?")

    f = sub.add_parser("finish", help="end the live session: process buffered events into memories")
    f.add_argument("--project", required=True)

    a = sub.add_parser("add", help="add one memory by hand")
    a.add_argument("--project", required=True)
    a.add_argument("--kind", default="fact")
    a.add_argument("text")

    s = sub.add_parser("search")
    s.add_argument("--project", required=True)
    s.add_argument("query")

    x = sub.add_parser("context", help="print the memory block to inject into a new session")
    x.add_argument("--project", required=True)
    x.add_argument("--query", required=True)
    x.add_argument("--out", help="also write the block to this file (e.g. MEMORY_CONTEXT.md)")

    ls = sub.add_parser("list")
    ls.add_argument("--project", required=True)

    u = sub.add_parser("useful", help="feedback loop: boost a helpful memory")
    u.add_argument("id", type=int)

    fg = sub.add_parser("forget")
    fg.add_argument("id", type=int)

    sub.add_parser("reindex", help="re-embed all memories (after switching embedder)")
    return p


def store_memories(store, project, items):
    added = 0
    for kind, text in items:
        _, new = store.add(project, kind, text)
        added += new
    return added


def main(argv=None):
    args = build_parser().parse_args(argv)
    store = MemoryStore()

    if args.cmd == "capture":
        with open(args.file) as fh:
            events = json.load(fh)
        print(f"Stored {store_memories(store, args.project, process(events))} new memories")
    elif args.cmd == "observe":
        if args.stdin:
            n = 0
            for line in sys.stdin:
                line = line.strip()
                if line:
                    ev = json.loads(line)
                    store.add_event(args.project, ev.get("type", "note"), ev["text"])
                    n += 1
            print(f"Buffered {n} events")
        elif args.text:
            store.add_event(args.project, args.type, args.text)
            print("Buffered 1 event")
        else:
            sys.exit("give text or --stdin")
    elif args.cmd == "finish":
        events = store.pop_events(args.project)
        added = store_memories(store, args.project, process(events))
        print(f"Processed {len(events)} events, stored {added} new memories")
    elif args.cmd == "add":
        mid, new = store.add(args.project, args.kind, args.text)
        print(f"id={mid} {'added' if new else 'duplicate'}")
    elif args.cmd == "search":
        for r in store.search(args.project, args.query):
            print(f"[{r['id']}] ({r['kind']}, score {r['score']}) {r['content']}")
    elif args.cmd == "context":
        rows = store.search(args.project, args.query)
        lines = ["## Relevant memories from past sessions"]
        lines += [f"- ({r['kind']}) {r['content']}" for r in rows]
        block = "\n".join(lines)
        print(block)
        if args.out:
            with open(args.out, "w") as fh:
                fh.write(block + "\n")
    elif args.cmd == "list":
        for r in store.list(args.project):
            print(f"[{r['id']}] ({r['kind']}, useful {r['useful']}) {r['content']}")
    elif args.cmd == "useful":
        store.mark_useful(args.id)
        print("Boosted")
    elif args.cmd == "forget":
        store.forget(args.id)
        print("Deleted")
    elif args.cmd == "reindex":
        print(f"Re-embedded {store.reindex()} memories")


if __name__ == "__main__":
    main()
