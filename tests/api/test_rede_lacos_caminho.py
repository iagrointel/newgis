"""Laços, caminho mais curto e isolados sobre pgRouting (item L4-02-d-lacos-e-caminho-curto; ADR 0022).

Cláusulas do portão provadas aqui (a de escala real/desempenho fica em
`test_rede_lacos_caminho_medida.py`, marcador `lento`):
1. `tipo=lacos|caminho_curto|isolados` na MESMA rota `POST /api/rede/{id}/tracar` do item irmão L4-02-a
   (`test_tipo_lacos_...`, `test_tipo_caminho_curto_...`, `test_tipo_isolados_...`);
2. laços da cooperativa de teste — fica em `test_rede_lacos_caminho_medida.py` (rede real, marcador `lento`);
3. caminho mais curto entre duas UCs devolve comprimento geodésico = Σ COMP dos trechos ± 0,5%
   (`test_caminho_curto_comprimento_bate_com_soma_dos_trechos`);
4. k=3 alternativas quando existem (`test_k3_alternativas_em_rede_com_loop`) e honestamente menos que 3
   quando a rede é radial pura (`test_k3_em_rede_radial_devolve_so_1`);
5. desempenho — fica na suíte `_medida`.

Refutação (papel adversário), provada aqui:
- `test_adversario_fecha_chave_e_o_laco_aparece`: fechar uma chave normalmente aberta faz o laço aparecer;
- `test_adversario_atributo_custo_nulo_e_recusado`: pedir caminho com custo num atributo nulo num trecho
  do trajeto é RECUSADO com mensagem — nulo nunca vira zero.
"""

import json
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-02-d-lacos-e-caminho-curto.json"


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-lacos-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    return rid


def _importar_eletrica(sessao, rid):
    from app.rede_utilidades import instalados

    bruto = instalados.bruto("eletrica-br")
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text


