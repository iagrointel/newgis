"""Portão do item L6-02-c-wfs-ogcapi, cláusula por cláusula.

Portão literal: "1 WFS e 1 OGC API Features públicos adicionados; camada copiada com 50 mil feições em tempo
medido; paginação conferida (contagem = numberMatched); tipos de atributo preservados; teste."

Refutação exigida: "adversário aponta WFS com 5 mi de feições e sem paginação: o modo copiado para no limite
declarado e avisa, sem travar o worker."

Os dois serviços são servidos por `tests/api/conexao/servidor_ogc.py`, no loopback: a suíte não pode depender
de um WFS de terceiro estar de pé para dar verde. Os serviços PÚBLICOS de verdade entram como medida
registrada (`test_medida_servicos_publicos_reais`), que anota o resultado e nunca reprova por indisponibilidade
alheia — um teste que falha por causa do servidor do órgão deixa de ser prova do nosso código.
"""

from __future__ import annotations

import json
import os
import socket
import time

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conexao.servidor_ogc import COLECAO, ServidorOGC
from tests.api.conftest import PREFIXO_TESTE
from tests.api.jobs.conftest import WorkerExtra, criar_job, esperar
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L6-02-c-wfs-ogcapi"
TOTAL_GRANDE = 50_000


# --------------------------------------------------------------------------- infraestrutura do teste


def _porta_livre() -> int:
    """Porta efêmera do sistema. Nada de número fixo: 18159 e 18162 já estavam ocupadas por workers de OUTRAS
    trilhas rodando ao mesmo tempo nesta máquina, e o `/saude` do worker alheio respondia — o `WorkerExtra`
    dava o worker por iniciado e o job ficava pendente para sempre (achado real, 06/09)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def portas_ogc():
    """Lote de portas reservado UMA vez para o módulo e declarado de uma vez na válvula
    `PLAT_TESTE_CONEXAO_ALVOS` (`app/conexao/seguranca.py::alvos_de_teste`).

    Por que um lote, e não uma porta nova por teste: o worker da fila herda o ambiente no instante em que
    sobe, e a cópia é um job. Com uma porta por teste, cada teste precisaria de um worker próprio — e subir e
    parar worker entre testes devolveu job no meio (`worker reiniciado`) e deixou a cópia pendente sem
    ninguém para pegá-la (medido 06/09). Com o lote, o worker do módulo já nasce sabendo de todas."""
    portas = [_porta_livre() for _ in range(12)]
    anterior = os.environ.get("PLAT_TESTE_CONEXAO_ALVOS")
    os.environ["PLAT_TESTE_CONEXAO_ALVOS"] = ",".join(f"127.0.0.1:{p}" for p in portas)
    yield list(portas)
    if anterior is None:
        os.environ.pop("PLAT_TESTE_CONEXAO_ALVOS", None)
    else:
        os.environ["PLAT_TESTE_CONEXAO_ALVOS"] = anterior


@pytest.fixture(scope="module")
def worker_ogc(env, portas_ogc):
    """UM worker para o módulo inteiro, iniciado DEPOIS de `portas_ogc` (a ordem importa: ele herda a válvula
    do ambiente). Dois processos, não um: com um só, o periódico `conexoes.saude_verificar` (item L6-02-l)
    ocupa o único lugar e o job pesado da cópia espera até o teste estourar o tempo (medido 06/09)."""
    nome = f"l602c-{os.getpid()}"
    w = WorkerExtra(env, nome, 2, _porta_livre())
    assert w.saude()["nome_base"] == nome, (
        f"a porta respondeu, mas quem respondeu foi o worker {w.saude()['nome_base']!r} de outra trilha"
    )
    yield w
    w.parar()


@pytest.fixture
def servidor(portas_ogc):
    """Fábrica de servidores OGC locais, cada um numa porta do lote; todos parados no fim do teste."""
    vivos: list[ServidorOGC] = []
    disponiveis = list(portas_ogc)

    def _novo(**kw) -> ServidorOGC:
        s = ServidorOGC(porta=disponiveis.pop(0), **kw)
        vivos.append(s)
        return s

    yield _novo
    for s in vivos:
        s.parar()


@pytest.fixture
def conexoes(sessao_a):
    criadas: list[str] = []

    def _criar(tipo: str, url: str, sufixo: str) -> str:
        r = sessao_a.post("/api/conexoes", json={
            "tipo": tipo, "nome": f"{PREFIXO_TESTE}-{tipo}-{sufixo}-{time.time_ns()}", "url": url,
            "modo": "copiada" if tipo == "wfs" else "referenciada",
        })
        assert r.status_code == 201, r.text
        criadas.append(r.json()["id"])
        return r.json()["id"]

    yield _criar
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


@pytest.fixture
def camadas(env):
    """Ids de item `camada_vetorial` criados pela cópia; o teardown apaga item E tabela física."""
    ids: list[str] = []
    yield ids
    if not ids:
        return
    from app.catalogo import destruidores

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        slugs = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
        contexto(con, slugs["demo"], usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
            for iid in ids:
                cur.execute("SELECT tipo, dados, miniatura_chave FROM plat.item WHERE id = %s::uuid", (iid,))
                item = cur.fetchone()
                if item is None:
                    continue
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (iid,))
                try:
                    destruidores.destruir(cur, item["tipo"], item["dados"], item["miniatura_chave"],
                                          lambda *_a: None)
                except destruidores.Recusado:
                    pass
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (iid,))
        con.commit()
    finally:
        con.close()


def _copiar(cliente_demo, conexao_id: str, camadas: list[str], *, timeout: float = 600, **params) -> dict:
    job = criar_job(cliente_demo, "conexao.copiar_vetor",
                    {"conexao_id": conexao_id, "colecao": COLECAO, **params})
    final = esperar(cliente_demo, job["id"], timeout=timeout)
    if final["estado"] == "concluido" and (final.get("resultado") or {}).get("item_id"):
        camadas.append(final["resultado"]["item_id"])
    return final


def _colunas(env, schema: str, tabela: str) -> dict[str, str]:
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s", (schema, tabela),
            )
            return {r["column_name"]: r["data_type"] for r in cur.fetchall()}
    finally:
        con.close()


def _dados_do_item_gravado(env, item_id: str) -> dict:
    """`plat.item.dados` da camada, sob o contexto do inquilino (RLS)."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        slugs = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
        contexto(con, slugs["demo"], usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (item_id,))
            linha = cur.fetchone()
            assert linha is not None, f"item {item_id} não existe"
            return linha["dados"]
    finally:
        con.close()


