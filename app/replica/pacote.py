"""Monta o GeoPackage da réplica (item L2-13-b) com `ogr2ogr`, direto do PostGIS.

⚠ RLS: a tabela física de camada (`d_<slug>.c_<uuid16>`) tem FORCE ROW LEVEL SECURITY por `tenant_id =
plat.tenant_atual()`, e `tenant_atual()` lê o GUC de SESSÃO `plat.tenant_id`. O `ogr2ogr` abre uma conexão
PRÓPRIA, que não herda o contexto da conexão da aplicação — sem o GUC ele leria ZERO linha EM SILÊNCIO
(nenhum erro, um pacote vazio). O contexto viaja pela variável de ambiente `PGOPTIONS` do subprocesso, que a
libpq manda ao servidor no arranque da conexão (medido nesta base antes de escrever este módulo). Depois de
gerar, `_conferir_contagem` compara a contagem lida pelo ogr com a contagem lida pela conexão da aplicação:
se o GUC não tiver chegado, o pacote sai vazio e a divergência levanta erro em vez de entregar dado faltando.

Senha: NUNCA na linha de comando (`ps` é legível por qualquer usuário da máquina). Vai por `PGPASSWORD` no
ambiente do subprocesso, junto do `PGOPTIONS`.

O que o pacote leva, além das camadas:
  * `plat_sync`  — uma linha por feição (camada_id, nome_gpkg, fid, globalid, versao): é o que o cliente
    compara para saber o que ELE mudou e qual versão leu;
  * `plat_replica` — uma linha por camada (geração do servidor, filtro, política de conflito, validade);
  * `plat_dominio` — valores de domínio de `dados.regras_campo` de cada camada (tabela de domínio, para o
    cliente montar lista fechada sem inventar valor fora do domínio);
  * `plat_anexo` — metadado dos anexos da feição (item L2-03-edicao) quando a réplica foi pedida com anexos.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app import limites
from app.erros import ErroAPI
from app.settings import settings

OGR2OGR = shutil.which("ogr2ogr") or "/usr/bin/ogr2ogr"
TEMPO_MAX_S = 900
# colunas de rastreio que VÃO para o pacote (o cliente precisa de globalid e versao para sincronizar; fid é a
# chave local do GeoPackage). `tenant_id` fica de fora de propósito: é dado de isolamento do servidor, não do campo.
RASTREIO = ("globalid", "versao", "criado_em", "atualizado_em")


def _dsn_ogr() -> str:
    """Conninfo para o driver PG do GDAL, SEM a senha (vai por PGPASSWORD)."""
    from urllib.parse import unquote, urlparse

    u = urlparse(settings.PLAT_DSN)
    partes = [f"dbname={unquote(u.path.lstrip('/'))}"]
    if u.hostname:
        partes.append(f"host={u.hostname}")
    if u.port:
        partes.append(f"port={u.port}")
    if u.username:
        partes.append(f"user={unquote(u.username)}")
    return "PG:" + " ".join(partes)


def _ambiente(tenant_id: int, usuario_id: int | None) -> dict[str, str]:
    from urllib.parse import unquote, urlparse

    u = urlparse(settings.PLAT_DSN)
    ambiente = dict(os.environ)
    opcoes = [f"-c plat.tenant_id={int(tenant_id)}"]
    if usuario_id:
        opcoes.append(f"-c plat.usuario_id={int(usuario_id)}")
    ambiente["PGOPTIONS"] = " ".join(opcoes)
    if u.password:
        ambiente["PGPASSWORD"] = unquote(u.password)
    ambiente["OGR_ORGANIZE_POLYGONS"] = "SKIP"  # geometria já validada na ingestão/edição; não reorganizar
    return ambiente


def _rodar(argumentos: list[str], ambiente: dict[str, str]) -> None:
    r = subprocess.run(
        argumentos, env=ambiente, capture_output=True, text=True, timeout=TEMPO_MAX_S, check=False
    )
    if r.returncode != 0:
        # a saída do ogr pode conter a conninfo (sem senha, ver _dsn_ogr); corta para não inchar o erro
        raise ErroAPI(
            500, "pacote_falhou", "ogr2ogr não conseguiu escrever o pacote da réplica",
            {"codigo": r.returncode, "saida": (r.stderr or r.stdout or "").strip()[:500]},
        )


def sql_da_camada(cur, dados: dict, filtro: str | None, extensao_geojson: str | None) -> str:
    """SELECT literal (já com os valores citados pelo psycopg2) que o ogr2ogr executa no servidor.

    O `filtro` do cliente NUNCA é concatenado: passa pelo analisador AST do FeatureServer
    (app/consulta/where_ast.py), que só aceita campo da lista branca desta camada e devolve SQL com
    parâmetro; `cur.mogrify` transforma parâmetro em literal citado pelo próprio psycopg2. O ogr2ogr
    recebe texto, não tem como receber parâmetro — mogrify é o único jeito seguro de chegar lá.
    """
    from app.consulta.where_ast import ErroWhere, compilar_where

    schema, tabela = dados["schema"], dados["tabela"]
    campos = [c["nome"] for c in dados.get("campos") or []]
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    colunas = ["fid", *RASTREIO, *[c for c in campos if c not in RASTREIO and c != "fid"]]
    lista = ", ".join(f'"{c}"' for c in colunas)
    if tem_geom:
        lista += ", geom"

    condicoes: list[str] = []
    if filtro:
        try:
            compilado = compilar_where(filtro, {c: f'"{c}"' for c in campos})
        except ErroWhere as e:
            raise ErroAPI(422, "filtro_invalido", f"filtro da camada não pôde ser analisado: {e}") from e
        condicoes.append(cur.mogrify(compilado.sql, compilado.params).decode("utf-8"))
    if extensao_geojson and tem_geom:
        srid = int(dados["srid"])
        condicoes.append(
            cur.mogrify(
                "ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s))",
                (extensao_geojson, srid),
            ).decode("utf-8")
        )
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return f'SELECT {lista} FROM "{schema}"."{tabela}"{onde}'


def _csv_para_gpkg(destino: Path, nome: str, cabecalho: list[str], linhas: list[list[Any]], ambiente) -> None:
    """Tabela de atributos (sem geometria) dentro do GeoPackage. Passa por CSV porque é o ogr que registra a
    tabela em `gpkg_contents` — escrever direto por sqlite3 deixaria a tabela invisível ao GDAL e ao QField."""
    if not linhas:
        return
    with tempfile.TemporaryDirectory(prefix="plat-replica-") as tmp:
        caminho = Path(tmp) / f"{nome}.csv"
        with caminho.open("w", encoding="utf-8", newline="") as f:
            escritor = csv.writer(f)
            escritor.writerow(cabecalho)
            escritor.writerows(linhas)
        _rodar(
            # `-lco FID=linha_id`: sem isto o driver GPKG adota a coluna `fid` do CSV como chave primária da
            # tabela, e duas camadas na mesma réplica repetem os seus fid (cada camada numera do 1) — a
            # segunda camada estoura por chave duplicada. `fid` aqui é DADO (o fid da feição naquela camada),
            # não a chave da tabela de sincronização.
            [OGR2OGR, "-f", "GPKG", str(destino), str(caminho), "-nln", nome, "-update",
             "-lco", "FID=linha_id",
             "-oo", "AUTODETECT_TYPE=YES", "-oo", "EMPTY_STRING_AS_NULL=YES"],
            ambiente,
        )


def contar(cur, dados: dict, filtro: str | None, extensao_geojson: str | None) -> int:
    """Contagem pela conexão da APLICAÇÃO (com contexto de inquilino), para conferir a do ogr."""
    sql = sql_da_camada(cur, dados, filtro, extensao_geojson)
    cur.execute(f"SELECT count(*) AS n FROM ({sql}) t")
    return int(cur.fetchone()["n"])


def contar_no_gpkg(caminho: Path, nome: str) -> int:
    """Contagem lida do arquivo pronto, pelo próprio GDAL (é a prova de que o pacote abre)."""
    r = subprocess.run(
        [shutil.which("ogrinfo") or "/usr/bin/ogrinfo", "-ro", "-so", "-json", str(caminho), nome],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if r.returncode != 0:
        raise ErroAPI(500, "pacote_ilegivel", "o GeoPackage gerado não abre no GDAL",
                      {"camada": nome, "saida": (r.stderr or "").strip()[:300]})
    return int(json.loads(r.stdout)["layers"][0]["featureCount"])


def escrever(cur, replica: dict, camadas: list[dict], destino: Path) -> dict:
    """Escreve o GeoPackage de `replica` em `destino`. `camadas` é a lista de dicionários montada por
    app/replica/servico.py::_camadas_da_replica (item, dados do catálogo, filtro, nome_gpkg, geração)."""
    ambiente = _ambiente(replica["tenant_id"], replica.get("dono_id"))
    fonte = _dsn_ogr()
    extensao = replica.get("extensao_geojson")
    sync: list[list[Any]] = []
    meta: list[list[Any]] = []
    dominios: list[list[Any]] = []
    contagens: dict[str, int] = {}

    for indice, camada in enumerate(camadas):
        dados = camada["dados"]
        esperado = contar(cur, dados, camada["filtro"], extensao)
        if esperado > limites.REPLICA_FEICOES_MAX:
            raise ErroAPI(
                413, "replica_grande",
                f"a camada {camada['nome_gpkg']} tem {esperado} feições no recorte, acima do teto de "
                f"{limites.REPLICA_FEICOES_MAX}; reduza o filtro ou a extensão",
                {"camada_id": camada["camada_id"], "feicoes": esperado, "teto": limites.REPLICA_FEICOES_MAX},
            )
        argumentos = [
            OGR2OGR, "-f", "GPKG", str(destino), fonte,
            "-sql", sql_da_camada(cur, dados, camada["filtro"], extensao),
            "-nln", camada["nome_gpkg"], "-lco", "FID=fid", "-lco", "SPATIAL_INDEX=YES",
        ]
        if indice or destino.exists():
            argumentos.append("-update")
        _rodar(argumentos, ambiente)
        obtido = contar_no_gpkg(destino, camada["nome_gpkg"])
        if obtido != esperado:
            raise ErroAPI(
                500, "pacote_incompleto",
                f"o pacote saiu com {obtido} feições e o servidor conta {esperado} na camada "
                f"{camada['nome_gpkg']} (contexto de inquilino não chegou ao ogr2ogr?)",
                {"camada_id": camada["camada_id"], "no_pacote": obtido, "no_servidor": esperado},
            )
        contagens[camada["camada_id"]] = obtido

        cur.execute(
            f'SELECT fid, globalid, versao FROM "{dados["schema"]}"."{dados["tabela"]}" '
            f"WHERE globalid IN (SELECT globalid FROM ({sql_da_camada(cur, dados, camada['filtro'], extensao)}) t)"
        )
        for linha in cur.fetchall():
            sync.append([camada["camada_id"], camada["nome_gpkg"], linha["fid"], str(linha["globalid"]),
                         linha["versao"]])
        meta.append([
            str(replica["id"]), camada["camada_id"], camada["nome_gpkg"], camada["geracao_servidor"],
            camada["filtro"] or "", replica["politica_conflito"], obtido,
            replica["expira_em"].isoformat() if replica.get("expira_em") else "",
        ])
        for campo, regra in (dados.get("regras_campo") or {}).items():
            for valor in (regra or {}).get("dominio_valores") or []:
                dominios.append([camada["camada_id"], camada["nome_gpkg"], campo, str(valor)])

    _csv_para_gpkg(destino, "plat_sync",
                   ["camada_id", "nome_gpkg", "fid", "globalid", "versao"], sync, ambiente)
    _csv_para_gpkg(destino, "plat_replica",
                   ["replica_id", "camada_id", "nome_gpkg", "geracao_servidor", "filtro", "politica_conflito",
                    "feicoes", "expira_em"], meta, ambiente)
    _csv_para_gpkg(destino, "plat_dominio",
                   ["camada_id", "nome_gpkg", "campo", "valor"], dominios, ambiente)
    if replica.get("com_anexos"):
        _csv_para_gpkg(destino, "plat_anexo", *_anexos(cur, camadas), ambiente)
    return contagens


def _anexos(cur, camadas: list[dict]) -> tuple[list[str], list[list[Any]]]:
    """Metadado dos anexos das feições da réplica (item L2-03-edicao). O CONTEÚDO fica no armazenamento de
    objetos e é baixado por `GET /api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}` quando há rede:
    embutir megabytes de foto num pacote de campo estouraria o teto declarado e é decisão de produto, não
    deste item (ver ADR e MANUAL). O cliente leva a lista para saber o que existe e o que falta baixar."""
    cabecalho = ["camada_id", "nome_gpkg", "globalid", "anexo_id", "nome", "content_type", "bytes", "sha256"]
    linhas: list[list[Any]] = []
    total = 0
    for camada in camadas:
        dados = camada["dados"]
        cur.execute(
            "SELECT id, globalid, nome, content_type, bytes, sha256 FROM plat.feicao_anexo "
            "WHERE schema_dado = %s AND tabela_dado = %s AND apagado_em IS NULL ORDER BY criado_em",
            (dados["schema"], dados["tabela"]),
        )
        for linha in cur.fetchall():
            total += int(linha["bytes"] or 0)
            if total > limites.REPLICA_ANEXOS_BYTES_MAX:
                raise ErroAPI(
                    413, "replica_anexos_grandes",
                    f"os anexos do recorte somam mais de {limites.REPLICA_ANEXOS_BYTES_MAX} bytes",
                    {"teto": limites.REPLICA_ANEXOS_BYTES_MAX},
                )
            linhas.append([camada["camada_id"], camada["nome_gpkg"], str(linha["globalid"]), str(linha["id"]),
                           linha["nome"], linha["content_type"], linha["bytes"], linha["sha256"]])
    return cabecalho, linhas
