"""`applyEdits`/`validar`/ativação da comporta (item L4-03-a-regras-de-conectividade; ADR
docs/adr/20260906T2058-regras-de-conectividade.md).

Cláusulas do portão provadas aqui: "applyEdits que conecta trecho de MT direto a UC de BT é recusado com
código e mensagem que cita a regra"; "'sem regra = proibido' é o padrão"; refutação do item: "adversário
liga MT em BT pela API e conecta trecho a nó inexistente" e "tenta desligar a regra por atributo e confere
que só admin da rede pode". CSV fica em `test_regras_csv.py` (é corpo não-JSON, token só)."""


import pytest

from app.rede_utilidades import instalados
from tests.api.conftest import PREFIXO_TESTE

TRAFO = "transformador_de_distribuicao"
MT = "trecho_de_media_tensao"
BT = "trecho_de_baixa_tensao"
UC = "unidade_consumidora"
POSTE = "ponto_notavel"

# três pontos separados por ~50 m (bem acima da tolerância de 0,5 m — não coincidem entre si) e cada
# feição de aresta liga o ponto de origem (que toca o transformador/UC/poste) a um destino qualquer
P0 = [-46.000000, -23.000000]  # o ponto notável comum (junção) de cada rede de teste
P1 = [-46.000600, -23.000000]  # ~50 m a oeste
P2 = [-46.000000, -23.000600]  # ~50 m ao norte


def _ponto(g):
    return {"type": "Point", "coordinates": g}


def _linha(a, b):
    return {"type": "LineString", "coordinates": [a, b]}


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


@pytest.fixture
def rede_eletrica(sessao_a, limpar_redes, request):
    r = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-regras-{request.node.name[:40]}",
                                          "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar_redes.append(rid)
    bruto = instalados.bruto("eletrica-br")
    assert sessao_a.post(f"/api/rede/{rid}/pacote", content=bruto,
                          headers={"Content-Type": "application/json"}).status_code == 201
    return rid


def _adicionar(sessao, rid, feicoes, associacoes=None):
    corpo = {"adicionar": feicoes, "atualizar": [], "apagar": []}
    if associacoes:
        corpo["associacoes"] = associacoes
    return sessao.post(f"/api/rede/{rid}/applyEdits", json=corpo)


# --------------------------------------------------------------------------------------- conexão permitida

def test_transformador_liga_ao_trecho_de_mt_pelo_terminal_alta(sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "alta"},
    ])
    assert r.status_code == 200, r.text
    assert r.json()["conexoes"] >= 1


def test_transformador_liga_ao_trecho_de_bt_pelo_terminal_baixa_e_ambas_pontas_na_mesma_chamada(
        sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "alta"},
        {"grupo": BT, "tipo": 1, "geometria": _linha(P0, P2), "terminal_inicio": "baixa"},
    ])
    assert r.status_code == 200, r.text
    assert r.json()["conexoes"] == 2  # AT no trecho de MT e BT no trecho de BT, as duas pontas do mesmo poste


# -------------------------------------------------------------------------------- recusa: terminal errado

def test_transformador_no_trecho_de_mt_pelo_terminal_baixa_e_recusado_citando_a_regra(sessao_a, rede_eletrica):
    """Regra existe para o par (transformador, trecho MT), mas só pelo terminal 'alta' — ligar pela
    'baixa' é terminal errado, não ausência de regra, e a mensagem cita a regra candidata."""
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "baixa"},
    ])
    assert r.status_code == 409, r.text
    corpo = r.json()
    assert corpo["erro"] == "terminal_errado"
    assert "alta" in corpo["mensagem"]
    assert corpo.get("detalhe", {}).get("regras_candidatas") or corpo.get("regras_candidatas")


# ------------------------------------------------------------------------ recusa: sem regra (o exemplo do portão)

def test_trecho_de_mt_direto_em_uc_de_bt_e_recusado_sem_regra_citando_a_politica(sessao_a, rede_eletrica):
    """A cláusula literal do portão: "applyEdits que conecta trecho de MT direto a UC de BT é recusado
    com código e mensagem que cita a regra". UC de baixa tensão (tipo 1) só tem regra para o RAMAL de
    ligação, nunca para o trecho de MT — ligar direto é a política padrão em ação."""
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": UC, "tipo": 1, "geometria": _ponto(P0), },
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "conexao"},
    ])
    assert r.status_code == 409, r.text
    corpo = r.json()
    assert corpo["erro"] == "sem_regra"
    assert "sem regra = proibido" in corpo["mensagem"]
    assert "unidade_consumidora" in corpo["mensagem"] and "trecho_de_media_tensao" in corpo["mensagem"]


def test_conectar_a_feicao_inexistente_e_404_nao_conexao_fantasma(sessao_a, rede_eletrica):
    """Refutação do item: "conecta trecho a nó inexistente" — atualizar uma feição que não existe é 404,
    nunca uma conexão criada do nada."""
    r = sessao_a.post(f"/api/rede/{rede_eletrica}/applyEdits", json={
        "adicionar": [], "apagar": [],
        "atualizar": [{"id": "00000000-0000-0000-0000-000000000000", "geometria": _ponto(P0)}],
    })
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "feicao_inexistente"


