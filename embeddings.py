import hashlib
import math
import os
import re

DIM = 512
STOP = {
    "the", "and", "for", "with", "that", "this", "from", "when", "are", "was",
    "were", "has", "have", "had", "not", "but", "you", "its", "into", "than",
    "then", "them", "they", "our", "can", "will", "would", "should", "could",
    "been", "being", "get", "got",
}


def _features(text):
    words = [w for w in re.findall(r"[a-z0-9_]+", text.lower()) if w not in STOP]
    for w in words:
        yield w, 2.0
        padded = f"#{w}#"
        for i in range(len(padded) - 2):
            yield padded[i : i + 3], 1.0


def _bucket(feature):
    h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
    return h % DIM, (1.0 if (h >> 40) & 1 else -1.0)


class HashEmbedder:
    """Offline embedder: signed hashing of words + character trigrams.

    Handles word forms and typos (fail/failing/failure) but NOT true synonyms.
    For real semantic embeddings set MEMORY_EMBEDDER=sbert.
    """

    name = "hash-ngram-512"

    def embed(self, text):
        vec = [0.0] * DIM
        for feat, weight in _features(text):
            idx, sign = _bucket(feat)
            vec[idx] += sign * weight
        norm = math.sqrt(sum(x * x for x in vec))
        return vec if norm == 0 else [x / norm for x in vec]


class SbertEmbedder:
    """Real semantic embeddings. Needs: pip install sentence-transformers"""

    name = "sbert-minilm"

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(self, text):
        return [float(x) for x in self.model.encode(text, normalize_embeddings=True)]


def get_embedder():
    if os.environ.get("MEMORY_EMBEDDER") == "sbert":
        try:
            return SbertEmbedder()
        except Exception as ex:
            print("sentence-transformers unavailable, using offline embedder:", ex)
    return HashEmbedder()
