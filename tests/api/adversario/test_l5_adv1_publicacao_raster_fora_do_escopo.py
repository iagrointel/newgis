"""Adversário de linha L5 builder (parte 1) — item L5-14-publicacao-links-embed.

Achado (hipótese transversal nº 1 do laudo): `app.catalogo.publicacao.camadas_citadas` só aceita itens
cuja FAMÍLIA (`plat.tipo_item.familia`) é `camada`. Medido direto no banco:

    SELECT nome, familia FROM plat.tipo_item WHERE nome IN ('raster', 'mosaico', 'camada_vetorial');
        raster          | raster
        mosaico         | raster
        camada_vetorial | camada

`raster`/`mosaico` têm família `raster`, nunca `camada` — por isso, quando `camadas_citadas` anda pelo
grafo de dependências (`app/catalogo/relacoes.py::AUTO_MAPA`/`FAMILIA_RELACAO_MAPA`, que TRATA raster como
camada de mapa: `"raster": "camada_de_mapa"`), um item raster citado por um `mapa` cai no `else` do laço
(`proxima.append(did)`, nunca `camadas.append(did)`) e NUNCA aparece na lista final nem no escopo do token
de publicação (`tiles:ler:<id>` fica de fora). O teste oficial do item
(`tests/api/catalogo/test_publicacao.py::_montar_app`) só testa a cadeia com `camada_vetorial` — a mesma
lacuna nunca foi exercitada com uma camada de imagem.

Consequência funcional: publicar um `app`/`painel` que usa um mapa com camada raster/mosaico entrega ao
visitante anônimo (link público) um token que NÃO lê os tiles daquela camada — o próprio texto do módulo
promete o oposto ("o escopo é calculado automaticamente a partir do grafo de dependências do documento").

Reprodução mínima abaixo: raster inserido direto em `plat.item` (mesma técnica de
`tests/api/imagens/apoio_raster.py::semear_raster`, sem gerar COG/pgstac — a falha acontece na camada de
catálogo, antes de qualquer leitura de pixel) citado por um `mapa`, citado por um `app`, publicado.
"""

import uuid

import pytest

# `itens_a` e uma FIXTURE do conftest do pacote tests/api/catalogo — conftest de pacote nao alcanca
# tests/api/adversario/, e sem trazer o nome para ca os dois testes morriam em "fixture 'itens_a' not
# found" (erro de PREPARO, nao refutacao). Medido em 18/09/2026.
from tests.api.catalogo.conftest import documento_mapa, itens_a, titulo_zt  # noqa: F401
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L5-14-publicacao-links-embed"


def _inserir_raster_direto(tenant_id: int, usuario_id: int) -> str:
    from app import db
    from app.catalogo.comum import jsonb

    raster_id = str(uuid.uuid4())
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="admin")
    with db.db(ctx) as cur:
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s)",
            (
                raster_id,
                tenant_id,
                titulo_zt("raster-adv"),
                usuario_id,
                jsonb({"colecao": "zt-adv", "stac_id": "zt-adv", "perfil": "cientifico", "origem": "copiado"}),
                usuario_id,
                usuario_id,
            ),
        )
    return raster_id


# CONSERTADO (17/09/2026, ramo wt/l56): `publicacao.FAMILIAS_DE_DADO` passou a incluir a família
# `raster` (raster/mosaico) além de `camada`. O par positivo — camada vetorial continua entrando, e
# item que NÃO é dado continua fora do escopo — está em tests/api/catalogo/test_publicacao.py e no
# segundo teste abaixo.
def test_camada_raster_citada_pelo_mapa_entra_no_escopo_do_token_publicado(sessao_a, itens_a, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    tenant_id = ids["demo"]
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]

    raster_id = _inserir_raster_direto(tenant_id, adm)

    mapa = itens_a.criar("mapa", dados=documento_mapa(raster_id))
    corpo_app = {"nos": [], "mapas": [mapa["id"]]}
    app_item = itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 2, "corpo": corpo_app})

    slug = f"zt-pub-raster-{uuid.uuid4().hex[:8]}"
    r = sessao_a.post(f"/api/itens/{app_item['id']}/publicacao", json={"slug": slug})
    assert r.status_code == 201, r.text
    j = r.json()

    # portão do item L5-14: "o escopo é calculado automaticamente a partir do grafo de dependências do
    # documento" — o raster citado pelo mapa do app publicado precisa aparecer nas camadas citadas.
    assert raster_id in j["camadas_citadas"], j["camadas_citadas"]

    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")  # SET LOCAL não sobrevive ao commit
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT k.escopos FROM plat.item_publicacao p JOIN plat.token_servico k ON k.id = p.token_id "
            "WHERE p.item_id = %s::uuid",
            (app_item["id"],),
        )
        escopos = set(cur.fetchone()["escopos"])
    assert f"tiles:ler:{raster_id}" in escopos, escopos


def test_item_sem_dado_fisico_continua_fora_do_escopo_do_token(sessao_a, itens_a, conexao_plat_app):
    """Par positivo: abrir o escopo para a família `raster` não pode ter aberto para tudo — um `mapa`
    citado pelo app continua NÃO recebendo `tiles:ler:<id>` (mapa não tem dado, é documento)."""
    mapa = itens_a.criar("mapa", dados=documento_mapa())
    app_item = itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 2,
                                           "corpo": {"nos": [], "mapas": [mapa["id"]]}})
    slug = f"zt-pub-semdado-{uuid.uuid4().hex[:8]}"
    r = sessao_a.post(f"/api/itens/{app_item['id']}/publicacao", json={"slug": slug})
    assert r.status_code == 201, r.text
    assert mapa["id"] not in r.json()["camadas_citadas"], r.json()["camadas_citadas"]