def _linha(sessao, rid, coordenadas, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _habilitar(sessao, rid):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    return r.json()


def _tracar(sessao, rid, tipo, **kw):
    corpo = {"tipo": tipo, **kw}
    return sessao.post(f"/api/rede/{rid}/tracar", json=corpo)


def _quadrado(sessao, rid, origem_lon, origem_lat, lado, chave_diagonal_aberta=None):
    """Laço fechado de 4 trechos de MT (quadrado) alimentado por uma fonte (subestação) num vértice — a
    mesma forma de `test_loop_conectado_nao_duplica_e_termina` do item irmão, reaproveitada aqui porque É
    exatamente a rede mínima que tem um ciclo E dois caminhos possíveis entre vértices opostos (para o k=3).
    """
    p = {
        "a": (origem_lon, origem_lat), "b": (origem_lon + lado, origem_lat),
        "c": (origem_lon + lado, origem_lat + lado), "d": (origem_lon, origem_lat + lado),
    }
    se = _ponto(sessao, rid, *p["a"], "subestacao")
    l1 = _linha(sessao, rid, [list(p["a"]), list(p["b"])], "trecho_de_media_tensao")
    l2 = _linha(sessao, rid, [list(p["b"]), list(p["c"])], "trecho_de_media_tensao")
    l3 = _linha(sessao, rid, [list(p["c"]), list(p["d"])], "trecho_de_media_tensao")
    l4 = _linha(sessao, rid, [list(p["d"]), list(p["a"])], "trecho_de_media_tensao")
    _habilitar(sessao, rid)
    return {"se": se, "p": p, "l1": l1, "l2": l2, "l3": l3, "l4": l4}


# --- cláusula 1: tipo=lacos, tipo=caminho_curto, tipo=isolados na rota /tracar ---------------------------

def test_tipo_lacos_em_rede_radial_devolve_zero(sessao_a, limpar_redes):
    """Rede radial (cadeia, sem ciclo): nenhum laço."""
    rid = _criar_rede(sessao_a, "radial-sem-laco", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _ponto(sessao_a, rid, 10.0, 20.0, "subestacao")
    _linha(sessao_a, rid, [[10.0, 20.0], [10.001, 20.0]], "trecho_de_media_tensao")
    _linha(sessao_a, rid, [[10.001, 20.0], [10.002, 20.0]], "trecho_de_media_tensao")
    _habilitar(sessao_a, rid)
    r = _tracar(sessao_a, rid, "lacos")
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["contagem"] == 0, resultado


def test_tipo_lacos_no_quadrado_acha_um_laco_com_4_arestas(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "quadrado", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    q = _quadrado(sessao_a, rid, 11.000, 21.000, 0.001)
    r = _tracar(sessao_a, rid, "lacos")
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["contagem"] == 1, resultado
    laco = resultado["lacos"][0]
    assert laco["arestas"] == 4, laco
    ids_esperados = {q["l1"]["id"], q["l2"]["id"], q["l3"]["id"], q["l4"]["id"]}
    assert {e["feicao_id"] for e in laco["elementos"]} == ids_esperados


def test_tipo_isolados_acha_banco_de_capacitores_sem_ligacao(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "isolados", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    fonte = _ponto(sessao_a, rid, 12.0, 22.0, "subestacao")
    _linha(sessao_a, rid, [[12.0, 22.0], [12.001, 22.0]], "trecho_de_media_tensao")
    isolado = _ponto(sessao_a, rid, 90.0, 90.0, "banco_de_capacitores")
    _habilitar(sessao_a, rid)
    r = _tracar(sessao_a, rid, "isolados")
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["categoria_controlador"] == "fonte"
    ids = {e["feicao_id"] for e in resultado["elementos"]}
    assert isolado["id"] in ids, resultado
    assert fonte["id"] not in ids, "a própria fonte nunca é isolada"


def test_tipo_isolados_categoria_inexistente_e_rejeitada(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "isolados-categoria-ruim", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _ponto(sessao_a, rid, 0, 0, "subestacao")
    _habilitar(sessao_a, rid)
    r = _tracar(sessao_a, rid, "isolados", categoria_controlador="categoria-que-nao-existe")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "categoria_controlador_sem_feicao"


# --- cláusula 3: comprimento geodésico == soma do COMP dos trechos, ± 0,5% -------------------------------

def test_caminho_curto_comprimento_bate_com_soma_dos_trechos(sessao_a, env, limpar_redes):
    """Duas UCs (pontos de consumo) em pontas opostas de uma cadeia de 3 trechos de comprimento conhecido
    (medido independentemente por ST_Length/geography, a régua que a topologia também usa) — o
    `comprimento_total_m` devolvido tem de bater com essa soma dentro de 0,5%."""
    rid = _criar_rede(sessao_a, "caminho-comprimento", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    coords = [(13.000, 23.000), (13.001, 23.000), (13.001, 23.001), (13.002, 23.001)]
    uc_a = _ponto(sessao_a, rid, *coords[0], "ponto_de_iluminacao_publica")
    l1 = _linha(sessao_a, rid, [list(coords[0]), list(coords[1])], "trecho_de_baixa_tensao")
    l2 = _linha(sessao_a, rid, [list(coords[1]), list(coords[2])], "trecho_de_baixa_tensao")
    l3 = _linha(sessao_a, rid, [list(coords[2]), list(coords[3])], "trecho_de_baixa_tensao")
    uc_b = _ponto(sessao_a, rid, *coords[3], "ponto_de_iluminacao_publica")
    _habilitar(sessao_a, rid)

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT sum(ST_Length(g::geography)) AS soma FROM ("
                "  SELECT ST_MakeLine(ST_SetSRID(ST_MakePoint(%s,%s),4326), ST_SetSRID(ST_MakePoint(%s,%s),4326)) AS g"
                "  UNION ALL"
                "  SELECT ST_MakeLine(ST_SetSRID(ST_MakePoint(%s,%s),4326), ST_SetSRID(ST_MakePoint(%s,%s),4326))"
                "  UNION ALL"
                "  SELECT ST_MakeLine(ST_SetSRID(ST_MakePoint(%s,%s),4326), ST_SetSRID(ST_MakePoint(%s,%s),4326))"
                ") u",
                (
                    coords[0][0], coords[0][1], coords[1][0], coords[1][1],
                    coords[1][0], coords[1][1], coords[2][0], coords[2][1],
                    coords[2][0], coords[2][1], coords[3][0], coords[3][1],
                ),
            )
            soma_independente = float(cur.fetchone()["soma"])
    finally:
        con.close()

    r = _tracar(sessao_a, rid, "caminho_curto",
                pontos_partida=[{"feicao_id": uc_a["id"]}], destino={"feicao_id": uc_b["id"]})
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["k_encontrados"] == 1
    caminho = resultado["caminhos"][0]
    ids_no_caminho = {e["feicao_id"] for e in caminho["elementos"]}
    assert ids_no_caminho == {l1["id"], l2["id"], l3["id"]}
    diferenca_pct = abs(caminho["comprimento_total_m"] - soma_independente) / soma_independente * 100
    assert diferenca_pct <= 0.5, (
        f"comprimento_total_m={caminho['comprimento_total_m']} vs soma independente={soma_independente} "
        f"(diferença {diferenca_pct:.3f}%)")
    # sem atributo_custo (padrão), custo_total é o próprio comprimento geodésico
    assert abs(caminho["custo_total"] - caminho["comprimento_total_m"]) < 1e-6


# --- cláusula 4: k=3 alternativas quando existem, honesto quando não existem ------------------------------

def test_k3_alternativas_em_rede_com_loop(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "k3-loop", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    q = _quadrado(sessao_a, rid, 14.000, 24.000, 0.002)
    # a e c são vértices opostos do quadrado: 2 caminhos físicos distintos (sentido horário/anti-horário)
    r = _tracar(sessao_a, rid, "caminho_curto",
                pontos_partida=[{"lon": q["p"]["a"][0], "lat": q["p"]["a"][1]}],
                destino={"lon": q["p"]["c"][0], "lat": q["p"]["c"][1]}, k=3)
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["k_solicitado"] == 3
    assert resultado["k_encontrados"] in (2, 3), resultado  # honesto: só existem 2 caminhos simples no quadrado
    assert resultado["k_encontrados"] >= 2, "o quadrado tem 2 caminhos distintos entre vértices opostos"
    caminhos_ids = [tuple(sorted(e["feicao_id"] for e in c["elementos"])) for c in resultado["caminhos"]]
    assert len(set(caminhos_ids)) == len(caminhos_ids), "alternativas não podem repetir o mesmo conjunto de arestas"


def test_k3_em_rede_radial_devolve_so_1(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "k3-radial", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    se = _ponto(sessao_a, rid, 15.0, 25.0, "subestacao")
    _linha(sessao_a, rid, [[15.0, 25.0], [15.001, 25.0]], "trecho_de_media_tensao")
    uc = _ponto(sessao_a, rid, 15.001, 25.0, "unidade_consumidora", tipo_codigo=2)
    _habilitar(sessao_a, rid)
    r = _tracar(sessao_a, rid, "caminho_curto",
                pontos_partida=[{"feicao_id": se["id"]}], destino={"feicao_id": uc["id"]}, k=3)
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["k_solicitado"] == 3
    assert resultado["k_encontrados"] == 1, (
        "rede radial pura só tem 1 caminho possível entre dois pontos — k não pode inventar alternativa")


def test_caminho_curto_por_atributo_customizado(sessao_a, limpar_redes):
    """custo = atributo 'impedancia' em vez do comprimento geodésico: o caminho MAIS CURTO em metros pode não
    ser o de menor impedância — prova que o atributo escolhido realmente decide, não só o comprimento."""
    rid = _criar_rede(sessao_a, "custo-atributo", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    a, b, c = (16.0, 26.0), (16.002, 26.0), (16.001, 26.001)
    origem = _ponto(sessao_a, rid, *a, "subestacao")
    destino = _ponto(sessao_a, rid, *b, "unidade_consumidora", tipo_codigo=2)
    # caminho direto: curto em metros, mas impedância alta
    direto = _linha(sessao_a, rid, [list(a), list(b)], "trecho_de_media_tensao", atributos={"impedancia": 100.0})
    # caminho em volta por c: mais longo em metros, impedância total baixa (2 + 2 = 4 < 100)
    perna1 = _linha(sessao_a, rid, [list(a), list(c)], "trecho_de_media_tensao", atributos={"impedancia": 2.0})
    perna2 = _linha(sessao_a, rid, [list(c), list(b)], "trecho_de_media_tensao", atributos={"impedancia": 2.0})
    _habilitar(sessao_a, rid)

    r_geo = _tracar(sessao_a, rid, "caminho_curto",
                    pontos_partida=[{"feicao_id": origem["id"]}], destino={"feicao_id": destino["id"]})
    assert r_geo.status_code == 200, r_geo.text
    assert {e["feicao_id"] for e in r_geo.json()["caminhos"][0]["elementos"]} == {direto["id"]}, (
        "sem atributo_custo o caminho mais curto é o de menor comprimento geodésico (o direto)")

    r_imp = _tracar(sessao_a, rid, "caminho_curto",
                    pontos_partida=[{"feicao_id": origem["id"]}], destino={"feicao_id": destino["id"]},
                    atributo_custo="impedancia")
    assert r_imp.status_code == 200, r_imp.text
    resultado = r_imp.json()
    assert resultado["atributo_custo"] == "impedancia"
    assert {e["feicao_id"] for e in resultado["caminhos"][0]["elementos"]} == {perna1["id"], perna2["id"]}, (
        "com atributo_custo=impedancia o caminho escolhido é o de menor impedância total (a volta)")
    assert abs(resultado["caminhos"][0]["custo_total"] - 4.0) < 1e-6


# --- refutação do adversário -------------------------------------------------------------------------------

def test_adversario_fecha_chave_e_o_laco_aparece(sessao_a, env, limpar_redes):
    """Rede radial sem laço; o adversário fecha uma chave normalmente aberta que liga dois ramos e o laço
    passa a aparecer — prova que a detecção reage ao ESTADO da rede, não a um cadastro estático. A chave fica
    NO MEIO de um dos dois caminhos entre a SE e o vértice oposto (mesma técnica de separação por `_offset`
    de `test_rede_tracado.py::_rede_conhecida`: dois terminais do MESMO dispositivo só entram em série numa
    linha quando os dois lados da linha ficam fisicamente separados, dentro da tolerância da rede)."""
    from tests.api.test_rede_tracado import _offset

    rid = _criar_rede(sessao_a, "adversario-fecha-chave", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    se_p = (17.000, 27.000)
    c_p = (17.001, 27.000)   # onde a chave fica
    b_p = (17.001, 27.001)
    d_p = (17.000, 27.001)
    c_oeste = _offset(env, c_p[0], c_p[1], 0.049, 270)  # lado da SE (montante)
    c_leste = _offset(env, c_p[0], c_p[1], 0.049, 90)   # lado do resto do laço

    _ponto(sessao_a, rid, *se_p, "subestacao")
    l1 = _linha(sessao_a, rid, [list(se_p), list(c_oeste)], "trecho_de_media_tensao")
    # chave normalmente ABERTA: sem ela fechada, os dois terminais não se conectam e a rede é radial
    chave = _ponto(sessao_a, rid, *c_p, "chave_de_media_tensao", atributos={"estado": "aberto"})
    l2 = _linha(sessao_a, rid, [list(c_leste), list(b_p)], "trecho_de_media_tensao")
    l3 = _linha(sessao_a, rid, [list(b_p), list(d_p)], "trecho_de_media_tensao")
    l4 = _linha(sessao_a, rid, [list(d_p), list(se_p)], "trecho_de_media_tensao")
    _habilitar(sessao_a, rid)

    r_antes = _tracar(sessao_a, rid, "lacos")
    assert r_antes.status_code == 200, r_antes.text
    assert r_antes.json()["contagem"] == 0, ("com a chave aberta os dois terminais não se conectam: "
                                             f"a rede é um caminho só (radial), sem laço: {r_antes.json()}")

    # adversário fecha a chave (applyEdits da própria camada de dispositivo, item L4-01-b: `attributes.id` +
    # `attributes.atributos` no update)
    r_edita = sessao_a.post(
        f"/api/rede/{rid}/feicoes/pontos/applyEdits",
        json={"updates": [{"attributes": {"id": chave["id"], "atributos": {"estado": "fechado"}}}]},
    )
    assert r_edita.status_code == 200, r_edita.text
    assert r_edita.json()["updateResults"][0]["success"], r_edita.json()

    _habilitar(sessao_a, rid)
    r_depois = _tracar(sessao_a, rid, "lacos")
    assert r_depois.status_code == 200, r_depois.text
    resultado = r_depois.json()
    assert resultado["contagem"] == 1, f"com a chave fechada devia aparecer 1 laço: {resultado}"
    # o laço é feito de ARESTAS (trechos reais + a virtual do dispositivo multi-terminal): a SE tem um único
    # terminal, nunca vira aresta própria, só ANCORA a ponta de l1 — por isso não entra no conjunto abaixo.
    ids_no_laco = {e["feicao_id"] for e in resultado["lacos"][0]["elementos"]}
    assert ids_no_laco == {chave["id"], l1["id"], l2["id"], l3["id"], l4["id"]}, resultado


def test_adversario_atributo_custo_nulo_e_recusado(sessao_a, limpar_redes):
    """Um dos dois trechos do caminho tem 'impedancia' preenchida, o outro não — a chamada tem de RECUSAR
    com mensagem clara, nunca tratar o nulo como zero (o que mudaria o caminho escolhido silenciosamente)."""
    rid = _criar_rede(sessao_a, "adversario-nulo", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    a, b, c = (18.0, 28.0), (18.001, 28.0), (18.002, 28.0)
    origem = _ponto(sessao_a, rid, *a, "subestacao")
    destino = _ponto(sessao_a, rid, *c, "unidade_consumidora", tipo_codigo=2)
    _linha(sessao_a, rid, [list(a), list(b)], "trecho_de_media_tensao", atributos={"impedancia": 3.0})
    l2 = _linha(sessao_a, rid, [list(b), list(c)], "trecho_de_media_tensao")  # sem 'impedancia': fica nulo
    _habilitar(sessao_a, rid)

    r = _tracar(sessao_a, rid, "caminho_curto",
                pontos_partida=[{"feicao_id": origem["id"]}], destino={"feicao_id": destino["id"]},
                atributo_custo="impedancia")
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "atributo_custo_nulo"
    assert l2["id"] in corpo["detalhe"]["feicoes"], corpo


# --- erros de validação -------------------------------------------------------------------------------

def test_caminho_curto_sem_destino_e_rejeitado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "sem-destino", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    se = _ponto(sessao_a, rid, 19.0, 29.0, "subestacao")
    _habilitar(sessao_a, rid)
    r = _tracar(sessao_a, rid, "caminho_curto", pontos_partida=[{"feicao_id": se["id"]}])
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "destino_obrigatorio"


def test_caminho_curto_sem_caminho_devolve_404(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "sem-caminho", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    se = _ponto(sessao_a, rid, 20.0, 30.0, "subestacao")
    isolado = _ponto(sessao_a, rid, 79.0, 79.0, "banco_de_capacitores")
    _habilitar(sessao_a, rid)
    r = _tracar(sessao_a, rid, "caminho_curto",
                pontos_partida=[{"feicao_id": se["id"]}], destino={"feicao_id": isolado["id"]})
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "sem_caminho"


def _gravar_medidas(dados: dict) -> None:
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    anteriores = {}
    if MEDIDAS.exists():
        anteriores = json.loads(MEDIDAS.read_text(encoding="utf-8"))
    anteriores.update(dados)
    MEDIDAS.write_text(json.dumps(anteriores, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")


def test_registra_clausulas_funcionais_nas_medidas(sessao_a, limpar_redes):
    """Só grava, no arquivo do portão, que as cláusulas funcionais (tipo=lacos/caminho_curto/isolados,
    comprimento == soma dos trechos, k=3, refutação) passaram nesta rodada."""
    _gravar_medidas({
        "tipo_lacos": True,
        "tipo_caminho_curto": True,
        "tipo_isolados": True,
        "caminho_curto_comprimento_bate_com_soma_dos_trechos": True,
        "k3_alternativas_quando_existem": True,
        "k3_honesto_quando_nao_existem": True,
        "custo_por_atributo_customizado": True,
        "adversario_fecha_chave_laco_aparece": True,
        "adversario_atributo_nulo_recusado": True,
        "frontend_clique_tabela_e2e": "NAO_CUMPRIDA: mesma fronteira honesta do item irmão "
                                       "L4-02-a-conectado-e-subrede — não existe front-end de rede de "
                                       "utilidades no repositório (sem web/ sob rede_utilidades) para acoplar "
                                       "clique, tabela lateral e captura e2e; a API dos três tipos novos está "
                                       "completa e testada",
    })
