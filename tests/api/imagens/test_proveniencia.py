"""Item L1-01-j (proveniência verificável do item raster — o "Lastro" aplicado à imagem). Duas frentes:

1. Unidades de `app/imagens/proveniencia.py` (canonicalização, manifesto, cadeia, preenchimento) — sem
   banco, sem rede: são funções puras, testadas pelo que fazem com o dicionário.
2. Integração no padrão dos vizinhos (`apoio_raster.py`/`test_raster_item_rls.py`): monta um item raster
   com OBJETOS REAIS no balde (sha256 verdadeiro) chamando a MESMA `app.imagens.ingestao._item_stac` que
   o job `imagens.ingestar` chama — não um dicionário STAC escrito à mão — e prova as três cláusulas do
   portão: (a) o item nasce com os campos de proveniência; (b) `POST /conferir` acusa divergência quando
   o adversário edita 1 byte do objeto no balde; (c) item de outro inquilino é invisível (404, nunca 403).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from types import SimpleNamespace

import pytest

from app.imagens import proveniencia as prov


# ==================================================================== 1. unidades (sem banco)
def _manifesto_base() -> dict:
    return {
        "type": "Feature", "stac_version": "1.0.0", "id": "x", "collection": "1-imagens",
        "geometry": {"type": "Point", "coordinates": [0, 0]}, "bbox": [0, 0, 0, 0],
        "properties": {"title": "teste", "datetime": "2026-01-01T00:00:00Z"},
        "assets": {}, "links": [],
    }


def test_canonicalizar_ordena_chaves_e_tira_espaco_supérfluo():
    a = prov.canonicalizar({"b": 1, "a": {"z": 1, "y": 2}})
    b = prov.canonicalizar({"a": {"y": 2, "z": 1}, "b": 1})
    assert a == b == b'{"a":{"y":2,"z":1},"b":1}'


def test_manifesto_sha256_e_deterministico_e_nao_depende_da_propria_chave():
    item = _manifesto_base()
    h1 = prov.manifesto_sha256(item)
    item["properties"]["plat:manifesto_sha256"] = "qualquer coisa, não deveria influenciar"
    h2 = prov.manifesto_sha256(item)
    assert h1 == h2 == hashlib.sha256(prov.canonicalizar({
        **item, "properties": {k: v for k, v in item["properties"].items() if k != "plat:manifesto_sha256"},
    })).hexdigest()


def test_manifesto_sha256_muda_com_qualquer_campo():
    base = prov.manifesto_sha256(_manifesto_base())
    variante_bbox = _manifesto_base()
    variante_bbox["bbox"] = [1, 1, 1, 1]
    variante_titulo = _manifesto_base()
    variante_titulo["properties"]["title"] = "outro título"
    assert prov.manifesto_sha256(variante_bbox) != base
    assert prov.manifesto_sha256(variante_titulo) != base


def test_selar_manifesto_grava_hash_que_bate_com_recalculo_e_nao_muta_entrada():
    item = _manifesto_base()
    original = dict(item)
    selado = prov.selar_manifesto(item)
    assert item == original, "selar_manifesto não pode mutar o dict do chamador"
    assert selado["properties"]["plat:manifesto_sha256"] == prov.manifesto_sha256(selado)


def test_multihash_sha256_ida_e_volta():
    sha = "a" * 64
    mh = prov.multihash_sha256(sha)
    assert mh == "1220" + sha
    assert prov.sha256_de_multihash(mh) == sha


@pytest.mark.parametrize("ruim", ["", None, "abcd", "9999" + "a" * 64, "1220" + "a" * 63])
def test_sha256_de_multihash_recusa_formato_errado(ruim):
    with pytest.raises(ValueError):
        prov.sha256_de_multihash(ruim)


def test_montar_cadeia_ingestao_tem_os_dois_passos_na_ordem():
    cientifico = SimpleNamespace(comando=[["gdal_translate", "-co", "COMPRESS=ZSTD", "in.tif", "out.tif"]],
                                 sha256="c" * 64)
    visual = SimpleNamespace(comando=[["gdal_translate", "-of", "VRT", "in.tif", "v.vrt"],
                                      ["gdal_translate", "-co", "COMPRESS=JPEG", "v.vrt", "out.tif"]],
                             sha256="v" * 64)
    cadeia = prov.montar_cadeia_ingestao(bruto_sha256="b" * 64, cientifico=cientifico, visual=visual)
    assert [p["passo"] for p in cadeia] == ["cientifico", "visual"]
    assert cadeia[0]["entrada_sha256"] == "b" * 64 and cadeia[0]["saida_sha256"] == "c" * 64
    assert cadeia[0]["comando"] == cientifico.comando
    assert len(cadeia[1]["comando"]) == 2 and cadeia[1]["saida_sha256"] == "v" * 64


def test_preencher_propriedades_recusa_origem_desconhecida():
    with pytest.raises(ValueError):
        prov.preencher_propriedades_proveniencia({}, versoes={}, cadeia=None, origem="chutada")


def test_preencher_propriedades_ingestao_tem_cadeia_e_lineage_de_ingestao():
    props = prov.preencher_propriedades_proveniencia(
        {"title": "x"}, versoes={"gdal": "3.8.4"}, cadeia=[{"passo": "cientifico"}], origem="ingestao",
    )
    assert props["title"] == "x"  # preserva o que já tinha
    assert props["processing:software"] == {"gdal": "3.8.4"}
    assert props["processing:lineage"] == prov.LINEAGE_INGESTAO
    assert props["plat:cadeia_origem"] == "ingestao"
    assert props["plat:cadeia"] == [{"passo": "cientifico"}]
    assert "plat:reexecucao" not in props


def test_preencher_propriedades_retroativa_sem_reconversao_omite_a_chave_cadeia():
    """`plat:cadeia` fica AUSENTE (chave omitida), nunca `null` — `pgstac` descarta valor `null` de
    `properties` na gravação (medido 10/09), e um `null` gravado quebraria o próprio manifesto: o hash
    seria calculado sobre um dict que o banco nunca devolve de volta igual."""
    props = prov.preencher_propriedades_proveniencia(
        {}, versoes={"gdal": "3.8.4"}, cadeia=None, origem="retroativa_sem_reconversao",
    )
    assert "plat:cadeia" not in props
    assert props.get("plat:cadeia") is None  # lado de leitura continua None, indistinguível de um null
    assert props["processing:lineage"] == prov.LINEAGE_RETROATIVA_SEM_RECONVERSAO


# ==================================================================== 2. integração (padrão dos vizinhos)
def _rel(epsg: int = 3857) -> SimpleNamespace:
    return SimpleNamespace(
        epsg=epsg, epsg_origem="arquivo", altura=8, largura=8, bandas=1, dtype="Byte",
        avisos=[], geotransform=[0.0, 10.0, 0.0, 0.0, 0.0, -10.0],
    )


def _produto_cog(sha256: str) -> SimpleNamespace:
    return SimpleNamespace(sha256=sha256, compressao="ZSTD",
                           comando=[["gdal_translate", "-co", "COMPRESS=ZSTD", "bruto.tif", "saida.tif"]])


def _montar_item_real(tenant_id: int, slug_bucket: str, titulo: str) -> dict:
    """Constrói um item raster com objetos REAIS no balde (`objetos.guardar`, sha256 verdadeiro) chamando
    `app.imagens.ingestao._item_stac` — a MESMA função que `imagens.ingestar` chama — em vez de escrever
    um dicionário STAC à mão (padrão de `apoio_raster.py`, adaptado para exercitar a proveniência nova)."""
    from app import db, objetos
    from app.catalogo.comum import jsonb
    from app.imagens import ingestao as ing
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="teste")
    item_id = str(uuid.uuid4())

    conteudo_cientifico = f"cientifico-{item_id}".encode() * 200
    conteudo_visual = f"visual-{item_id}".encode() * 100
    conteudo_bruto = f"bruto-{item_id}".encode() * 50
    conteudo_mini = b"\x89PNG\r\n\x1a\n" + item_id.encode()

    with db.db(ctx) as cur:
        objetos.garantir_bucket(cur, tenant_id, slug_bucket)
    with db.db(ctx) as cur:
        o_cient = objetos.guardar(cur, "raster", conteudo_cientifico, "image/tiff", item_id=item_id,
                                  usuario_id=usuario_id)
        o_vis = objetos.guardar(cur, "raster", conteudo_visual, "image/tiff", item_id=item_id,
                                usuario_id=usuario_id)
        o_bruto = objetos.guardar(cur, "raster", conteudo_bruto, "application/octet-stream", item_id=item_id,
                                  usuario_id=usuario_id)
        o_mini = objetos.guardar(cur, "raster", conteudo_mini, "image/png", item_id=item_id,
                                 usuario_id=usuario_id)

    rel = _rel()
    stats = [{"banda": 1, "min": 0.0, "max": 255.0, "mean": 100.0, "std": 30.0, "nodata": 0.0}]
    geometria = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    bbox = [0.0, 0.0, 1.0, 1.0]
    objetos_ref = {
        "visual": {**o_vis, "compressao": "JPEG"},
        "cientifico": o_cient,
        "bruto": o_bruto,
        "miniatura": o_mini,
    }
    cientifico_prod = _produto_cog(o_cient["sha256"])
    visual_prod = _produto_cog(o_vis["sha256"])
    cadeia = prov.montar_cadeia_ingestao(bruto_sha256=o_bruto["sha256"], cientifico=cientifico_prod,
                                         visual=visual_prod)
    versoes = {"gdal": "3.8.4", "rio-cogeo": "7.0.2", "rasterio": "1.5.0", "plat": "0.1.0"}
    stac = ing._item_stac(item_id, ps.nome_colecao(tenant_id, ing.SLUG_COLECAO), titulo, rel, stats, geometria,
                          bbox, objetos_ref, versoes, [0.0], cadeia)

    dados_item = {
        "colecao": stac["collection"], "stac_id": item_id, "perfil": "visual", "origem": "copiado",
        "srid_nativo": rel.epsg, "bandas": [{"nome": "banda_1"}],
    }
    with db.db(ctx) as cur:
        colecao_id = ing._colecao_garantir(cur, tenant_id)
        assert colecao_id == stac["collection"]
        ps.item_criar(cur, tenant_id, colecao_id, stac)
        ri.espelhar(cur, tenant_id, colecao_id, item_id, {
            "sha256": o_cient["sha256"], "perfil": "visual+cientifico",
            "bytes": o_cient["bytes"] + o_vis["bytes"], "estado": "ativo",
        })
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (item_id, tenant_id, titulo, usuario_id, jsonb(dados_item), o_cient["bytes"] + o_vis["bytes"],
             usuario_id, usuario_id),
        )
    return {"item_id": item_id, "colecao": colecao_id, "tenant_id": tenant_id, "chave_cientifico": o_cient["chave"]}


@pytest.fixture(scope="module")
def item_a(tenant_id_a, sessao_a):
    return _montar_item_real(tenant_id_a, "demo", f"prov-{secrets.token_hex(4)}")


@pytest.fixture(scope="module")
def item_b(tenant_id_b, sessao_b):
    return _montar_item_real(tenant_id_b, "demo2", f"prov-b-{secrets.token_hex(4)}")


def test_item_novo_nasce_com_os_campos_de_proveniencia(item_a, sessao_a):
    r = sessao_a.get(f"/api/imagens/{item_a['item_id']}")
    assert r.status_code == 200, r.text
    p = r.json()["proveniencia"]
    assert set(p["processing_software"]) >= {"gdal", "rio-cogeo", "rasterio", "plat"}
    assert p["cadeia_origem"] == "ingestao"
    assert [passo["passo"] for passo in p["cadeia"]] == ["cientifico", "visual"]
    assert p["cadeia"][0]["comando"] and isinstance(p["cadeia"][0]["comando"][0], list)
    assert p["manifesto_sha256"] and len(p["manifesto_sha256"]) == 64

    from app import db
    from app.imagens import pgstac as ps

    ctx = db.Contexto(tenant_id=item_a["tenant_id"], usuario_id=0, login="teste")
    with db.db(ctx) as cur:
        stac = ps.item_obter(cur, item_a["tenant_id"], item_a["colecao"], item_a["item_id"])
    assert prov.EXTENSAO_PROCESSING in stac["stac_extensions"]
    assert stac["properties"]["plat:manifesto_sha256"] == prov.manifesto_sha256(stac)


def test_conferir_0_divergencias_no_item_recem_montado(item_a, sessao_a):
    r = sessao_a.post(f"/api/imagens/{item_a['item_id']}/conferir")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is True
    assert corpo["manifesto_ok"] is True
    assert len(corpo["ativos"]) == 4  # bruto, visual, miniatura, cientifico
    assert all(a["ok"] for a in corpo["ativos"]), corpo


def test_conferir_acusa_divergencia_quando_1_byte_do_objeto_muda(item_a, sessao_a):
    """A refutação do item, ao pé da letra: o adversário edita 1 byte do objeto no balde (chave RW) e roda
    `verificar` — TEM de acusar."""
    from app import db, objetos
    from app.garage import ClienteS3
    from app.settings import settings

    with db.db(db.Contexto(tenant_id=item_a["tenant_id"], usuario_id=0, login="teste")) as cur:
        bucket = objetos.garantir_bucket(cur, item_a["tenant_id"], "demo")
    _, obj_key = objetos._chave_e_objeto(item_a["chave_cientifico"])  # noqa: SLF001 — teste, monta a chave S3 direta
    cli = ClienteS3(settings.PLAT_GARAGE_URL, bucket["chave_rw_id"], bucket["chave_rw_segredo"],
                    settings.PLAT_GARAGE_REGIAO)
    original = cli.get(bucket["bucket_alias"], obj_key)
    adulterado = bytearray(original)
    adulterado[0] ^= 0xFF  # 1 byte trocado, tamanho igual — prova que não é só uma checagem de bytes
    cli.put(bucket["bucket_alias"], obj_key, bytes(adulterado), "image/tiff")
    try:
        r = sessao_a.post(f"/api/imagens/{item_a['item_id']}/conferir")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is False
        cientifico = next(a for a in corpo["ativos"] if a["asset"] == "cientifico")
        assert cientifico["ok"] is False
        assert cientifico["sha256_recalculado"] != cientifico["sha256_registrado"]
        # os OUTROS ativos continuam batendo — a divergência é POR ATIVO, não um veredito único e cego
        outros = [a for a in corpo["ativos"] if a["asset"] != "cientifico"]
        assert all(a["ok"] for a in outros), corpo
    finally:
        cli.put(bucket["bucket_alias"], obj_key, original, "image/tiff")  # devolve o objeto como estava


def test_item_de_outro_inquilino_e_invisivel_no_painel_e_na_conferencia(item_b, sessao_a):
    r1 = sessao_a.get(f"/api/imagens/{item_b['item_id']}")
    assert r1.status_code == 404, r1.text
    r2 = sessao_a.post(f"/api/imagens/{item_b['item_id']}/conferir")
    assert r2.status_code == 404, r2.text


def test_preencher_leve_e_idempotente(item_a):
    """`prov.preencher_leve` sobre um item que JÁ nasceu com proveniência (ingestão nova) não tem nada a
    fazer — devolve `None`, nunca reescreve."""
    from app import db
    from app.imagens import pgstac as ps

    ctx = db.Contexto(tenant_id=item_a["tenant_id"], usuario_id=0, login="teste")
    with db.db(ctx) as cur:
        stac = ps.item_obter(cur, item_a["tenant_id"], item_a["colecao"], item_a["item_id"])
        resultado = prov.preencher_leve(cur, item_a["tenant_id"], item_a["colecao"], item_a["item_id"], stac)
    assert resultado is None


def test_preencher_pendentes_preenche_item_sem_proveniencia(tenant_id_a, sessao_a):
    """Item "antigo" simulado: STAC criado SEM os campos novos (como os 2 itens reais do demo, ingeridos
    antes deste item) — a rota de administração preenche sem reconverter."""
    from app import db, objetos
    from app.catalogo.comum import jsonb
    from app.imagens import ingestao as ing
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    with db.db(db.Contexto(tenant_id=tenant_id_a, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id_a,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id_a, usuario_id=usuario_id, login="teste")
    item_id = str(uuid.uuid4())
    conteudo = f"antigo-{item_id}".encode() * 80
    with db.db(ctx) as cur:
        objetos.garantir_bucket(cur, tenant_id_a, "demo")
    with db.db(ctx) as cur:
        o = objetos.guardar(cur, "raster", conteudo, "image/tiff", item_id=item_id, usuario_id=usuario_id)
    colecao = ps.nome_colecao(tenant_id_a, ing.SLUG_COLECAO)
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    asset = {"href": f"/api/objetos/{o['chave']}", "type": tipo_cog, "file:size": o["bytes"],
             "file:checksum": prov.multihash_sha256(o["sha256"])}
    stac_antigo = {
        "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
        "geometry": {"type": "Point", "coordinates": [0, 0]}, "bbox": [0, 0, 0, 0],
        "properties": {"title": "item antigo (pré L1-01-j)", "datetime": "2026-01-01T00:00:00Z",
                       "plat:versoes": {"gdal": "3.8.4", "rio-cogeo": "7.0.2", "rasterio": "1.5.0", "plat": "0.1.0"}},
        "assets": {"cientifico": {**asset, "roles": ["data"]}}, "links": [],
    }
    with db.db(ctx) as cur:
        colecao_id = ing._colecao_garantir(cur, tenant_id_a)
        ps.item_criar(cur, tenant_id_a, colecao_id, stac_antigo)
        ri.espelhar(cur, tenant_id_a, colecao_id, item_id,
                   {"sha256": o["sha256"], "perfil": "cientifico", "bytes": o["bytes"], "estado": "ativo"})
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (item_id, tenant_id_a, "item antigo", usuario_id,
             jsonb({"colecao": colecao_id, "stac_id": item_id, "perfil": "cientifico", "origem": "copiado",
                    "srid_nativo": 3857, "bandas": [{"nome": "banda_1"}]}),
             o["bytes"], usuario_id, usuario_id),
        )

    r0 = sessao_a.get(f"/api/imagens/{item_id}")
    assert r0.json()["proveniencia"]["cadeia_origem"] is None  # ainda não preenchido

    r = sessao_a.post("/api/imagens/proveniencia/preencher-pendentes", json={"limite": 2000})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["preenchidos"] >= 1
    assert not corpo["falhas"]

    r2 = sessao_a.get(f"/api/imagens/{item_id}")
    p = r2.json()["proveniencia"]
    assert p["cadeia_origem"] == "retroativa_sem_reconversao"
    assert p["cadeia"] is None
    assert p["processing_software"] == {"gdal": "3.8.4", "rio-cogeo": "7.0.2", "rasterio": "1.5.0", "plat": "0.1.0"}
    assert p["manifesto_sha256"]

    r3 = sessao_a.post(f"/api/imagens/{item_id}/conferir")
    assert r3.status_code == 200
    assert r3.json()["ok"] is True  # objeto não mudou, checksum original ainda bate