# -------------------------------------------------------------------------------------- associação (contenção)

def test_associacao_de_contencao_permitida_e_a_invertida_e_recusada(sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": POSTE, "tipo": 1, "geometria": _ponto(P1)},
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P2)},
    ])
    assert r.status_code == 200, r.text
    poste_id, trafo_id = r.json()["adicionadas"]

    ok = sessao_a.post(f"/api/rede/{rede_eletrica}/applyEdits", json={
        "adicionar": [], "atualizar": [], "apagar": [],
        "associacoes": {"adicionar": [{"tipo": "contencao", "de": poste_id, "para": trafo_id}], "apagar": []},
    })
    assert ok.status_code == 200, ok.text
    assert ok.json()["associacoes_adicionadas"] == 1

    invertida = sessao_a.post(f"/api/rede/{rede_eletrica}/applyEdits", json={
        "adicionar": [], "atualizar": [], "apagar": [],
        "associacoes": {"adicionar": [{"tipo": "contencao", "de": trafo_id, "para": poste_id}], "apagar": []},
    })
    assert invertida.status_code == 409, invertida.text
    assert invertida.json()["erro"] == "sem_regra"


# --------------------------------------------------------------------------------------------- validar (lote)

def test_validar_acha_o_erro_que_a_ativacao_desligada_deixou_passar(sessao_a, rede_eletrica):
    """A comporta desligada grava a conexão sem regra (regra_id NULL); `validar` reavalia tudo contra o
    conjunto vigente e acha o erro que o applyEdits, sob comporta desligada, deixou passar — a validação
    NUNCA respeita a comporta (senão desligar escondia o próprio instrumento de auditoria)."""
    desl = sessao_a.put(f"/api/rede/{rede_eletrica}/regras/ativacao", json={"ativa": False})
    assert desl.status_code == 200 and desl.json()["regras_ativas"] is False
    try:
        r = _adicionar(sessao_a, rede_eletrica, [
            {"grupo": UC, "tipo": 1, "geometria": _ponto(P0)},
            {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "conexao"},
        ])
        assert r.status_code == 200, r.text  # a comporta desligada deixa passar
        v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar")
        assert v.status_code == 200, v.text
        corpo = v.json()
        assert corpo["total_erros"] >= 1
        assert any(e["codigo"] == "sem_regra" for e in corpo["erros"])
    finally:
        sessao_a.put(f"/api/rede/{rede_eletrica}/regras/ativacao", json={"ativa": True})


# ------------------------------------------------------------------------------------ comporta: só rede.administrar

def test_editor_nao_desliga_a_comporta_so_administrar_pode(sessao_a, usuarios_a, rede_eletrica):
    """Refutação do item: "tenta desligar a regra por atributo e confere que só admin da rede pode" — não
    existe atributo de feição que abra a comporta; a única porta é `PUT .../regras/ativacao`, e só
    `rede.administrar` (perfil admin) passa."""
    editor, _, _ = usuarios_a.sessao("editor")
    r = editor.put(f"/api/rede/{rede_eletrica}/regras/ativacao", json={"ativa": False})
    assert r.status_code == 403, r.text
    assert r.json()["erro"] == "sem_privilegio"

    campo_extra = editor.post(f"/api/rede/{rede_eletrica}/applyEdits", json={
        "adicionar": [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0), "regras_ativas": False}],
        "atualizar": [], "apagar": [],
    })
    assert campo_extra.status_code == 422  # extra="forbid": não existe esse campo na entrada de feição

    admin = sessao_a
    ligado = admin.put(f"/api/rede/{rede_eletrica}/regras/ativacao", json={"ativa": True})
    assert ligado.status_code == 200 and ligado.json()["regras_ativas"] is True


def test_ativacao_e_isolada_por_rede_desligar_uma_nao_afeta_outra(sessao_a, limpar_redes):
    r1 = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-regras-iso-1", "disciplina": "eletrica"})
    r2 = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-regras-iso-2", "disciplina": "eletrica"})
    rid1, rid2 = r1.json()["id"], r2.json()["id"]
    limpar_redes += [rid1, rid2]
    for rid in (rid1, rid2):
        assert sessao_a.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                              headers={"Content-Type": "application/json"}).status_code == 201
    assert sessao_a.put(f"/api/rede/{rid1}/regras/ativacao", json={"ativa": False}).status_code == 200
    assert sessao_a.get(f"/api/rede/{rid1}").json()["regras_ativas"] is False
    assert sessao_a.get(f"/api/rede/{rid2}").json()["regras_ativas"] is True


# -------------------------------------------------------------------------------- isolamento entre inquilinos

def test_regras_de_um_inquilino_nao_valem_para_a_rede_de_outro(sessao_a, sessao_b, limpar_redes):
    r = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-regras-cross", "disciplina": "eletrica"})
    rid = r.json()["id"]
    limpar_redes.append(rid)
    assert sessao_a.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                          headers={"Content-Type": "application/json"}).status_code == 201
    assert sessao_b.get(f"/api/rede/{rid}").status_code == 404
    assert sessao_b.put(f"/api/rede/{rid}/regras/ativacao", json={"ativa": False}).status_code == 404
    assert sessao_b.post(f"/api/rede/{rid}/validar").status_code == 404
