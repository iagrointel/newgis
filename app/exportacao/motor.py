"""Motor da exportação (item L0-04-h-exportar; ADR 0018): monta a consulta, chama o `ogr2ogr` como neto do
job, converte o que o GDAL não faz (KMZ, GeoParquet, CSV brasileiro) e devolve o caminho do arquivo pronto.

Três decisões de segurança que este módulo carrega:

1. **A RLS do PostgreSQL vale DENTRO do ogr2ogr.** O `ogr2ogr` abre uma conexão própria, fora do pool da
   aplicação, então `set_config('plat.tenant_id', ...)` do `app/db.py` não o alcança. Em vez de confiar num
   `WHERE tenant_id = ...` escrito por nós (que um erro de programação apagaria em silêncio), o inquilino é
   posto na PRÓPRIA string de conexão (`options='-c plat.tenant_id=N'`), e a política de RLS da tabela de
   camada faz o resto. MEDIDO em 06/09/2026 nesta máquina, tabela com 50 mil linhas de cada um de dois
   inquilinos: sem a opção, o ogr2ogr exporta **0 feição**; com `-c plat.tenant_id=1`, exatamente as 50 mil
   do inquilino 1. É o banco, não o nosso código, que impede a exportação de trazer linha de outro.
2. **Nada do cliente entra no texto do SQL.** O filtro passa por `app.consulta.where_ast` (lista branca de
   colunas, todo literal vira parâmetro) e só então por `cursor.mogrify`, que é quem escreve o literal com o
   escape do próprio libpq. O `-sql` do ogr2ogr precisa de um comando já pronto (não aceita parâmetro), e
   `mogrify` é o único jeito de produzir esse texto sem concatenar string de usuário.
3. **Nome de coluna e de tabela nunca vêm do corpo do pedido**: saem do item de catálogo (`dados.campos`,
   `dados.schema`, `dados.tabela`), lido sob RLS no contexto do inquilino do job.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import psycopg2.extensions

from app import limites
from app.consulta import where_ast
from app.consulta.cql2 import compilar_cql2
from app.exportacao.formatos import Formato
from app.settings import settings

RAIZ = Path(__file__).resolve().parents[2]  # raiz do repositório (onde o pacote `app` mora)


class ErroExportacao(Exception):
    """Falha que o usuário pode corrigir (formato/CRS/filtro/disco); a tarefa a converte em FalhaDefinitiva."""


def conninfo_pg(tenant_id: int, usuario_id: int | None = None) -> str:
    """`PG:...` para o ogr2ogr, JÁ no contexto do inquilino (ver decisão 1 no topo do módulo)."""
    partes = psycopg2.extensions.parse_dsn(settings.PLAT_DSN)
    pares = " ".join(f"{k}={v}" for k, v in partes.items() if k in ("dbname", "host", "port", "user", "password"))
    gucs = f"-c plat.tenant_id={int(tenant_id)}"
    if usuario_id:
        gucs += f" -c plat.usuario_id={int(usuario_id)}"
    return f"PG:{pares} options='{gucs}' application_name=plat-exportacao"


def colunas_permitidas(campos: list[dict]) -> dict[str, str]:
    """Lista branca do `where`: nome do campo → identificador SQL entre aspas. Só o que está no item."""
    saida = {}
    for c in campos or []:
        nome = c.get("nome")
        if nome and where_ast.IDENT_RE.match(nome):
            saida[nome] = f'"{nome}"'
    return saida


def montar_select(
    cur,
    *,
    schema: str,
    tabela: str,
    campos: list[str],
    coluna_geom: str,
    where: str | None,
    bbox: list[float] | None,
    srid_tabela: int,
    colunas_brancas: dict[str, str],
    com_geometria: bool = True,
    ids: list | None = None,
    filtro_cql2: dict | None = None,
    colunas_cql2: dict | None = None,
) -> str:
    """Comando SQL COMPLETO (sem parâmetro) para o `-sql` do ogr2ogr. Levanta `where_ast.ErroWhere` para
    filtro malformado e `psycopg2.Error` para o que só o banco recusa (tipo incompatível, função inexistente)
    — quem chama decide o código HTTP."""
    selecionadas = [f'"{c}"' for c in campos]
    if com_geometria and coluna_geom:
        selecionadas.append(f'"{coluna_geom}"')
    condicoes: list[str] = []
    params: list = []
    if ids is not None:
        # exportação DA SELEÇÃO do mapa (item L2-01-l): a lista de fid entra como UM parâmetro (array), não
        # como N literais concatenados — 200 mil fids num `IN (...)` viram megabytes de texto de SQL, e o
        # `= ANY(%s)` usa o índice da chave primária do mesmo jeito.
        condicoes.append('"fid" = ANY(%s)')
        params.append([int(v) for v in ids])
    if filtro_cql2 is not None:
        consulta_cql2 = compilar_cql2(filtro_cql2, colunas_cql2 or {})
        condicoes.append(f"({consulta_cql2.sql})")
        params.extend(consulta_cql2.params)
    if where:
        consulta = where_ast.compilar_where(where, colunas_brancas)
        condicoes.append(f"({consulta.sql})")
        params.extend(consulta.params)
    if bbox:
        condicoes.append(
            f'"{coluna_geom}" && ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), {int(srid_tabela)})'
        )
        params.extend([float(x) for x in bbox])
    sql = f'SELECT {", ".join(selecionadas)} FROM "{schema}"."{tabela}"'
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    return cur.mogrify(sql, params).decode("utf-8")


def conferir_where(cur, sql_completo: str) -> None:
    """Roda o comando com `LIMIT 0`: o banco valida tipo, função e coluna sem ler uma linha. Deixa subir
    `psycopg2.Error` para a rota devolver 400 com o erro saneado."""
    cur.execute(f"SELECT 1 FROM ({sql_completo}) AS conferencia LIMIT 0")


def espaco_livre(caminho: Path) -> int:
    return shutil.disk_usage(caminho).free


def exigir_disco(caminho: Path, estimativa_bytes: int) -> None:
    livre = espaco_livre(caminho)
    preciso = int(estimativa_bytes) + limites.EXPORTACAO_DISCO_MIN_LIVRE_BYTES
    if livre < preciso:
        raise ErroExportacao(
            f"disco insuficiente para a exportação: {livre // (1024 * 1024)} MB livres, "
            f"necessários {preciso // (1024 * 1024)} MB (estimativa do arquivo mais a folga mínima)"
        )


def argumentos_ogr2ogr(
    formato: Formato,
    *,
    destino: Path,
    conninfo: str,
    sql: str,
    nome_camada: str,
    srid_saida: int | None,
    codificacao: str,
) -> list[str]:
    argv = ["ogr2ogr", "-f", formato.driver, str(destino), conninfo, "-sql", sql, "-nln", nome_camada]
    alvo_crs = crs_de_saida(formato, srid_saida)
    if alvo_crs:
        argv += ["-t_srs", f"EPSG:{int(alvo_crs)}"]
    for opcao in formato.lco:
        argv += ["-lco", opcao]
    for opcao in formato.dsco:
        argv += ["-dsco", opcao]
    if formato.nome == "shapefile":
        argv += ["-lco", f"ENCODING={codificacao}"]
    if formato.nome == "csv":
        argv += ["-lco", "GEOMETRY=AS_XY", "-lco", "STRING_QUOTING=IF_AMBIGUOUS"]
    return argv


def crs_de_saida(formato: Formato, srid_pedido: int | None) -> int | None:
    """EPSG que o ogr2ogr vai receber, já obedecendo a política do formato (bloco CRS de `formatos.py`).

    Formato de CRS preso devolve o CRS preso mesmo quando ninguém pediu nada: sem isso, uma camada em
    SIRGAS 2000 / UTM sairia com coordenada projetada dentro de um GeoJSON que se declara WGS 84. Quem
    pede um CRS INCOMPATÍVEL com o formato é recusado na entrada da rota (422), não aqui."""
    if formato.crs_saida == "4326":
        return 4326
    if formato.crs_saida == "3857":
        return 3857
    if formato.crs_saida == "nenhum":
        return int(srid_pedido) if srid_pedido else None
    return int(srid_pedido) if srid_pedido else None


def zipar_diretorio(origem: Path, destino_zip: Path, nome_interno: str = "") -> None:
    """Zip de todos os arquivos que o driver escreveu (shapefile: .shp/.shx/.dbf/.prj/.cpg). `write` lê do
    disco em blocos — nenhum arquivo é montado inteiro em memória."""
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in sorted(origem.rglob("*")):
            if arquivo.is_file():
                relativo = arquivo.relative_to(origem)
                z.write(arquivo, str(Path(nome_interno) / relativo) if nome_interno else str(relativo))


def zipar_arquivo(origem: Path, destino_zip: Path, nome_interno: str) -> None:
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(origem, nome_interno)


def _argv_parquet(*args: str) -> list[str]:
    return [sys.executable, "-m", "app.exportacao.parquet_cli", *args]


def _rodar_parquet(argv: list[str], executar=None) -> int:
    """Roda `app.exportacao.parquet_cli` (processo próprio; ver o docstring daquele módulo) e devolve a
    contagem de linhas que ele imprimiu. `executar` é `ctx.subprocesso` dentro do job (o neto morre com o
    cancelamento e o stdout/stderr vai para o log); fora do job, `subprocess.run`.

    `cwd=RAIZ` é obrigatório: `ctx.subprocesso` roda o neto no DIRETÓRIO DE TRABALHO DO JOB, e de lá o
    `python -m app.exportacao.parquet_cli` não acha o pacote `app` ("No module named 'app'"; medido nesta
    trilha em 06/09/2026, com o job falhando em 0,5 s)."""
    rodar = executar or (lambda a, **kw: subprocess.run(a, capture_output=True, text=True, timeout=1800, **kw))
    r = rodar(argv, cwd=str(RAIZ))
    if r.returncode != 0:
        detalhe = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        raise ErroExportacao(f"GeoParquet: {(detalhe[-1] if detalhe else 'sem detalhe')[:300]}")
    for linha in reversed((r.stdout or "").splitlines()):
        if linha.strip().startswith("{"):
            return int(json.loads(linha)["linhas"])
    raise ErroExportacao("GeoParquet: o conversor não devolveu a contagem de linhas")


def gpkg_para_geoparquet(origem_gpkg: Path, destino: Path, memoria_mb: int, executar=None) -> int:
    """GeoParquet a partir do GPKG intermediário. Devolve o número de linhas escritas."""
    return _rodar_parquet(
        _argv_parquet("converter", str(origem_gpkg), str(destino), str(int(memoria_mb))), executar
    )


def contar_feicoes(caminho: Path, formato: Formato, executar=None) -> int | None:
    """Contagem lida do ARQUIVO GERADO (não do banco): é o que prova que o arquivo saiu com o que se pediu.
    `None` quando a leitura não foi possível — nunca 0 por omissão."""
    if formato.nome == "geoparquet":
        return _rodar_parquet(_argv_parquet("contar", str(caminho)), executar)
    alvo = str(caminho)
    if formato.nome == "shapefile":
        alvo = f"/vsizip/{caminho}"
    elif formato.nome == "kmz":
        alvo = f"/vsizip/{caminho}/doc.kml"
    elif formato.caminho_interno:
        alvo = f"/vsizip/{caminho}/{formato.caminho_interno}"
    r = subprocess.run(["ogrinfo", "-so", "-al", alvo], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return None
    total = 0
    achou = False
    for linha in r.stdout.splitlines():
        if linha.strip().startswith("Feature Count:"):
            total += int(linha.split(":", 1)[1].strip())
            achou = True
    return total if achou else None


def tamanho(caminho: Path) -> int:
    if caminho.is_dir():
        return sum(a.stat().st_size for a in caminho.rglob("*") if a.is_file())
    return caminho.stat().st_size


def cronometrar(funcao, *args, **kwargs):
    inicio = time.monotonic()
    resultado = funcao(*args, **kwargs)
    return resultado, int((time.monotonic() - inicio) * 1000)


def nome_arquivo_seguro(nome: str, extensao: str) -> str:
    """Nome que o usuário vê ao baixar: só letra, dígito, `-`, `_` e `.`; nunca caminho, nunca vazio."""
    base = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (nome or "").strip())
    base = base.strip("._") or "exportacao"
    return base[: limites.EXPORTACAO_NOME_MAX] + extensao


def limpar(caminho: Path) -> None:
    try:
        if caminho.is_dir():
            shutil.rmtree(caminho, ignore_errors=True)
        elif caminho.exists():
            os.remove(caminho)
    except OSError:
        pass
