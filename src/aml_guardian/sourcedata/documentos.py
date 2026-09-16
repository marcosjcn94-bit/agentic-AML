"""Documentos e contas sintéticos da camada brasileira (T0.7, SPEC.md §8.3, DT-03).

Todo CPF/CNPJ é gerado em tempo de execução a partir de uma seed e tem dígito verificador válido — nenhum
documento é versionado no repositório (`CLAUDE.md`, "Dados de teste"; gate de saída do M0). Os documentos são
sintéticos, mas o `SPEC.md` §8.1 manda tratá-los como dado pessoal real: só existem no `core_sintetico`.

O DV segue o algoritmo de módulo 11 da Receita Federal. Documentos de dígitos repetidos (`111.111.111-11`)
satisfazem a aritmética, mas são inválidos por convenção: são recusados na validação e nunca gerados.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

CPF_DIGITOS = 11
CNPJ_DIGITOS = 14

#: Pesos do módulo 11, do dígito mais à esquerda para o mais à direita, em cada passada.
_PESOS_CPF_1 = tuple(range(10, 1, -1))
_PESOS_CPF_2 = tuple(range(11, 1, -1))
_PESOS_CNPJ_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

#: Sufixo de filial do CNPJ: a PoC gera apenas matriz (`0001`), como é o caso da esmagadora maioria dos clientes.
_FILIAL_MATRIZ = (0, 0, 0, 1)

#: Pesos cíclicos do DV da conta bancária sintética (2 a 9, da direita para a esquerda).
_PESOS_CONTA = (2, 3, 4, 5, 6, 7, 8, 9)
_CONTA_DIGITOS = 11


def _dv(digitos: Sequence[int], pesos: Sequence[int]) -> int:
    """Dígito verificador de módulo 11: resto < 2 vira 0, os demais viram `11 - resto`."""
    resto = sum(digito * peso for digito, peso in zip(digitos, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def _digitos(documento: str, tamanho: int) -> list[int] | None:
    """Converte para lista de inteiros; devolve `None` se não for exatamente `tamanho` dígitos ou se for repetido."""
    if len(documento) != tamanho or not documento.isdigit():
        return None
    if len(set(documento)) == 1:
        return None
    return [int(caractere) for caractere in documento]


def cpf_valido(documento: str) -> bool:
    """`True` se `documento` tem 11 dígitos, não é repetição de um único dígito e os dois DV conferem."""
    digitos = _digitos(documento, CPF_DIGITOS)
    if digitos is None:
        return False
    return digitos[9] == _dv(digitos[:9], _PESOS_CPF_1) and digitos[10] == _dv(digitos[:10], _PESOS_CPF_2)


def cnpj_valido(documento: str) -> bool:
    """`True` se `documento` tem 14 dígitos, não é repetição de um único dígito e os dois DV conferem."""
    digitos = _digitos(documento, CNPJ_DIGITOS)
    if digitos is None:
        return False
    return digitos[12] == _dv(digitos[:12], _PESOS_CNPJ_1) and digitos[13] == _dv(digitos[:13], _PESOS_CNPJ_2)


def documento_valido(documento: str) -> bool:
    """`True` para CPF ou CNPJ válido, apenas dígitos (sem pontuação)."""
    return cpf_valido(documento) or cnpj_valido(documento)


def _com_dv(base: list[int], pesos_1: Sequence[int], pesos_2: Sequence[int]) -> str:
    primeiro = _dv(base, pesos_1)
    segundo = _dv([*base, primeiro], pesos_2)
    return "".join(str(digito) for digito in [*base, primeiro, segundo])


def gera_cpf(rng: random.Random) -> str:
    """CPF sintético de DV válido, só dígitos. Determinístico para um mesmo `rng` e mesma ordem de chamadas."""
    while True:
        base = [rng.randrange(10) for _ in range(9)]
        documento = _com_dv(base, _PESOS_CPF_1, _PESOS_CPF_2)
        if cpf_valido(documento):
            return documento


def gera_cnpj(rng: random.Random) -> str:
    """CNPJ sintético de matriz (`0001`) com DV válido, só dígitos."""
    while True:
        base = [rng.randrange(10) for _ in range(8)] + list(_FILIAL_MATRIZ)
        documento = _com_dv(base, _PESOS_CNPJ_1, _PESOS_CNPJ_2)
        if cnpj_valido(documento):
            return documento


def gera_documentos(rng: random.Random, quantidade: int, *, pessoa_juridica: bool = False) -> list[str]:
    """`quantidade` documentos distintos: a unicidade é garantida aqui, não confiada ao sorteio.

    O `cpf_cnpj` é chave única no `core_sintetico` (um documento por cliente), então a colisão precisa ser
    resolvida na geração — descartar o repetido e sortear de novo mantém o resultado determinístico pela seed.
    """
    if quantidade < 0:
        raise ValueError(f"quantidade de documentos negativa: {quantidade}")
    gerador = gera_cnpj if pessoa_juridica else gera_cpf
    documentos: list[str] = []
    vistos: set[str] = set()
    while len(documentos) < quantidade:
        documento = gerador(rng)
        if documento in vistos:
            continue
        vistos.add(documento)
        documentos.append(documento)
    return documentos


def conta_bancaria(conta_origem: str) -> str:
    """Conta no formato brasileiro `AAAA-CCCCCCC-D` derivada da conta numérica do SAML-D.

    A derivação é determinística e injetora: os dígitos da origem, preenchidos à esquerda até 11, viram agência
    e número, e o DV é calculado sobre eles. O preenchimento só é injetor sobre números em forma canônica —
    `1` e `00000000001` seriam a mesma conta —, e as contas do SAML-D têm de 4 a 10 dígitos SEM zero à
    esquerda (conferido nas 9.504.852 linhas: nenhuma ocorrência dos dois lados). Zero à esquerda é recusado
    aqui para que a injeção seja invariante imposta, e não suposição sobre a base de origem.
    """
    digitos = "".join(caractere for caractere in conta_origem if caractere.isdigit())
    if not digitos:
        raise ValueError(f"conta de origem sem dígito algum: {conta_origem!r}")
    if len(digitos) > _CONTA_DIGITOS:
        raise ValueError(f"conta de origem com mais de {_CONTA_DIGITOS} dígitos: {conta_origem!r}")
    if len(digitos) > 1 and digitos.startswith("0"):
        raise ValueError(f"conta de origem com zero à esquerda quebraria a injeção: {conta_origem!r}")
    preenchida = digitos.zfill(_CONTA_DIGITOS)
    agencia, numero = preenchida[:4], preenchida[4:]
    invertidos = [int(caractere) for caractere in reversed(preenchida)]
    soma = sum(digito * _PESOS_CONTA[indice % len(_PESOS_CONTA)] for indice, digito in enumerate(invertidos))
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return f"{agencia}-{numero}-{dv}"
