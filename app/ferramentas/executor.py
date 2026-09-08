"""Execução de ferramenta (item L2-05-a): resolve as entradas (item de camada do inquilino → tabela, versão e
sha256 do conteúdo), chama a função registrada com um destino `c_<16 hex>` no schema de dado do inquilino, e
publica o resultado como item `camada_vetorial` com o bloco de proveniência em `dados.procedencia.ferramenta`
(o esquema do tipo é fechado e pertence ao L0-04; `procedencia` é o único ramo aberto) e a relação `derivado_de`
para cada entrada. O MESMO caminho roda como job (`ferramentas.executar`, worker L0-05) e em processo
(`ContextoSincrono`, para `/execute` do GPServer e para a API própria abaixo do custo declarado).
Cancelamento ou falha depois de a tabela existir apaga a tabela: nunca fica camada órfã."""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import psycopg2.extras
from pydantic import BaseModel, Field

from app import db as banco
from app import limites
from app.ferramentas import registro
from app.jobs.registro import Cancelado, FalhaDefinitiva, tarefa

UTC = datetime.UTC
FAMILIA_POR_TIPO = {"GPFeatureRecordSetLayer": "camada", "GPRasterDataLayer": "raster"}


class ErroExecucao(Exception):
    """Erro nomeado da execução (vira ErroAPI na rota, FalhaDefinitiva no job)."""

    def __init__(self, status: int, codigo: str, mensagem: str, detalhe=None):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem, self.detalhe = status, codigo, mensagem, detalhe


class ContextoSincrono:
    """O que a ferramenta recebe quando roda no processo da API (mesma interface mínima de ContextoJob):
    db(), progresso(), verificar(), log(), entrada(). Sem job_id; o cancelamento é só o do cliente (não há)."""

    def __init__(self, ctx: banco.Contexto):
        self.job_id = None
        self.tenant_id = ctx.tenant_id
        self.usuario_id = ctx.usuario_id
        self.tipo = "ferramentas.executar"
        self.entradas: list[dict] = []
        self.linhas_log: list[tuple[str, str]] = []
        self._ctx = ctx
        self._dir_trabalho: Path | None = None

    @property
    def dir_trabalho(self) -> Path:
        """Diretório temporário próprio desta execução (as ferramentas raster escrevem o produto nele).
        Criado só quando alguém pede; apagado por `fechar()` no fim da execução."""
        if self._dir_trabalho is None:
            self._dir_trabalho = Path(tempfile.mkdtemp(prefix="plat-ferramenta-"))
        return self._dir_trabalho

    def fechar(self) -> None:
        if self._dir_trabalho is not None:
            shutil.rmtree(self._dir_trabalho, ignore_errors=True)
            self._dir_trabalho = None

    def subprocesso(self, argv: list[str], **kw) -> subprocess.CompletedProcess:
        """Mesma interface do ContextoJob para as ferramentas que chamam utilitário do GDAL. Aqui não há
        job para cancelar: o que limita é o relógio (FERRAMENTA_JOB_TIMEOUT_S), e o custo declarado da
        ferramenta é o que decide se ela roda em processo ou vai para a fila."""
        kw.setdefault("cwd", str(self.dir_trabalho))
        kw.setdefault("text", True)
        kw.setdefault("timeout", limites.FERRAMENTA_JOB_TIMEOUT_S)
        r = subprocess.run(argv, capture_output=True, **kw)  # noqa: S603 — argv montado em código, nunca shell
        for nome, texto in (("stdout", r.stdout), ("stderr", r.stderr)):
            for linha in (texto or "").splitlines():
                if linha.strip():
                    self.log("INFO" if nome == "stdout" else "AVISO", f"{argv[0]} {nome}: {linha}")
        return r

    def db(self):
        return banco.db(self._ctx)

    def progresso(self, pct: int, mensagem: str = "") -> None:
        self.verificar()

    def verificar(self) -> None:
        return None

    def log(self, nivel: str, mensagem: str) -> None:
        self.linhas_log.append((nivel, mensagem))

    def entrada(self, item_id, sha256: str, descricao: str = "") -> None:
        self.entradas.append({"item_id": str(item_id) if item_id else None, "sha256": sha256,
                              "descricao": descricao[:200]})


