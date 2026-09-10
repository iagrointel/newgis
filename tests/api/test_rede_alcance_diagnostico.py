"""Alcance do traçado e diagnóstico de órfão por classe (item L4-01-f-alcance-do-tracado-rede-real).

O item nasceu de uma medida: no ativo de referência, o traçado a jusante de um alimentador alcançava 34 dos
50 transformadores que o cadastro filia a ele. A causa medida não é o traçado — é a topologia, e dentro dela
uma coisa só: a camada de PONTO do arquivo guarda a coordenada com 6 casas decimais de grau e a camada de
LINHA com 13, então o MESMO poste aparece nas duas com até 0,073 m de diferença. Os 16 transformadores fora
estavam todos entre 0,051 m e 0,071 m da ponta de trecho mais próxima.

O conserto NÃO é subir a tolerância da rede: no mesmo ativo, com 1,0 m os laços da média tensão sobem de 584
para 638, porque o que funde nessa folga são pontas de trechos VIZINHOS. O conserto é a tolerância declarada
por PAR DE TIPOS (`plat.rede_regra.tolerancia_m`): o par (dispositivo de ponto, trecho) ganha a folga que a
precisão do cadastro de ponto exige e o par (trecho, trecho) não ganha nada.

Aqui isso é provado em rede pequena e determinística, sem depender do ativo (que não está no repositório):
os MESMOS 0,08 m conectam num par e não conectam no outro, na MESMA rede e na MESMA construção. A medida em
dado real está em `tests/api/test_rede_alcance_medida.py`."""

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

DIST_ALEM_DA_REDE_M = 0.08   # > 0,05 (tolerância da rede) e < 0,10 (tolerância declarada no par de ponto)


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar, tolerancia_m=None):
    corpo = {"nome": f"{PREFIXO_TESTE}-alcance-{sufixo}", "disciplina": "eletrica"}
    if tolerancia_m is not None:
        corpo["tolerancia_m"] = tolerancia_m
    r = sessao.post("/api/rede", json=corpo)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                    headers={"Content-Type": "application/json"}, timeout=300)
    assert r.status_code == 201, r.text
    return rid


