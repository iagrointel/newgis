"""Testes do módulo campo (item L2-07-campo): fila de trabalho, roteiro do dia e visita com foto. Camada de
apoio própria (`zt_campo_`, mesmo padrão de tests/api/test_agol.py::_criar_camada_hospedada) — uma tabela
mínima com `globalid` (a mesma chave que `GET /api/camadas/{id}/feicoes/{globalid}` usa) e alguns pontos.

Portão do item, cláusula por cláusula:
  - "adversário coleta sem rede, muda relógio, sincroniza duas vezes: sem duplicata e sem perda" ->
    test_visita_sincronizar_duas_vezes_nao_duplica (mesmo cliente_uuid, resposta 200 na 2ª vez, 1 linha só) e
    test_visita_relogio_do_aparelho_nao_e_usado_para_decidir (capturado_em no passado/futuro não muda nada).
  - fluxo completo fila -> roteiro -> visita -> foto -> ler de volta: test_fluxo_completo.
  - multi-inquilino: test_inquilino_b_nao_ve_fila_de_a.
"""

import base64
import io
import os
import uuid

import psycopg2
import psycopg2.extras
import pytest
from PIL import Image

from app.schema_ambiente import CursorSchemaAmbiente

PREFIXO_TABELA = "zt_campo_"


def _conexao():
    """Consultas por aqui usam `plat.*` no texto; `CursorSchemaAmbiente` reescreve para o schema da trilha
    (PLAT_SCHEMA) — sem isso, uma consulta direta a `plat.campo_visita` numa base de trilha bate no schema
    `plat` de PRODUÇÃO com permissão negada (o papel da trilha só enxerga o schema dela)."""
    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    return con


def _conexao_com_contexto_demo():
    """Conexão direta + contexto de RLS do inquilino "demo" (mesmo padrão de tests/api/test_rls.py::contexto)
    — sem `set_config('plat.tenant_id', ...)` a policy `tenant_id = plat.tenant_atual()` devolve 0 linhas
    para QUALQUER consulta, mesmo no schema certo. `set_config(..., true)` é LOCAL À TRANSAÇÃO: com
    autocommit=True cada statement fecha a própria transação e o contexto some antes da consulta seguinte
    (achado ao escrever este teste) — por isso autocommit=False aqui, contexto e consulta na MESMA transação."""
    con = _conexao()
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        r = cur.fetchone()
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)",
            (str(r["tenant_id"]), str(r["usuario_id"]), "admin"),
        )
    return con