# ---------------------------------------------------------------- entradas
def _ident(nome: str) -> str:
    if not registro.PADRAO_NOME.match(nome) and not nome.isidentifier():
        raise ErroExecucao(422, "campo_invalido", f"nome de campo inválido: {nome!r}")
    return '"' + nome.replace('"', '""') + '"'


def sha256_camada(cur, schema: str, tabela: str, campos: list[str]) -> str:
    """Hash do CONTEÚDO da camada: fid, campos declarados no item e a geometria em WKB, em ordem de fid. Deixa
    de fora as colunas de sistema (globalid, criado_em…), que mudam a cada carga — é isso que faz duas execuções
    com a mesma entrada darem a mesma saída (cláusula "rerodar reproduz o sha256")."""
    colunas = ", ".join(["fid"] + [_ident(c) for c in campos] + ["ST_AsBinary(geom)"])
    cur.execute(
        f'SELECT encode(sha256(convert_to(coalesce(string_agg(md5(row({colunas})::text), \',\' ORDER BY fid), \'\'), '
        f'\'UTF8\')), \'hex\') AS h FROM "{schema}"."{tabela}"'
    )
    return cur.fetchone()["h"]


def resolver_camada(cur, item_id: str, nome_parametro: str) -> dict:
    """Item de camada vetorial legível pelo chamador (RLS + pode_ler): {item_id, titulo, versao, schema, tabela,
    srid, geometria, campos, feicoes, sha256}. Item de outro inquilino, apagado ou de outro tipo = 404 (nunca
    confirma existência)."""
    cur.execute("SELECT id, titulo, tipo, dados, versao_atual FROM plat.item "
                "WHERE id = %s::uuid AND apagado_em IS NULL AND plat.pode_ler(id)", (item_id,))
    r = cur.fetchone()
    if r is None or r["tipo"] != "camada_vetorial":
        raise ErroExecucao(404, "camada_inexistente", f"{nome_parametro}: camada inexistente ou sem leitura",
                           {"campo": nome_parametro})
    d = r["dados"] or {}
    schema, tabela = d.get("schema"), d.get("tabela")
    if not schema or not tabela or not registro.PADRAO_NOME.match(schema) or not registro.PADRAO_NOME.match(tabela):
        raise ErroExecucao(422, "camada_sem_tabela", f"{nome_parametro}: item de camada sem tabela física")
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS existe", (f'"{schema}"."{tabela}"',))
    if not cur.fetchone()["existe"]:
        raise ErroExecucao(422, "camada_sem_tabela", f"{nome_parametro}: a tabela da camada não existe")
    campos = [c["nome"] for c in d.get("campos") or []]
    cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
    feicoes = int(cur.fetchone()["n"])
    return {
        "item_id": str(r["id"]), "titulo": r["titulo"], "versao": int(r["versao_atual"]), "schema": schema,
        "tabela": tabela, "srid": int(d.get("srid") or 4326), "geometria": d.get("geometria") or "Geometry",
        "campos": campos, "feicoes": feicoes, "sha256": sha256_camada(cur, schema, tabela, campos),
    }