def _linha(sessao, rid, coordenadas, grupo="trecho_de_media_tensao", tipo_codigo=1):
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas",
                    json={"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas})
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo="transformador_de_distribuicao", tipo_codigo=1):
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos",
                    json={"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat})
    assert r.status_code == 201, r.text
    return r.json()


def _habilitar(sessao, rid):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar", timeout=300)
    assert r.status_code == 201, r.text
    return r.json()


def _projetar(env, lon, lat, distancia_m, azimute_graus) -> tuple[float, float]:
    """Ponto a `distancia_m` exatos, medido pelo PostGIS em `geography` — a mesma régua da construção."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT ST_X(p::geometry) AS lon, ST_Y(p::geometry) AS lat FROM (SELECT "
                "ST_Project(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, radians(%s)) AS p) s",
                (lon, lat, distancia_m, azimute_graus),
            )
            r = cur.fetchone()
            return r["lon"], r["lat"]
    finally:
        con.close()


def _classes(sessao, rid, limiar_m=1.0) -> dict:
    r = sessao.get(f"/api/rede/{rid}/topologia/diagnostico?limiar_m={limiar_m}&exemplos=2")
    assert r.status_code == 200, r.text
    corpo = r.json()
    return {c["classe"]: c for c in corpo["classes"]}, corpo


# --- o conserto: a mesma distância conecta num par de tipos e não no outro ------------------------------

def test_dispositivo_conecta_a_008m_e_a_ponta_de_trecho_vizinha_nao(sessao_a, limpar_redes, env):
    """0,08 m está além da tolerância da rede (0,05) e dentro da tolerância declarada no par
    (dispositivo de ponto, trecho) do pacote elétrica-BR (0,10). Na MESMA rede e na MESMA construção:
    o transformador liga; a ponta do trecho vizinho não funde."""
    rid = _criar_rede(sessao_a, "par", limpar_redes)
    p_lon, p_lat = -47.5, -16.0
    _linha(sessao_a, rid, [[-47.501, -16.0], [p_lon, p_lat]])          # trecho A termina em P
    tr_lon, tr_lat = _projetar(env, p_lon, p_lat, DIST_ALEM_DA_REDE_M, 90)
    _ponto(sessao_a, rid, tr_lon, tr_lat)                              # transformador a 0,08 m de P
    b_lon, b_lat = _projetar(env, p_lon, p_lat, DIST_ALEM_DA_REDE_M, 270)
    _linha(sessao_a, rid, [[b_lon, b_lat], [-47.499, -16.0]])          # trecho B começa a 0,08 m de P

    resumo = _habilitar(sessao_a, rid)
    arestas = {e["origem_id"]: e for e in sessao_a.get(f"/api/rede/{rid}/topologia/arestas").json()["itens"]}
    assert resumo["arestas"] == 2 and resumo["arestas_sem_no"] == 0
    # as duas linhas continuam sem nó em comum: o par (trecho, trecho) não ganhou folga nenhuma
    nos = [set() for _ in range(2)]
    for i, e in enumerate(arestas.values()):
        nos[i] = {e["no_origem_id"], e["no_destino_id"]}
    assert nos[0].isdisjoint(nos[1]), "trecho com trecho não pode fundir a 0,08 m com tolerância de rede 0,05"

    # e o transformador ENCOSTOU: um dos seus dois terminais virou nó com aresta (deixou de ser órfão)
    classes, corpo = _classes(sessao_a, rid)
    assert "fora_da_tolerancia_declarada" not in classes, corpo
    assert classes["terminal_sem_par_no_dispositivo"]["contagem"] == 1, corpo
    assert corpo["nos_orfaos"] == 1, corpo


def test_sem_a_tolerancia_do_par_o_mesmo_dispositivo_fica_orfao(sessao_a, limpar_redes, env):
    """Controle negativo do teste acima: a mesma geometria numa rede cujo pacote NÃO declara tolerância no
    par (aqui, apagando a declaração das regras) deixa o transformador fora, e o diagnóstico diz por quê e
    a que distância. É a prova de que quem conecta é a tolerância declarada, não a proximidade."""
    rid = _criar_rede(sessao_a, "sem-par", limpar_redes)
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo"])
        with con.cursor() as cur:
            cur.execute("UPDATE plat.rede_regra SET tolerancia_m = NULL WHERE rede_id = %s::uuid", (rid,))
            assert cur.rowcount > 0, "nenhuma regra alterada: o contexto de inquilino não é o da rede"
        con.commit()
    finally:
        con.close()

    p_lon, p_lat = -47.5, -16.0
    _linha(sessao_a, rid, [[-47.501, -16.0], [p_lon, p_lat]])
    tr_lon, tr_lat = _projetar(env, p_lon, p_lat, DIST_ALEM_DA_REDE_M, 90)
    _ponto(sessao_a, rid, tr_lon, tr_lat)

    resumo = _habilitar(sessao_a, rid)
    assert resumo["nos_orfaos"] == 2, "os dois terminais do transformador ficam fora sem a tolerância do par"
    classes, corpo = _classes(sessao_a, rid)
    fora = classes["fora_da_tolerancia_declarada"]
    assert fora["contagem"] == 2, corpo
    assert fora["distancia_min_m"] == pytest.approx(DIST_ALEM_DA_REDE_M, abs=0.002), corpo
    assert fora["exemplos"][0]["tolerancia_do_par_m"] == pytest.approx(0.05), corpo


# --- a refutação do item: nenhum laço novo no tier de média tensão --------------------------------------

def test_a_tolerancia_do_par_nao_fabrica_laco_na_media_tensao(sessao_a, limpar_redes, env):
    """Refutação declarada do item: "subir a tolerância sozinha não pode ser a solução; o teste reprova se
    aparecer laço no tier de MT". Aqui a malha é um caminho aberto A-B-C cujas duas pontas livres ficam a
    0,08 m uma da outra: com folga de 0,08 m no par (trecho, trecho) elas fundiriam e fechariam um ciclo.
    Com a tolerância declarada só no par de dispositivo, o detector de laços do produto devolve zero."""
    rid = _criar_rede(sessao_a, "laco", limpar_redes)
    a0 = (-47.40, -16.20)
    b0 = _projetar(env, a0[0], a0[1], DIST_ALEM_DA_REDE_M, 90)
    _linha(sessao_a, rid, [[a0[0], a0[1]], [-47.398, -16.20]])
    _linha(sessao_a, rid, [[-47.398, -16.20], [-47.398, -16.198]])
    _linha(sessao_a, rid, [[-47.398, -16.198], [b0[0], b0[1]]])
    _ponto(sessao_a, rid, a0[0], a0[1])   # transformador exatamente na ponta livre

    resumo = _habilitar(sessao_a, rid)
    assert resumo["arestas"] == 3
    r = sessao_a.post(f"/api/rede/{rid}/tracar", json={"tipo": "lacos"}, timeout=300)
    assert r.status_code == 200, r.text
    assert r.json()["contagem"] == 0, r.json()


# --- diagnóstico por classe ------------------------------------------------------------------------------

def test_classes_de_orfao_com_exemplo_e_distancia(sessao_a, limpar_redes, env):
    """Cada classe do diagnóstico aparece com contagem, distância medida e exemplo, numa rede montada para
    ter uma de cada: derivação no meio do trecho, ponto longe de tudo, e o segundo terminal do dispositivo
    sem a camada do outro tier."""
    rid = _criar_rede(sessao_a, "classes", limpar_redes)
    # trecho longo o bastante para que o meio dele fique longe das duas pontas
    _linha(sessao_a, rid, [[-47.30, -16.30], [-47.29, -16.30]])
    meio_lon, meio_lat = -47.295, -16.30
    derivado_lon, derivado_lat = _projetar(env, meio_lon, meio_lat, 0.03, 0)
    _ponto(sessao_a, rid, derivado_lon, derivado_lat)          # encosta no MEIO do trecho
    _ponto(sessao_a, rid, -47.20, -16.30)                      # longe de tudo
    _ponto(sessao_a, rid, -47.30, -16.30)                      # na ponta: liga um terminal, sobra o outro

    _habilitar(sessao_a, rid)
    classes, corpo = _classes(sessao_a, rid)
    assert classes["derivacao_sem_no"]["contagem"] == 2, corpo   # os dois terminais do que encosta no meio
    assert classes["derivacao_sem_no"]["distancia_max_m"] <= 0.1, corpo
    assert classes["derivacao_sem_no"]["exemplos"][0]["feicao_id"], corpo
    assert classes["sem_vizinho_no_limiar"]["contagem"] == 2, corpo
    assert classes["terminal_sem_par_no_dispositivo"]["contagem"] == 1, corpo
    assert corpo["nos_orfaos"] == corpo["nos_orfaos_no_resumo"], corpo


def test_diagnostico_recusa_topologia_inexistente_e_limiar_absurdo(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "recusa", limpar_redes)
    r = sessao_a.get(f"/api/rede/{rid}/topologia/diagnostico")
    assert r.status_code == 409 and r.json()["erro"] == "topologia_inexistente", r.text
    _linha(sessao_a, rid, [[-47.10, -16.40], [-47.09, -16.40]])
    _habilitar(sessao_a, rid)
    r = sessao_a.get(f"/api/rede/{rid}/topologia/diagnostico?limiar_m=999")
    assert r.status_code == 400 and r.json()["erro"] == "limiar_invalido", r.text