def _criar_camada_pontos(sessao, titulo: str, pontos: list[tuple[float, float]], schema: str = "d_demo"):
    """Camada vetorial hospedada com N pontos; devolve (camada_id, [globalid, ...]) na mesma ordem de `pontos`."""
    tabela = (PREFIXO_TABELA + titulo).replace("-", "_")
    con = _conexao()
    try:
        with con.cursor() as cur:
            cur.execute(
                f'CREATE TABLE IF NOT EXISTS "{schema}"."{tabela}" '
                f"(fid bigserial PRIMARY KEY, globalid uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE, "
                f"nome text, geom geometry(Point, 4326))"
            )
            cur.execute(f'TRUNCATE "{schema}"."{tabela}"')
            globalids = []
            for i, (lon, lat) in enumerate(pontos):
                cur.execute(
                    f'INSERT INTO "{schema}"."{tabela}" (nome, geom) VALUES '
                    f"(%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) RETURNING globalid",
                    (f"{titulo}-{i}", lon, lat),
                )
                globalids.append(str(cur.fetchone()["globalid"]))
    finally:
        con.close()
    r = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": titulo,
        "dados": {"schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4326,
                  "campos": [{"nome": "nome", "tipo": "text"}], "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    return r.json()["id"], globalids


def _foto_base64(cor=(200, 50, 50)) -> str:
    im = Image.new("RGB", (40, 30), cor)
    b = io.BytesIO()
    im.save(b, "JPEG")
    return base64.b64encode(b.getvalue()).decode("ascii")


@pytest.fixture
def itens_teste(sessao_a):
    criados = []
    yield criados
    for iid in criados:
        sessao_a.delete(f"/api/itens/{iid}")


# ---------------------------------------------------------------------- fluxo completo
def test_fluxo_completo(sessao_a, itens_teste):
    camada_id, globalids = _criar_camada_pontos(sessao_a, f"fluxo-{uuid.uuid4().hex[:8]}", [
        (-46.6, -23.5), (-46.61, -23.51), (-46.62, -23.52),
    ])
    itens_teste.append(camada_id)

    # 1. criar fila já com os 3 alvos
    r = sessao_a.post("/api/campo/filas", json={
        "titulo": "fila de teste", "camada_id": camada_id, "globalids": globalids,
    })
    assert r.status_code == 201, r.text
    fila = r.json()
    assert fila["adicionados"] == 3 and fila["ignorados"] == []
    fila_id = fila["id"]

    r = sessao_a.get(f"/api/campo/filas/{fila_id}")
    assert r.status_code == 200, r.text
    detalhe = r.json()
    assert len(detalhe["alvos"]) == 3
    assert [a["ordem"] for a in detalhe["alvos"]] == [1, 2, 3]

    # camada de alvos no mapa
    r = sessao_a.get(f"/api/campo/filas/{fila_id}/alvos.geojson")
    assert r.status_code == 200, r.text
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 3
    assert {f["properties"]["status"] for f in fc["features"]} == {"pendente"}

    # 2. roteiro a partir da fila inteira (todos pendentes)
    r = sessao_a.post("/api/campo/roteiros", json={
        "fila_id": fila_id, "origem": {"lon": -46.59, "lat": -23.49, "rotulo": "base"},
    })
    assert r.status_code == 201, r.text
    roteiro = r.json()
    assert roteiro["n_paradas"] == 3
    assert roteiro["motor"] == "linha_reta"
    assert roteiro["aviso"]  # honesto: sem motor de estrada ligado
    roteiro_id = roteiro["id"]

    r = sessao_a.get(f"/api/campo/roteiros/{roteiro_id}")
    assert r.status_code == 200, r.text
    r_detalhe = r.json()
    assert len(r_detalhe["paradas"]) == 3
    assert [p["ordem"] for p in r_detalhe["paradas"]] == [1, 2, 3]

    r = sessao_a.get(f"/api/campo/roteiros/{roteiro_id}/trajeto.geojson")
    assert r.status_code == 200, r.text
    traj = r.json()
    assert traj["features"][0]["geometry"]["type"] == "LineString"
    assert len(traj["features"][0]["geometry"]["coordinates"]) == 4  # origem + 3 paradas

    # 3. visita no 1º alvo do roteiro
    primeira_parada = r_detalhe["paradas"][0]
    cliente_uuid = str(uuid.uuid4())
    r = sessao_a.post("/api/campo/visitas", json={
        "cliente_uuid": cliente_uuid, "camada_id": camada_id, "globalid": primeira_parada["globalid"],
        "alvo_id": primeira_parada["alvo_id"], "fila_id": fila_id, "roteiro_id": roteiro_id,
        "status": "confirmado", "texto": "tudo certo", "lat": -23.5, "lon": -46.6,
        "capturado_em": "2026-09-10T12:00:00Z",
    })
    assert r.status_code == 201, r.text
    visita = r.json()
    assert visita["ja_existia"] is False
    visita_id = visita["id"]

    # o alvo correspondente passa a "visitado"
    r = sessao_a.get(f"/api/campo/filas/{fila_id}")
    status_por_id = {a["id"]: a["status"] for a in r.json()["alvos"]}
    assert status_por_id[primeira_parada["alvo_id"]] == "visitado"

    # 4. foto da visita
    r = sessao_a.post(f"/api/campo/visitas/{visita_id}/fotos", json={"conteudo": _foto_base64()})
    assert r.status_code == 201, r.text
    foto = r.json()
    assert foto["bytes"] > 0 and foto["url"].startswith("/api/objetos/")

    # 5. ler de volta: a visita mostra a foto
    r = sessao_a.get(f"/api/campo/visitas/{visita_id}")
    assert r.status_code == 200, r.text
    v = r.json()
    assert len(v["fotos"]) == 1
    assert v["fotos"][0]["sha256"] == foto["sha256"]

    # a URL assinada da foto realmente entrega a imagem
    r_img = sessao_a.get(v["fotos"][0]["url"])
    assert r_img.status_code == 200, r_img.text
    assert r_img.headers["content-type"].startswith("image/")

    # visitas listadas pela fila
    r = sessao_a.get("/api/campo/visitas", params={"fila_id": fila_id})
    assert r.status_code == 200, r.text
    assert len(r.json()["visitas"]) == 1
    assert r.json()["visitas"][0]["n_fotos"] == 1


# ---------------------------------------------------------------------- refutação: sincronizar 2x, relógio
def test_visita_sincronizar_duas_vezes_nao_duplica(sessao_a, itens_teste):
    camada_id, globalids = _criar_camada_pontos(sessao_a, f"dedup-{uuid.uuid4().hex[:8]}", [(-46.6, -23.5)])
    itens_teste.append(camada_id)
    cliente_uuid = str(uuid.uuid4())
    corpo = {
        "cliente_uuid": cliente_uuid, "camada_id": camada_id, "globalid": globalids[0],
        "status": "visitado", "capturado_em": "2026-09-10T09:00:00Z",
    }
    r1 = sessao_a.post("/api/campo/visitas", json=corpo)
    assert r1.status_code == 201, r1.text
    visita_id = r1.json()["id"]
    assert r1.json()["ja_existia"] is False

    # sincroniza de novo (mesmo cliente_uuid, dispositivo mandou outra vez por falta de confirmação de rede)
    r2 = sessao_a.post("/api/campo/visitas", json=corpo)
    assert r2.status_code == 200, r2.text  # não é 201: não criou nada
    assert r2.json()["id"] == visita_id
    assert r2.json()["ja_existia"] is True

    # 3ª vez, com um payload levemente diferente (o app reenvia o mesmo cliente_uuid; o servidor nunca
    # sobrescreve com base num reenvio — a visita gravada é a da 1ª chegada)
    r3 = sessao_a.post("/api/campo/visitas", json={**corpo, "texto": "tentativa tardia"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["id"] == visita_id
    assert r3.json()["texto"] is None  # a 1ª gravação venceu; nunca perdeu, nunca duplicou

    con = _conexao_com_contexto_demo()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.campo_visita WHERE cliente_uuid = %s", (cliente_uuid,))
            assert cur.fetchone()["n"] == 1
    finally:
        con.close()


def test_visita_relogio_do_aparelho_nao_e_usado_para_decidir(sessao_a, itens_teste):
    """`capturado_em` no passado ou no futuro (relógio do aparelho errado) nunca cria duplicata nem some: é só
    um campo de exibição. `recebido_em` (relógio do servidor) é quem manda."""
    camada_id, globalids = _criar_camada_pontos(sessao_a, f"relogio-{uuid.uuid4().hex[:8]}", [(-46.6, -23.5)])
    itens_teste.append(camada_id)
    for capturado_em in ("2019-01-01T00:00:00Z", "2099-01-01T00:00:00Z", "2026-09-10T09:00:00Z"):
        cliente_uuid = str(uuid.uuid4())
        r = sessao_a.post("/api/campo/visitas", json={
            "cliente_uuid": cliente_uuid, "camada_id": camada_id, "globalid": globalids[0],
            "status": "visitado", "capturado_em": capturado_em,
        })
        assert r.status_code == 201, r.text
        v = r.json()
        assert v["capturado_em"] == capturado_em  # exibido tal qual veio
        assert v["recebido_em"] is not None
        # recebido_em é do relógio do SERVIDOR: nunca cai em 2019 nem em 2099
        assert v["recebido_em"].startswith("2026-")


# ---------------------------------------------------------------------- ordem, ignorados
def test_reordenar_fila(sessao_a, itens_teste):
    camada_id, globalids = _criar_camada_pontos(sessao_a, f"ordem-{uuid.uuid4().hex[:8]}", [
        (-46.6, -23.5), (-46.61, -23.51),
    ])
    itens_teste.append(camada_id)
    r = sessao_a.post("/api/campo/filas", json={
        "titulo": "fila ordem", "camada_id": camada_id, "globalids": globalids,
    })
    fila_id = r.json()["id"]
    alvos = sessao_a.get(f"/api/campo/filas/{fila_id}").json()["alvos"]
    invertido = [a["id"] for a in reversed(alvos)]
    r = sessao_a.put(f"/api/campo/filas/{fila_id}/ordem", json={"alvo_ids": invertido})
    assert r.status_code == 200, r.text
    assert r.json()["reordenados"] == 2
    alvos2 = sessao_a.get(f"/api/campo/filas/{fila_id}").json()["alvos"]
    assert [a["id"] for a in alvos2] == invertido


def test_adicionar_globalid_inexistente_e_ignorado(sessao_a, itens_teste):
    camada_id, globalids = _criar_camada_pontos(sessao_a, f"ignora-{uuid.uuid4().hex[:8]}", [(-46.6, -23.5)])
    itens_teste.append(camada_id)
    r = sessao_a.post("/api/campo/filas", json={
        "titulo": "fila com lixo", "camada_id": camada_id, "globalids": [globalids[0], str(uuid.uuid4())],
    })
    assert r.status_code == 201, r.text
    assert r.json()["adicionados"] == 1
    assert len(r.json()["ignorados"]) == 1


# ---------------------------------------------------------------------- multi-inquilino
def test_inquilino_b_nao_ve_fila_de_a(sessao_a, sessao_b, itens_teste):
    camada_id, globalids = _criar_camada_pontos(sessao_a, f"cruz-{uuid.uuid4().hex[:8]}", [(-46.6, -23.5)])
    itens_teste.append(camada_id)
    r = sessao_a.post("/api/campo/filas", json={
        "titulo": "fila do inquilino A", "camada_id": camada_id, "globalids": globalids,
    })
    fila_id = r.json()["id"]

    # B não enxerga a fila de A
    assert sessao_b.get(f"/api/campo/filas/{fila_id}").status_code == 404
    assert sessao_b.get(f"/api/campo/filas/{fila_id}/alvos.geojson").status_code == 404
    assert fila_id not in [f["id"] for f in sessao_b.get("/api/campo/filas").json()["filas"]]

    # B não consegue criar alvo/roteiro/visita contra a fila/camada de A
    r = sessao_b.post(f"/api/campo/filas/{fila_id}/alvos", json={"globalids": globalids})
    assert r.status_code == 404
    r = sessao_b.post("/api/campo/roteiros", json={
        "fila_id": fila_id, "origem": {"lon": -46.6, "lat": -23.5},
    })
    assert r.status_code == 404
    r = sessao_b.post("/api/campo/visitas", json={
        "cliente_uuid": str(uuid.uuid4()), "camada_id": camada_id, "globalid": globalids[0],
        "fila_id": fila_id, "status": "visitado", "capturado_em": "2026-09-10T09:00:00Z",
    })
    assert r.status_code == 404
