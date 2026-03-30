from __future__ import annotations

from .index import TatianaExampleIndex
from .schemas import RetrievedExample


def retrieve_for_case(
    *,
    index: TatianaExampleIndex,
    query_text: str,
    style_top_k: int = 3,
    retrieval_top_k: int = 5,
    style_labels: set[str] | None = None,
    retrieval_labels: set[str] | None = None,
    exclude_example_ids: set[str] | None = None,
) -> tuple[list[RetrievedExample], list[RetrievedExample]]:
    style = index.retrieve_style(
        query_text=query_text,
        top_k=style_top_k,
        label_filter=style_labels,
        exclude_example_ids=exclude_example_ids,
    )
    similar = index.retrieve_retrieval(
        query_text=query_text,
        top_k=retrieval_top_k,
        label_filter=retrieval_labels,
        exclude_example_ids=exclude_example_ids,
    )
    return style, similar
