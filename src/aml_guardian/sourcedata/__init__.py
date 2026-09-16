"""Dados de origem (ADR-005, SPEC.md §8.3): mapeamento de tipologias e leitura do SAML-D."""

from aml_guardian.sourcedata.mapping import (
    CRITICAS_ESPERADAS,
    MAPPINGS_DIR,
    SAML_D_MAPPING_FILE,
    SamlDMapping,
    Tipologia,
    load_saml_d_mapping,
)
from aml_guardian.sourcedata.saml_loader import (
    FIXED_COLUMNS,
    FLAG_COLUMNS,
    RAW_DIR,
    SAML_D_FILE,
    TYPE_COLUMNS,
    LoadReport,
    SamlHeader,
    SamlLoaderError,
    iter_transactions,
    read_header,
    validate_file,
    validate_header,
)

__all__ = [
    "CRITICAS_ESPERADAS",
    "FIXED_COLUMNS",
    "FLAG_COLUMNS",
    "MAPPINGS_DIR",
    "RAW_DIR",
    "SAML_D_FILE",
    "SAML_D_MAPPING_FILE",
    "TYPE_COLUMNS",
    "LoadReport",
    "SamlDMapping",
    "SamlHeader",
    "SamlLoaderError",
    "Tipologia",
    "iter_transactions",
    "load_saml_d_mapping",
    "read_header",
    "validate_file",
    "validate_header",
]
