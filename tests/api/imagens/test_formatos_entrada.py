"""Formatos de entrada raster (item L1-01-f) — o portão INTEIRO contra o job de ingestão real
(`imagens.ingestar`), o Garage e o pgstac desta trilha.

Portão, cláusula por cláusula (LITERAL do item):
 - cláusula 1: um arquivo aberto por formato listado em tests/dados/raster/ importa e vira COG válido
   (o job roda `rio-cogeo cog_validate --strict` em cada perfil que produz; aqui os resultados são
   conferidos E o científico de um GeoTIFF e do mosaico é revalidado FORA do job, no processo do teste);
 - cláusula 2: ECW/MrSID recusam com a mensagem exata da tabela (`app.imagens.formatos`);
 - cláusula 3: zip com 4 cenas contíguas vira 1 item com 1 COG mosaicado (bbox/dimensões da UNIÃO);
 - cláusula 4: zip com cenas de CRS diferentes recusa DIZENDO quais (EPSG de cada arquivo na mensagem);
 - cláusula 5: GET /api/imagens/formatos devolve exatamente `formatos.lista()` — a tela lê a MESMA
   tabela do código; tabela diferente é a refutação nomeada do item.

Refutações pedidas, cada uma com o arquivo pronto: JP2 de 16 bits por pixel importa com o dtype
preservado; IMG com pirâmides externas .rrd importa (o irmão viaja no zip); netCDF com eixo de tempo
recusa apontando o item L1-19 (nunca importa como 4 bandas silenciosas); ASCII Grid com vírgula
decimal recusa com a mensagem dirigida.

A ingestão acontece no PROCESSO do teste (corpo do job de verdade, com subprocessos gdal isolados),
contra o inquilino temporário, o Garage e o pgstac da trilha — o mesmo caminho que o worker roda.
"""

import subprocess
import uuid
from pathlib import Path

import pytest

ITEM = "L1-01-f-formatos-de-entrada"
DADOS = Path(__file__).resolve().parents[2] / "dados" / "raster"

# (arquivo, formato_entrada esperado, epsg esperado, epsg a declarar no envio)
ACEITOS = [
    ("geotiff_sintetico.tif", "GeoTIFF / BigTIFF", 31983, None),
    ("bigtiff_sintetico.tif", "GeoTIFF / BigTIFF", 31983, None),
    ("jpeg2000_sintetico.jp2", "JPEG 2000", 31983, None),
    ("erdas_piramides_externas.zip", "Erdas Imagine (.img)", 31983, None),  # refutação: par com .rrd
    ("envi_par.zip", "ENVI (dat + hdr)", 31983, None),
    ("ascii_grid_sintetico.asc", "ASCII Grid (ESRI)", None, 31983),  # sem .prj: EPSG declarado no envio
    ("png_world.zip", "PNG com world file", None, 4326),  # world file não traz CRS
    ("jpeg_world.zip", "JPEG com world file", None, 4326),
    ("netcdf_sintetico.nc", "netCDF (1 variável × 1 tempo)", 31983, None),
    ("grib_sintetico.grb2", "GRIB (1 mensagem)", 31998, None),
    ("loja_zarr.zarr", "Zarr (armazém zipado)", 31983, None),
    ("superoverlay.kmz", "KMZ superoverlay (imagem base)", 4326, None),
]
# (arquivo, trecho obrigatório da mensagem de recusa)
RECUSADOS = [
    ("proprietario.ecw", "SDK proprietário"),
    ("proprietario.sid", "SDK proprietário"),
    ("geopdf_sintetico.pdf", "não abre PDF raster"),
    ("hdf5_sem_georref.h5", "não carrega georreferência"),
    ("ascii_grid_virgula.asc", "vírgula decimal"),
    ("netcdf_eixo_tempo.nc", "L1-19"),
]


class _CtxIngestao:
    """O mínimo da interface de ContextoJob que `imagens_ingestar` usa (db, log, progresso, entrada,
    subprocesso): cursor por inquilino, log/progresso mudos e subprocesso real com captura."""

    def __init__(self, tenant_id: int, usuario_id: int, dir_trabalho: Path):
        from app import db as mod_db

        self.tenant_id = tenant_id
        self.usuario_id = usuario_id
        self.dir_trabalho = dir_trabalho
        self.dir_trabalho.mkdir(parents=True, exist_ok=True)
        self.entradas: list[dict] = []
        self._ctx = mod_db.Contexto(tenant_id, usuario_id, "teste")

    def db(self):
        from app import db as mod_db

        return mod_db.db(self._ctx)

    def progresso(self, pct: int, mensagem: str = "") -> None:
        pass

    def log(self, nivel: str, mensagem: str) -> None:
        pass

    def entrada(self, item_id, sha256: str, descricao: str = "") -> None:
        self.entradas.append({"item_id": str(item_id), "sha256": sha256})

    def subprocesso(self, argv: list[str], **kw) -> subprocess.CompletedProcess:
        kw.setdefault("text", True)
        return subprocess.run(argv, capture_output=True, **kw)


