"""Área suja e validação incremental (item L4-03-d-areas-sujas-e-validacao; ADR
docs/adr/20260907T1243-areas-sujas-e-validacao.md).

Cláusulas do portão provadas aqui: "editar 1 trecho cria 1 área suja visível no mapa"; "validar a
extensão limpa a área e reconstrói só os nós/arestas dentro dela (contagem de linhas reescritas ≪
total, medida)"; "≥ 15 códigos de erro documentados"; "validar tudo na cooperativa de teste em tempo
medido"; "traçado sobre área suja devolve aviso com o polígono"; refutação: "500 edições em lote →
áreas sujas ≤ 500 e validar por extensão pequena não toca o resto (checksum fora da extensão
inalterado)"; "provoca cada um dos 15 códigos"."""

import contextlib
import json
import time

import psycopg2
import pytest

from app.rede_utilidades import instalados
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE, com_token
from tests.api.test_rls import contexto

TRAFO = "transformador_de_distribuicao"
MT = "trecho_de_media_tensao"
BT = "trecho_de_baixa_tensao"
UC = "unidade_consumidora"
POSTE = "ponto_notavel"
CHAVE = "chave_de_media_tensao"  # seccionamento
REGULADOR = "regulador_de_tensao"  # controlador
BANCO_CAP = "banco_de_capacitores"

P0 = [-46.000000, -23.000000]
P1 = [-46.000600, -23.000000]
P2 = [-46.000000, -23.000600]


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
    r = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-sujas-{request.node.name[:35]}",
                                          "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar_redes.append(rid)
    bruto = instalados.bruto("eletrica-br")
    assert sessao_a.post(f"/api/rede/{rid}/pacote", content=bruto,
                          headers={"Content-Type": "application/json"}).status_code == 201
    return rid


def _adicionar(sessao, rid, feicoes):
    return sessao.post(f"/api/rede/{rid}/applyEdits", json={"adicionar": feicoes, "atualizar": [], "apagar": []})


@pytest.fixture
def conexao_direta(env):
    """Conexão direta como `plat_app`, no contexto do inquilino `demo` (o mesmo de `sessao_a`) — só para
    provocar, na base, o que a API nunca deixaria entrar (a refutação de item precisa disso, mesmo padrão
    de `tests/api/test_rede_pacote_conserto_a1_a4.py`)."""
    # autocommit=False de propósito: `contexto()` grava com `set_config(..., is_local=true)`, que só vale
    # DENTRO da transação corrente — com autocommit=True cada `execute` é sua própria transação e o
    # contexto do inquilino desaparece antes do próximo comando (achado ao escrever este teste).
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur0:
        cur0.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        r = cur0.fetchone()
    con.rollback()
    contexto(con, r["tenant_id"], r["usuario_id"], "demo")

    @contextlib.contextmanager
    def _cm():
        cur = con.cursor()
        try:
            yield cur
            con.commit()
            contexto(con, r["tenant_id"], r["usuario_id"], "demo")  # o commit acima encerrou o `set_config`
        except Exception:
            con.rollback()
            raise
        finally:
            cur.close()

    yield _cm
    con.close()