def _contar(env, schema: str, tabela: str) -> tuple[int, list[float]]:
    """Conta as linhas da camada COMO A APLICAÇÃO as vê. O contexto de inquilino é obrigatório: a tabela tem
    RLS FORCE (`plat.camada_preparar`), e sem `plat.tenant_id` no `set_config` a mesma consulta devolve zero —
    o que pareceria "a cópia não gravou nada" quando na verdade gravou e a política escondeu."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        slugs = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
        contexto(con, slugs["demo"], usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute(f'SELECT count(*) AS n, ST_AsGeoJSON(ST_Extent(geom)::geometry) AS ext '  # noqa: S608
                        f'FROM "{schema}"."{tabela}"')
            r = cur.fetchone()
            coords = json.loads(r["ext"])["coordinates"][0] if r["ext"] else []
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            caixa = [min(xs), min(ys), max(xs), max(ys)] if coords else []
            return int(r["n"]), caixa
    finally:
        con.close()


# --------------------------------------------------------------------------- cláusula 1: os dois serviços


def test_wfs_e_ogc_api_adicionados_e_lidos(sessao_a, servidor, conexoes):
    """Cláusula 1 do portão: uma conexão WFS 2.0 e uma OGC API - Features são registradas e a plataforma lê o
    que cada uma publica (coleção, CRS declarado, atributos e o TIPO declarado de cada atributo)."""
    s = servidor(total=250)
    id_wfs = conexoes("wfs", s.url_wfs, "cl1")
    id_ogc = conexoes("ogc_api", s.url_ogc, "cl1")

    r = sessao_a.get(f"/api/conexoes/{id_wfs}/colecoes")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    col_wfs = r.json()["itens"][0]
    assert col_wfs["nome"].endswith(COLECAO)
    assert col_wfs["srid_nativo"] == 31983, "o CRS nativo declarado pelo WFS tem de ser lido, não presumido"
    assert "application/json" in col_wfs["formatos"]

    r = sessao_a.get(f"/api/conexoes/{id_ogc}/colecoes")
    assert r.status_code == 200, r.text
    col_ogc = r.json()["itens"][0]
    assert col_ogc["nome"] == COLECAO
    assert col_ogc["srid_entregue"] == 4326  # OGC API Parte 1: /items é sempre CRS84

    for cid, origem_esperada in ((id_wfs, "describefeaturetype"), (id_ogc, "queryables")):
        r = sessao_a.get(f"/api/conexoes/{cid}/colecoes/{COLECAO}/campos")
        assert r.status_code == 200, r.text
        por_nome = {c["nome"]: c for c in r.json()["itens"]}
        assert set(por_nome) == {"nome", "quantia", "medida", "ativo", "dia"}
        assert all(c["origem_do_tipo"] == origem_esperada for c in por_nome.values())
        assert por_nome["quantia"]["tipo"] in ("integer", "bigint")
        assert por_nome["medida"]["tipo"] == "double precision"
        assert por_nome["ativo"]["tipo"] == "boolean"
        assert por_nome["dia"]["tipo"] == "date"


def test_modo_referenciado_bbox_datetime_e_cache_curto(sessao_a, servidor, conexoes):
    """Modo referenciado: consulta ao vivo com bbox e datetime, e a MESMA consulta logo em seguida vem do cache
    curto (sem uma segunda ida ao serviço) — é o que impede a tela de arrastar o mapa e martelar o órgão."""
    s = servidor(total=400)
    cid = conexoes("ogc_api", s.url_ogc, "ref")

    r = sessao_a.get(f"/api/conexoes/{cid}/colecoes/{COLECAO}/feicoes?limite=50")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["numberReturned"] == 50
    assert corpo["numberMatched"] == 400
    assert corpo["do_cache"] is False

    antes = len(s.pedidos)
    r2 = sessao_a.get(f"/api/conexoes/{cid}/colecoes/{COLECAO}/feicoes?limite=50")
    assert r2.status_code == 200
    assert r2.json()["do_cache"] is True
    assert len(s.pedidos) == antes, "a segunda consulta idêntica não pode ir ao serviço externo"

    # bbox recorta de verdade (o servidor filtra pelos mesmos graus que o conector manda)
    r3 = sessao_a.get(f"/api/conexoes/{cid}/colecoes/{COLECAO}/feicoes?limite=1000&bbox=-47.9,-15.8,-47.89,-15.79")
    assert r3.status_code == 200, r3.text
    assert 0 < r3.json()["numberReturned"] < 400

    r4 = sessao_a.get(f"/api/conexoes/{cid}/colecoes/{COLECAO}/feicoes?limite=1000&datahora=2026-01-01/2026-01-05")
    assert r4.status_code == 200, r4.text
    assert 0 < r4.json()["numberReturned"] < 400


def test_conexao_de_tipo_sem_conector_recusa_com_nome(sessao_a, servidor, conexoes):
    """Uma conexão `wms` não é feição: a rota do conector recusa com 422 nomeado, nunca com 500."""
    s = servidor(total=10)
    cid = conexoes("wms", s.url_wfs, "wms")
    r = sessao_a.get(f"/api/conexoes/{cid}/colecoes")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "tipo_sem_conector"


# --------------------------------------------------------------------------- cláusula 3: paginação


@pytest.mark.parametrize("tipo", ["wfs", "ogc_api"])
def test_paginacao_bate_com_number_matched(sessao_a, servidor, conexoes, tipo):
    """Cláusula 3: a contagem lida página a página tem de ser IGUAL ao `numberMatched` que o serviço declara,
    e a leitura tem de ter usado mais de uma página (senão não se provou paginação nenhuma)."""
    from app.conexao import vetor_externo as ve

    s = servidor(total=1234)
    url = s.url_wfs if tipo == "wfs" else s.url_ogc
    conexoes(tipo, url, "pag")  # a conexão existe na API; a paginação em si é medida no conector
    conector = ve.Conector(tipo=tipo, url=url)
    col = ve.colecao_ou_erro(conector, COLECAO)
    declarado = ve.contar(conector, col)
    assert declarado == 1234

    formato = ve._formato_json_wfs(col) if tipo == "wfs" else "application/geo+json"
    pag = ve.Paginador(conector, col, tam_pagina=100, limite=10_000, formato_json=formato)
    lidas = sum(len(lote) for lote in pag.paginas_json())
    assert lidas == declarado == pag.relatorio.numero_matched
    assert pag.relatorio.paginas >= 13, "1.234 feições a 100 por página não cabem em menos de 13 requisições"
    assert pag.relatorio.limite_atingido is False
    assert pag.relatorio.ignora_paginacao is False

    if tipo == "wfs":
        indices = [int(q["startindex"]) for _, q in s.pedidos if q.get("request", "").lower() == "getfeature"
                   and "startindex" in q]
        assert indices[:3] == [0, 100, 200], f"o conector tem de andar com STARTINDEX; viu {indices[:5]}"
    else:
        desloc = [int(q.get("offset", 0)) for c, q in s.pedidos if c.endswith("/items")]
        assert sorted(set(desloc))[:3] == [0, 100, 200], f"o link rel=next tem de andar; viu {desloc[:5]}"


# --------------------------------------------------------------------------- cláusulas 2 e 4: cópia e tipos


def test_copia_50_mil_feicoes_com_tempo_medido(sessao_a, cliente_demo, servidor, conexoes, camadas,
                                               worker_ogc, env, medida):
    """Cláusulas 2 e 4: 50 mil feições copiadas de um WFS 2.0, em tempo medido; tipos de atributo preservados
    como o serviço os DECLAROU; CRS nativo (EPSG:31983, em metros) gravado e geometria reprojetada para 4326."""
    s = servidor(total=TOTAL_GRANDE)
    cid = conexoes("wfs", s.url_wfs, "copia50k")
    t0 = time.monotonic()
    final = _copiar(cliente_demo, cid, camadas, tam_pagina=5000, limite_feicoes=TOTAL_GRANDE, timeout=900)
    decorrido = time.monotonic() - t0
    assert final["estado"] == "concluido", json.dumps(final)[:900]
    res = final["resultado"]
    assert res["feicoes"] == TOTAL_GRANDE
    assert res["declaradas_pelo_servico"] == TOTAL_GRANDE
    assert res["limite_atingido"] is False
    assert res["paginas"] >= 10
    assert res["srid_nativo"] == 31983 and res["srid_entregue"] == 31983 and res["srid_gravado"] == 4326

    n, caixa = _contar(env, res["schema"], res["tabela"])
    assert n == TOTAL_GRANDE, "a tabela tem de ter exatamente as feições que o serviço declarou"
    assert -75 < caixa[0] < -30 and -35 < caixa[1] < 10, (
        f"a reprojeção de EPSG:31983 para 4326 tem de cair no Brasil, e caiu em {caixa}"
    )

    tipos = _colunas(env, res["schema"], res["tabela"])
    assert tipos["nome"] == "text"
    assert tipos["quantia"] == "integer", "xsd:int declarado tem de virar integer, não bigint nem text"
    assert tipos["medida"] == "double precision"
    assert tipos["ativo"] == "boolean"
    assert tipos["dia"] == "date"

    medida(ITEM)("copia_50k_feicoes_s", round(decorrido, 2), "segundos",
                 "pytest tests/api/conexao/test_wfs_ogcapi.py::test_copia_50_mil_feicoes_com_tempo_medido")
    medida(ITEM)("copia_50k_download_s", res["segundos_download"], "segundos", "resultado do job")
    medida(ITEM)("copia_50k_carga_ogr2ogr_s", res["segundos_carga"], "segundos", "resultado do job")
    medida(ITEM)("copia_50k_paginas", res["paginas"], "requisições", "resultado do job")


def test_copia_ogc_api_preserva_tipos_de_queryables(sessao_a, cliente_demo, servidor, conexoes, camadas,
                                                    worker_ogc, env):
    """O mesmo para OGC API - Features: os tipos vêm de `/queryables` (JSON Schema). `integer` do JSON Schema
    não tem largura, então vira `bigint` — e é isso que a ficha diz, sem fingir precisão que o padrão não dá."""
    s = servidor(total=3000)
    cid = conexoes("ogc_api", s.url_ogc, "copiaogc")
    final = _copiar(cliente_demo, cid, camadas, tam_pagina=1000, limite_feicoes=10_000, timeout=300)
    assert final["estado"] == "concluido", json.dumps(final)[:900]
    res = final["resultado"]
    assert res["feicoes"] == 3000 == res["declaradas_pelo_servico"]
    tipos = _colunas(env, res["schema"], res["tabela"])
    assert tipos["nome"] == "text"
    assert tipos["quantia"] == "bigint"
    assert tipos["medida"] == "double precision"
    assert tipos["ativo"] == "boolean"
    assert tipos["dia"] == "date"


def test_copia_wfs_so_com_gml(sessao_a, cliente_demo, servidor, conexoes, camadas, worker_ogc, env):
    """WFS que não anuncia nenhum outputFormat JSON: as páginas vêm em GML 3.2 e são convertidas LOCALMENTE
    pelo GDAL (nenhuma requisição sai do ogr2ogr). O modo referenciado, esse sim, recusa com motivo nomeado."""
    s = servidor(total=800, declara_json=False)
    cid = conexoes("wfs", s.url_wfs, "gml")

    r = sessao_a.get(f"/api/conexoes/{cid}/colecoes/{COLECAO}/feicoes?limite=10")
    assert r.status_code == 422 and r.json()["erro"] == "formato_json_indisponivel"

    final = _copiar(cliente_demo, cid, camadas, tam_pagina=200, limite_feicoes=5000, timeout=300)
    assert final["estado"] == "concluido", json.dumps(final)[:900]
    res = final["resultado"]
    assert res["feicoes"] == 800
    n, caixa = _contar(env, res["schema"], res["tabela"])
    assert n == 800
    assert -75 < caixa[0] < -30 and -35 < caixa[1] < 10, f"GML reprojetado tem de cair no Brasil, caiu em {caixa}"
    tipos = _colunas(env, res["schema"], res["tabela"])
    assert tipos["quantia"] == "integer" and tipos["dia"] == "date"


# --------------------------------------------------------------------------- refutação do adversário


def test_wfs_de_5_milhoes_sem_paginacao_para_no_limite_e_avisa(sessao_a, cliente_demo, servidor, conexoes,
                                                               camadas, worker_ogc, env, medida):
    """Refutação exigida: um WFS que declara 5.000.000 de feições e IGNORA `COUNT`/`STARTINDEX` (devolve sempre
    o mesmo bloco). O job tem de TERMINAR — no limite que NÓS declaramos —, marcar o limite atingido, escrever
    o aviso na procedência da camada e não prender o worker."""
    s = servidor(total=4000, ignora_paginacao=True, matched_declarado=5_000_000, pagina_forcada=2000)
    cid = conexoes("wfs", s.url_wfs, "5mi")
    t0 = time.monotonic()
    final = _copiar(cliente_demo, cid, camadas, tam_pagina=500, limite_feicoes=1000, timeout=300)
    decorrido = time.monotonic() - t0

    assert final["estado"] == "concluido", json.dumps(final)[:900]
    res = final["resultado"]
    assert res["declaradas_pelo_servico"] == 5_000_000
    assert res["feicoes"] == 1000, "a cópia tem de parar no limite declarado, não no que o serviço quiser"
    assert res["limite_atingido"] is True
    assert res["ignora_paginacao"] is True
    assert any("5000000" in a or "5.000.000" in a or "ignora a paginação" in a for a in res["avisos"]), res["avisos"]

    n, _ = _contar(env, res["schema"], res["tabela"])
    assert n == 1000

    # o aviso vai para a ficha da camada, não só para o log do job (quem abrir a camada daqui a um mês tem de
    # ver que ela é um pedaço, não a coleção inteira). Lê-se `plat.item.dados` direto, e não `GET /api/itens/
    # {id}`, para o teste não depender de item de outra trilha ainda não aplicado nesta base — o que se prova
    # aqui é o que ficou GRAVADO, que é onde a informação tem de estar.
    dados = _dados_do_item_gravado(env, res["item_id"])
    assert dados["conexao"]["limite_atingido"] is True
    assert dados["conexao"]["declaradas_pelo_servico"] == 5_000_000
    assert dados["procedencia"]["limites"], "a procedência tem de carregar os avisos"

    # o worker segue vivo e aceitando trabalho depois do serviço de má-fé
    assert worker_ogc.proc.poll() is None
    outro = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 1, "passos": 2})
    assert esperar(cliente_demo, outro["id"], timeout=120)["estado"] == "concluido"

    medida(ITEM)("refutacao_5mi_sem_paginacao_s", round(decorrido, 2), "segundos",
                 "pytest tests/api/conexao/test_wfs_ogcapi.py::"
                 "test_wfs_de_5_milhoes_sem_paginacao_para_no_limite_e_avisa")


def test_servico_que_repete_a_mesma_pagina_para_na_hora(servidor):
    """Variante da má-fé: o serviço aceita `STARTINDEX` mas devolve sempre a MESMA página. Sem a trava de
    repetição o laço só pararia no teto de páginas — aqui ele para na segunda."""
    from app.conexao import vetor_externo as ve

    s = servidor(total=2000, ignora_paginacao=True, pagina_forcada=10)
    conector = ve.Conector(tipo="ogc_api", url=s.url_ogc)
    col = ve.colecao_ou_erro(conector, COLECAO)
    pag = ve.Paginador(conector, col, tam_pagina=10, limite=1_000_000, formato_json="application/geo+json")
    lidas = sum(len(lote) for lote in pag.paginas_json())
    assert lidas == 10
    assert pag.relatorio.repetiu_pagina is True
    assert pag.relatorio.paginas == 2, "duas requisições bastam para provar que a paginação não anda"
    assert any("repetiu" in a for a in pag.relatorio.avisos)


# --------------------------------------------------------------------------- medida contra serviço público


def test_medida_servicos_publicos_reais(medida):
    """Cláusula 1 na sua leitura literal ("públicos"): mede um WFS e um OGC API - Features REAIS, com o mesmo
    código. Nunca reprova por indisponibilidade de terceiro — grava o que aconteceu e segue. A prova do código
    é o servidor local; isto aqui é a prova de que o mesmo código fala com o mundo."""
    from app.conexao import vetor_externo as ve

    alvos = [
        ("wfs", "https://geoservicos.ibge.gov.br/geoserver/ows", "IBGE GeoServer (WFS 2.0)"),
        ("ogc_api", "https://demo.pygeoapi.io/master", "pygeoapi demo (OGC API - Features)"),
    ]
    resumo = {}
    for tipo, url, rotulo in alvos:
        inicio = time.monotonic()
        try:
            cols = ve.listar_colecoes(ve.Conector(tipo=tipo, url=url))
            resumo[rotulo] = {"url": url, "colecoes": len(cols),
                              "exemplo": cols[0].nome if cols else None,
                              "ms": int((time.monotonic() - inicio) * 1000)}
        except Exception as e:  # noqa: BLE001 — indisponibilidade de terceiro é dado, não falha nossa
            resumo[rotulo] = {"url": url, "erro": f"{type(e).__name__}: {str(e)[:160]}",
                              "ms": int((time.monotonic() - inicio) * 1000)}
    medida(ITEM)("servicos_publicos_lidos", resumo, "coleções por serviço",
                 "pytest tests/api/conexao/test_wfs_ogcapi.py::test_medida_servicos_publicos_reais")
    assert resumo  # a medida existe mesmo quando os dois estiverem fora do ar


def test_conexao_de_outro_inquilino_nao_vaza_nem_chega_a_falar_com_o_servico(sessao_a, sessao_b, servidor,
                                                                             conexoes):
    """Trava cruzada A→B das três rotas novas (o mesmo que `tests/api/test_cruzado.py` faz para as demais; aqui
    à mão porque `docs/openapi.json` está desatualizado no ramo e a varredura só enxerga o que está no arquivo
    — ver o handoff do item). Prova também que a RLS decide ANTES do I/O de rede: o servidor não recebe nem
    uma requisição quando o id é de outro inquilino."""
    s = servidor(total=10)
    cid = conexoes("ogc_api", s.url_ogc, "rls")
    antes = len(s.pedidos)
    for caminho in ("colecoes", f"colecoes/{COLECAO}/campos", f"colecoes/{COLECAO}/feicoes"):
        r = sessao_b.get(f"/api/conexoes/{cid}/{caminho}")
        assert r.status_code == 404, (caminho, r.status_code, r.text[:200])
        assert "conexao_inexistente" in r.text
    assert len(s.pedidos) == antes, "a rota falou com o serviço externo antes de a RLS recusar"
