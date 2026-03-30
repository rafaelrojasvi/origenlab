from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .schemas import ExampleRecord, RetrievedExample


def _tokenize(s: str) -> list[str]:
    return re.findall(r"[a-záéíóúñü0-9]+", (s or "").lower())


class TatianaExampleIndex:
    def __init__(
        self,
        *,
        style_examples: list[ExampleRecord],
        retrieval_examples: list[ExampleRecord],
        method: str = "tfidf",
    ) -> None:
        self.style_examples = style_examples
        self.retrieval_examples = retrieval_examples
        self.method = method

        self._idf: dict[str, float] = {}
        self._style_vecs: list[dict[str, float]] = []
        self._retr_vecs: list[dict[str, float]] = []
        self._style_norms: list[float] = []
        self._retr_norms: list[float] = []
        self._sbert_model_name: str | None = None
        self._style_emb = None
        self._retr_emb = None

    @classmethod
    def build(
        cls,
        *,
        style_examples: list[ExampleRecord],
        retrieval_examples: list[ExampleRecord],
        method: str = "tfidf",
        sbert_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> "TatianaExampleIndex":
        idx = cls(
            style_examples=style_examples,
            retrieval_examples=retrieval_examples,
            method=method,
        )
        if method == "sbert":
            idx._build_sbert(sbert_model)
        else:
            idx._build_tfidf()
        return idx

    def _build_tfidf(self) -> None:
        docs = [e.search_text for e in (self.style_examples + self.retrieval_examples)]
        doc_tokens = [set(_tokenize(t)) for t in docs]
        n = max(1, len(doc_tokens))
        df: Counter[str] = Counter()
        for toks in doc_tokens:
            for t in toks:
                df[t] += 1
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

        def vec(text: str) -> tuple[dict[str, float], float]:
            toks = _tokenize(text)
            tf = Counter(toks)
            if not tf:
                return {}, 0.0
            out: dict[str, float] = {}
            for t, c in tf.items():
                out[t] = (c / len(toks)) * self._idf.get(t, 0.0)
            norm = math.sqrt(sum(v * v for v in out.values()))
            return out, norm

        for e in self.style_examples:
            v, nrm = vec(e.search_text)
            self._style_vecs.append(v)
            self._style_norms.append(nrm)
        for e in self.retrieval_examples:
            v, nrm = vec(e.search_text)
            self._retr_vecs.append(v)
            self._retr_norms.append(nrm)

    def _build_sbert(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers missing; use method=tfidf or install ml deps"
            ) from e
        model = SentenceTransformer(model_name)
        self._sbert_model_name = model_name
        self._style_emb = model.encode([e.search_text for e in self.style_examples], normalize_embeddings=True)
        self._retr_emb = model.encode([e.search_text for e in self.retrieval_examples], normalize_embeddings=True)
        self._sbert_model = model

    def _tfidf_scores(self, query: str, vecs: list[dict[str, float]], norms: list[float]) -> list[float]:
        q_tf = Counter(_tokenize(query))
        if not q_tf:
            return [0.0] * len(vecs)
        q_len = sum(q_tf.values())
        if q_len <= 0:
            return [0.0] * len(vecs)
        q_vec: dict[str, float] = {}
        for t, c in q_tf.items():
            q_vec[t] = (c / q_len) * self._idf.get(t, 0.0)
        q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
        if q_norm == 0.0:
            return [0.0] * len(vecs)

        scores: list[float] = []
        for v, nrm in zip(vecs, norms, strict=False):
            if nrm == 0.0:
                scores.append(0.0)
                continue
            dot = 0.0
            for t, qv in q_vec.items():
                dot += qv * v.get(t, 0.0)
            scores.append(dot / (q_norm * nrm))
        return scores

    def _sbert_scores(self, query: str, emb):  # pragma: no cover
        q = self._sbert_model.encode([query], normalize_embeddings=True)[0]
        return (emb @ q).tolist()

    def _retrieve(
        self,
        *,
        query_text: str,
        examples: list[ExampleRecord],
        vecs,
        norms,
        top_k: int,
        label_filter: set[str] | None,
        exclude_example_ids: set[str] | None,
    ) -> list[RetrievedExample]:
        if self.method == "sbert":  # pragma: no cover
            scores = self._sbert_scores(query_text, vecs)
        else:
            scores = self._tfidf_scores(query_text, vecs, norms)

        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True,
        )
        out: list[RetrievedExample] = []
        blocked = exclude_example_ids or set()
        for idx, score in ranked:
            ex = examples[idx]
            if ex.example_id in blocked:
                continue
            if label_filter and ex.label not in label_filter:
                continue
            out.append(
                RetrievedExample(
                    example_id=ex.example_id,
                    score=float(score),
                    label=ex.label,
                    subject=ex.subject,
                    body_text=ex.body_text,
                    metadata=ex.metadata,
                )
            )
            if len(out) >= top_k:
                break
        return out

    def retrieve_style(
        self,
        *,
        query_text: str,
        top_k: int = 3,
        label_filter: set[str] | None = None,
        exclude_example_ids: set[str] | None = None,
    ) -> list[RetrievedExample]:
        return self._retrieve(
            query_text=query_text,
            examples=self.style_examples,
            vecs=self._style_emb if self.method == "sbert" else self._style_vecs,
            norms=None if self.method == "sbert" else self._style_norms,
            top_k=top_k,
            label_filter=label_filter,
            exclude_example_ids=exclude_example_ids,
        )

    def retrieve_retrieval(
        self,
        *,
        query_text: str,
        top_k: int = 5,
        label_filter: set[str] | None = None,
        exclude_example_ids: set[str] | None = None,
    ) -> list[RetrievedExample]:
        return self._retrieve(
            query_text=query_text,
            examples=self.retrieval_examples,
            vecs=self._retr_emb if self.method == "sbert" else self._retr_vecs,
            norms=None if self.method == "sbert" else self._retr_norms,
            top_k=top_k,
            label_filter=label_filter,
            exclude_example_ids=exclude_example_ids,
        )

    def save(self, path: Path) -> None:
        obj = {
            "method": self.method,
            "style_examples": [asdict(x) for x in self.style_examples],
            "retrieval_examples": [asdict(x) for x in self.retrieval_examples],
            "idf": self._idf if self.method == "tfidf" else {},
            "style_vecs": self._style_vecs if self.method == "tfidf" else [],
            "retr_vecs": self._retr_vecs if self.method == "tfidf" else [],
            "style_norms": self._style_norms if self.method == "tfidf" else [],
            "retr_norms": self._retr_norms if self.method == "tfidf" else [],
            "sbert_model": self._sbert_model_name,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "TatianaExampleIndex":
        obj = json.loads(path.read_text(encoding="utf-8"))
        style = [ExampleRecord(**x) for x in obj["style_examples"]]
        retr = [ExampleRecord(**x) for x in obj["retrieval_examples"]]
        idx = cls(style_examples=style, retrieval_examples=retr, method=obj["method"])
        if idx.method == "tfidf":
            idx._idf = {k: float(v) for k, v in obj["idf"].items()}
            idx._style_vecs = [{k: float(v) for k, v in d.items()} for d in obj["style_vecs"]]
            idx._retr_vecs = [{k: float(v) for k, v in d.items()} for d in obj["retr_vecs"]]
            idx._style_norms = [float(x) for x in obj["style_norms"]]
            idx._retr_norms = [float(x) for x in obj["retr_norms"]]
        else:  # pragma: no cover
            # sbert indices are rebuilt at runtime in v1; persisted artifact is metadata only.
            idx = cls.build(style_examples=style, retrieval_examples=retr, method="sbert", sbert_model=obj.get("sbert_model") or "sentence-transformers/all-MiniLM-L6-v2")
        return idx
