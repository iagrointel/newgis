"""Rede simples — equivalente de disciplina ao Trace Network da Esri (item L4-18-rede-simples-trace-network).

Cláusulas do portão provadas aqui:
1. criar rede simples a partir de DUAS camadas do inquilino (linhas + pontos) numa chamada só, com a rede,
   as feições e a topologia prontas no fim (`test_cria_rede_simples_de_duas_camadas`); os ≤ 3 cliques da tela
   estão em `tests/e2e/test_rede_simples.py`;
2. direção de fluxo POR ATRIBUTO: o campo declarado da camada é traduzido para o vocabulário fechado
   (`test_direcao_de_fluxo_vem_do_atributo_declarado`) e manda no traçado
   (`test_jusante_e_montante_seguem_a_direcao`);
3. montante/jusante contra networkx na bacia do BC250 — em `test_rede_simples_bacia_bc250.py`;
4. 'promover a rede de utilidades' cria o pacote mínimo (`test_promover_cria_pacote_minimo`);
5. paridade escrita contra o Trace Network — `docs/rede/REDE_SIMPLES.md`, conferida por
   `tests/unit/test_rede_simples_paridade.py`.

Refutação do item (`test_refutacao_indeterminada_para_o_tracado_com_aviso`): direção 'indeterminada' num
trecho faz montante e jusante pararem nele, com aviso nomeando o trecho e o nó.
"""

import pytest

from tests.api.apoio_camada_teste import (
    conexao,
    criar_tabela_linhas,
    criar_tabela_pontos,
    registrar_item,
)
from tests.api.conftest import PREFIXO_TESTE

SCHEMA_DADO = "d_demo"
TAB_LINHAS = "zt_l418_trechos"
TAB_PONTOS = "zt_l418_juncoes"
CAMPOS_LINHA = ["nome", "sentido"]
CAMPOS_PONTO = ["nome"]
MAPA = {"jusante": "digitalizada", "invertido": "contra", "desconhecido": "indeterminada"}

# rede sintética em cruz: A->B, D->B, C->B digitalizado mas com fluxo CONTRA (logo B->C), C->E indeterminado.
A, B, C, D, E = (0.0, 0.0), (0.001, 0.0), (0.002, 0.0), (0.001, 0.001), (0.003, 0.0)
TRECHOS = [
    {"nome": "t1", "sentido": "jusante", "coordenadas": [A, B]},
    {"nome": "t2", "sentido": "jusante", "coordenadas": [D, B]},
    {"nome": "t3", "sentido": "invertido", "coordenadas": [C, B]},
    {"nome": "t4", "sentido": "desconhecido", "coordenadas": [C, E]},
]
PONTOS = [{"nome": n, "lon": p[0], "lat": p[1]} for n, p in
          (("A", A), ("B", B), ("C", C), ("D", D), ("E", E))]


@pytest.fixture(scope="module")
def camadas_sinteticas():
    """As duas camadas do inquilino demo, criadas uma vez por módulo (tabelas de nome fixo com o prefixo do
    item; nada fora desse prefixo é tocado)."""
    con = conexao()
    try:
        criar_tabela_linhas(con, SCHEMA_DADO, TAB_LINHAS, TRECHOS, CAMPOS_LINHA)
        criar_tabela_pontos(con, SCHEMA_DADO, TAB_PONTOS, PONTOS, CAMPOS_PONTO)
    finally:
        con.close()
    return {"linhas": TAB_LINHAS, "pontos": TAB_PONTOS}