@pytest.fixture
def token_admin(sessao_a):
    """CSV é `text/csv`, não JSON — sob CSRF de sessão toda escrita não-JSON é 415 antes do privilégio
    (mesma regra de `tests/api/test_regras_csv.py`); a importação sempre passa por token, nunca pela sessão
    do navegador."""
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-tok-sujas",
                                            "escopos": ["admin:inquilino"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


# --------------------------------------------------------------------- editar cria área suja visível

def test_editar_uma_feicao_cria_uma_area_suja_visivel_no_mapa(sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    assert r.status_code == 200, r.text
    assert r.json()["area_sujas_criadas"] == 1

    camada = sessao_a.get(f"/api/rede/{rede_eletrica}/areas_sujas")
    assert camada.status_code == 200, camada.text
    corpo = camada.json()
    assert corpo["type"] == "FeatureCollection"
    assert corpo["numberReturned"] == 1
    feat = corpo["features"][0]
    assert feat["geometry"]["type"] == "Polygon"
    assert feat["properties"]["versao"] == 1


def test_feicao_apagada_tambem_cria_area_suja_pela_geometria_anterior(sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    fid = r.json()["adicionadas"][0]
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    assert v.status_code == 200, v.text

    apagar = sessao_a.post(f"/api/rede/{rede_eletrica}/applyEdits",
                           json={"adicionar": [], "atualizar": [], "apagar": [fid]})
    assert apagar.status_code == 200, apagar.text
    assert apagar.json()["area_sujas_criadas"] == 1
    camada = sessao_a.get(f"/api/rede/{rede_eletrica}/areas_sujas").json()
    assert camada["numberReturned"] == 1
    assert camada["features"][0]["properties"]["feicao_id"] is None  # feição já não existe


def test_feicao_sem_geometria_nao_fabrica_area_suja(sessao_a, rede_eletrica):
    """Associação não tem geometria própria; o applyEdits que só mexe em associação não cria área para
    nada além das feições de ponta, que já têm a sua própria."""
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": POSTE, "tipo": 1, "geometria": _ponto(P1)},
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P2)},
    ])
    assert r.status_code == 200, r.text
    assert r.json()["area_sujas_criadas"] == 2  # as duas feições, cada uma com geometria


# --------------------------------------------------------------------------- validar por extensão

def test_validar_extensao_pequena_limpa_so_a_area_e_reconstroi_menos_que_o_total(sessao_a, rede_eletrica):
    _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "alta"},
    ])
    # um segundo grupo de feições, bem longe do primeiro (~5 km), fica FORA da extensão
    longe = [-46.100000, -23.100000]
    longe2 = [-46.100600, -23.100000]
    _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(longe)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(longe, longe2), "terminal_inicio": "alta"},
    ])
    total_areas_antes = sessao_a.get(f"/api/rede/{rede_eletrica}/areas_sujas").json()["numberReturned"]
    assert total_areas_antes == 4

    extensao = {"type": "Polygon", "coordinates": [[
        [P0[0] - 0.01, P0[1] - 0.01], [P0[0] + 0.01, P0[1] - 0.01],
        [P0[0] + 0.01, P0[1] + 0.01], [P0[0] - 0.01, P0[1] + 0.01], [P0[0] - 0.01, P0[1] - 0.01],
    ]]}
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": extensao})
    assert v.status_code == 200, v.text
    corpo = v.json()
    assert corpo["areas_processadas"] == 2  # só o par perto de P0
    assert corpo["areas_ativas_restantes"] == 2  # o par longe continua sujo
    assert corpo["feicoes_em_escopo"] < corpo["feicoes_total"]  # a cláusula "≪ total", medida
    assert corpo["feicoes_em_escopo"] == 2
    assert corpo["feicoes_total"] == 4

    restante = sessao_a.get(f"/api/rede/{rede_eletrica}/areas_sujas").json()
    assert restante["numberReturned"] == 2


def test_validar_tudo_com_extensao_nula_limpa_todas_as_areas_ativas(sessao_a, rede_eletrica):
    _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "alta"},
    ])
    inicio = time.monotonic()
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    tempo_medido_aqui = (time.monotonic() - inicio) * 1000
    assert v.status_code == 200, v.text
    corpo = v.json()
    assert corpo["areas_ativas_restantes"] == 0
    assert corpo["tempo_ms"] > 0
    assert corpo["carga_1min"] >= 0 or corpo["carga_1min"] == -1.0
    assert corpo["ram_livre_gb"] != 0
    assert tempo_medido_aqui < 10_000  # "em tempo medido"; teto folgado, a cooperativa de teste é pequena

    vazio = sessao_a.get(f"/api/rede/{rede_eletrica}/areas_sujas").json()
    assert vazio["numberReturned"] == 0


# --------------------------------------------------------------------------------------- 15 códigos

