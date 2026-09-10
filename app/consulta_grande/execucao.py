"""Driver das ferramentas grandes: decide o motor, roda o SQL e devolve o que o executor do L2-05-a espera
(item L2-15-b-consultas-duckdb-em-escala).

Uma ferramenta grande escreve UM construtor de SQL e chama `rodar`. É aqui, e só aqui, que mora a decisão de
onde a conta acontece, a preparação dos arquivos e a carga do resultado — nenhuma ferramenta repete isso.

Regra da decisão, sem meio-termo:

* toda fonte é item Parquet -> DuckDB;
* toda fonte é camada do Postgres e nenhuma passa de `CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB` linhas -> PostGIS;
* qualquer camada do Postgres acima do limiar -> recusa nomeando `geoparquet.gerar`;
* mistura de Parquet com camada do Postgres na mesma execução -> recusa. Não se junta o que está em dois
  motores fingindo que é um só: o resultado teria de passar por uma cópia silenciosa de um lado para o outro,
  e é justamente essa cópia que o item existe para evitar.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app import limites
from app.consulta_grande import dialeto as dial
from app.consulta_grande import motor
from app.ferramentas.executor import ErroExecucao


class ErroFerramentaGrande(ErroExecucao):
    """Erro que o usuário corrige (campo inexistente, fonte grande demais, mistura de motores). Herda de
    `ErroExecucao` para virar 422 nomeado na API e FalhaDefinitiva no job, sem nenhuma tradução no meio."""

    def __init__(self, mensagem: str, codigo: str = "ferramenta_grande_invalida", status: int = 422):
        super().__init__(status, codigo, mensagem)


def _normalizar(nome: str, entrada: dict) -> dict:
    """Descrição comum das duas formas de fonte, para o construtor de SQL não precisar saber qual é."""
    if entrada.get("formato") == "parquet":
        return {
            "nome": nome, "formato": "parquet", "item_id": entrada["item_id"], "titulo": entrada["titulo"],
            "versao": entrada["versao"], "sha256": entrada["sha256"], "srid": int(entrada["crs"]),
            "campos": [c["nome"] for c in entrada.get("esquema") or []], "linhas": int(entrada["linhas"]),
            "arquivos": entrada["arquivos"], "bytes": int(entrada.get("bytes") or 0),
            "view": "v_" + nome,
        }
    return {
        "nome": nome, "formato": "postgis", "item_id": entrada["item_id"], "titulo": entrada["titulo"],
        "versao": entrada["versao"], "sha256": entrada["sha256"], "srid": int(entrada["srid"]),
        "campos": list(entrada["campos"]), "linhas": int(entrada["feicoes"]),
        "schema": entrada["schema"], "tabela": entrada["tabela"], "bytes": 0,
    }


def escolher_motor(fontes: dict) -> str:
    formatos = {f["formato"] for f in fontes.values()}
    if not formatos:
        raise ErroFerramentaGrande("a ferramenta não recebeu nenhuma fonte")
    if formatos == {"parquet"}:
        return "duckdb"
    if formatos == {"postgis"}:
        grandes = [f for f in fontes.values() if f["linhas"] > limites.CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB]
        if grandes:
            nomes = ", ".join(f"{f['nome']} ({f['linhas']} linhas)" for f in grandes)
            raise ErroFerramentaGrande(
                f"fonte acima do limiar de {limites.CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB} linhas: {nomes}. "
                "Publique a camada como GeoParquet (job geoparquet.gerar) e repita a ferramenta sobre o item "
                "Parquet: a partir daí a consulta roda no DuckDB, sem copiar o dado a cada execução")
        return "postgis"
    raise ErroFerramentaGrande(
        "a execução mistura fonte Parquet com camada do Postgres; publique todas as fontes no mesmo formato")


# ---------------------------------------------------------------- PostGIS
def _rodar_postgis(ctx, fontes: dict, parametros: dict, destino: dict, construtor, metodo: str) -> dict:
    sql, srid = construtor(dial.POSTGIS, fontes, parametros)
    alvo = f'"{destino["schema"]}"."{destino["tabela"]}"'
    ctx.progresso(20, "rodando a consulta no PostGIS")
    with ctx.db() as cur:
        cur.execute(f"CREATE TABLE {alvo} AS {sql}")
        cur.execute("SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                    (destino["schema"], destino["tabela"]))
        colunas = [(r["column_name"], r["data_type"]) for r in cur.fetchall()]
        tem_geom = any(c == "geom" for c, _ in colunas)
        if not tem_geom:
            cur.execute(f"ALTER TABLE {alvo} ADD COLUMN geom geometry(Geometry, {int(srid)})")
            geometria = "Geometry"
        else:
            cur.execute(f"SELECT DISTINCT ST_GeometryType(geom) AS t FROM {alvo} "
                        "WHERE geom IS NOT NULL LIMIT 8")
            tipos = {(r["t"] or "").replace("ST_", "") for r in cur.fetchall()}
            geometria = tipos.pop() if len(tipos) == 1 else "Geometry"
            cur.execute(f"ALTER TABLE {alvo} ALTER COLUMN geom TYPE geometry({geometria}, {int(srid)}) "
                        f"USING ST_SetSRID(geom, {int(srid)})")
        cur.execute(f"ALTER TABLE {alvo} ADD COLUMN fid bigserial PRIMARY KEY")
        campos = [{"nome": c, "tipo": t, "alias": c} for c, t in colunas if c != "geom"]
    return {"geometria": geometria, "srid": int(srid), "campos": campos, "metodo": f"{metodo} (PostGIS)",
            "sql": sql, "motor": "postgis"}


# ---------------------------------------------------------------- DuckDB
def _rodar_duckdb(ctx, fontes: dict, parametros: dict, destino: dict, construtor, metodo: str) -> dict:
    if len(fontes) > limites.CONSULTA_GRANDE_FONTES_MAX:
        raise ErroFerramentaGrande(f"no máximo {limites.CONSULTA_GRANDE_FONTES_MAX} fontes por execução")
    sql, srid = construtor(dial.DUCKDB, fontes, parametros)
    base, temporario = _diretorio(ctx)
    try:
        views: dict[str, list[str]] = {}
        for f in fontes.values():
            ctx.progresso(10, f"trazendo {len(f['arquivos'])} arquivo(s) de {f['titulo']}")
            views[f["view"]] = motor.preparar_dados(f, base / "dados" / f["nome"])
        ctx.progresso(35, "rodando a consulta no DuckDB")
        manifesto = motor.executar_sql(ctx, sql=sql, views=views, dir_trabalho=base / "saida")
        ctx.log("INFO", f"consulta grande: {manifesto['linhas']} linha(s) em {manifesto['ms']} ms "
                        f"(memory_limit {manifesto['memoria_mb']} MB, threads {manifesto['threads']})")
        ctx.progresso(65, "carregando o resultado como camada")
        with ctx.db() as cur:
            saida = motor.carregar_no_destino(cur, destino, manifesto, manifesto["saida_csv"], srid)
        saida["metodo"] = f"{metodo} (DuckDB spatial)"
        saida["motor"] = "duckdb"
        saida["sql"] = sql
        saida["consulta_grande"] = motor.proveniencia(sql, list(fontes.values()), manifesto)
        return saida
    finally:
        if temporario:
            shutil.rmtree(base, ignore_errors=True)


def _diretorio(ctx) -> tuple[Path, bool]:
    """Diretório de trabalho do job quando existe; senão um temporário só desta execução (o caminho síncrono
    do GPServer não tem diretório de job). O segundo valor diz se cabe a nós apagar."""
    proprio = getattr(ctx, "dir_trabalho", None)
    if proprio:
        alvo = Path(proprio) / "consulta_grande"
        alvo.mkdir(parents=True, exist_ok=True)
        return alvo, False
    return Path(tempfile.mkdtemp(prefix="plat-consulta-")), True


# ---------------------------------------------------------------- porta única
def rodar(ctx, entradas: dict, parametros: dict, destino: dict, construtor, metodo: str) -> dict:
    fontes = {nome: _normalizar(nome, e) for nome, e in entradas.items()}
    escolhido = escolher_motor(fontes)
    ctx.log("INFO", f"consulta grande no motor {escolhido}: "
                    + ", ".join(f"{f['nome']}={f['linhas']} linhas ({f['formato']})" for f in fontes.values()))
    try:
        if escolhido == "duckdb":
            saida = _rodar_duckdb(ctx, fontes, parametros, destino, construtor, metodo)
        else:
            saida = _rodar_postgis(ctx, fontes, parametros, destino, construtor, metodo)
    except motor.ErroConsulta as e:
        raise ErroFerramentaGrande(str(e), e.motivo, 504 if e.tempo else 422) from e
    saida.setdefault("consulta_grande", {"motor": escolhido, "sql": saida["sql"],
                                         "fontes": [{"item_id": f["item_id"], "versao": f["versao"],
                                                     "sha256": f["sha256"], "arquivos": []}
                                                    for f in fontes.values()]})
    return saida


# ---------------------------------------------------------------- SQL livre do usuário
def rodar_sql_livre(ctx, entradas: dict, sql: str, destino: dict, tempo_s: int | None = None) -> dict:
    """Mesmo caminho das ferramentas grandes, só que o SQL vem do usuário. Cada fonte vira uma view com o
    NOME DO PARÂMETRO (`fonte_a`… `fonte_d`): o usuário nunca escreve caminho de arquivo, e o portão de
    `app.consulta_grande.seguranca` recusa qualquer tentativa de escrever um.

    Só fonte Parquet: SQL livre sobre tabela do Postgres seria outra coisa (outro motor, outra superfície de
    ataque, outra conversa sobre RLS) e não é o que este item entrega."""
    fontes = {nome: _normalizar(nome, e) for nome, e in entradas.items()}
    if not fontes:
        raise ErroFerramentaGrande("informe ao menos uma fonte Parquet em fonte_a")
    de_fora = [f["nome"] for f in fontes.values() if f["formato"] != "parquet"]
    if de_fora:
        raise ErroFerramentaGrande(
            "o SQL livre só lê fonte Parquet do catálogo; estas não são: " + ", ".join(de_fora)
            + ". Publique a camada com o job geoparquet.gerar e repita")
    for f in fontes.values():
        f["view"] = f["nome"]
    srid = int(next(iter(fontes.values()))["srid"])
    base, temporario = _diretorio(ctx)
    try:
        views: dict[str, list[str]] = {}
        for f in fontes.values():
            ctx.progresso(10, f"trazendo {len(f['arquivos'])} arquivo(s) de {f['titulo']}")
            views[f["view"]] = motor.preparar_dados(f, base / "dados" / f["nome"])
        ctx.progresso(35, "rodando o SQL no DuckDB")
        try:
            manifesto = motor.executar_sql(ctx, sql=sql, views=views, dir_trabalho=base / "saida",
                                           tempo_s=tempo_s)
        except motor.ErroConsulta as e:
            raise ErroFerramentaGrande(str(e), e.motivo, 504 if e.tempo else 422) from e
        ctx.log("INFO", f"SQL livre: {manifesto['linhas']} linha(s) em {manifesto['ms']} ms")
        ctx.progresso(65, "carregando o resultado como camada")
        with ctx.db() as cur:
            saida = motor.carregar_no_destino(cur, destino, manifesto, manifesto["saida_csv"], srid)
        saida["metodo"] = "SQL do usuário sobre as views Parquet do inquilino (DuckDB spatial)"
        saida["motor"] = "duckdb"
        saida["sql"] = sql
        saida["consulta_grande"] = motor.proveniencia(sql, list(fontes.values()), manifesto)
        return saida
    finally:
        if temporario:
            shutil.rmtree(base, ignore_errors=True)