def resolver_raster(cur, tenant_id: int, item_id: str, nome_parametro: str) -> dict:
    """Item raster legível pelo chamador -> {item_id, titulo, versao, colecao, chave, asset, sha256, epsg,
    bandas, dtype, nodata, largura, altura, bloco, resolucao, limites}. O caminho de leitura NASCE daqui
    (asset do item STAC do inquilino), nunca de endereço vindo do cliente — o mesmo desenho do motor de
    ladrilho. Item de outro inquilino, apagado ou de outro tipo = 404, sem confirmar existência."""
    from app.imagens import pgstac as ps
    from app.raster import fonte as fonte_raster

    cur.execute("SELECT id, titulo, tipo, dados, versao_atual FROM plat.item "
                "WHERE id = %s::uuid AND apagado_em IS NULL AND plat.pode_ler(id)", (item_id,))
    r = cur.fetchone()
    if r is None or r["tipo"] != "raster":
        raise ErroExecucao(404, "raster_inexistente", f"{nome_parametro}: raster inexistente ou sem leitura",
                           {"campo": nome_parametro})
    d = r["dados"] or {}
    colecao, stac_id = d.get("colecao"), d.get("stac_id") or str(r["id"])
    stac = ps.item_obter(cur, tenant_id, colecao, stac_id) if colecao else None
    if stac is None:
        raise ErroExecucao(422, "raster_sem_stac", f"{nome_parametro}: o item raster não tem registro STAC")
    asset, ativo = _asset_de_dado(stac, nome_parametro)
    chave = (ativo.get("href") or "")[len("/api/objetos/"):]
    origem = fonte_raster.da_chave(chave)
    with fonte_raster.abrir(origem) as ds:
        meta = {
            "epsg": ds.crs.to_epsg() if ds.crs else None, "crs": str(ds.crs) if ds.crs else None,
            "geografico": bool(ds.crs and ds.crs.is_geographic), "bandas": ds.count,
            "dtype": ds.dtypes[0], "nodata": ds.nodatavals[0], "nodata_por_banda": list(ds.nodatavals),
            "largura": ds.width, "altura": ds.height, "bloco": list(ds.block_shapes[0]),
            "resolucao": [abs(ds.transform.a), abs(ds.transform.e)],
            "limites": [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top],
            "piramide": len(ds.overviews(1)),
        }
    checksum = (ativo.get("file:checksum") or "")
    return {
        "item_id": str(r["id"]), "titulo": r["titulo"], "versao": int(r["versao_atual"]), "colecao": colecao,
        "stac_id": stac_id, "asset": asset, "chave": chave, "caminho": origem.caminho, "origem": origem,
        "sha256": checksum[4:] if checksum.startswith("1220") else checksum,
        "bytes": int(ativo.get("file:size") or 0), "familia": "raster", **meta,
    }


def _asset_de_dado(stac: dict, nome_parametro: str) -> tuple[str, dict]:
    """O asset que a análise lê: `cientifico` (dtype original) quando existe; senão o primeiro com papel
    `data`; senão o `visual`. Asset que não é objeto do armazenamento da plataforma não serve para
    ferramenta (não se lê endereço de terceiro a partir de item de catálogo)."""
    ativos = stac.get("assets") or {}
    ordem = ["cientifico"] + [k for k, v in sorted(ativos.items()) if "data" in (v.get("roles") or [])] + ["visual"]
    for nome in ordem:
        a = ativos.get(nome)
        if a and str(a.get("href") or "").startswith("/api/objetos/"):
            return nome, a
    raise ErroExecucao(422, "raster_sem_asset",
                       f"{nome_parametro}: o item raster não tem asset de dado no armazenamento da plataforma",
                       {"disponiveis": sorted(ativos)})


def resolver_entradas(cur, f: registro.Ferramenta, parametros: dict, tenant_id: int | None = None) -> dict:
    entradas = {}
    for p in f.entradas:
        valor = parametros.get(p.nome)
        if not valor:
            continue
        if p.tipo == "GPFeatureRecordSetLayer":
            entradas[p.nome] = resolver_camada(cur, valor, p.nome)
        elif p.tipo == "GPRasterDataLayer":
            if tenant_id is None:
                raise ErroExecucao(500, "tenant_ausente", "resolução de raster exige o inquilino")
            entradas[p.nome] = resolver_raster(cur, tenant_id, valor, p.nome)
        elif p.tipo == "GPMultiValue" and p.subtipo == "GPRasterDataLayer":
            if tenant_id is None:
                raise ErroExecucao(500, "tenant_ausente", "resolução de raster exige o inquilino")
            for i, item in enumerate(valor, start=1):
                entradas[f"{p.nome}[{i}]"] = resolver_raster(cur, tenant_id, item, f"{p.nome}[{i}]")
    return entradas


def custo_estimado(f: registro.Ferramenta, entradas: dict, parametros: dict) -> int:
    try:
        return max(0, int(f.custo(entradas, parametros)))
    except Exception as e:  # noqa: BLE001 — custo mal escrito não pode derrubar a rota; vira 422 nomeado
        raise ErroExecucao(422, "custo_indisponivel", f"não foi possível estimar o custo: {e}") from e


