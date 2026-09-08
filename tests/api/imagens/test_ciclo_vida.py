"""Ciclo de vida do item de imagem (item L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo).

Portão, cláusula por cláusula (LITERAL do item):
 - excluir item pelo navegador: tiles respondem 404 em <= 5 s (a RLS do catálogo esconde o item apagado;
   o teste MEDE o tempo do pedido);
 - STAC não lista (o corpo STAC sai do pgstac na exclusão e volta na restauração);
 - objetos somem após a retenção, com relógio simulado: a exclusão agenda `imagens.raster_apagar_objetos`
   com agendado_para ~ +7 dias (provado na linha de plat.job); para o apagamento em si, o teste ADIANTA o
   relógio da linha do espelho (`excluido_em` 8 dias no passado) e chama o CORPO do job diretamente — é o
   mesmo código que o worker roda, sem esperar 7 dias;
 - restaurar dentro da retenção devolve tudo (STAC de volta, espelho ativo, objetos nunca saíram);
 - relatório de órfãos e quebrados gerado por `plat raster gc` (o CLI de verdade, em subprocesso) e
   visível em Tarefas (GET /api/jobs/{id} do inquilino mostra estado 'concluido' com o resultado);
 - cota recalculada após exclusão bate com o balde (GetBucketInfo do Garage: bytes e objetos caem exatamente
   o que o item apagado tinha).

Refutação (o adversário): 3 itens, apaga 2, roda o gc e confere que o 3º está intacto — STAC lista, espelho
ativo, bytes do objeto idênticos antes e depois — e que tentar o COG excluído pela URL antiga com o token
não volta: dentro da retenção a subrequisição de autorização nega (403, que barra até a fatia em cache do
nginx); depois da retenção o objeto já não existe no balde (o que ao nginx só resta responder 404).

O item é construído NO BALDE REAL do Garage (mesmo padrão de tests/api/test_garage_inquilino.py): os COGs
aqui são bytes sintéticos nomeados pela mesma regra `<item>/<asset>_<sha8>.<ext>` — o ciclo de vida não
depende do conteúdo ser um TIFF de verdade; o que ele toca são chaves, STAC, espelho, lixeira e cota.
Todos os baldes criados são apagados no fim.
"""

import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from tests.api.imagens.conftest import item_stac

ITEM = "L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo"
RAIZ = Path(__file__).resolve().parents[3]  # raiz do worktree (onde mora o pacote `app`)
COLECAO_SLUG = "imagens"
DIAS_RETENCAO = 7


# ---------------------------------------------------------------- apoio
class _CtxJob:
    """O mínimo da interface de ContextoJob que `ciclo_vida.apagar_objetos` usa, para chamar o corpo do job
    no processo do teste (relógio simulado): cursor por inquilino e progresso que não escreve nada."""

    def __init__(self, tenant_id: int):
        from app import db as mod_db

        self._ctx = mod_db.Contexto(tenant_id, 0, "teste")

    def db(self):
        from app import db as mod_db

        return mod_db.db(self._ctx)

    def progresso(self, pct: int, mensagem: str = "") -> None:
        pass


