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
import uuid

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


def resolver_entradas(cur, f: registro.Ferramenta, parametros: dict) -> dict:
    """{nome do parâmetro: camada resolvida}. Parâmetro GPMultiValue de camadas (ferramenta `mesclar`) devolve
    LISTA de camadas resolvidas — `entradas_planas` é quem achata isso para proveniência e derivado_de."""
    entradas = {}
    for p in f.entradas:
        if not parametros.get(p.nome):
            continue
        if p.tipo == "GPFeatureRecordSetLayer":
            entradas[p.nome] = resolver_camada(cur, parametros[p.nome], p.nome)
        elif p.tipo == "GPMultiValue" and p.subtipo == "GPFeatureRecordSetLayer":
            entradas[p.nome] = [resolver_camada(cur, v, f"{p.nome}[{i}]")
                                for i, v in enumerate(parametros[p.nome])]
        elif p.tipo == "GPRasterDataLayer":
            raise ErroExecucao(422, "raster_nao_suportado", f"{p.nome}: entrada raster depende do item L1-01")
    return entradas


def entradas_planas(entradas: dict) -> list[tuple[str, dict]]:
    """(rótulo, camada) de cada camada de entrada, com o índice no rótulo quando o parâmetro é lista."""
    planas = []
    for nome, valor in entradas.items():
        if isinstance(valor, list):
            planas.extend((f"{nome}[{i}]", e) for i, e in enumerate(valor))
        else:
            planas.append((nome, valor))
    return planas


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


def executar(ctx, f: registro.Ferramenta, parametros: dict, titulo: str | None = None, autor: dict | None = None,
             request=None) -> dict:
    """Roda a ferramenta e publica o item de resultado. `parametros` já normalizados por `validar_parametros`.
    Devolve {"item_id", "titulo", "feicoes", "sha256", "tabela", "custo"}."""
    with ctx.db() as cur:
        entradas = resolver_entradas(cur, f, parametros)
        custo = custo_estimado(f, entradas, parametros)
        schema = _schema_do_inquilino(cur, ctx.tenant_id)
        cur.execute("SELECT login FROM plat.usuario WHERE id = %s", (ctx.usuario_id,))
        r = cur.fetchone()
        login = r["login"] if r else None
    planas = entradas_planas(entradas)
    for nome, e in planas:
        ctx.entrada(e["item_id"], e["sha256"], f"{nome}: {e['titulo']} (versão {e['versao']})")
    item_id = str(uuid.uuid4())
    tabela = "c_" + uuid.UUID(item_id).hex[:16]
    destino = {"schema": schema, "tabela": tabela, "item_id": item_id}
    ctx.log("INFO", f"ferramenta {f.nome} v{f.versao}: custo estimado {custo}; destino {schema}.{tabela}")
    ctx.progresso(5, "entradas resolvidas")
    iniciado_em = datetime.datetime.now(UTC)
    try:
        saida = f.funcao(ctx, entradas, parametros, destino)
        ctx.progresso(80, "preparando a camada")
        with ctx.db() as cur:
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, int(saida["srid"]), saida["geometria"], ctx.usuario_id))
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
            campos = [c["nome"] for c in saida["campos"]]
            sha_saida = sha256_camada(cur, schema, tabela, campos)
            cur.execute(
                f'SELECT (SELECT count(*) FROM "{schema}"."{tabela}") AS feicoes, ST_XMin(e) AS x0, '
                f'ST_YMin(e) AS y0, ST_XMax(e) AS x1, ST_YMax(e) AS y1 FROM (SELECT ST_Transform('
                f'ST_SetSRID(ST_Extent(geom)::geometry, {int(saida["srid"])}), 4326) AS e '
                f'FROM "{schema}"."{tabela}") t'
            )
            est = cur.fetchone()
            cur.execute('SELECT pg_total_relation_size(%s::regclass) AS b', (f'"{schema}"."{tabela}"',))
            tamanho = int(cur.fetchone()["b"])
        ctx.progresso(90, "publicando no catálogo")
        extent = None
        # os quatro cantos vêm em número, não em GeoJSON: camada de uma feição só devolve um ponto como
        # extensão, e a leitura do anel do polígono quebrava nesse caso (achado no item L2-05-d)
        if est["x0"] is not None:
            xs, ys = [float(est["x0"]), float(est["x1"])], [float(est["y0"]), float(est["y1"])]
            if -180 <= min(xs) and max(xs) <= 180 and -90 <= min(ys) and max(ys) <= 90:
                # saída de UMA feição pontual tem extensão degenerada, e ST_MakeEnvelope com os quatro cantos
                # iguais devolve polígono inválido (o CHECK item_extent_check recusa): abre-se 1e-9 grau
                # (cerca de 0,1 mm) para o retângulo existir
                folga = 1e-9
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
                if x1 - x0 < folga:
                    x0, x1 = x0 - folga, x1 + folga
                if y1 - y0 < folga:
                    y0, y1 = y0 - folga, y1 + folga
                extent = [x0, y0, x1, y1]
        proveniencia = {
            "ferramenta": f.nome, "versao": f.versao, "parametros": parametros,
            "entradas": [{"parametro": n, "item_id": e["item_id"], "versao": e["versao"], "sha256": e["sha256"]}
                         for n, e in planas],
            "executada_em": iniciado_em.isoformat(timespec="seconds"),
            "autor": {"usuario_id": ctx.usuario_id, "login": login},
            "job_id": str(ctx.job_id) if ctx.job_id else None, "custo_estimado": custo,
        }
        dados = {
            "schema": schema, "tabela": tabela, "geometria": saida["geometria"], "srid": int(saida["srid"]),
            "campos": saida["campos"], "fonte": "hospedada",
            "procedencia": {"gerador": f"plat ferramenta {f.nome} v{f.versao}", "metodo": saida.get("metodo"),
                            "sha256": sha_saida, "job_id": proveniencia["job_id"], "ferramenta": proveniencia},
            "estatisticas": {"feicoes": int(est["feicoes"]), "extent_nativo": extent, "calculadas_em": None},
        }
        titulo_final = (titulo or f"{f.titulo}: " + ", ".join(e["titulo"] for _, e in planas))[:250] or f.titulo
        with ctx.db() as cur:
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, extent, "
                "extent_origem, criado_por, modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, "
                + ("ST_MakeEnvelope(%s,%s,%s,%s,4326)" if extent else "NULL") + ", %s, %s, %s)",
                [item_id, ctx.tenant_id, titulo_final, ctx.usuario_id, _jsonb(dados), tamanho]
                + (extent or []) + (["dado"] if extent else [None]) + [ctx.usuario_id, ctx.usuario_id],
            )
            for _, e in planas:
                cur.execute(
                    "INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id) VALUES (%s::uuid, %s::uuid, "
                    "'derivado_de', %s) ON CONFLICT DO NOTHING", (item_id, e["item_id"], ctx.tenant_id),
                )
            cur.execute("UPDATE plat.tenant SET uso_bytes = uso_bytes + %s WHERE id = %s", (tamanho, ctx.tenant_id))
            props = {"ferramenta": f.nome, "versao": f.versao, "job_id": proveniencia["job_id"],
                     "entradas": [e["item_id"] for _, e in planas], "feicoes": int(est["feicoes"])}
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