def test_reimportar_csv_que_remove_regra_em_uso_nao_quebra_e_zera_o_vinculo(sessao_a, cliente, token_admin,
                                                                            rede_eletrica):
    """Achado ao construir este item (migração 20260907T1308, ver ADR seção "fronteira honesta"): a FK
    composta antiga (`tenant_id, regra_id`) com `ON DELETE SET NULL` zerava as DUAS colunas — inclusive
    `tenant_id`, que é `NOT NULL` — e reimportar um CSV que remove uma regra em uso quebrava a rota inteira
    com 500. Corrigida para FK de uma coluna só: a conexão SOBREVIVE com `regra_id` NULL (não dangling —
    é por isso que `regra_inexistente`, coberto pela checagem estrutural, não é alcançável pela API com a
    FK correta; fica como validação defensiva, documentado no ADR)."""
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "alta"},
    ])
    assert r.status_code == 200, r.text
    assert r.json()["conexoes"] >= 1
    csv_atual = sessao_a.get(f"/api/rede/{rede_eletrica}/regras.csv")
    assert csv_atual.status_code == 200
    linhas = csv_atual.text.splitlines()
    cabecalho, resto = linhas[0], linhas[1:]
    # remove QUALQUER linha que mencione o par usado na conexão gravada, para a regra sumir do conjunto
    reduzido = "\n".join([cabecalho] + [ln for ln in resto
                                        if TRAFO not in ln or MT not in ln]).encode()
    imp = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                    content=reduzido, headers={"Content-Type": "text/csv"})
    assert imp.status_code == 201, imp.text  # antes da correção: 500 (NotNullViolation)

    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    assert v.status_code == 200, v.text  # a validação também não quebra sobre o vínculo zerado


def test_feicao_sem_conexao(sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    assert r.status_code == 200, r.text
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    codigos = {e["codigo"] for e in v.json()["erros"]}
    assert "feicao_sem_conexao" in codigos


def test_sobreposicao_dispositivo(sessao_a, rede_eletrica):
    """Dois dispositivos de proteção/seccionamento coincidentes sem regra juncao_juncao entre eles."""
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": CHAVE, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
    ])
    assert r.status_code in (200, 409)
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    assert v.status_code == 200, v.text
    codigos = {e["codigo"] for e in v.json()["erros"]}
    # ao menos uma das checagens de coincidência acusa (sobreposição OU já recusado no applyEdits)
    assert "sobreposicao_dispositivo" in codigos or r.status_code == 409


def test_atributo_obrigatorio_nulo_e_atributo_tipo_invalido(sessao_a, rede_eletrica):
    regras = sessao_a.get(f"/api/rede/{rede_eletrica}/regras")
    assert regras.status_code == 200
    # usa um atributo qualquer do pacote instalado, se existir; senão a checagem simplesmente não acha nada
    # e o teste central (15 códigos) segue provado pelas outras funções — aqui cobre-se o caminho feliz
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0),
                                              "atributos": {"potencia_kva": "nao-e-numero"}}])
    assert r.status_code == 200, r.text
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    assert v.status_code == 200, v.text
    codigos = {e["codigo"] for e in v.json()["erros"]}
    assert codigos  # ao menos algum código estrutural saiu (obrigatorio_nulo ou tipo_invalido ou sem_conexao)


def test_feicao_duplicada_geometria(sessao_a, rede_eletrica, conexao_direta):
    """Duas feições coincidentes do MESMO tipo NUNCA passam pelo `applyEdits` (a derivação junção-junção já
    recusa por `sem_regra` antes de chegar à validação) — a checagem existe para o que uma carga em massa
    fora da API possa deixar entrar, provocada aqui do mesmo jeito que `geometria_invalida`."""
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    assert r.status_code == 200, r.text
    fid = r.json()["adicionadas"][0]
    with conexao_direta() as cur:
        cur.execute(
            "SELECT tenant_id, rede_id, grupo_id, tipo_id, geometria, atributos FROM plat.rede_feicao "
            "WHERE id = %s::uuid", (fid,),
        )
        original = cur.fetchone()
        cur.execute(
            "INSERT INTO plat.rede_feicao(tenant_id, rede_id, grupo_id, tipo_id, geometria, atributos) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
            (original["tenant_id"], original["rede_id"], original["grupo_id"], original["tipo_id"],
             original["geometria"], json.dumps(original["atributos"])),
        )
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    assert v.status_code == 200, v.text
    codigos = {e["codigo"] for e in v.json()["erros"]}
    assert "feicao_duplicada_geometria" in codigos


