"""Documentos sintéticos da camada brasileira (T0.7): CPF/CNPJ com DV válido por seed e guarda de versionamento.

Nenhum documento é versionado: todos são gerados em tempo de execução (`TASKS.md` §1, CLAUDE.md "Dados de teste").
A última seção varre o próprio repositório para provar que nenhum CPF/CNPJ de DV válido entrou no git.
"""

from __future__ import annotations

import random
import re
import subprocess
from pathlib import Path

import pytest

from aml_guardian.sourcedata.documentos import (
    cnpj_valido,
    conta_bancaria,
    cpf_valido,
    documento_valido,
    gera_cnpj,
    gera_cpf,
    gera_documentos,
)

RAIZ = Path(__file__).resolve().parents[2]

#: Sequências de 11 ou 14 dígitos, com ou sem a pontuação usual, como apareceriam num arquivo versionado.
CANDIDATO = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")

#: Extensões varridas: todo arquivo de texto do repositório. Binários e dados brutos ficam fora.
EXTENSOES = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".cfg", ".ini", ".sql", ".html", ".j2"}


def _rng(seed: int = 20260916) -> random.Random:
    return random.Random(seed)


# --- Dígito verificador ---


def test_todo_cpf_gerado_tem_dv_valido():
    rng = _rng()
    documentos = [gera_cpf(rng) for _ in range(500)]
    assert all(len(documento) == 11 and documento.isdigit() for documento in documentos)
    assert all(cpf_valido(documento) for documento in documentos)


def test_todo_cnpj_gerado_tem_dv_valido():
    rng = _rng()
    documentos = [gera_cnpj(rng) for _ in range(500)]
    assert all(len(documento) == 14 and documento.isdigit() for documento in documentos)
    assert all(cnpj_valido(documento) for documento in documentos)


def test_dv_errado_e_recusado():
    rng = _rng()
    cpf = gera_cpf(rng)
    trocado = cpf[:-1] + str((int(cpf[-1]) + 1) % 10)
    assert not cpf_valido(trocado)
    cnpj = gera_cnpj(rng)
    trocado = cnpj[:-1] + str((int(cnpj[-1]) + 1) % 10)
    assert not cnpj_valido(trocado)


def test_documento_de_digitos_repetidos_e_recusado():
    """`111.111.111-11` satisfaz a aritmética do DV, mas é documento inválido e não pode ser gerado."""
    assert not cpf_valido("11111111111")
    assert not cpf_valido("00000000000")
    assert not cnpj_valido("11111111111111")


def test_documento_de_tamanho_errado_e_recusado():
    assert not cpf_valido("123456789")
    assert not cnpj_valido("1234567890123")
    assert not documento_valido("")
    assert not documento_valido("abcdefghijk")


def test_documento_valido_aceita_as_duas_larguras():
    rng = _rng()
    assert documento_valido(gera_cpf(rng))
    assert documento_valido(gera_cnpj(rng))


def test_geracao_e_deterministica_por_seed():
    assert [gera_cpf(_rng()) for _ in range(3)] == [gera_cpf(_rng()) for _ in range(3)]
    assert gera_cpf(_rng(1)) != gera_cpf(_rng(2))


def test_documentos_gerados_em_lote_nao_se_repetem():
    """`cpf_cnpj` é chave única no `core_sintetico`: a unicidade é garantida, não confiada ao sorteio."""
    documentos = gera_documentos(_rng(), 2000)
    assert len(set(documentos)) == 2000
    assert all(cpf_valido(documento) for documento in documentos)
    assert documentos == gera_documentos(_rng(), 2000)


def test_lote_de_cnpj_tambem_e_unico_e_valido():
    documentos = gera_documentos(_rng(), 500, pessoa_juridica=True)
    assert len(set(documentos)) == 500
    assert all(cnpj_valido(documento) for documento in documentos)


# --- Conta bancária sintética ---


def test_conta_bancaria_e_deterministica_e_formatada():
    conta = conta_bancaria("8724731955")
    assert conta == conta_bancaria("8724731955")
    assert re.fullmatch(r"\d{4}-\d{7}-\d", conta), conta


def test_contas_de_origem_diferentes_nao_colidem():
    contas = {conta_bancaria(str(8724731955 + i)) for i in range(500)}
    assert len(contas) == 500


def test_contas_de_comprimentos_diferentes_nao_colidem():
    """O SAML-D tem contas de 4 a 10 dígitos; sem zero à esquerda, o preenchimento continua injetor."""
    origens = ("1", "12", "1234", "123456789", "1234567890")
    assert len({conta_bancaria(origem) for origem in origens}) == len(origens)


def test_conta_com_zero_a_esquerda_e_recusada():
    """`1` e `00000000001` virariam a mesma conta: a forma não canônica é recusada em vez de colidir."""
    with pytest.raises(ValueError, match="zero à esquerda"):
        conta_bancaria("00000000001")
    with pytest.raises(ValueError, match="zero à esquerda"):
        conta_bancaria("0872473195")


# --- Guarda: nenhum CPF/CNPJ literal versionado (Gate de saída do M0) ---


def _arquivos_versionados() -> list[Path]:
    saida = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, text=True, check=True, timeout=120
    ).stdout
    return [RAIZ / nome for nome in saida.split("\0") if nome and Path(nome).suffix in EXTENSOES]


def test_nenhum_cpf_ou_cnpj_de_dv_valido_esta_versionado():
    arquivos = _arquivos_versionados()
    assert arquivos, "git ls-files não retornou arquivo de texto algum"
    achados: list[str] = []
    for arquivo in arquivos:
        try:
            texto = arquivo.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for bruto in CANDIDATO.findall(texto):
            documento = re.sub(r"\D", "", bruto)
            if documento_valido(documento):
                achados.append(f"{arquivo.relative_to(RAIZ)}: {bruto}")
    assert achados == [], f"documento de DV válido versionado: {achados}"


def test_a_varredura_detecta_um_documento_plantado(tmp_path):
    """Guarda da guarda: prova que a varredura acima falharia se um documento válido fosse versionado."""
    documento = gera_cpf(_rng())
    plantado = tmp_path / "exemplo.md"
    plantado.write_text(f"cliente: {documento}\n", encoding="utf-8")
    achados = [bruto for bruto in CANDIDATO.findall(plantado.read_text(encoding="utf-8"))]
    assert achados == [documento]
    assert documento_valido(re.sub(r"\D", "", achados[0]))


@pytest.mark.parametrize("texto", ["12345678901", "000.000.000-00", "tx-0001", "9504852"])
def test_varredura_ignora_numero_que_nao_e_documento(texto):
    achados = [re.sub(r"\D", "", bruto) for bruto in CANDIDATO.findall(texto)]
    assert not any(documento_valido(documento) for documento in achados)
