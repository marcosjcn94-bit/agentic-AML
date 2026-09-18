from aml_guardian.sourcedata.mapping import load_saml_d_mapping
from aml_guardian.sourcedata.mapping_validation import (
    curated_typology_labels,
    validate_curated_article_refs,
)


def test_curadoria_existente_aponta_para_chunks_do_corpus() -> None:
    mapping = load_saml_d_mapping()
    refs = {
        "CC4001/art1/i1/d",
        "CC4001/art1/i1/e",
        "CC4001/art1/i1/k",
        "CC4001/art1/i4",
    }

    assert validate_curated_article_refs(mapping, refs) == []
    assert curated_typology_labels(mapping) == {"Structuring"}


def test_referencia_curada_inexistente_falha() -> None:
    mapping = load_saml_d_mapping()
    assert validate_curated_article_refs(mapping, set()) == [
        "Structuring: article_ref ausente no corpus: CC4001/art1/i1/d",
        "Structuring: article_ref ausente no corpus: CC4001/art1/i1/e",
        "Structuring: article_ref ausente no corpus: CC4001/art1/i1/k",
        "Structuring: article_ref ausente no corpus: CC4001/art1/i4",
    ]
