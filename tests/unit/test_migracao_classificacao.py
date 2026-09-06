"""Tabela de classificação e leitura de dependência do inventário de Portal/AGOL
(item L2-08-a-leitor-portal-inventario). Sem banco e sem rede: só as decisões de leitura."""

import json
from pathlib import Path

import pytest

from app.migracao import classificacao as c
from app.migracao import inventario as motor
from app.migracao import portal as p

RESPOSTAS = Path(__file__).resolve().parents[1] / "migracao" / "respostas" / "portal.json"


# ------------------------------------------------------------------ classificação
def test_camada_hospedada_migra_e_nao_hospedada_e_parcial():
    hospedada = c.classificar("Feature Service", ["Feature Service", "Hosted Service"])
    assert hospedada.classe == c.MIGRA
    nao_hospedada = c.classificar("Feature Service", ["Feature Service"])
    assert nao_hospedada.classe == c.MIGRA_PARCIAL
    assert "Hosted Service" in nao_hospedada.motivo  # o motivo diz POR QUE, não só o rótulo


@pytest.mark.parametrize("tipo", ["Web Experience", "StoryMap", "Notebook", "Workflow", "Hub Site Application",
                                  "Insights Workbook"])
def test_o_que_nao_tem_equivalente_e_nao_migra(tipo):
    assert c.classificar(tipo, []).classe == c.NAO_MIGRA


def test_tipo_fora_da_tabela_e_desconhecido_nunca_nao_migra():
    """Regra 1 do cabeçalho: dizer 'não migra' sobre tipo que ninguém leu é afirmar mais do que se mediu."""
    d = c.classificar("Quantum Widget", [])
    assert d.classe == c.DESCONHECIDO
    assert "Quantum Widget" in d.motivo


def test_palavra_chave_de_rede_de_utilidades_manda_no_tipo():
    d = c.classificar("Feature Service", ["Hosted Service", "Utility Network"])
    assert d.classe == c.NAO_MIGRA and "Utility Network" in d.motivo


def test_toda_decisao_da_tabela_tem_classe_valida_e_motivo():
    for tipo, decisao in c.TABELA.items():
        assert decisao.classe in c.CLASSES, tipo
        assert len(decisao.motivo) > 10, tipo


def test_resumo_sempre_traz_as_quatro_classes():
    assert set(c.resumo([c.MIGRA, c.MIGRA])) == set(c.CLASSES)
    assert c.resumo([c.MIGRA, c.MIGRA])[c.NAO_MIGRA] == 0


# ------------------------------------------------------------------ dependências
def test_dependencia_de_web_map_sai_do_json_do_documento():
    acervo = json.loads(RESPOSTAS.read_text(encoding="utf-8"))
    web_map_id, documento = next(
        (i, d) for i, d in acervo["dados"].items()
        if any(x["type"] == "Web Map" and x["id"] == i for x in acervo["itens"])
    )
    dependencias = motor.dependencias_de(documento, web_map_id)
    assert len(dependencias) >= 1
    assert all(motor.ID_ESRI.match(d["alvo"]) for d in dependencias)
    assert web_map_id not in {d["alvo"] for d in dependencias}  # nunca depende de si mesmo


def test_texto_em_itemid_que_nao_e_id_esri_nao_vira_dependencia():
    achados = motor.dependencias_de({"itemId": "camada de bairros", "webmap": "nao-e-id"})
    assert achados == []


def test_varredura_de_dependencia_tem_teto_de_profundidade():
    fundo = {"itemId": "a" * 32}
    for _ in range(motor.PROFUNDIDADE_MAX + 3):
        fundo = {"nivel": fundo}
    assert motor.dependencias_de(fundo) == []


# ------------------------------------------------------------------ credencial em texto
def test_redigir_troca_o_token_em_qualquer_texto():
    assert p.redigir("falhou com tok-123", "tok-123") == "falhou com ***"
    assert p.redigir("sem token", None) == "sem token"


def test_o_token_viaja_em_cabecalho_e_nunca_na_url():
    """Se o token fosse `?token=...`, toda URL em log de job, log de acesso e mensagem de erro carregaria a
    credencial do cliente. A prova de ponta a ponta está no teste de API; aqui é a unidade."""
    cliente = p.ClientePortal(base="https://portal.invalido/portal", token="tok-secreto")
    url = p._juntar("https://portal.invalido/portal", "sharing/rest/search", {"q": "orgid:1", "f": "json"})
    cabecalhos = cliente._cabecalhos(url)
    assert cabecalhos["X-Esri-Authorization"] == "Bearer tok-secreto"
    assert "tok-secreto" not in url and url.startswith("https://portal.invalido/portal/sharing/rest/search?")
    # achado B1/B1b (conserto): a MESMA credencial não viaja para um host que não é o portal configurado
    assert "X-Esri-Authorization" not in cliente._cabecalhos("https://outro-host.invalido/servico")


def test_modulo_so_monta_caminho_de_leitura():
    """Só-leitura literal, conferido no CÓDIGO e não no texto: todo caminho que o módulo sabe montar sai de
    uma lista fechada de leitura, e o único método diferente de GET é o POST do generateToken."""
    import ast

    arvore = ast.parse(Path(p.__file__).read_text(encoding="utf-8"))
    permitidos = {
        "sharing/rest", "sharing/rest/generateToken", "sharing/rest/portals/self", "sharing/rest/search",
        "sharing/rest/content/items/{item_id}", "sharing/rest/content/items/{item_id}/data",
        "sharing/rest/content/items/{item_id}/resources",
        "sharing/rest/content/items/{item_id}/relatedItems",
        "sharing/rest/portals/{portal_id}/groups", "sharing/rest/community/groups/{grupo_id}/users",
        "sharing/rest/portals/{portal_id}/users", "{camada_id}/query", "",
    }
    caminhos, metodos = set(), set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and getattr(no.func, "attr", getattr(no.func, "id", "")) in (
            "obter", "_juntar", "_json", "_requisitar"
        ):
            for arg in no.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    (metodos if arg.value in ("GET", "POST", "HEAD") else caminhos).add(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    partes = []
                    for pedaco in arg.values:
                        if isinstance(pedaco, ast.Constant):
                            partes.append(str(pedaco.value))
                        else:
                            alvo = pedaco.value
                            partes.append("{%s}" % (getattr(alvo, "id", getattr(alvo, "attr", "?"))))
                    caminhos.add("".join(partes))
    assert caminhos - permitidos == set(), caminhos - permitidos
    assert metodos <= {"GET", "POST"}
