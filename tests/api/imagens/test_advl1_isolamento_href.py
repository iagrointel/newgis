"""ADVERSÁRIO DE LINHA L1 (T9, 16/09/2026) — suposição transversal que os itens L1-01-ingest-raster,
L1-01-a, L1-01-d e L1-01-j compartilham e que NENHUM deles confere: o `href` de um asset dentro do
corpo de um item STAC é tratado como um ponteiro digno de confiança para o objeto que o PRÓPRIO
inquilino/coleção gravou no Garage — mas `POST /svc/<token>/stac/collections/{colecao}/items`
(app/imagens/rotas_stac.py::item_criar -> app/imagens/pgstac.py::item_criar) gravava o corpo do
cliente, `assets` incluído, SEM checar se o `href` aponta para um objeto do próprio inquilino.

`app/imagens/rotas_cog.py::_resolver_asset`, `app/imagens/rotas_tiles.py::_fonte_do_item` e
`app/imagens/proveniencia.py::conferir_item` extraem a chave direto desse `href` e chamam
`app.objetos.tamanho/ler_intervalo/fonte_gdal/sha256_remoto` — funções que resolvem o BUCKET pelo
`<slug>` DENTRO da própria chave (comportamento aceito e documentado em app/objetos.py para o
armazenamento cru: "existe()/ler() resolvem pelo slug DENTRO da própria chave", ver
tests/api/test_arquivos.py::test_dois_inquilinos_nao_veem_objeto_um_do_outro) sem exigir a
assinatura HMAC de `/api/objetos/{chave}` nem conferir que o slug bate com o inquilino do TOKEN que
está pedindo. Resultado: um token com `imagens:escrever`/`imagens:ler` de um inquilino conseguia
servir bytes reais do balde de OUTRO inquilino bastando fabricar um item cujo asset aponte para a
chave real de um objeto de lá.

CONSERTO (16/09/2026), dois pontos únicos:
(a) escrita — `app/imagens/pgstac.py::_validar_assets_href` (chamada por `item_criar`/`item_atualizar`)
    recusa com 422 nomeado (`asset_de_outro_inquilino`) qualquer asset cujo `href` de `/api/objetos/`
    tenha um `<slug>` diferente do inquilino do token. Prova: `test_item_stac_recusa_href_de_outro_
    inquilino_na_escrita` — o item forjado nem chega a existir no catálogo.
(b) leitura — `app/objetos.py` ganhou `tenant_slug_esperado` em `tamanho/ler_intervalo/fonte_gdal/
    sha256_remoto`: quando o CHAMADOR já sabe de que inquilino a chave deveria ser (é o caso das três
    rotas de imagem, que só resolvem `href` de item do PRÓPRIO inquilino), o slug embutido na chave
    nunca é a última palavra — `ChaveDeOutroInquilino` se não bater. Defesa em profundidade: as duas
    provas abaixo criam o item BYPASSANDO `item_criar` (inserção direta em `pgstac.create_item`, o que
    simula um item que chegou ao catálogo por outro caminho que não a validação de escrita — migração,
    acesso direto ao banco, regressão futura em (a)) para provar que (b) sozinha já barra o vazamento.
"""

from __future__ import annotations

import secrets

import pytest

from tests.api.imagens.conftest import item_stac
from tests.api.test_rls import contexto


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