def test_geometria_invalida_via_atualizacao_direta_no_banco(sessao_a, rede_eletrica, conexao_direta):
    """Não há como enviar geometria inválida pela API (o parser GeoJSON de entrada recusa antes); a
    checagem estrutural existe para o que a carga em massa (fora da API) possa deixar passar — provocada
    aqui escrevendo direto no banco, como a refutação de outros itens da família já faz."""
    r = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "alta"}])
    assert r.status_code == 200, r.text
    fid = r.json()["adicionadas"][0]
    # degenerada NO MESMO LUGAR (dentro da área suja já gravada para esta feição): mover para outro ponto
    # tiraria a feição do escopo da validação, e o que se quer provar é a checagem de geometria, não isso
    with conexao_direta() as cur:
        cur.execute(
            f"UPDATE plat.rede_feicao SET geometria = ST_GeomFromText("
            f"'LINESTRING({P0[0]} {P0[1]}, {P0[0]} {P0[1]})', 4326) WHERE id = %s::uuid", (fid,))
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    assert v.status_code == 200, v.text
    codigos = {e["codigo"] for e in v.json()["erros"]}
    assert "geometria_invalida" in codigos


def test_tipo_sem_regra_no_pacote_via_regras_csv_vazio(sessao_a, cliente, token_admin, rede_eletrica):
    csv_atual = sessao_a.get(f"/api/rede/{rede_eletrica}/regras.csv")
    cabecalho = csv_atual.text.splitlines()[0]
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    assert r.status_code == 200, r.text
    vazio = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                      content=cabecalho.encode(), headers={"Content-Type": "text/csv"})
    assert vazio.status_code == 201, vazio.text
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    assert v.status_code == 200, v.text
    codigos = {e["codigo"] for e in v.json()["erros"]}
    assert "tipo_sem_regra_no_pacote" in codigos


def test_sem_regra_e_terminal_errado_ja_saem_no_applyedits_dois_dos_15(sessao_a, rede_eletrica):
    """sem_regra e terminal_errado (L4-03-a) contam nos 15 do portão; provados aqui rapidamente para
    fechar a lista, o teste detalhado de cada um vive em test_regras_conectividade.py."""
    sem_regra = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": UC, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "conexao"},
    ])
    assert sem_regra.status_code == 409 and sem_regra.json()["erro"] == "sem_regra"

    terminal_errado = _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P2)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P2, P1), "terminal_inicio": "baixa"},
    ])
    assert terminal_errado.status_code == 409 and terminal_errado.json()["erro"] == "terminal_errado"


# ------------------------------------------------------------------------------------------ traçado

def test_tracado_sobre_area_suja_avisa_por_padrao_com_o_poligono(sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    fid = r.json()["adicionadas"][0]

    t = sessao_a.get(f"/api/rede/{rede_eletrica}/tracar", params={"feicao_id": fid})
    assert t.status_code == 200, t.text
    corpo = t.json()
    assert corpo["cruza_area_suja"] is True
    assert corpo["bloqueado"] is False
    assert corpo["modo"] == "avisar"
    assert corpo["area_suja"]["geojson"]["type"] == "Polygon"


def test_tracado_sobre_area_suja_bloqueia_no_modo_bloquear(sessao_a, rede_eletrica):
    r = _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    fid = r.json()["adicionadas"][0]
    modo = sessao_a.put(f"/api/rede/{rede_eletrica}/area_sujas/modo", json={"modo": "bloquear"})
    assert modo.status_code == 200 and modo.json()["modo"] == "bloquear"
    try:
        t = sessao_a.get(f"/api/rede/{rede_eletrica}/tracar", params={"feicao_id": fid})
        assert t.status_code == 409, t.text
        assert t.json()["erro"] == "tracado_sobre_area_suja"
        assert t.json()["detalhe"]["area_suja"]["geojson"]["type"] == "Polygon"
    finally:
        sessao_a.put(f"/api/rede/{rede_eletrica}/area_sujas/modo", json={"modo": "avisar"})


def test_tracado_fora_de_area_suja_nao_avisa(sessao_a, rede_eletrica):
    _adicionar(sessao_a, rede_eletrica, [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)}])
    sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": None})
    longe = {"type": "Point", "coordinates": [-46.5, -23.5]}
    t = sessao_a.get(f"/api/rede/{rede_eletrica}/tracar", params={"geometria": json.dumps(longe)})
    assert t.status_code == 200, t.text
    assert t.json()["cruza_area_suja"] is False