def _contexto_de():
    from tests.api.test_rls import contexto

    return contexto


@pytest.fixture(scope="module")
def inquilino(sessao_plat, env):
    """Inquilino zt-inq-* novo com balde próprio (mesmo padrão de test_ciclo_vida); apagado no fim."""
    import psycopg2

    from app import objetos
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.conftest import InquilinoTemporario

    inq = InquilinoTemporario(sessao_plat)
    yield inq
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        _contexto_de()(con, inq.id, usuario_id=inq.admin_id, login="admin")
        with con.cursor() as cur:
            objetos.apagar_bucket_do_inquilino(cur, inq.id)
        con.commit()
    finally:
        con.close()
    inq.apagar()


@pytest.fixture(scope="module")
def cenario(inquilino, medida, tmp_path_factory):
    """Ingere TODOS os arquivos do portão UMA vez (cada um com seu item `arquivo` + objeto bruto no
    balde, e o corpo do job `imagens_ingestar` rodado no processo do teste). Devolve {nome: resultado}
    — recusas viram {"falha": mensagem}. A conexão de setup é própria (fixtures de módulo)."""
    import psycopg2

    from app import objetos
    from app.imagens.ingestao import imagens_ingestar
    from app.jobs.registro import FalhaDefinitiva
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(_env_dsn(), cursor_factory=CursorSchemaAmbiente)
    base = tmp_path_factory.mktemp("formatos-entrada")
    resultados: dict[str, dict] = {}

    def ingerir(nome: str, *, epsg_declarado: int | None = None, titulo: str | None = None) -> dict:
        if nome in resultados:
            return resultados[nome]
        caminho = DADOS / nome
        contexto = _contexto_de()
        contexto(con, inquilino.id, usuario_id=inquilino.admin_id, login="admin")
        with con.cursor() as cur:
            # o bruto sobe pelo MESMO contrato do POST /api/arquivos (objetos.guardar: chave canônica
            # <slug>/<classe>/<sha256>.<ext>) — é o formato de chave que o job lê com objetos.baixar;
            # objetos_raster.guardar_bytes é só para os objetos de imagem do item (visual/científico)
            bruto = objetos.guardar(
                cur, "bruto", caminho.read_bytes(), "application/octet-stream",
                usuario_id=inquilino.admin_id,
            )
            iid = str(uuid.uuid4())
            from app.catalogo.comum import jsonb

            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s::uuid, %s, 'arquivo', %s, %s, %s, %s, %s, %s)",
                (iid, inquilino.id, titulo or nome, inquilino.admin_id,
                 jsonb({"chave": bruto["chave"], "sha256": bruto["sha256"], "bytes": bruto["bytes"],
                        "content_type": "application/octet-stream", "nome_original": nome}),
                 bruto["bytes"], inquilino.admin_id, inquilino.admin_id),
            )
        con.commit()
        ctx = _CtxIngestao(inquilino.id, inquilino.admin_id, base / nome)
        try:
            resultados[nome] = {"ok": imagens_ingestar(
                ctx, uuid.UUID(iid), titulo=titulo or nome, epsg_declarado=epsg_declarado,
            )}
        except FalhaDefinitiva as e:
            resultados[nome] = {"falha": str(e)}
        except Exception as e:  # noqa: BLE001 — falha de conversão/inesperada também é um resultado
            resultados[nome] = {"falha": f"{type(e).__name__}: {e}"}
        return resultados[nome]

    for nome, _, _, epsg in ACEITOS:
        ingerir(nome, epsg_declarado=epsg, titulo=f"formato {nome}")
    for nome, _trecho in RECUSADOS:
        ingerir(nome)
    r = ingerir("jpeg2000_12bits.jp2", titulo="formato jp2 12 bits")  # refutação
    r["ok"]["_refutacao_12bits"] = True
    r = ingerir("mosaico_4cenas.zip", titulo="formato mosaico 4 cenas")  # cláusula 3
    r["ok"]["_mosaico"] = True
    r = ingerir("mosaico_crs_diferente.zip")  # cláusula 4
    r["_crs_diferente"] = True

    yield {"inquilino": inquilino, "con": con, "resultados": resultados}
    con.close()