def _semear_objeto_de_b(conexao_plat_app, tenant_id_b, conteudo: bytes) -> dict:
    from app import objetos

    contexto(conexao_plat_app, tenant_id_b, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        objeto = objetos.guardar(cur, "zt_advl1_vazamento", conteudo, "image/tiff")
    conexao_plat_app.commit()
    assert objeto["chave"].startswith("demo2/"), objeto["chave"]
    return objeto


@pytest.fixture
def token_a_leitura_escrita(sessao_a):
    r = sessao_a.post(
        "/api/tokens",
        json={"nome": f"zt-advl1-{secrets.token_hex(4)}", "escopos": ["imagens:escrever", "imagens:ler"]},
    )
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok
    sessao_a.delete(f"/api/tokens/{tok['id']}")


def _semear_item_direto_no_pgstac(cur, tenant_id: int, colecao: str, item_id: str, href_alheio: str) -> None:
    """Cria o item STAC BYPASSANDO `app.imagens.pgstac.item_criar` (e portanto a defesa (a) de escrita) —
    simula um item que chegou ao catálogo por outro caminho que não a rota HTTP validada (migração,
    acesso direto ao banco, regressão futura na validação). É exatamente o cenário que a defesa (b) de
    `app.objetos` — nunca confiar no `<slug>` do `href`, só no do CONTEXTO de quem pede — tem de cobrir
    sozinha, sem depender de (a) ter rodado."""
    from app.catalogo.comum import jsonb
    from app.imagens import raster_item as ri

    corpo = item_stac(item_id, colecao)
    corpo["assets"] = {
        "cientifico": {"href": href_alheio, "type": "image/tiff", "file:checksum": "1220" + "0" * 64},
    }
    conteudo = {**corpo, "type": "Feature", "stac_version": "1.0.0", "collection": colecao}
    conteudo.setdefault("links", [])
    cur.execute("SELECT pgstac.create_item(%s::jsonb)", (jsonb(conteudo),))
    ri.espelhar(cur, tenant_id, colecao, item_id, {"perfil": "cientifico", "bytes": 0, "estado": "ativo"})


def test_item_stac_recusa_href_de_outro_inquilino_na_escrita(
    conexao_plat_app, tenant_id_b, token_a_leitura_escrita
):
    """defesa (a): a escrita recusa (422 nomeado `asset_de_outro_inquilino`) o item inteiro quando um
    asset aponta para o balde de outro inquilino — ponto único que fecha a porta ANTES de qualquer
    objeto ser lido (o item forjado nem passa a existir no catálogo)."""
    conteudo_b = b"SEGREDO-DO-TENANT-B-" + secrets.token_hex(8).encode()
    objeto_b = _semear_objeto_de_b(conexao_plat_app, tenant_id_b, conteudo_b)
    c = _cliente()
    try:
        token = token_a_leitura_escrita["token"]
        slug = f"advl1-vaz-{secrets.token_hex(4)}"
        rc = c.post(f"/svc/{token}/stac/collections", params={"slug": slug}, json={})
        assert rc.status_code == 201, rc.text
        colecao = rc.json()["id"]
        corpo = item_stac("item-vazamento-escrita", colecao)
        corpo["assets"] = {
            "cientifico": {"href": f"/api/objetos/{objeto_b['chave']}", "type": "image/tiff",
                          "file:checksum": "1220" + "0" * 64},
        }
        ri = c.post(f"/svc/{token}/stac/collections/{colecao}/items", json=corpo)
        assert ri.status_code == 422, ri.text
        assert ri.json().get("erro") == "asset_de_outro_inquilino", ri.text
    finally:
        from app import objetos

        objetos.apagar(objeto_b["chave"])


def test_cog_nao_deve_servir_objeto_de_outro_inquilino_por_href_forjado(
    conexao_plat_app, tenant_id_a, tenant_id_b, token_a_leitura_escrita
):
    """defesa (b), em profundidade: mesmo que um item chegue ao catálogo com um `href` de outro
    inquilino sem passar pela validação de escrita (ver o teste acima para a validação em si),
    `rotas_cog.py::servir_cog` nunca serve o objeto — `app.objetos` só resolve a chave do inquilino do
    CONTEXTO (`auth.tenant_slug`), nunca do slug embutido no `href`."""
    conteudo_b = b"SEGREDO-DO-TENANT-B-" + secrets.token_hex(8).encode()
    objeto_b = _semear_objeto_de_b(conexao_plat_app, tenant_id_b, conteudo_b)
    c = _cliente()
    try:
        token = token_a_leitura_escrita["token"]
        slug = f"advl1-vaz-{secrets.token_hex(4)}"
        rc = c.post(f"/svc/{token}/stac/collections", params={"slug": slug}, json={})
        assert rc.status_code == 201, rc.text
        colecao = rc.json()["id"]
        item_id = "item-vazamento-1"
        contexto(conexao_plat_app, tenant_id_a, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            _semear_item_direto_no_pgstac(cur, tenant_id_a, colecao, item_id, f"/api/objetos/{objeto_b['chave']}")
        conexao_plat_app.commit()
        resp = c.get(f"/svc/{token}/cog/{item_id}/cientifico.tif")
        # o que o item promete: um asset cujo objeto não é do inquilino do token NUNCA é servido
        assert resp.status_code in (403, 404, 422), (
            f"vazou objeto de outro inquilino: status={resp.status_code} corpo={resp.content[:80]!r}"
        )
    finally:
        from app import objetos

        objetos.apagar(objeto_b["chave"])


def test_conferir_nao_deve_ler_objeto_de_outro_inquilino_por_href_forjado(
    conexao_plat_app, tenant_id_b, tenant_id_a
):
    """defesa (b), em profundidade: `app/imagens/proveniencia.py::conferir_item` não relê objeto de
    outro inquilino nem quando o item chegou ao catálogo com o `href` alheio sem passar pela validação
    de escrita — vira oráculo de existência/hash de objeto de qualquer inquilino se confiar cegamente
    no `href` do item que está conferindo."""
    from app import objetos
    from app.imagens import pgstac as ps
    from app.imagens import proveniencia as prov

    conteudo_b = b"SEGREDO-DO-TENANT-B-" + secrets.token_hex(8).encode()
    objeto_b = _semear_objeto_de_b(conexao_plat_app, tenant_id_b, conteudo_b)
    try:
        contexto(conexao_plat_app, tenant_id_a, usuario_id=0, login="teste")
        slug = f"advl1-vaz-{secrets.token_hex(4)}"
        item_id = "item-vazamento-2"
        with conexao_plat_app.cursor() as cur:
            colecao = ps.nome_colecao(tenant_id_a, slug)
            ps.colecao_criar(cur, tenant_id_a, slug, {})
            _semear_item_direto_no_pgstac(cur, tenant_id_a, colecao, item_id, f"/api/objetos/{objeto_b['chave']}")
            resultado = prov.conferir_item(cur, tenant_id_a, colecao, item_id)
        # o que o item promete: conferir nunca chega a comparar sha256 de objeto que não é do inquilino
        ativo = resultado["ativos"][0]
        assert ativo.get("erro") and "não" in ativo["erro"].lower(), (
            f"conferir leu objeto de outro inquilino e devolveu: {ativo}"
        )
    finally:
        objetos.apagar(objeto_b["chave"])


# ---------------------------------------------------------------------------------------------------------
# CONTROLES POSITIVOS do conserto (turno de segurança, 17/09/2026): sem eles o conserto não vale, porque
# recusar TUDO também faria os três testes de ataque acima passarem. Cada um é o par legítimo exato de um
# ataque: mesmo caminho, mesma rota, mesma função — só que o objeto é do PRÓPRIO inquilino do token.
def _semear_objeto_do_proprio(conexao_plat_app, tenant_id_a, conteudo: bytes) -> dict:
    from app import objetos

    contexto(conexao_plat_app, tenant_id_a, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        objeto = objetos.guardar(cur, "zt_advl1_legitimo", conteudo, "image/tiff")
    conexao_plat_app.commit()
    assert objeto["chave"].startswith("demo/"), objeto["chave"]
    return objeto


def test_legitimo_item_stac_com_href_do_proprio_inquilino_e_aceito_na_escrita(
    conexao_plat_app, tenant_id_a, token_a_leitura_escrita
):
    """PAR de `test_item_stac_recusa_href_de_outro_inquilino_na_escrita`: o MESMO corpo, com o asset
    apontando para um objeto do PRÓPRIO inquilino, continua sendo aceito (201) — a validação de escrita
    não fechou a porta legítima junto com a forjada."""
    objeto = _semear_objeto_do_proprio(conexao_plat_app, tenant_id_a, b"COG-LEGITIMO-" + secrets.token_hex(8).encode())
    c = _cliente()
    try:
        token = token_a_leitura_escrita["token"]
        slug = f"advl1-ok-{secrets.token_hex(4)}"
        rc = c.post(f"/svc/{token}/stac/collections", params={"slug": slug}, json={})
        assert rc.status_code == 201, rc.text
        colecao = rc.json()["id"]
        corpo = item_stac("item-legitimo-escrita", colecao)
        corpo["assets"] = {
            "cientifico": {"href": f"/api/objetos/{objeto['chave']}", "type": "image/tiff",
                           "file:checksum": "1220" + "0" * 64},
        }
        ri = c.post(f"/svc/{token}/stac/collections/{colecao}/items", json=corpo)
        assert ri.status_code == 201, ri.text
    finally:
        from app import objetos

        objetos.apagar(objeto["chave"])


def test_legitimo_cog_do_proprio_inquilino_continua_sendo_servido(
    conexao_plat_app, tenant_id_a, token_a_leitura_escrita
):
    """PAR de `test_cog_nao_deve_servir_objeto_de_outro_inquilino_por_href_forjado`: mesma rota, mesmo
    caminho de código (`objetos.tamanho`/`ler_intervalo` com `tenant_slug_esperado`), objeto do próprio
    inquilino — tem de devolver 200 e os bytes de verdade."""
    conteudo = b"COG-LEGITIMO-" + secrets.token_hex(16).encode()
    objeto = _semear_objeto_do_proprio(conexao_plat_app, tenant_id_a, conteudo)
    c = _cliente()
    try:
        token = token_a_leitura_escrita["token"]
        slug = f"advl1-ok-{secrets.token_hex(4)}"
        rc = c.post(f"/svc/{token}/stac/collections", params={"slug": slug}, json={})
        assert rc.status_code == 201, rc.text
        colecao = rc.json()["id"]
        item_id = "item-legitimo-1"
        contexto(conexao_plat_app, tenant_id_a, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            _semear_item_direto_no_pgstac(cur, tenant_id_a, colecao, item_id, f"/api/objetos/{objeto['chave']}")
        conexao_plat_app.commit()
        resp = c.get(f"/svc/{token}/cog/{item_id}/cientifico.tif")
        assert resp.status_code == 200, f"o caso legítimo deixou de funcionar: {resp.status_code} {resp.text[:200]}"
        assert conteudo in resp.content
    finally:
        from app import objetos

        objetos.apagar(objeto["chave"])


def test_legitimo_conferir_le_objeto_do_proprio_inquilino(conexao_plat_app, tenant_id_a):
    """PAR de `test_conferir_nao_deve_ler_objeto_de_outro_inquilino_por_href_forjado`: a conferência de
    proveniência continua lendo e comparando o objeto quando ele é do próprio inquilino — aqui o
    `file:checksum` do item é de propósito um valor falso, então o veredito esperado é 'não confere'
    (o sha256 foi RECALCULADO), nunca o erro de acesso do caso forjado."""
    import hashlib

    from app import objetos
    from app.imagens import pgstac as ps
    from app.imagens import proveniencia as prov

    conteudo = b"CONFERIR-LEGITIMO-" + secrets.token_hex(16).encode()
    objeto = _semear_objeto_do_proprio(conexao_plat_app, tenant_id_a, conteudo)
    try:
        contexto(conexao_plat_app, tenant_id_a, usuario_id=0, login="teste")
        slug = f"advl1-ok-{secrets.token_hex(4)}"
        item_id = "item-legitimo-2"
        with conexao_plat_app.cursor() as cur:
            colecao = ps.nome_colecao(tenant_id_a, slug)
            ps.colecao_criar(cur, tenant_id_a, slug, {})
            _semear_item_direto_no_pgstac(cur, tenant_id_a, colecao, item_id, f"/api/objetos/{objeto['chave']}")
            resultado = prov.conferir_item(cur, tenant_id_a, colecao, item_id)
        ativo = resultado["ativos"][0]
        assert not ativo.get("erro"), f"o caso legítimo passou a dar erro de acesso: {ativo}"
        # o sha256 informado no item é falso de propósito; o que importa é que a leitura ACONTECEU
        assert hashlib.sha256(conteudo).hexdigest() in repr(ativo), ativo
    finally:
        objetos.apagar(objeto["chave"])


# ---------------------------------------------------------------------------------------------------------
# L1-02-b (token de serviço com escopo por LISTA de itens/coleções/mosaicos): o vocabulário de escopo
# (app/auth/escopos.py::ESCOPO) só aceita `tiles:ler:<uuid>` no formato ESTRITO 8-4-4-4-12; a ingestão de
# verdade (app/imagens/ingestao.py::imagens_ingestar, linha 236) sempre gera `item_id = str(uuid.uuid4())`,
# mas a MESMA API STAC que o item promete expor a clientes externos (ArcGIS Pro/QGIS/GDAL, `imagens:escrever`)
# aceita qualquer string de 1 a 256 caracteres como id do item (app/imagens/pgstac.py::item_criar) — e é o
# padrão usado pelo PRÓPRIO conjunto de testes da casa (tests/api/imagens/conftest.py::item_stac, ids como
# "item-a-1"). Para um item assim, a promessa "escopo por LISTA, não por camada inteira" (portão do item)
# é impossível de cumprir: `POST /api/tokens` recusa `tiles:ler:item-a-1` como escopo FORA DO VOCABULÁRIO
# antes mesmo de checar posse — o único jeito de dar a alguém acesso a UM item desses é `imagens:ler`
# (todo o inquilino) ou `admin:inquilino` (tudo). Vocabulário, fora do escopo do conserto de isolamento
# por href acima — fica xfail.
@pytest.mark.xfail(strict=True, reason=(
    "app/auth/escopos.py::ESCOPO só aceita tiles:ler:<uuid> em formato estrito 8-4-4-4-12; um item STAC "
    "criado pela própria API de imagens (imagens:escrever) pode ter qualquer id de 1-256 caracteres "
    "(app/imagens/pgstac.py::item_criar não exige UUID) — para esses itens 'escopo por lista' (L1-02-b) "
    "é impossível: POST /api/tokens recusa por vocabulário antes de checar posse (achado do adversário "
    "de linha L1, T9 16/09/2026)"
))
def test_token_deveria_conseguir_escopo_por_item_com_id_nao_uuid(sessao_a, token_stac_a):
    c = _cliente()
    tok = token_stac_a["token"]
    slug = f"advl1-naouuid-{secrets.token_hex(4)}"
    rc = c.post(f"/svc/{tok}/stac/collections", params={"slug": slug}, json={})
    assert rc.status_code == 201, rc.text
    colecao = rc.json()["id"]
    item_id = "item-nao-uuid-1"  # mesmo padrão de tests/api/imagens/conftest.py::item_stac
    ri = c.post(f"/svc/{tok}/stac/collections/{colecao}/items", json=item_stac(item_id, colecao))
    assert ri.status_code == 201, ri.text

    r = sessao_a.post(
        "/api/tokens",
        json={"nome": f"zt-advl1-escopo-lista-{secrets.token_hex(4)}", "escopos": [f"tiles:ler:{item_id}"]},
    )
    # o que L1-02-b promete: "escopo em lista de itens" cobre item de imagem existente e legível pelo
    # dono — não deveria recusar por vocabulário só porque o id do item STAC não é formatado como UUID
    assert r.status_code == 201, (
        f"escopo por lista não aceita id de item STAC não-UUID (mesmo formato usado pela própria suíte "
        f"de testes da casa, tests/api/imagens/conftest.py::item_stac): {r.status_code} {r.text}"
    )
    if r.status_code == 201:
        sessao_a.delete(f"/api/tokens/{r.json()['id']}")