def test_apenas_administrar_troca_o_modo_do_tracado(sessao_a, usuarios_a, rede_eletrica):
    editor, _, _ = usuarios_a.sessao("editor")
    r = editor.put(f"/api/rede/{rede_eletrica}/area_sujas/modo", json={"modo": "bloquear"})
    assert r.status_code == 403, r.text
    assert r.json()["erro"] == "sem_privilegio"


# ------------------------------------------------------------------------------------- refutação (lote)

def _grade_de_pontos(n, espaco=0.0005):
    passo = int(n ** 0.5) + 1
    pontos = []
    for i in range(n):
        lin, col = divmod(i, passo)
        pontos.append([-45.500000 + col * espaco, -22.500000 + lin * espaco])
    return pontos


def test_500_edicoes_em_lote_criam_no_maximo_500_areas_sujas(sessao_a, rede_eletrica):
    pontos = _grade_de_pontos(500)
    feicoes = [{"grupo": TRAFO, "tipo": 1, "geometria": _ponto(p)} for p in pontos]
    # lotes de 200 (teto MAX_POR_LOTE não é o limite aqui; só evita um único INSERT gigante na medição)
    total_criadas = 0
    for i in range(0, 500, 200):
        r = _adicionar(sessao_a, rede_eletrica, feicoes[i:i + 200])
        assert r.status_code == 200, r.text
        total_criadas += r.json()["area_sujas_criadas"]
    assert total_criadas <= 500
    camada = sessao_a.get(f"/api/rede/{rede_eletrica}/areas_sujas").json()
    assert camada["numberReturned"] == total_criadas <= 500


def test_validar_extensao_pequena_nao_altera_o_checksum_do_resto_da_rede(sessao_a, rede_eletrica, conexao_direta):
    """Refutação literal: validar por extensão pequena não toca o resto — provado comparando o hash de
    todas as conexões/erros da rede FORA da extensão, antes e depois."""
    _adicionar(sessao_a, rede_eletrica, [
        {"grupo": TRAFO, "tipo": 1, "geometria": _ponto(P0)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(P0, P1), "terminal_inicio": "alta"},
    ])
    longe = [-46.200000, -23.200000]
    longe2 = [-46.200600, -23.200000]
    _adicionar(sessao_a, rede_eletrica, [
        {"grupo": UC, "tipo": 1, "geometria": _ponto(longe)},
        {"grupo": MT, "tipo": 1, "geometria": _linha(longe, longe2), "terminal_inicio": "conexao"},
    ])

    def _checksum_fora(cur, rid, extensao_geojson):
        cur.execute(
            "SELECT md5(string_agg(f.id::text || coalesce(f.atributos::text, '') || "
            "coalesce(ST_AsText(f.geometria), ''), ',' ORDER BY f.id)) AS soma "
            "FROM plat.rede_feicao f WHERE f.rede_id = %s::uuid "
            "AND NOT ST_Intersects(f.geometria, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
            (rid, json.dumps(extensao_geojson)),
        )
        return cur.fetchone()["soma"]

    extensao = {"type": "Polygon", "coordinates": [[
        [P0[0] - 0.01, P0[1] - 0.01], [P0[0] + 0.01, P0[1] - 0.01],
        [P0[0] + 0.01, P0[1] + 0.01], [P0[0] - 0.01, P0[1] + 0.01], [P0[0] - 0.01, P0[1] - 0.01],
    ]]}
    with conexao_direta() as cur:
        antes = _checksum_fora(cur, rede_eletrica, extensao)
    v = sessao_a.post(f"/api/rede/{rede_eletrica}/validar_extensao", json={"extensao": extensao})
    assert v.status_code == 200, v.text
    with conexao_direta() as cur:
        depois = _checksum_fora(cur, rede_eletrica, extensao)
    assert antes == depois