# ---------------------------------------------------------------- execução e publicação
def _schema_do_inquilino(cur, tenant_id: int) -> str:
    cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (tenant_id,))
    slug = cur.fetchone()["slug"]
    # só cria/concede quando o schema ainda não existe: o GRANT dentro de camada_schema_garantir disputa com
    # outra sessão que faça DDL no mesmo schema ("tuple concurrently updated", achado nesta suíte)
    cur.execute("SELECT to_regnamespace(%s) IS NULL AS falta", (f"d_{slug}",))
    if cur.fetchone()["falta"]:
        cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
    return f"d_{slug}"


def _jsonb(v):
    return psycopg2.extras.Json(v, dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str))


def _apagar_tabela(ctx, schema: str, tabela: str) -> None:
    try:
        with ctx.db() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
    except Exception as e:  # noqa: BLE001 — a limpeza nunca esconde a exceção original
        ctx.log("AVISO", f"não foi possível apagar {schema}.{tabela}: {e}")


def proveniencia_bloco(ctx, f: registro.Ferramenta, parametros: dict, entradas: dict, custo: int,
                       login: str | None, iniciado_em) -> dict:
    """O bloco de proveniência que vai ao item de resultado, igual para saída vetorial e raster: quem, com
    que ferramenta, em que versão, com que parâmetros, sobre que entradas (item, versão e sha256)."""
    return {
        "ferramenta": f.nome, "versao": f.versao, "parametros": parametros,
        "entradas": [{"parametro": n, "item_id": e["item_id"], "versao": e["versao"], "sha256": e["sha256"],
                      "familia": e.get("familia", "camada")} for n, e in entradas.items()],
        "executada_em": iniciado_em.isoformat(timespec="seconds"),
        "autor": {"usuario_id": ctx.usuario_id, "login": login},
        "job_id": str(ctx.job_id) if ctx.job_id else None, "custo_estimado": custo,
    }