def _env_dsn() -> str:
    from tests.conftest import valores_env

    return valores_env()["PLAT_DSN"]


# ---------------------------------------------------------------- cláusula 1: cada formato vira COG válido
@pytest.mark.parametrize(("nome", "rotulo", "epsg", "epsg_declarado"), ACEITOS)
def test_c1_formato_aceito_importa_e_vira_cog_valido(cenario, nome, rotulo, epsg, epsg_declarado):
    r = cenario["resultados"][nome]
    assert "ok" in r, f"{nome} recusado: {r.get('falha')}"
    ok = r["ok"]
    assert ok["formato_entrada"] == rotulo, (nome, ok["formato_entrada"])
    if epsg is not None:
        assert ok["epsg"] == epsg, (nome, ok["epsg"])
    assert ok["mosaico"] is False and ok["cenas"] == 1, nome
    assert ok["item_id"] == ok["stac_id"] and ok["bytes_cientifico"] > 0


def test_c1b_os_cogs_sao_validos_fora_do_job(cenario, medida, tmp_path):
    """Confirmação independente (cláusula 1): o científico de um GeoTIFF e o do MOSAICO saem do balde e
    passam no `rio-cogeo cog_validate --strict` no processo do teste — a validade não é o job dizendo
    que se validou."""
    import rasterio
    from rio_cogeo.cogeo import cog_validate

    from app import db as mod_db
    from app import objetos
    from app.imagens import pgstac as ps

    inq = cenario["inquilino"]
    conferidos = {}
    for nome in ("geotiff_sintetico.tif", "mosaico_4cenas.zip"):
        ok = cenario["resultados"][nome]["ok"]
        with mod_db.db(mod_db.Contexto(inq.id, inq.admin_id, "admin")) as cur:
            stac = ps.item_obter(cur, inq.id, ok["colecao"], ok["item_id"])
        assert stac is not None, nome
        chave_cog = stac["assets"]["cientifico"]["href"].removeprefix("/api/objetos/")
        destino = tmp_path / f"{ok['stac_id']}_cientifico.tif"
        baixados = objetos.baixar(chave_cog, destino)
        assert baixados == stac["assets"]["cientifico"]["file:size"], nome
        with rasterio.open(destino) as ds:
            assert ds.driver == "GTiff", nome
            if nome.startswith("mosaico"):
                assert (ds.width, ds.height) == (192, 144), (nome, ds.width, ds.height)
        valido, erros, _avisos = cog_validate(str(destino), strict=True)
        assert valido and not erros, (nome, erros)
        conferidos[nome] = {"bytes": baixados, "cog_valido_strict": True}
    medida(ITEM)("cogs_validos_fora_do_job", conferidos, "itens",
                 "rio_cogeo.cog_validate(strict=True) sobre o asset cientifico baixado do balde")


# ---------------------------------------------------------------- cláusula 2: ECW/MrSID
def test_c2_ecw_e_mrsid_recusam_com_a_mensagem_da_tabela(cenario):
    from app.imagens import formatos

    for nome in ("proprietario.ecw", "proprietario.sid"):
        r = cenario["resultados"][nome]
        assert "falha" in r, f"{nome} não foi recusado"
        recusado = formatos.recusado_por_extensao(Path(nome).suffix)
        assert recusado.mensagem in r["falha"], (nome, r["falha"])
        assert "raster recusado" in r["falha"]


# ---------------------------------------------------------------- cláusula 3: zip -> 1 item mosaicado
def test_c3_zip_de_4_cenas_vira_um_item_com_um_cog_mosaicado(cenario, medida):
    from app import db as mod_db
    from app.imagens import pgstac as ps

    inq = cenario["inquilino"]
    r = cenario["resultados"]["mosaico_4cenas.zip"]
    assert "ok" in r, r.get("falha")
    ok = r["ok"]
    assert ok["mosaico"] is True and ok["cenas"] == 4, ok
    # 4 cenas 2×2 de 96×72 = 192×144 na união; geotransform do VRT começa na cena de cima à esquerda
    assert ok["dimensoes"] == [192, 144], ok["dimensoes"]
    with mod_db.db(mod_db.Contexto(inq.id, inq.admin_id, "admin")) as cur:
        stac = ps.item_obter(cur, inq.id, ok["colecao"], ok["item_id"])
    assert stac is not None, "o item STAC do mosaico tem de estar no catálogo"
    assert stac["assets"]["cientifico"]["file:size"] == ok["bytes_cientifico"]
    medida(ITEM)("mosaico_4_cenas", {"cenas": ok["cenas"], "dimensoes": ok["dimensoes"],
                                     "bytes_cientifico": ok["bytes_cientifico"]}, "item",
                 "imagens_ingestar sobre tests/dados/raster/mosaico_4cenas.zip")