def _bucket(conexao_plat_app, inq):
    from app import objetos

    contexto = _contexto_de()
    contexto(conexao_plat_app, inq.id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        linha = objetos.garantir_bucket(cur, inq.id, inq.slug)
    conexao_plat_app.commit()
    return linha


def _contexto_de():
    from tests.api.test_rls import contexto

    return contexto


def _uso(conexao_plat_app, inq) -> dict:
    from app import objetos

    return objetos.uso_detalhado(inq.slug)


def _ler_objeto(bucket: dict, chave: str) -> bytes:
    from app import objetos

    cli = objetos._cliente(bucket, ro=True)
    return cli.get(bucket["bucket_alias"], chave.partition("/")[2])


def _apagar_objeto(bucket: dict, chave: str) -> None:
    from app import objetos

    objetos._cliente(bucket).delete(bucket["bucket_alias"], chave.partition("/")[2])


def _criar_item_raster(conexao_plat_app, inq, bucket, nome: str, com_visual: bool = True) -> dict:
    """Um item de imagem completo (objetos no balde + item STAC + espelho + plat.item) SEM o job de
    conversão: o ciclo de vida toca chaves e registros, não o conteúdo do TIFF."""
    from app import objetos_raster
    from app.catalogo import tipos as tipos_item
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    item_id = f"item{nome}"
    _contexto_de()(conexao_plat_app, inq.id, usuario_id=inq.admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        o_vis = objetos_raster.guardar_bytes(
            cur, item_id, "visual", f"conteudo do COG visual do item {nome}: {secrets.token_hex(8)}".encode()
        )
        colecao = ps.nome_colecao(inq.id, COLECAO_SLUG)
        if ps.colecao_obter(cur, inq.id, colecao) is None:
            ps.colecao_criar(cur, inq.id, COLECAO_SLUG, {"title": "imagens do teste de ciclo de vida"})
        stac = item_stac(item_id, colecao)
        stac["assets"] = {
            "visual": {
                "href": f"/api/objetos/{o_vis['chave']}",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "file:checksum": f"1220{o_vis['sha256']}",
                "file:size": o_vis["bytes"],
            },
        }
        if com_visual is False:  # item quebrado de propósito: STAC aponta para objeto que não existe
            _apagar_objeto(bucket, o_vis["chave"])
        ps.item_criar(cur, inq.id, colecao, stac)
        ri.espelhar(cur, inq.id, colecao, item_id, {
            "sha256": o_vis["sha256"], "perfil": "visual+cientifico",
            "bytes": o_vis["bytes"], "estado": "ativo",
        })
        dados = {
            "colecao": colecao, "stac_id": item_id, "perfil": "visual", "origem": "copiado",
            "srid_nativo": 4326, "guardar_original": False,
            "bandas": [{"nome": "banda_1"}],
        }
        tipos_item.validar("raster", dados)  # o esquema do tipo aceita guardar_original (migração 1911)
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), inq.id, f"Imagem {nome}", inq.admin_id, jsonb(dados),
             o_vis["bytes"], inq.admin_id, inq.admin_id),
        )
        cur.execute("SELECT id FROM plat.item WHERE dados->>'stac_id' = %s", (item_id,))
        id_item = str(cur.fetchone()["id"])
    conexao_plat_app.commit()
    return {"id": id_item, "stac_id": item_id, "chave": o_vis["chave"], "sha256": o_vis["sha256"],
            "bytes": o_vis["bytes"], "conteudo": None}


@pytest.fixture(scope="module")
def inquilino(sessao_plat, env):
    """Inquilino zt-inq-* novo com balde próprio; apagado no fim (Garage + banco + inquilino)."""
    import psycopg2

    from app import objetos
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.conftest import InquilinoTemporario

    inq = InquilinoTemporario(sessao_plat)
    yield inq
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        _contexto_de()(con, inq.id, usuario_id=0, login="teste")
        with con.cursor() as cur:
            objetos.apagar_bucket_do_inquilino(cur, inq.id)
        con.commit()
    finally:
        con.close()
    inq.apagar()