def executar(ctx, f: registro.Ferramenta, parametros: dict, titulo: str | None = None, autor: dict | None = None,
             request=None) -> dict:
    """Roda a ferramenta e publica o item de resultado. `parametros` já normalizados por `validar_parametros`.
    Devolve {"item_id", "titulo", "feicoes", "sha256", "tabela", "custo"}."""
    with ctx.db() as cur:
        entradas = resolver_entradas(cur, f, parametros, ctx.tenant_id)
        custo = custo_estimado(f, entradas, parametros)
        schema = _schema_do_inquilino(cur, ctx.tenant_id)
        cur.execute("SELECT login FROM plat.usuario WHERE id = %s", (ctx.usuario_id,))
        r = cur.fetchone()
        login = r["login"] if r else None
    for nome, e in entradas.items():
        ctx.entrada(e["item_id"], e["sha256"], f"{nome}: {e['titulo']} (versão {e['versao']})")
    item_id = str(uuid.uuid4())
    tabela = "c_" + uuid.UUID(item_id).hex[:16]
    destino = {"schema": schema, "tabela": tabela, "item_id": item_id}
    ctx.log("INFO", f"ferramenta {f.nome} v{f.versao}: custo estimado {custo}; destino {schema}.{tabela}")
    ctx.progresso(5, "entradas resolvidas")
    iniciado_em = datetime.datetime.now(UTC)
    try:
        saida = f.funcao(ctx, entradas, parametros, destino)
        if saida.get("familia") == "raster":
            from app.ferramentas import saida_raster

            prov = proveniencia_bloco(ctx, f, parametros, entradas, custo, login, iniciado_em)
            return saida_raster.publicar(ctx, f, saida, destino, entradas, prov, titulo, custo, request)
        ctx.progresso(80, "preparando a camada")
        with ctx.db() as cur:
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, int(saida["srid"]), saida["geometria"], ctx.usuario_id))
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
            campos = [c["nome"] for c in saida["campos"]]
            sha_saida = sha256_camada(cur, schema, tabela, campos)
            cur.execute(
                f'SELECT count(*) AS feicoes, ST_AsGeoJSON(ST_Transform(ST_SetSRID(ST_Extent(geom)::geometry, '
                f'{int(saida["srid"])}), 4326)) AS extent FROM "{schema}"."{tabela}"'
            )
            est = cur.fetchone()
            cur.execute('SELECT pg_total_relation_size(%s::regclass) AS b', (f'"{schema}"."{tabela}"',))
            tamanho = int(cur.fetchone()["b"])
        ctx.progresso(90, "publicando no catálogo")
        extent = None
        if est["extent"]:
            coords = json.loads(est["extent"])["coordinates"][0]
            xs, ys = [c[0] for c in coords], [c[1] for c in coords]
            if -180 <= min(xs) and max(xs) <= 180 and -90 <= min(ys) and max(ys) <= 90:
                extent = [min(xs), min(ys), max(xs), max(ys)]
        proveniencia = proveniencia_bloco(ctx, f, parametros, entradas, custo, login, iniciado_em)
        dados = {
            "schema": schema, "tabela": tabela, "geometria": saida["geometria"], "srid": int(saida["srid"]),
            "campos": saida["campos"], "fonte": "hospedada",
            "procedencia": {"gerador": f"plat ferramenta {f.nome} v{f.versao}", "metodo": saida.get("metodo"),
                            "sha256": sha_saida, "job_id": proveniencia["job_id"], "ferramenta": proveniencia},
            "estatisticas": {"feicoes": int(est["feicoes"]), "extent_nativo": extent, "calculadas_em": None},
        }
        titulo_final = (titulo or f"{f.titulo}: " + ", ".join(e["titulo"] for e in entradas.values()))[:250] or f.titulo
        with ctx.db() as cur:
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, extent, "
                "extent_origem, criado_por, modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, "
                + ("ST_MakeEnvelope(%s,%s,%s,%s,4326)" if extent else "NULL") + ", %s, %s, %s)",
                [item_id, ctx.tenant_id, titulo_final, ctx.usuario_id, _jsonb(dados), tamanho]
                + (extent or []) + (["dado"] if extent else [None]) + [ctx.usuario_id, ctx.usuario_id],
            )
            for e in entradas.values():
                cur.execute(
                    "INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id) VALUES (%s::uuid, %s::uuid, "
                    "'derivado_de', %s) ON CONFLICT DO NOTHING", (item_id, e["item_id"], ctx.tenant_id),
                )
            cur.execute("UPDATE plat.tenant SET uso_bytes = uso_bytes + %s WHERE id = %s", (tamanho, ctx.tenant_id))
            props = {"ferramenta": f.nome, "versao": f.versao, "job_id": proveniencia["job_id"],
                     "entradas": [e["item_id"] for e in entradas.values()], "feicoes": int(est["feicoes"])}
            if request is not None:
                from app.auth.comum import registrar_evento

                registrar_evento(cur, request, "analises/executar", "item", item_id, props)
            else:
                cur.execute("SELECT plat.evento_registrar('analises/executar', 'item', %s, %s::jsonb, NULL, NULL)",
                            (item_id, json.dumps(props, default=str)))
    except (Cancelado, Exception):
        _apagar_tabela(ctx, schema, tabela)
        raise
    ctx.progresso(100, "concluído")
    return {"item_id": item_id, "titulo": titulo_final, "feicoes": int(est["feicoes"]), "sha256": sha_saida,
            "schema": schema, "tabela": tabela, "custo": custo, "entradas": ctx.entradas}


# ---------------------------------------------------------------- job
class ExecutarParametros(BaseModel):
    ferramenta: str = Field(..., max_length=40, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    parametros: dict = Field(default_factory=dict)
    titulo: str | None = Field(None, max_length=250)


@tarefa(nome="ferramentas.executar", descricao="Roda uma ferramenta de análise registrada e publica o resultado",
        parametros=ExecutarParametros, pesado=True, memoria_mb=limites.FERRAMENTA_JOB_MEMORIA_MB,
        timeout_s=limites.FERRAMENTA_JOB_TIMEOUT_S, tentativas=1, perfil_minimo="editor", versao=1)
def ferramentas_executar(ctx, ferramenta: str, parametros: dict | None = None, titulo: str | None = None) -> dict:
    f = registro.obter(ferramenta)
    if f is None:
        raise FalhaDefinitiva(f"ferramenta não registrada: {ferramenta!r}")
    try:
        normalizados = registro.validar_parametros(f, parametros or {})
        return executar(ctx, f, normalizados, titulo)
    except (registro.ErroParametro, ErroExecucao) as e:
        raise FalhaDefinitiva(str(e)) from e
