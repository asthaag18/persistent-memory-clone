import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cli import main  # noqa: E402
from processor import heuristic_process  # noqa: E402
from store import MemoryStore  # noqa: E402

SESSION = os.path.join(os.path.dirname(__file__), "..", "sample_session.json")


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["MEMORY_DB"] = os.path.join(self.tmp, "t.db")
        self.store = MemoryStore()

    def test_dedupe(self):
        _, first = self.store.add("p", "fact", "uses SQLite")
        _, second = self.store.add("p", "fact", "uses SQLite")
        self.assertTrue(first)
        self.assertFalse(second)

    def test_processor_drops_noise_and_groups_files(self):
        with open(SESSION) as fh:
            items = heuristic_process(json.load(fh))
        texts = [t for _, t in items]
        self.assertNotIn("ok", texts)
        self.assertIn("Files changed: auth/jwt.py, config.py", texts)

    def test_search_handles_word_forms(self):
        self.store.add("p", "error", "JWT decode fails with InvalidSignatureError when SECRET_KEY is read from .env")
        self.store.add("p", "decision", "We decided to use SQLite instead of Postgres because the app is small")
        hits = self.store.search("p", "decoding failure")
        self.assertTrue(hits)
        self.assertIn("JWT", hits[0]["content"])

    def test_search_ignores_unrelated(self):
        self.store.add("p", "decision", "We decided to use SQLite instead of Postgres because the app is small")
        self.assertEqual(self.store.search("p", "kubernetes ingress"), [])

    def test_projects_are_isolated(self):
        self.store.add("a", "fact", "alpha uses redis cache")
        self.assertEqual(self.store.search("b", "redis cache"), [])

    def test_useful_feedback_boosts_ranking(self):
        a, _ = self.store.add("p", "fact", "cache layer uses redis")
        b, _ = self.store.add("p", "fact", "cache layer uses memcached")
        for _ in range(3):
            self.store.mark_useful(b)
        self.assertEqual(self.store.search("p", "cache layer")[0]["id"], b)

    def test_forget(self):
        mid, _ = self.store.add("p", "fact", "temporary fact about pandas")
        self.store.forget(mid)
        self.assertEqual(self.store.search("p", "pandas"), [])

    def test_live_observe_then_finish(self):
        main(["observe", "--project", "p", "--type", "error", "Traceback: KeyError in parser module"])
        main(["observe", "--project", "p", "--type", "fix", "Guard the dict lookup with .get()"])
        main(["finish", "--project", "p"])
        self.assertTrue(self.store.search("p", "KeyError parser"))
        self.assertEqual(self.store.pop_events("p"), [])

    def test_reindex(self):
        self.store.add("p", "fact", "something to reindex")
        self.assertEqual(self.store.reindex(), 1)


if __name__ == "__main__":
    unittest.main()
