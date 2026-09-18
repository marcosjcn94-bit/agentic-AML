"""Revisor determinístico de citações normativas (T1.8, RF-07): verificação de `chunk_id` e SHA-256, sem LLM."""

from aml_guardian.review.verifier import review_citations

__all__ = ["review_citations"]
