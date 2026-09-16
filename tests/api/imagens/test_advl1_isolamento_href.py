"""ADVERSÁRIO DE LINHA L1 (T9, 16/09/2026) — suposição transversal que os itens L1-01-ingest-raster,
L1-01-a, L1-01-d e L1-01-j compartilham e que NENHUM deles confere: o `href` de um asset dentro do
corpo de um item STAC é tratado como um ponteiro digno de confiança para o objeto que o PRÓPRIO
inquilino/coleção gravou no Garage — mas `POST /svc/<token>/stac/collections/{colecao}/items`
(app/imagens/rotas_stac.py::item_criar -> app/imagens/pgstac.py::item_criar) grava o corpo do
cliente, `assets` incluído, SEM checar se o `href` aponta para um objeto do próprio inquilino.

`app/imagens/rotas_cog.py::_resolver_asset`, `app/imagens/rotas_tiles.py::_fonte_do_item` e
`app/imagens/proveniencia.py::conferir_item` extraem a chave direto desse `href` e chamam
`app.objetos.tamanho/ler_intervalo/fonte_gdal/sha256_remoto` — funções que resolvem o BUCKET pelo
`<slug>` DENTRO da própria chave (comportamento aceito e documentado em app/objetos.py para o
armazenamento cru: "existe()/ler() resolvem pelo slug DENTRO da própria chave", ver
tests/api/test_arquivos.py::test_dois_inquilinos_nao_veem_objeto_um_do_outro) sem exigir a
assinatura HMAC de `/api/objetos/{chave}` nem conferir que o slug bate com o inquilino do TOKEN que
está pedindo. Resultado: um token com `imagens:escrever`/`imagens:ler` de um inquilino consegue
servir bytes reais do balde de OUTRO inquilino bastando fabricar um item cujo asset aponte para a
chave real de um objeto de lá — sem precisar de RW, sem precisar de assinatura, sem que o Garage
veja nada de errado (a chamada usa a chave RO do bucket ALVO, resolvida pelo próprio slug).

Duas rotas provadas aqui: `/svc/<token>/cog/<item>/<asset>.tif` (download direto) e
`POST /api/imagens/{item}/conferir` (proveniência, item L1-01-j) — a segunda nem precisa achar,
só de reler o objeto de outro inquilino e devolver o sha256 recalculado já é vazamento (oráculo de
hash e de existência através do limite de inquilino).
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


def _item_apontando_para_chave_alheia(c, token: str, chave_alheia: str) -> tuple[str, str]:
    slug = f"advl1-vaz-{secrets.token_hex(4)}"
    rc = c.post(f"/svc/{token}/stac/collections", params={"slug": slug}, json={})
    assert rc.status_code == 201, rc.text
    colecao = rc.json()["id"]
    item_id = "item-vazamento-1"
    corpo = item_stac(item_id, colecao)
    corpo["assets"] = {"cientifico": {"href": f"/api/objetos/{chave_alheia}", "type": "image/tiff",
                                      "file:checksum": "1220" + "0" * 64}}
    ri = c.post(f"/svc/{token}/stac/collections/{colecao}/items", json=corpo)
    assert ri.status_code == 201, ri.text
    return colecao, item_id


@pytest.mark.xfail(strict=True, reason=(
    "item_criar não valida o prefixo <slug> de assets.*.href contra o inquilino/coleção do item; "
    "rotas_cog.servir_cog serve bytes de OUTRO inquilino via /svc/<token>/cog/<item>/<asset>.tif "
    "quando o href aponta para a chave real de um objeto alheio no Garage (achado do adversário de "
    "linha L1, T9 16/09/2026 — comum a L1-01-ingest-raster/L1-01-a/L1-01-d)"
))
def test_cog_nao_deve_servir_objeto_de_outro_inquilino_por_href_forjado(
    conexao_plat_app, tenant_id_b, token_a_leitura_escrita
):
    conteudo_b = b"SEGREDO-DO-TENANT-B-" + secrets.token_hex(8).encode()
    objeto_b = _semear_objeto_de_b(conexao_plat_app, tenant_id_b, conteudo_b)
    c = _cliente()
    try:
        _colecao, item_id = _item_apontando_para_chave_alheia(
            c, token_a_leitura_escrita["token"], objeto_b["chave"]
        )
        resp = c.get(f"/svc/{token_a_leitura_escrita['token']}/cog/{item_id}/cientifico.tif")
        # o que o item promete: um asset cujo objeto não é do inquilino do token NUNCA é servido
        assert resp.status_code in (403, 404, 422), (
            f"vazou objeto de outro inquilino: status={resp.status_code} corpo={resp.content[:80]!r}"
        )
    finally:
        from app import objetos

        objetos.apagar(objeto_b["chave"])


@pytest.mark.xfail(strict=True, reason=(
    "app/imagens/proveniencia.py::conferir_item baixa o objeto do href sem checar que a chave é do "
    "próprio inquilino: vira oráculo de existência/hash de objetos de OUTRO inquilino através de "
    "POST /api/imagens/{item}/conferir (achado do adversário de linha L1, T9 16/09/2026)"
))
def test_conferir_nao_deve_ler_objeto_de_outro_inquilino_por_href_forjado(
    conexao_plat_app, tenant_id_b, tenant_id_a, token_a_leitura_escrita
):
    from app import objetos

    conteudo_b = b"SEGREDO-DO-TENANT-B-" + secrets.token_hex(8).encode()
    objeto_b = _semear_objeto_de_b(conexao_plat_app, tenant_id_b, conteudo_b)
    c = _cliente()
    try:
        colecao, item_id = _item_apontando_para_chave_alheia(
            c, token_a_leitura_escrita["token"], objeto_b["chave"]
        )
        contexto(conexao_plat_app, tenant_id_a, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            from app.imagens import proveniencia as prov

            resultado = prov.conferir_item(cur, tenant_id_a, colecao, item_id)
        # o que o item promete: conferir nunca chega a comparar sha256 de objeto que não é do inquilino
        ativo = resultado["ativos"][0]
        assert ativo.get("erro") and "não" in ativo["erro"].lower(), (
            f"conferir leu objeto de outro inquilino e devolveu: {ativo}"
        )
    finally:
        objetos.apagar(objeto_b["chave"])


# ---------------------------------------------------------------------------------------------------------
# L1-02-b (token de serviço com escopo por LISTA de itens/coleções/mosaicos): o vocabulário de escopo
# (app/auth/escopos.py::ESCOPO) só aceita `tiles:ler:<uuid>` no formato ESTRITO 8-4-4-4-12; a ingestão de
# verdade (app/imagens/ingestao.py::imagens_ingestar, linha 236) sempre gera `item_id = str(uuid.uuid4())`,
# mas a MESMA API STAC que o item promete expor a clientes externos (ArcGIS Pro/QGIS, `imagens:escrever`)
# aceita qualquer string de 1 a 256 caracteres como id do item (app/imagens/pgstac.py::item_criar) — e é o
# padrão usado pelo PRÓPRIO conjunto de testes da casa (tests/api/imagens/conftest.py::item_stac, ids como
# "item-a-1"). Para um item assim, a promessa "escopo por LISTA, não por camada inteira" (portão do item)
# é impossível de cumprir: `POST /api/tokens` recusa `tiles:ler:item-a-1` como escopo FORA DO VOCABULÁRIO
# antes mesmo de checar posse — o único jeito de dar a alguém acesso a UM item desses é `imagens:ler`
# (todo o inquilino) ou `admin:inquilino` (tudo).
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