@pytest.fixture
def redes_criadas(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _itens(sessao, sufixo: str) -> tuple[str, str]:
    linha = registrar_item(sessao, f"{PREFIXO_TESTE}-l418-linhas-{sufixo}", SCHEMA_DADO, TAB_LINHAS,
                           "MultiLineString", CAMPOS_LINHA)
    ponto = registrar_item(sessao, f"{PREFIXO_TESTE}-l418-pontos-{sufixo}", SCHEMA_DADO, TAB_PONTOS,
                           "Point", CAMPOS_PONTO)
    return linha, ponto


def _criar_rede(sessao, redes, sufixo, camada_linha, camada_ponto, campo_direcao="sentido", mapa=None):
    corpo = {
        "nome": f"{PREFIXO_TESTE}-simples-{sufixo}", "disciplina": "agua",
        "camada_linha_id": camada_linha, "camada_ponto_id": camada_ponto,
        "campo_direcao": campo_direcao, "mapa_direcao": MAPA if mapa is None else mapa,
        "atributos_rede": [{"nome": "nome", "tipo_dado": "texto", "de": "linha"}],
    }
    r = sessao.post("/api/rede/simples", json=corpo)
    assert r.status_code == 201, r.text
    redes.append(r.json()["rede_id"])
    return r.json()


def _tracar(sessao, rid, tipo, lon, lat, **extra):
    corpo = {"tipo": tipo, "pontos_partida": [{"lon": lon, "lat": lat, "tolerancia_m": 1.0}], **extra}
    r = sessao.post(f"/api/rede/{rid}/tracar", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def t4_id(sessao, rid) -> str:
    r = sessao.get(f"/api/rede/{rid}/feicoes/linhas?limite=100")
    return next(f["id"] for f in r.json()["itens"] if f["atributos"]["nome"] == "t4")


def _nomes(sessao, rid, resultado) -> set[str]:
    """Os nomes dos TRECHOS que o traçado devolveu (elemento sem terminal é trecho)."""
    r = sessao.get(f"/api/rede/{rid}/feicoes/linhas?limite=100")
    assert r.status_code == 200, r.text
    por_id = {f["id"]: f["atributos"].get("nome") for f in r.json()["itens"]}
    return {por_id[e["feicao_id"]] for e in resultado["elementos"] if e["terminal"] is None}


# --- cláusula 1 -------------------------------------------------------------------------------------------

def test_cria_rede_simples_de_duas_camadas(sessao_a, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "criar")
    saida = _criar_rede(sessao_a, redes_criadas, "criar", linha, ponto)
    assert saida["modo"] == "simples"
    assert saida["feicoes"] == {"trechos": len(TRECHOS), "juncoes": len(PONTOS)}
    # 5 nós: a junção de cada ponto funde com as pontas de trecho coincidentes (A,B,C,D,E)
    assert saida["topologia"]["nos"] == 5, saida["topologia"]
    assert saida["topologia"]["arestas"] == len(TRECHOS)
    assert saida["topologia"]["arestas_sem_no"] == 0

    ficha = sessao_a.get(f"/api/rede/{saida['rede_id']}").json()
    assert ficha["pacote"] is None, "rede simples não tem pacote de ativos"
    assert sessao_a.get(f"/api/rede/{saida['rede_id']}/pacote").status_code == 404

    cfg = sessao_a.get(f"/api/rede/{saida['rede_id']}/simples").json()
    assert cfg["camada_linha_id"] == linha and cfg["camada_ponto_id"] == ponto
    assert cfg["campo_direcao"] == "sentido"
    assert cfg["atributos_rede"] == [{"nome": "nome", "tipo_dado": "texto", "de": "linha"}]


def test_camada_de_outro_tipo_e_recusada(sessao_a, camadas_sinteticas):
    r = sessao_a.post("/api/itens", json={"tipo": "mapa", "titulo": f"{PREFIXO_TESTE}-l418-mapa",
                                          "dados": {"esquema_versao": 1, "corpo": {}}})
    assert r.status_code == 201, r.text
    mapa_id = r.json()["id"]
    r = sessao_a.post("/api/rede/simples", json={
        "nome": f"{PREFIXO_TESTE}-simples-recusa", "disciplina": "agua", "camada_linha_id": mapa_id})
    assert r.status_code == 422 and r.json()["erro"] == "item_nao_e_camada", r.text


def test_campo_de_direcao_inexistente_e_recusado(sessao_a, camadas_sinteticas):
    linha, _ponto = _itens(sessao_a, "campo-ruim")
    r = sessao_a.post("/api/rede/simples", json={
        "nome": f"{PREFIXO_TESTE}-simples-campo-ruim", "disciplina": "agua",
        "camada_linha_id": linha, "campo_direcao": "nao_existe"})
    assert r.status_code == 422 and r.json()["erro"] == "campo_direcao_inexistente", r.text


# --- cláusula 2 -------------------------------------------------------------------------------------------

def test_direcao_de_fluxo_vem_do_atributo_declarado(sessao_a, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "direcao")
    saida = _criar_rede(sessao_a, redes_criadas, "direcao", linha, ponto)
    r = sessao_a.get(f"/api/rede/{saida['rede_id']}/feicoes/linhas?limite=100")
    por_nome = {f["atributos"]["nome"]: f["atributos"] for f in r.json()["itens"]}
    assert por_nome["t1"]["direcao_fluxo"] == "digitalizada"
    assert por_nome["t3"]["direcao_fluxo"] == "contra"
    assert por_nome["t4"]["direcao_fluxo"] == "indeterminada"
    # o campo de origem continua no atributo da feição: a tradução acrescenta, nunca substitui
    assert por_nome["t3"]["sentido"] == "invertido"


def test_sem_campo_declarado_tudo_e_digitalizada(sessao_a, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "sem-campo")
    saida = _criar_rede(sessao_a, redes_criadas, "sem-campo", linha, ponto, campo_direcao=None)
    r = sessao_a.get(f"/api/rede/{saida['rede_id']}/feicoes/linhas?limite=100")
    direcoes = {f["atributos"]["direcao_fluxo"] for f in r.json()["itens"]}
    assert direcoes == {"digitalizada"}


def test_valor_fora_do_mapa_vira_indeterminada(sessao_a, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "fora-do-mapa")
    saida = _criar_rede(sessao_a, redes_criadas, "fora-do-mapa", linha, ponto,
                        mapa={"jusante": "digitalizada"})
    r = sessao_a.get(f"/api/rede/{saida['rede_id']}/feicoes/linhas?limite=100")
    por_nome = {f["atributos"]["nome"]: f["atributos"]["direcao_fluxo"] for f in r.json()["itens"]}
    assert por_nome == {"t1": "digitalizada", "t2": "digitalizada", "t3": "indeterminada",
                        "t4": "indeterminada"}


def test_mapa_com_valor_fora_do_vocabulario_e_recusado(sessao_a, camadas_sinteticas):
    linha, _p = _itens(sessao_a, "mapa-ruim")
    r = sessao_a.post("/api/rede/simples", json={
        "nome": f"{PREFIXO_TESTE}-simples-mapa-ruim", "disciplina": "agua", "camada_linha_id": linha,
        "campo_direcao": "sentido", "mapa_direcao": {"jusante": "para_baixo"}})
    assert r.status_code == 422 and r.json()["erro"] == "direcao_invalida", r.text


def test_jusante_e_montante_seguem_a_direcao(sessao_a, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "tracar")
    saida = _criar_rede(sessao_a, redes_criadas, "tracar", linha, ponto)
    rid = saida["rede_id"]

    jus = _tracar(sessao_a, rid, "jusante", *A)
    # de A: t1 leva a B; em B o t3 conduz B->C (direção 'contra'); em C o t4 é indeterminado e para.
    assert _nomes(sessao_a, rid, jus) == {"t1", "t3"}
    assert jus["nos_alcancados"] == 3
    assert jus["parou_em_indeterminada"] is True

    mon = _tracar(sessao_a, rid, "montante", *C)
    # de C: sobe por t3 até B, e de B sobem t1 (A) e t2 (D). O t4 não entra: ele está a jusante de C.
    assert _nomes(sessao_a, rid, mon) == {"t1", "t2", "t3"}
    assert mon["nos_alcancados"] == 4
    # o t4 sai de C e é indeterminado: pelo que se sabe, ele PODERIA correr para C e trazer o E para o
    # montante. O traçado não o atravessa e avisa — resultado curto declarado, nunca silencioso.
    assert mon["parou_em_indeterminada"] is True
    assert {a["feicao_id"] for a in mon["avisos"]} == {t4_id(sessao_a, rid)}

    # jusante de D chega em B e C, mas nunca em A (o t1 aponta para B, não a partir dele)
    assert _nomes(sessao_a, rid, _tracar(sessao_a, rid, "jusante", *D)) == {"t2", "t3"}


def test_barreira_contem_o_tracado_de_fluxo(sessao_a, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "barreira")
    saida = _criar_rede(sessao_a, redes_criadas, "barreira", linha, ponto)
    rid = saida["rede_id"]
    jus = _tracar(sessao_a, rid, "jusante", *A,
                  barreiras=[{"lon": C[0], "lat": C[1], "tolerancia_m": 1.0}])
    assert _nomes(sessao_a, rid, jus) == {"t1"}
    assert jus["nos_alcancados"] == 2


def test_conectado_ignora_a_direcao(sessao_a, camadas_sinteticas, redes_criadas):
    """O traçado conectado (L4-02-a) continua sendo conectividade pura: alcança a rede toda a partir de A,
    inclusive o trecho indeterminado. É a diferença que justifica montante/jusante existirem."""
    linha, ponto = _itens(sessao_a, "conectado")
    saida = _criar_rede(sessao_a, redes_criadas, "conectado", linha, ponto)
    rid = saida["rede_id"]
    con = _tracar(sessao_a, rid, "conectado", *A)
    assert _nomes(sessao_a, rid, con) == {"t1", "t2", "t3", "t4"}


# --- refutação do item ------------------------------------------------------------------------------------

def test_refutacao_indeterminada_para_o_tracado_com_aviso(sessao_a, camadas_sinteticas, redes_criadas):
    """O adversário marca o t3 como indeterminado (por applyEdits, sem reconstruir a topologia) e confere que
    jusante e montante param nele, com aviso nomeando o trecho e o nó da parada."""
    linha, ponto = _itens(sessao_a, "refutacao")
    saida = _criar_rede(sessao_a, redes_criadas, "refutacao", linha, ponto)
    rid = saida["rede_id"]
    feicoes = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas?limite=100").json()["itens"]
    t3 = next(f for f in feicoes if f["atributos"]["nome"] == "t3")

    antes = _tracar(sessao_a, rid, "jusante", *A)
    assert "t3" in _nomes(sessao_a, rid, antes)

    r = sessao_a.post(f"/api/rede/{rid}/feicoes/linhas/applyEdits", json={"updates": [
        {"attributes": {"id": t3["id"], "atributos": {**t3["atributos"], "direcao_fluxo": "indeterminada"}}}
    ]})
    assert r.status_code == 200 and r.json()["updateResults"][0]["success"] is True, r.text

    depois = _tracar(sessao_a, rid, "jusante", *A)
    assert _nomes(sessao_a, rid, depois) == {"t1"}, "o traçado tinha de parar no trecho indeterminado"
    assert depois["parou_em_indeterminada"] is True
    avisos = [a for a in depois["avisos"] if a["feicao_id"] == t3["id"]]
    assert len(avisos) == 1 and avisos[0]["codigo"] == "direcao_indeterminada", depois["avisos"]

    mon = _tracar(sessao_a, rid, "montante", *C)
    assert _nomes(sessao_a, rid, mon) == set(), "montante de C não atravessa o t3 indeterminado"
    assert mon["parou_em_indeterminada"] is True
    assert t3["id"] in {a["feicao_id"] for a in mon["avisos"]}


def test_direcao_com_valor_estranho_e_lida_como_indeterminada(sessao_a, camadas_sinteticas, redes_criadas):
    """Alguém grava 'talvez' no atributo por applyEdits: o traçado para, nunca adivinha um sentido."""
    linha, ponto = _itens(sessao_a, "estranho")
    saida = _criar_rede(sessao_a, redes_criadas, "estranho", linha, ponto)
    rid = saida["rede_id"]
    feicoes = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas?limite=100").json()["itens"]
    t1 = next(f for f in feicoes if f["atributos"]["nome"] == "t1")
    sessao_a.post(f"/api/rede/{rid}/feicoes/linhas/applyEdits", json={"updates": [
        {"attributes": {"id": t1["id"], "atributos": {**t1["atributos"], "direcao_fluxo": "talvez"}}}]})
    jus = _tracar(sessao_a, rid, "jusante", *A)
    assert _nomes(sessao_a, rid, jus) == set()
    assert [a["feicao_id"] for a in jus["avisos"]] == [t1["id"]]


# --- cláusula 4 -------------------------------------------------------------------------------------------

def test_promover_cria_pacote_minimo(sessao_a, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "promover")
    saida = _criar_rede(sessao_a, redes_criadas, "promover", linha, ponto)
    rid = saida["rede_id"]
    assert sessao_a.get(f"/api/rede/{rid}/pacote").status_code == 404

    r = sessao_a.post(f"/api/rede/{rid}/promover")
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["modo"] == "utilidades" and res["codigo"] == "rede-simples"
    assert res["contagens"] == {"dominios": 1, "tiers": 1, "categorias": 0, "terminais": 1, "grupos": 2,
                                "tipos": 2, "atributos": 1, "regras": 1}

    pacote = sessao_a.get(f"/api/rede/{rid}/pacote")
    assert pacote.status_code == 200, pacote.text
    import hashlib

    assert hashlib.sha256(pacote.content).hexdigest() == res["sha256"], "o pacote exportado é o carimbado"
    doc = pacote.json()
    assert doc["esquema"] == "plat.rede.pacote"
    assert {g["codigo"] for g in doc["grupos"]} == {"juncao", "trecho"}

    ficha = sessao_a.get(f"/api/rede/{rid}").json()
    assert ficha["pacote"]["codigo"] == "rede-simples" and ficha["pacote"]["sha256"] == res["sha256"]

    # promover duas vezes não faz sentido: a rede já é de utilidades
    assert sessao_a.post(f"/api/rede/{rid}/promover").status_code == 409

    # e a rede continua funcionando: o traçado de fluxo dá o mesmo resultado depois de promovida
    assert _nomes(sessao_a, rid, _tracar(sessao_a, rid, "jusante", *A)) == {"t1", "t3"}


def test_promover_rede_de_utilidades_e_recusado(sessao_a, redes_criadas):
    r = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-simples-nao-e", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    redes_criadas.append(rid)
    r = sessao_a.post(f"/api/rede/{rid}/promover")
    assert r.status_code == 409 and r.json()["erro"] == "rede_nao_e_simples", r.text


# --- isolamento entre inquilinos (cláusula inegociável de toda a linha) -----------------------------------

def test_inquilino_b_nunca_ve_a_rede_simples_de_a(sessao_a, sessao_b, camadas_sinteticas, redes_criadas):
    linha, ponto = _itens(sessao_a, "isolamento")
    saida = _criar_rede(sessao_a, redes_criadas, "isolamento", linha, ponto)
    rid = saida["rede_id"]
    assert sessao_b.get(f"/api/rede/{rid}/simples").status_code == 404
    assert sessao_b.post(f"/api/rede/{rid}/promover").status_code == 404
    assert sessao_b.post(f"/api/rede/{rid}/tracar",
                         json={"tipo": "jusante",
                               "pontos_partida": [{"lon": A[0], "lat": A[1]}]}).status_code == 404
    assert sessao_b.post("/api/rede/simples", json={
        "nome": f"{PREFIXO_TESTE}-simples-roubo", "disciplina": "agua",
        "camada_linha_id": linha}).status_code == 404
