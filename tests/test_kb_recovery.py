import glob
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import faiss
import numpy as np

import createbase
import search


class FakeEmbeddingClient:
    embedding_conf = {"model": "test-model"}

    def __init__(self, calls):
        self.calls = calls

    def embed_texts(self, texts):
        self.calls.append(len(texts))
        vectors = []
        for text in texts:
            seed = sum(text.encode("utf-8"))
            vectors.append([
                float(seed % 17 + 1),
                float(seed % 13 + 1),
                float(seed % 11 + 1),
                float(seed % 7 + 1),
            ])
        return vectors


class KnowledgeBaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kb-recovery-")
        self.source_dir = os.path.join(self.temp_dir, "2026-07-21")
        self.kb_dir = os.path.join(self.temp_dir, "kb")
        os.makedirs(self.source_dir)
        with open(os.path.join(self.source_dir, "paper.txt"), "w", encoding="utf-8") as f:
            f.write(
                "# First\n\n" + "A" * 350
                + "\n\n# Second\n\n" + "B" * 350
                + "\n\n# Third\n\n" + "C" * 350
            )
        self.calls = []
        self.client = FakeEmbeddingClient(self.calls)
        self.model_patch = mock.patch.object(
            createbase.ModelClient,
            "from_config_path",
            classmethod(lambda cls, path: self.client),
        )
        self.model_patch.start()

    def tearDown(self):
        self.model_patch.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def build(self):
        createbase.build_kb(
            source_dir=self.source_dir,
            kb_dir=self.kb_dir,
            api_key_path="unused",
        )

    def test_faiss_and_jsonl_recover_without_embedding_calls(self):
        self.build()
        first_calls = sum(self.calls)
        self.calls.clear()

        os.remove(os.path.join(self.kb_dir, "vectors.faiss"))
        self.build()
        self.assertEqual(sum(self.calls), 0)

        self.calls.clear()
        with open(os.path.join(self.kb_dir, "doc_store.jsonl"), "a", encoding="utf-8") as f:
            f.write("{broken json\n")
        os.remove(os.path.join(self.kb_dir, "vectors.faiss"))
        self.build()
        self.assertEqual(sum(self.calls), 0)
        self.assertGreater(first_calls, 0)

        index = faiss.read_index(os.path.join(self.kb_dir, "vectors.faiss"))
        self.assertEqual(index.ntotal, 3)
        with open(os.path.join(self.kb_dir, "doc_store.jsonl"), encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(records), 3)

        doc_store_path = os.path.join(self.kb_dir, "doc_store.jsonl")
        os.remove(doc_store_path)
        record = search.load_records_by_ids(doc_store_path, {1})[1]
        self.assertEqual(record["vector_id"], 1)

    def test_legacy_index_only_embeds_missing_vectors(self):
        self.build()
        index_path = os.path.join(self.kb_dir, "vectors.faiss")
        index = faiss.read_index(index_path)
        stale_vector = index.reconstruct(3)
        index.remove_ids(np.asarray([3], dtype="int64"))
        index.add_with_ids(
            np.asarray([stale_vector], dtype="float32"),
            np.asarray([99], dtype="int64"),
        )
        faiss.write_index(index, index_path)

        for pattern in ("embedding_cache_*.sqlite3*", "chunk_store.sqlite3*"):
            for path in glob.glob(os.path.join(self.kb_dir, pattern)):
                os.remove(path)
        os.remove(os.path.join(self.kb_dir, "source_manifest.json"))
        self.calls.clear()

        self.build()

        self.assertEqual(sum(self.calls), 1)
        repaired = faiss.read_index(index_path)
        self.assertEqual(repaired.ntotal, 3)
        self.assertEqual(createbase.get_index_vector_ids(repaired, faiss), {1, 2, 3})


if __name__ == "__main__":
    unittest.main()