# ---------------------------------------------------------------- cláusula 4: CRS diferentes dizem quais
def test_c4_zip_com_crs_diferentes_recusa_dizendo_quais(cenario):
    r = cenario["resultados"]["mosaico_crs_diferente.zip"]
    assert "falha" in r, "zip com CRS diferentes não pode importar"
    mensagem = r["falha"]
    assert "CRS diferentes" in mensagem, mensagem
    assert "EPSG:31983" in mensagem and "EPSG:4326" in mensagem, mensagem
    assert "mosaico_cena1.tif" in mensagem and "mosaico_cena_geo.tif" in mensagem, mensagem


# ---------------------------------------------------------------- refutações do item
def test_r1_jp2_de_mais_de_8_bits_importa_com_o_dtype_preservado(cenario):
    r = cenario["resultados"]["jpeg2000_12bits.jp2"]
    assert "ok" in r, r.get("falha")
    assert r["ok"]["dtype"] == "UInt16", r["ok"]["dtype"]
    assert r["ok"]["_refutacao_12bits"] is True


def test_r2_img_com_piramides_externas_importa(cenario):
    r = cenario["resultados"]["erdas_piramides_externas.zip"]
    assert "ok" in r, r.get("falha")
    assert r["ok"]["formato_entrada"] == "Erdas Imagine (.img)"


def test_r3_netcdf_com_eixo_de_tempo_recusa_apontando_o_l1_19(cenario):
    r = cenario["resultados"]["netcdf_eixo_tempo.nc"]
    assert "falha" in r, "netCDF com eixo de tempo não pode importar como bandas silenciosas"
    assert "L1-19" in r["falha"] and "4 fatias" in r["falha"], r["falha"]


def test_r4_ascii_grid_com_virgula_decimal_recusa(cenario):
    r = cenario["resultados"]["ascii_grid_virgula.asc"]
    assert "falha" in r
    assert "vírgula decimal" in r["falha"] and "ponto decimal" in r["falha"], r["falha"]


# ---------------------------------------------------------------- cláusula 5: tela == tabela do código
def test_c5_rota_formatos_devolve_a_mesma_tabela_do_codigo(cenario, medida):
    from app.imagens import formatos

    r = cenario["inquilino"].admin.get("/api/imagens/formatos")
    assert r.status_code == 200, r.text
    devolvido = r.json()
    tabela = formatos.lista()
    assert devolvido == tabela, "a rota não devolve a MESMA tabela do código (refutação do item)"
    assert len(devolvido) == len(formatos.FORMATOS) + len(formatos.RECUSADOS)
    medida(ITEM)("tabela_da_rota_igual_ao_codigo", {
        "aceitos": len(formatos.FORMATOS), "recusados": len(formatos.RECUSADOS),
    }, "formatos", "GET /api/imagens/formatos == app.imagens.formatos.lista()")


def test_c5b_rota_de_ingestao_enfileira_o_job_com_o_arquivo(cenario, conexao_plat_app):
    """POST /api/imagens/ingestoes (a porta HTTP que a tela de upload usa) aceita um item `arquivo` e
    registra o job `imagens.ingestar` (aqui ele fica pendente: quem o rodaria é o worker de produção)."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    inq = cenario["inquilino"]
    r = cenario["inquilino"].admin.post(
        "/api/imagens/ingestoes",
        json={"arquivo_id": _algum_arquivo_id(conexao_plat_app, inq), "titulo": "via rota HTTP"},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    con = psycopg2.connect(_env_dsn(), cursor_factory=CursorSchemaAmbiente)
    try:
        _contexto_de()(con, inq.id, usuario_id=inq.admin_id, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT tipo, estado FROM plat.job WHERE id = %s::uuid", (job_id,))
            linha = cur.fetchone()
        assert linha is not None and linha["tipo"] == "imagens.ingestar"
    finally:
        con.close()


def _algum_arquivo_id(conexao_plat_app, inq) -> str:
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(_env_dsn(), cursor_factory=CursorSchemaAmbiente)
    try:
        _contexto_de()(con, inq.id, usuario_id=inq.admin_id, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT id FROM plat.item WHERE tenant_id = %s AND tipo = 'arquivo' LIMIT 1",
                        (inq.id,))
            return str(cur.fetchone()["id"])
    finally:
        con.close()
