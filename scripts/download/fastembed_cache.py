"""B3: aquece o cache local dos candidatos de embedding do SPEC.md §6 (escolha por recall@5 em ADR-009, M4)."""

from fastembed import TextEmbedding

CANDIDATOS = [
    "paraphrase-multilingual-MiniLM-L12-v2",
    "intfloat/multilingual-e5-small",
]


def main():
    for nome in CANDIDATOS:
        try:
            print(f"baixando {nome}")
            TextEmbedding(model_name=nome)
            print(f"OK {nome}")
        except Exception as e:
            print(f"FALHA {nome}: {e}")


if __name__ == "__main__":
    main()