@pytest.fixture(scope="module")
def cenario(inquilino, medida):
    """Monta o cenário inteiro UMA vez (a ordem importa e está comentada passo a passo); devolve um dicionário
    com o que cada teste precisa. As exclusões/restaurações do portão acontecem AQUI, dentro do módulo.
    A conexão de setup é própria (a `conexao_plat_app` da suíte é function-scoped e não pode entrar aqui)."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.conftest import valores_env

    con = psycopg2.connect(valores_env()["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    bucket = _bucket(con, inquilino)
    uso_antes = _uso(con, inquilino)

    # --- itens A, B, C (a refutação pede 3) + D quebrado + 1 órfão; a fotografia de cota que serve de base
    # da comparação é a DEPOIS da criação (o GetBucketInfo do Garage é o juiz, não uma soma nossa)
    item_a = _criar_item_raster(con, inquilino, bucket, "a")
    item_b = _criar_item_raster(con, inquilino, bucket, "b")
    item_c = _criar_item_raster(con, inquilino, bucket, "c")
    item_d = _criar_item_raster(con, inquilino, bucket, "d", com_visual=False)
    item_c["conteudo"] = _ler_objeto(bucket, item_c["chave"])  # o sha256 de C, ANTES de qualquer gc

    # órfão: objeto na forma de imagem sem item nenhum (o gc tem de LISTAR, nunca apagar por conta própria)
    from app import objetos_raster

    _contexto_de()(con, inquilino.id, usuario_id=0, login="teste")
    with con.cursor() as cur:
        orfao = objetos_raster.guardar_bytes(cur, "orfaoexemplo1", "visual", b"objeto sem item dono")
    con.commit()
    uso_apos_criacao = _uso(con, inquilino)

    c = inquilino.admin
    r = c.post("/api/tokens", json={"nome": "zt-ciclo-stac", "escopos": ["imagens:ler", "imagens:escrever"]})
    assert r.status_code == 201, r.text
    token = r.json()

    def stac_busca(item_id: str) -> list[dict]:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app, base_url="http://testserver") as tc:
            resp = tc.get(
                f"/svc/{token['token']}/stac/search",
                params={"collections": ps_nome_colecao(inquilino.id), "limit": 50},
            )
            assert resp.status_code == 200, resp.text
            return [f["id"] for f in resp.json()["features"]]

    saida = {
        "bucket": bucket, "uso_antes": uso_antes, "uso_apos_criacao": uso_apos_criacao,
        "orfaos": orfao, "token": token,
        "a": item_a, "b": item_b, "c": item_c, "d": item_d, "stac_busca": stac_busca,
    }

    # --- 1. A é excluído e RESTAURADO (dentro da retenção) e depois excluído de novo
    assert item_a["stac_id"] in stac_busca(item_a["stac_id"])
    r = c.delete(f"/api/itens/{item_a['id']}")
    assert r.status_code == 204, r.text
    saida["job_agendado"] = _job_de_apagar_objetos(con, inquilino, item_a["stac_id"])
    saida["tiles_404_s"] = _tempo_do_tile_404(c, item_a["id"])
    r = c.post(f"/api/lixeira/{item_a['id']}/restaurar")
    assert r.status_code == 200, r.text
    assert item_a["stac_id"] in stac_busca(item_a["stac_id"]), "restaurar tem de devolver o item ao STAC"
    # o estado do espelho no MOMENTO da restauração (o A é excluído de novo logo abaixo; o que os testes
    # leem depois é o estado final, 'excluido')
    restaurou = {"objeto_presente": objetos_raster.existe(item_a["chave"])}
    _contexto_de()(con, inquilino.id, usuario_id=0, login="teste")
    with con.cursor() as cur:
        cur.execute("SELECT estado, stac FROM plat.raster_item WHERE item_id = %s", (item_a["stac_id"],))
        linha = cur.fetchone()
    restaurou["espelho_ativo"] = bool(linha and linha["estado"] == "ativo")
    restaurou["stac_consumido"] = bool(linha and linha["stac"] is None)
    saida["restaurou"] = restaurou
    r = c.delete(f"/api/itens/{item_a['id']}")
    assert r.status_code == 204, r.text

    # --- 2. B é excluído, a retenção é ADIANTADA (relógio simulado) e o corpo do job apaga os objetos
    r = c.delete(f"/api/itens/{item_b['id']}")
    assert r.status_code == 204, r.text
    contexto = _contexto_de()
    contexto(con, inquilino.id, usuario_id=0, login="teste")
    with con.cursor() as cur:
        cur.execute(
            "UPDATE plat.raster_item SET excluido_em = now() - make_interval(days => %s) WHERE item_id = %s",
            (DIAS_RETENCAO + 1, item_b["stac_id"]),
        )
    con.commit()

    from app.imagens import ciclo_vida

    resultado = ciclo_vida.apagar_objetos(_CtxJob(inquilino.id), item_b["stac_id"])
    saida["job_b"] = resultado

    MEDIDAS = {}
    yield {"inquilino": inquilino, "bucket": bucket, **saida, "MEDIDAS": MEDIDAS, "admin": c}
    con.close()


def ps_nome_colecao(tenant_id: int) -> str:
    from app.imagens import pgstac as ps

    return ps.nome_colecao(tenant_id, COLECAO_SLUG)


def _job_de_apagar_objetos(conexao_plat_app, inq, stac_id: str) -> dict:
    contexto = _contexto_de()
    contexto(conexao_plat_app, inq.id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT id, tipo, estado, agendado_para, criado_em FROM plat.job "
            "WHERE tipo = 'imagens.raster_apagar_objetos' AND parametros->>'item_id' = %s "
            "ORDER BY criado_em DESC LIMIT 1",
            (stac_id,),
        )
        r = cur.fetchone()
    assert r is not None, "a exclusão tem de enfileirar imagens.raster_apagar_objetos com retenção de 7 dias"
    atraso_s = (r["agendado_para"] - r["criado_em"]).total_seconds()
    assert abs(atraso_s - DIAS_RETENCAO * 86400) < 3600, f"agendado_para não é ~+7 dias: {atraso_s / 86400:.2f} d"
    return {"id": str(r["id"]), "atraso_dias": round(atraso_s / 86400, 2)}


def _tempo_do_tile_404(c, item_id: str) -> float:
    """Cláusula do portão: tiles respondem 404 em <= 5 s após a exclusão."""
    inicio = time.monotonic()
    r = c.get(f"/api/imagens/{item_id}/tiles/3/2/1.png")
    decorrido = time.monotonic() - inicio
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert decorrido < 5.0, f"tile levou {decorrido:.2f} s para dar 404 (portão: <= 5 s)"
    return round(decorrido, 3)


# ---------------------------------------------------------------- cláusulas do portão
def test_a_exclusao_esconde_do_stac_e_responde_404_no_tempo(cenario, medida):
    """STAC não lista + tiles 404 em <= 5 s (o tempo já foi medido e guardado no cenário)."""
    assert cenario["a"]["stac_id"] not in cenario["stac_busca"](cenario["a"]["stac_id"])
    assert 0 <= cenario["tiles_404_s"] < 5.0
    medida(ITEM)("tiles_404_em_s", cenario["tiles_404_s"], "s",
                 "GET /api/imagens/{id}/tiles/3/2/1.png logo após DELETE /api/itens/{id}")


def test_b_restaurar_dentro_da_retencao_devolve_tudo(cenario):
    """A restauração do A (capturada no cenário, no momento em que aconteceu): espelho voltou a 'ativo',
    corpo STAC guardado consumido, e os objetos nunca saíram do balde — é a diferença inteira entre lixeira
    e expurgo. (O A termina excluído de novo no cenário; o estado final é conferido na refutação.)"""
    from app import objetos_raster

    r = cenario["restaurou"]
    assert r["espelho_ativo"], "a restauração tem de reativar o espelho"
    assert r["stac_consumido"], "o corpo STAC guardado é consumido na restauração"
    assert objetos_raster.existe(cenario["a"]["chave"]), "dentro da retenção o objeto continua no balde"


def test_c_objetos_somem_apos_a_retencao_com_relogio_simulado(cenario, conexao_plat_app):
    """B: retenção adiantada + corpo do job rodado = objetos fora do balde, cota do Garage recalculada, e
    `plat.arquivo` com apagado_em. A segunda chamada do job é idempotente (zeros)."""
    from app import objetos_raster

    assert cenario["job_b"]["objetos"] == 1 and cenario["job_b"]["bytes"] == cenario["b"]["bytes"]
    assert cenario["job_b"]["pulado"] is None
    assert not objetos_raster.existe(cenario["b"]["chave"]), "os objetos de B têm de sair do balde"
    # cota recalculada bate com o balde (GetBucketInfo do Garage, não uma soma nossa): a base é a fotografia
    # DEPOIS da criação dos itens (o órfão e o D quebrado entram nos dois lados e se cancelam)
    uso = _uso(conexao_plat_app, cenario["inquilino"])
    base = cenario["uso_apos_criacao"]
    esperado = base["bytes_usados"] - cenario["b"]["bytes"]
    assert uso["bytes_usados"] == esperado, (uso["bytes_usados"], esperado)
    assert uso["objetos_usados"] == base["objetos_usados"] - 1
    contexto = _contexto_de()
    contexto(conexao_plat_app, cenario["inquilino"].id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT apagado_em FROM plat.arquivo WHERE classe = 'raster' AND referencia = %s",
                    (cenario["b"]["stac_id"],))
        linhas = cur.fetchall()
    assert linhas and all(ln["apagado_em"] is not None for ln in linhas)
    from app.imagens import ciclo_vida

    de_novo = ciclo_vida.apagar_objetos(_CtxJob(cenario["inquilino"].id), cenario["b"]["stac_id"])
    assert de_novo == {"objetos": 0, "bytes": 0, "pulado": None}, "a segunda execução do job é idempotente"


def test_d_restaurar_fora_da_retencao_e_recusado(cenario):
    """B não tem mais objetos: a rota de restauração recusa com 409 objetos_ja_apagados, nunca devolve um
    item sem dado."""
    r = cenario["admin"].post(f"/api/lixeira/{cenario['b']['id']}/restaurar")
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "objetos_ja_apagados"


def test_e_gc_gera_relatorio_visivel_em_tarefas(cenario, medida):
    """`plat raster gc` de verdade (subprocesso, o mesmo binário do scripts/plat): lista o órfão, o item
    quebrado e a lixeira vencida, registra o job concluído e ele aparece em Tarefas (GET /api/jobs/{id})."""
    inq = cenario["inquilino"]
    env = {**os.environ}
    proc = subprocess.run(
        [sys.executable, "-m", "app.imagens.ciclo_vida", "gc", "--inquilino", inq.slug],
        cwd=RAIZ, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    relatorios = json.loads(proc.stdout)
    meus = [r for r in relatorios if r["inquilino"] == inq.slug]
    assert len(meus) == 1, proc.stdout
    relatorio = meus[0]
    assert relatorio["orfaos"]["objetos"] == 1, relatorio["orfaos"]
    assert any(q["item_id"] == cenario["d"]["stac_id"] and q["motivo"] == "sem_objeto_visual"
               for q in relatorio["quebrados"]), relatorio["quebrados"]
    assert relatorio["lixeira_vencida"] == 1, "B está excluído há mais de 7 dias (relógio simulado)"
    assert all(q["item_id"] != cenario["c"]["stac_id"] for q in relatorio["quebrados"]), "C não pode aparecer"
    r = cenario["admin"].get(f"/api/jobs/{relatorio['job_id']}")
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["estado"] == "concluido"
    assert job["resultado"]["orfaos"]["objetos"] == 1
    cenario["MEDIDAS"]["gc_relatorio"] = {
        "orfaos": relatorio["orfaos"]["objetos"], "quebrados": len(relatorio["quebrados"]),
        "lixeira_vencida": relatorio["lixeira_vencida"],
    }
    medida(ITEM)("gc_relatorio", cenario["MEDIDAS"]["gc_relatorio"], "itens",
                 f"plat raster gc --inquilino {inq.slug} (subprocesso)")


def test_f_o_terceiro_item_fica_intacto_e_o_cog_excluido_nao_volta(cenario, conexao_plat_app, medida):
    """A refutação inteira: C intocado (bytes idênticos, espelho ativo, STAC lista); o COG de A (excluído,
    dentro da retenção) não volta pela URL antiga com o token — a autorização nega; o de B (fora da
    retenção) não existe mais no balde, que é o que faz o nginx responder 404."""
    from app import objetos_raster

    bucket = cenario["bucket"]
    agora = _ler_objeto(bucket, cenario["c"]["chave"])
    assert agora == cenario["c"]["conteudo"], "o gc tocou o objeto do item intacto"
    assert objetos_raster.existe(cenario["c"]["chave"])

    token = cenario["token"]["token"]
    slug = cenario["inquilino"].slug

    def uri_de(item: dict) -> str:
        sha8 = item["sha256"][:8]
        return f"/svc/{token}/cog/{slug}/{item['stac_id']}/visual_{sha8}.tif"

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="http://testserver") as tc:
        # item ATIVO (C): a autorização passa (204)
        r = tc.get("/api/arquivos/_cog/autorizar", headers={"X-Original-URI": uri_de(cenario["c"])})
        assert r.status_code == 204, r.text
        # item EXCLUÍDO dentro da retenção (A): nega MESMO com o objeto ainda no balde — é isto que barra
        # a fatia em cache do nginx sem PURGE
        r = tc.get("/api/arquivos/_cog/autorizar", headers={"X-Original-URI": uri_de(cenario["a"])})
        assert r.status_code == 403, r.text
        # item EXCLUÍDO fora da retenção (B): o objeto já não existe no balde — a resposta do nginx à URL
        # antiga é 404 (NoSuchKey da fatia); a nível de aplicação a verdade é a ausência do objeto
        assert not objetos_raster.existe(cenario["b"]["chave"])

    assert cenario["a"]["stac_id"] not in cenario["stac_busca"](cenario["a"]["stac_id"])
    contexto = _contexto_de()
    contexto(conexao_plat_app, cenario["inquilino"].id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT estado FROM plat.raster_item WHERE item_id = %s", (cenario["c"]["stac_id"],))
        assert cur.fetchone()["estado"] == "ativo"

    medida(ITEM)("refutacao_3_itens_intacto", {
        "c_sha256_ok": True, "cog_excluido_autorizar": 403, "cog_retido_objeto_presente": False,
        "tiles_404_em_s": cenario["tiles_404_s"], "retencao_dias": DIAS_RETENCAO,
        "agendado_dias": cenario["job_agendado"]["atraso_dias"],
        "bytes_liberados_b": cenario["job_b"]["bytes"],
    }, "tests/api/imagens/test_ciclo_vida.py", "python -m pytest tests/api/imagens/test_ciclo_vida.py -q")


def test_g_expurgo_do_catalogo_apaga_o_raster_inteiro(cenario, conexao_plat_app, medida):
    """Cláusula de expurgo pelo catálogo (destruidor do tipo 'raster', o corpo que o job
    `catalogo.lixeira_expurgar` roda — aqui no processo do teste, com o relógio simulado pelo mesmo
    envelhecimento do A): objetos fora do balde, item STAC fora do pgstac, linha do espelho fora e
    `plat.item` fora, com os bytes liberados no resultado. É o caminho que a lixeira do navegador usa
    no "apagar agora" (POST /api/lixeira/{id}/expurgar enfileira este mesmo corpo)."""
    from app import objetos_raster
    from app.catalogo.tarefas import catalogo_lixeira_expurgar

    inq = cenario["inquilino"]
    a = cenario["a"]
    contexto = _contexto_de()
    contexto(conexao_plat_app, inq.id, usuario_id=inq.admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
        cur.execute("UPDATE plat.item SET apagado_em = now() - interval '31 days' WHERE id = %s::uuid "
                    "RETURNING id", (a["id"],))
        assert cur.fetchone(), "o item A tem de estar na lixeira para envelhecer"
    conexao_plat_app.commit()
    assert objetos_raster.existe(a["chave"]), "o objeto de A tem de estar no balde antes do expurgo"

    class _CtxTarefa(_CtxJob):
        job_id = uuid.uuid4()

        def log(self, nivel: str, mensagem: str) -> None:  # noqa: ARG002 — o teste não precisa do log
            pass

    resultado = catalogo_lixeira_expurgar(_CtxTarefa(inq.id), dias=30, ids=[uuid.UUID(a["id"])])
    assert resultado["expurgados"] == 1, resultado
    assert resultado["recusados"] == [], resultado
    assert resultado["bytes_liberados"] >= a["bytes"], resultado

    assert not objetos_raster.existe(a["chave"]), "o expurgo tem de tirar o objeto do balde"
    contexto(conexao_plat_app, inq.id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT 1 FROM plat.raster_item WHERE item_id = %s", (a["stac_id"],))
        assert cur.fetchone() is None, "a linha do espelho tem de sair"
    colecao = ps_nome_colecao(inq.id)
    from app.imagens import pgstac as ps

    with conexao_plat_app.cursor() as cur:
        assert ps.item_obter(cur, inq.id, colecao, a["stac_id"]) is None, "o item tem de sair do STAC"
    r = cenario["admin"].get("/api/lixeira")
    assert r.status_code == 200, r.text
    assert all(i["id"] != a["id"] for i in r.json()["itens"]), "o item tem de sair da lixeira"

    medida(ITEM)("expurgo_catalogo", {
        "expurgados": resultado["expurgados"], "bytes_liberados": resultado["bytes_liberados"],
        "objeto_fora_do_balde": True,
    }, "tests/api/imagens/test_ciclo_vida.py", "python -m pytest tests/api/imagens/test_ciclo_vida.py -q")
