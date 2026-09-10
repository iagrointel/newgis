"""Guardas da matriz de conformidade dos serviços (item L2-04-j).

Não toca banco nem rede: lê `tests/esri/conformidade.json` (a saída de `make conformidade`) e a
matriz declarada em `tests/esri/conformidade.py`, e confere quatro coisas que o adversário deste
item vai tentar quebrar:

  1. a seção do `docs/PARIDADE.md` é EXATAMENTE a que se gera do JSON — diferença aqui significa
     documento editado à mão, que é o vício que o item existe para acabar;
  2. nenhuma linha diz `suportado` sem prova que passou na rodada que gerou o JSON;
  3. todos os 45 parâmetros da doc Esri de `query` viraram linha (parâmetro da doc ausente da
     matriz = buraco, e é o primeiro lugar onde o adversário vai olhar);
  4. todo item irmão desta família que já foi construído aparece na matriz."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from tests.esri import conformidade as conf  # noqa: E402

# Itens irmãos com trabalho feito (parcial ou entregue) no laço; a matriz tem de falar de todos.
IRMAOS_CONSTRUIDOS = (
    "L2-04-b-featureserver-catalogo-metadados",
    "L2-04-c-featureserver-query",
    "L2-04-d-featureserver-edicao-anexos",
    "L2-04-e-vector-tile-server-tilejson",
    "L2-04-g-ogc-api-features-crs-cql2",
    "L2-04-servicos-esri-ogc",
)


def _dados() -> dict:
    if not conf.SAIDA.exists():
        pytest.skip(f"{conf.SAIDA.relative_to(RAIZ)} ainda não foi gerado (rode `make conformidade`)")
    return json.loads(conf.SAIDA.read_text(encoding="utf-8"))


def test_secao_do_paridade_e_gerada_sem_edicao_a_mao():
    dados = _dados()
    atual = conf.PARIDADE.read_text(encoding="utf-8")
    assert conf.INICIO in atual and conf.FIM in atual, "docs/PARIDADE.md sem os marcadores da seção gerada"
    esperado = conf._trocar_secao(atual, conf.secao(dados))  # noqa: SLF001 -- a função é do mesmo módulo
    assert esperado == atual, (
        "docs/PARIDADE.md divergiu de tests/esri/conformidade.json — a seção é GERADA: rode "
        "`make conformidade` em vez de editar o documento"
    )


def test_nenhuma_linha_suportada_sem_prova_que_passou():
    dados = _dados()
    sem_prova = [
        li["linha"] for li in dados["linhas"]
        if li["estado"] in ("suportado", "parcial")
        and not [p for p in li["provas"] if p.get("resultado") == "passou"]
    ]
    assert not sem_prova, f"linhas afirmadas sem prova que passou: {sem_prova}"


def test_nenhuma_linha_refutada_ficou_no_documento_como_suportada():
    dados = _dados()
    refutadas = [li["linha"] for li in dados["linhas"] if li["estado"] == "refutado"]
    assert not refutadas, f"prova reprovou e a linha está refutada: {refutadas}"


def test_os_45_parametros_da_doc_de_query_viraram_linha():
    da_matriz = {li["linha"].split(" · ")[-1] for li in conf.matriz() if li["familia"] == "query"}
    faltando = set(conf.PARAMETROS_QUERY_DOC) - da_matriz
    assert not faltando, f"parâmetro da doc Esri ausente da matriz: {sorted(faltando)}"
    assert len(conf.PARAMETROS_QUERY_DOC) == 45, len(conf.PARAMETROS_QUERY_DOC)
    assert len(set(conf.PARAMETROS_QUERY_DOC)) == 45, "parâmetro repetido na lista declarada"


def test_todo_item_irmao_construido_aparece_na_matriz():
    da_matriz = {li["item"] for li in conf.matriz()}
    faltando = set(IRMAOS_CONSTRUIDOS) - da_matriz
    assert not faltando, f"item irmão construído e ausente da matriz: {sorted(faltando)}"


def test_toda_linha_tem_estado_conhecido_e_fonte_datada():
    for li in conf.matriz():
        assert li["estado_declarado"] in conf.ESTADOS, li
        assert li["fonte"] in conf.FONTES, li
        url, acesso = conf.FONTES[li["fonte"]]
        assert url.startswith("https://") and len(acesso) == 10, (li["fonte"], url, acesso)


def test_linha_sem_prova_nunca_e_afirmada_como_suportada_na_matriz_declarada():
    """A regra vale já na DECLARAÇÃO: afirmar 'suportado' sem nomear prova é erro de escrita da matriz."""
    ruins = [li["linha"] for li in conf.matriz()
             if li["estado_declarado"] in ("suportado", "parcial") and not li["provas"]]
    assert not ruins, f"linha afirmada sem prova nomeada: {ruins}"


def test_protocolo_do_parceiro_existe_e_esta_pendente():
    doc = RAIZ / "docs" / "TESTE_PARCEIRO_PRO_AGOL.md"
    assert doc.exists(), "docs/TESTE_PARCEIRO_PRO_AGOL.md não existe"
    texto = doc.read_text(encoding="utf-8")
    assert "resultado: pendente" in texto, "o protocolo do parceiro tem de declarar 'resultado: pendente'"
    assert "resultado: feito" not in texto, "resultado 'feito' sem evidência devolvida pelo parceiro"
