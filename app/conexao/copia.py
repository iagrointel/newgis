"""Job `conexao.copiar_vetor` (item L6-02-c-wfs-ogcapi, modo COPIADO): traz uma coleção de um WFS 2.0 ou de um
OGC API - Features para uma tabela PostGIS do inquilino, com item de catálogo `camada_vetorial` e procedência.

Desenho, e por que ele é assim:

1. **Quem fala com o serviço externo é `app/conexao/vetor_externo.py`, nunca o GDAL.** O driver `WFS:`/`OAPIF:`
   do GDAL faria a requisição por fora de `app.conexao.seguranca` e a defesa contra requisição forjada pelo
   servidor (SSRF) do item L6-02-a deixaria de valer no caminho que mais recebe URL de terceiro. Aqui as
   páginas são baixadas por `buscar_seguro`, gravadas em arquivo LOCAL no diretório do job, e só então o
   `ogr2ogr` entra — lendo arquivo local. Para provar que não sobrou caminho de rede, o subprocesso roda com
   `GDAL_HTTP_PROXY` apontando para uma porta fechada do loopback: qualquer requisição que o GDAL tentasse
   fazer falharia na hora em vez de sair da máquina.

2. **O limite é nosso, não do serviço.** `limite_feicoes` (padrão `CONEXAO_VETOR_LIMITE_PADRAO`) é o teto de
   feições que esta cópia aceita. Quando o serviço declara mais do que isso — ou ignora a paginação e despeja
   tudo de uma vez — o job TERMINA, marca `limite_atingido` e escreve o aviso na procedência da camada. Nunca
   fica girando: é a refutação exigida pelo item ("WFS com 5 mi de feições e sem paginação").

3. **CRS nativo gravado, geometria reprojetada para 4326.** O que o serviço declara (`DefaultCRS` do WFS,
   `storageCrs` do OGC API) vai para a ficha; a tabela fica em 4326, reprojetada aqui pelo `ogr2ogr`
   (`-s_srs`/`-t_srs`), nunca pedindo reprojeção ao serviço — pedir `SRSNAME=urn:...EPSG::4326` traz eixo
   latitude/longitude em alguns servidores e longitude/latitude em outros, e o erro só aparece no mapa.

4. **Tipo de atributo é o DECLARADO.** Depois da carga, cada coluna é levada ao tipo que o serviço declarou em
   `DescribeFeatureType` (WFS) ou `/queryables` (OGC API). Sem isso um `xsd:int` chega como texto ou como
   `bigint` conforme o palpite do GDAL sobre a amostra. Quando o `ALTER` falha (dado que não cabe no tipo
   declarado), a coluna FICA COMO ESTÁ e um aviso nomeado entra na procedência — nunca se perde linha para
   fazer o tipo bater.
"""

from __future__ import annotations

import json
import os
import time
import uuid

import psycopg2
import psycopg2.extensions
import psycopg2.extras
from pydantic import BaseModel, Field

from app import limites
from app.conexao import credencial as credencial_mod
from app.conexao import vetor_externo
from app.ingestao import nomes as nomes_mod
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings

# porta fechada do loopback: existe só para o `ogr2ogr` não conseguir falar com ninguém (ver seção 1 acima)
PROXY_MORTO = "127.0.0.1:1"
SRID_APOS_GML = 4326  # o `ogr2ogr -f GeoJSONSeq -t_srs EPSG:4326` de `_baixar_gml` já entrega em 4326
FAMILIA_MULTI = {
    "Point": "MultiPoint", "MultiPoint": "MultiPoint",
    "LineString": "MultiLineString", "MultiLineString": "MultiLineString",
    "Polygon": "MultiPolygon", "MultiPolygon": "MultiPolygon",
}


class CopiarParametros(BaseModel):
    conexao_id: uuid.UUID
    colecao: str = Field(min_length=1, max_length=250)
    titulo: str | None = Field(default=None, max_length=250)
    limite_feicoes: int = Field(
        limites.CONEXAO_VETOR_LIMITE_PADRAO, ge=1, le=limites.CONEXAO_VETOR_LIMITE_MAX
    )
    tam_pagina: int = Field(limites.CONEXAO_VETOR_PAGINA_PADRAO, ge=1, le=limites.CONEXAO_VETOR_PAGINA_MAX)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    datahora: str | None = Field(default=None, max_length=100)


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _pg_conninfo() -> str:
    partes = psycopg2.extensions.parse_dsn(settings.PLAT_DSN)
    pares = " ".join(f"{k}={v}" for k, v in partes.items() if k in ("dbname", "host", "port", "user", "password"))
    return f"PG:{pares} application_name=plat-conexao-copia"


def _ambiente_gdal() -> dict:
    """Ambiente do `ogr2ogr`: o do processo + o proxy morto. `PGCLIENTENCODING` fecha o caso do serviço que
    devolve texto latin-1 dentro de um XML que se diz utf-8."""
    env = dict(os.environ)
    env.update({"GDAL_HTTP_PROXY": PROXY_MORTO, "GDAL_HTTP_PROXYUSERPWD": "", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": "",
                "PGCLIENTENCODING": "UTF8", "OGR_GEOJSON_MAX_OBJ_SIZE": "0"})
    return env


def _conector_de(cur, conexao_id: str) -> tuple[vetor_externo.Conector, dict]:
    cur.execute("SELECT id, tipo, url, modo, nome, credencial_cifrada FROM plat.conexao WHERE id = %s::uuid",
                (conexao_id,))
    r = cur.fetchone()
    if r is None:
        raise FalhaDefinitiva("conexão inexistente ou fora do inquilino do job")
    if r["tipo"] not in vetor_externo.TIPOS_SUPORTADOS:
        raise FalhaDefinitiva(
            f"conexão do tipo {r['tipo']!r}: este job copia só {vetor_externo.TIPOS_SUPORTADOS}"
        )
    cabecalhos = None
    if r["credencial_cifrada"]:
        try:
            token = credencial_mod.decifrar(r["credencial_cifrada"], settings.PLAT_SECRET)
            cabecalhos = {"Authorization": f"Bearer {token}"}
        except ValueError:
            cabecalhos = None  # PLAT_SECRET trocado: tenta sem credencial e o serviço decide (401 vira aviso)
    return vetor_externo.Conector(tipo=r["tipo"], url=r["url"], cabecalhos=cabecalhos), dict(r)


def _normalizar_campos(campos: list[vetor_externo.Campo]) -> list[dict]:
    """Nome de coluna pelo mesmo normalizador da ingestão de arquivo (ADR 0005 seção 8): a camada que veio de um
    WFS e a que veio de um shapefile têm de nomear as colunas do mesmo jeito, senão a mesma expressão salva num
    mapa quebra ao trocar a origem."""
    usados: set[str] = set()
    saida = []
    for i, c in enumerate(campos):
        nome, motivo = nomes_mod.normalizar(c.nome, usados, posicao=i)
        usados.add(nome)
        saida.append({"nome": nome, "origem": c.nome, "tipo": c.tipo, "tipo_declarado": c.tipo_declarado,
                      "origem_do_tipo": c.origem, "aviso_nome": motivo})
    return saida


def _linha_geojson(feicao: dict, campos: list[dict]) -> str:
    props_origem = feicao.get("properties") or {}
    props = {}
    for c in campos:
        valor = props_origem.get(c["origem"])
        if isinstance(valor, (dict, list)):
            valor = json.dumps(valor, ensure_ascii=False)
        props[c["nome"]] = valor
    return json.dumps({"type": "Feature", "geometry": feicao.get("geometry"), "properties": props},
                      ensure_ascii=False, default=str)


@tarefa(
    nome="conexao.copiar_vetor",
    descricao="Copia uma coleção WFS 2.0 / OGC API - Features para tabela PostGIS do inquilino (modo copiado)",
    parametros=CopiarParametros,
    pesado=True,
    memoria_mb=limites.COPIA_MEMORIA_MB,
    timeout_s=limites.COPIA_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"conexao-copia:{p.get('conexao_id')}:{p.get('colecao')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def conexao_copiar_vetor(ctx, conexao_id: uuid.UUID, colecao: str, titulo: str | None = None,
                         limite_feicoes: int = limites.CONEXAO_VETOR_LIMITE_PADRAO,
                         tam_pagina: int = limites.CONEXAO_VETOR_PAGINA_PADRAO,
                         bbox: list[float] | None = None, datahora: str | None = None) -> dict:
    cid = str(conexao_id)
    t0 = time.monotonic()
    with ctx.db() as cur:
        conector, linha = _conector_de(cur, cid)
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        slug = cur.fetchone()["slug"]

    schema = f"d_{slug}"
    item_id = str(uuid.uuid4())
    tabela = f"c_{item_id.replace('-', '')[:16]}"
    tabela_criada = False
    reservado = 0

    try:
        ctx.progresso(3, "lendo o que o serviço declara")
        col = vetor_externo.colecao_ou_erro(conector, colecao)
        campos_declarados, metadado_bytes = vetor_externo.descrever_campos(conector, col)
        if not campos_declarados:
            ctx.log("AVISO", "o serviço não declara nenhum atributo para esta coleção; a camada fica só com a "
                             "geometria e as colunas obrigatórias")
        campos = _normalizar_campos(campos_declarados)
        formato_json = vetor_externo._formato_json_wfs(col) if conector.tipo == "wfs" else "application/geo+json"
        if conector.tipo == "wfs" and not formato_json:
            ctx.log("AVISO", "o WFS não anuncia nenhum outputFormat JSON; as páginas virão em GML e serão "
                             "convertidas localmente pelo GDAL")

        ctx.progresso(6, "perguntando quantas feições existem")
        try:
            declaradas = vetor_externo.contar(conector, col, bbox=bbox, datahora=datahora)
        except vetor_externo.ErroConector as e:
            declaradas = None
            ctx.log("AVISO", f"o serviço não respondeu a contagem ({e.motivo}); a cópia segue sem saber o total")

        pag = vetor_externo.Paginador(conector, col, bbox=bbox, datahora=datahora, tam_pagina=tam_pagina,
                                      limite=limite_feicoes, formato_json=formato_json)
        pag.relatorio.numero_matched = declaradas
        caminho = ctx.dir_trabalho / "feicoes.geojsonl"
        ctx.progresso(10, "baixando as páginas")
        escritas = 0
        familias: set[str] = set()
        t_baixa = time.monotonic()
        with open(caminho, "w", encoding="utf-8") as saida:
            if formato_json:
                for lote in pag.paginas_json():
                    for f in lote:
                        geo = f.get("geometry") or {}
                        if geo.get("type"):
                            familias.add(str(geo["type"]))
                        saida.write(_linha_geojson(f, campos) + "\n")
                        escritas += 1
                    ctx.progresso(min(10 + int(escritas / max(limite_feicoes, 1) * 45), 55),
                                  f"{escritas} feições baixadas em {pag.relatorio.paginas} páginas")
            else:
                escritas, familias = _baixar_gml(ctx, pag, campos, saida)

        relatorio = pag.relatorio
        if escritas == 0:
            raise FalhaDefinitiva("o serviço não devolveu nenhuma feição para esta coleção/filtro")
        segundos_baixa = round(time.monotonic() - t_baixa, 3)
        ctx.log("INFO", f"{escritas} feições em {relatorio.paginas} páginas, {relatorio.bytes} bytes, "
                        f"{segundos_baixa} s de download")

        estimativa = max(caminho.stat().st_size * limites.CARGA_FATOR_COTA, 1024 * 1024)
        with ctx.db() as cur:
            cur.execute("SELECT cota_bytes, uso_bytes, uso_reservado_bytes FROM plat.tenant WHERE id = %s FOR UPDATE",
                        (ctx.tenant_id,))
            t = cur.fetchone()
            if t["uso_bytes"] + t["uso_reservado_bytes"] + estimativa > t["cota_bytes"]:
                faltam = (t["uso_bytes"] + t["uso_reservado_bytes"] + estimativa - t["cota_bytes"]) // (1024 * 1024)
                raise FalhaDefinitiva(f"cota do inquilino excedida: faltam {faltam} MB")
            cur.execute("UPDATE plat.tenant SET uso_reservado_bytes = uso_reservado_bytes + %s WHERE id = %s",
                        (estimativa, ctx.tenant_id))
            reservado = estimativa
        _garantir_schema_de_dado(ctx, slug)
        with ctx.db() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')

        familia_unica = {FAMILIA_MULTI.get(f) for f in familias}
        nlt = familia_unica.pop() if len(familia_unica) == 1 and None not in familia_unica else "GEOMETRY"
        # No caminho do GML a conversão local já entregou 4326 (ver `_baixar_gml`); no caminho do GeoJSON as
        # coordenadas vêm no CRS nativo que o serviço declarou, e é aqui que a reprojeção acontece.
        srid_origem = col.srid_entregue if formato_json else SRID_APOS_GML
        ctx.progresso(60, f"carregando no PostGIS (reprojetando de EPSG:{srid_origem} para 4326)")
        t_carga = time.monotonic()
        argv = [
            "ogr2ogr", "-f", "PostgreSQL", _pg_conninfo(), str(caminho),
            "-nln", f"{schema}.{tabela}", "-nlt", nlt,
            "-s_srs", f"EPSG:{srid_origem}", "-t_srs", "EPSG:4326",
            "-lco", "GEOMETRY_NAME=geom", "-lco", "FID=fid", "-lco", "FID64=YES",
            "-lco", "SPATIAL_INDEX=NONE", "-lco", "PRECISION=NO", "-lco", "LAUNDER=NO",
            "--config", "PG_USE_COPY", "YES",
        ]
        r = ctx.subprocesso(argv, env=_ambiente_gdal())
        if r.returncode != 0:
            linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            raise FalhaDefinitiva(f"ogr2ogr falhou: {(linhas[-1] if linhas else 'sem detalhe')[:200]}")
        tabela_criada = True
        segundos_carga = round(time.monotonic() - t_carga, 3)

        ctx.progresso(75, "levando as colunas ao tipo declarado pelo serviço")
        tipos_aplicados, avisos_tipo = _aplicar_tipos(ctx, schema, tabela, campos)

        ctx.progresso(82, "preparando a tabela (RLS, índices, gatilhos)")
        with ctx.db() as cur:
            cur.execute(
                "SELECT type FROM geometry_columns WHERE f_table_schema=%s AND f_table_name=%s AND "
                "f_geometry_column='geom'", (schema, tabela),
            )
            r_tipo = cur.fetchone()
            mapa = {"POINT": "Point", "MULTIPOINT": "MultiPoint", "LINESTRING": "LineString",
                    "MULTILINESTRING": "MultiLineString", "POLYGON": "Polygon", "MULTIPOLYGON": "MultiPolygon",
                    "GEOMETRY": "Geometry", "GEOMETRYCOLLECTION": "Geometry"}
            tipo_geom = mapa.get((r_tipo["type"] if r_tipo else "").upper(), "Geometry")
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, 4326, tipo_geom, ctx.usuario_id))

        ctx.progresso(90, "estatísticas e catálogo")
        with ctx.db() as cur:
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
            cur.execute(f'SELECT count(*) AS n, ST_AsGeoJSON(ST_Extent(geom)::geometry) AS ext '
                        f'FROM "{schema}"."{tabela}"')
            est = cur.fetchone()
            cur.execute('SELECT pg_total_relation_size(%s::regclass) AS b', (f'"{schema}"."{tabela}"',))
            tamanho_bytes = int(cur.fetchone()["b"])
        extent = None
        if est["ext"]:
            coords = json.loads(est["ext"])["coordinates"][0]
            xs, ys = [c[0] for c in coords], [c[1] for c in coords]
            if -180 <= min(xs) and max(xs) <= 180 and -90 <= min(ys) and max(ys) <= 90:
                extent = [min(xs), min(ys), max(xs), max(ys)]

        avisos = list(relatorio.avisos) + avisos_tipo
        if relatorio.numero_matched is not None and relatorio.numero_matched != escritas and \
                not relatorio.limite_atingido:
            avisos.append(
                f"o serviço declarou {relatorio.numero_matched} feições e entregou {escritas}: a paginação não "
                f"fechou (contagem declarada e contagem lida têm de bater)"
            )
        item_dados = _dados_do_item(
            conexao=linha, colecao=col, campos=campos, escritas=escritas, relatorio=relatorio,
            tipo_geom=tipo_geom, avisos=avisos, metadado_bytes=metadado_bytes, tipos_aplicados=tipos_aplicados,
            segundos_baixa=segundos_baixa, segundos_carga=segundos_carga, job_id=str(ctx.job_id),
            limite=limite_feicoes, bbox=bbox, datahora=datahora, tabela=tabela, schema=schema,
            srid_origem=srid_origem, formato=formato_json or 'GML (convertido localmente)',
        )
        titulo_final = (titulo or f"{col.titulo or col.nome} ({linha['nome']})")[:250]
        with ctx.db() as cur:
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, extent, "
                "extent_origem, origem, url, criado_por, modificado_por) "
                "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, "
                + ("ST_MakeEnvelope(%s,%s,%s,%s,4326)" if extent else "NULL")
                # `origem` do item é o enum 'hospedado'|'referenciado' da migração 011: depois da cópia o dado
                # está NA NOSSA máquina, logo 'hospedado'. De onde ele veio fica em `dados.conexao` e em
                # `dados.procedencia`, com o protocolo, a URL e a coleção — nunca escondido num enum.
                + ", %s, 'hospedado', %s, %s, %s)",
                [item_id, ctx.tenant_id, titulo_final, ctx.usuario_id, _jsonb(item_dados), tamanho_bytes]
                + (extent if extent else [])
                + (["dado"] if extent else [None])
                + [linha["url"], ctx.usuario_id, ctx.usuario_id],
            )
            cur.execute(
                "UPDATE plat.tenant SET uso_reservado_bytes = greatest(0, uso_reservado_bytes - %s), "
                "uso_bytes = uso_bytes + %s WHERE id = %s", (reservado, tamanho_bytes, ctx.tenant_id),
            )
            reservado = 0
        ctx.progresso(100, f"{escritas} feições copiadas")
        return {
            "item_id": item_id, "schema": schema, "tabela": tabela, "feicoes": escritas,
            "declaradas_pelo_servico": relatorio.numero_matched, "paginas": relatorio.paginas,
            "limite_atingido": relatorio.limite_atingido, "ignora_paginacao": relatorio.ignora_paginacao,
            "repetiu_pagina": relatorio.repetiu_pagina, "srid_nativo": col.srid_nativo,
            "srid_entregue": srid_origem, "srid_gravado": 4326,
            "segundos_download": segundos_baixa, "segundos_carga": segundos_carga,
            "segundos_total": round(time.monotonic() - t0, 3), "avisos": avisos,
        }
    except Exception:
        with ctx.db() as cur:
            if tabela_criada:
                cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
            cur.execute("DELETE FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,))
            if reservado:
                cur.execute("UPDATE plat.tenant SET uso_reservado_bytes = greatest(0, uso_reservado_bytes - %s) "
                            "WHERE id = %s", (reservado, ctx.tenant_id))
        raise


def _garantir_schema_de_dado(ctx, slug: str, tentativas: int = 4) -> None:
    """`plat.camada_schema_garantir` faz `CREATE SCHEMA IF NOT EXISTS` + `GRANT USAGE ... TO plat_leitor`.
    Duas cargas simultâneas para o MESMO inquilino executam o mesmo GRANT ao mesmo tempo e o PostgreSQL
    devolve `tuple concurrently updated` (a linha do catálogo `pg_namespace` sendo atualizada por duas
    transações) — não é erro do dado, é corrida no catálogo do banco, e reexecutar resolve. MEDIDO em
    06/09/2026 com duas trilhas carregando camada no mesmo schema `d_demo` no mesmo segundo.

    Aqui se repete com espera curta, no máximo `tentativas` vezes. Repetir é seguro porque a função é
    idempotente por construção (IF NOT EXISTS + GRANT). Se ainda assim não passar, o erro sobe como qualquer
    outro — nunca se engole a falha."""
    for n in range(1, tentativas + 1):
        try:
            with ctx.db() as cur:
                cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            return
        except psycopg2.InternalError as e:
            if "tuple concurrently updated" not in str(e) or n == tentativas:
                raise
            ctx.log("AVISO", f"corrida no catálogo do banco ao garantir o schema de dado (tentativa {n}): {e}")
            time.sleep(0.2 * n)


def _baixar_gml(ctx, pag, campos, saida) -> tuple[int, set[str]]:
    """WFS que só fala GML: cada página vai para disco e o `ogr2ogr` LOCAL a converte para GeoJSON, que é então
    normalizado como as demais. Nenhuma requisição sai do GDAL (ver seção 1 do módulo). `corte` é quantas
    feições daquela página ainda cabem no limite — o paginador já o calculou."""
    escritas = 0
    familias: set[str] = set()
    for i, (corpo, corte) in enumerate(pag.paginas_brutas()):
        gml = ctx.dir_trabalho / f"pagina_{i:05d}.gml"
        convertido = ctx.dir_trabalho / f"pagina_{i:05d}.geojsonl"
        gml.write_bytes(corpo)
        # `-t_srs EPSG:4326` explícito: o GeoJSON do GDAL já sairia em WGS84 por causa da RFC 7946, e uma
        # reprojeção que acontece por padrão de biblioteca é uma reprojeção que ninguém revisa. Escrita aqui,
        # ela é a razão de `srid_entregue` virar 4326 no caminho do GML (ver `SRID_APOS_GML`).
        r = ctx.subprocesso(["ogr2ogr", "-f", "GeoJSONSeq", "-t_srs", "EPSG:4326", str(convertido), str(gml)],
                            env=_ambiente_gdal())
        if r.returncode != 0:
            linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            raise FalhaDefinitiva(f"conversão local do GML falhou: {(linhas[-1] if linhas else '')[:200]}")
        desta_pagina = 0
        with open(convertido, encoding="utf-8") as entrada:
            for linha in entrada:
                if desta_pagina >= corte:
                    break
                f = json.loads(linha)
                geo = f.get("geometry") or {}
                if geo.get("type"):
                    familias.add(str(geo["type"]))
                saida.write(_linha_geojson(f, campos) + "\n")
                desta_pagina += 1
                escritas += 1
        gml.unlink(missing_ok=True)
        convertido.unlink(missing_ok=True)
        ctx.progresso(min(10 + int(escritas / max(pag.limite, 1) * 45), 55), f"{escritas} feições (GML)")
    return escritas, familias


def _aplicar_tipos(ctx, schema: str, tabela: str, campos: list[dict]) -> tuple[dict, list[str]]:
    """Leva cada coluna ao tipo DECLARADO pelo serviço. Cada `ALTER` num savepoint próprio: o que não converte
    fica como o GDAL deixou e vira aviso nomeado, nunca linha perdida nem tipo silenciosamente errado."""
    aplicados: dict[str, str] = {}
    avisos: list[str] = []
    with ctx.db() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
            (schema, tabela),
        )
        atuais = {r["column_name"]: r["data_type"] for r in cur.fetchall()}
        for c in campos:
            nome, alvo = c["nome"], c["tipo"]
            if nome not in atuais:
                avisos.append(f"campo {c['origem']!r} declarado pelo serviço não veio em nenhuma feição")
                continue
            atual = atuais[nome]
            aplicados[nome] = atual
            if _ja_e(atual, alvo):
                aplicados[nome] = alvo
                continue
            cur.execute("SAVEPOINT tipo_campo")
            try:
                cur.execute(
                    f'ALTER TABLE "{schema}"."{tabela}" ALTER COLUMN "{nome}" TYPE {alvo} '
                    f'USING NULLIF(btrim("{nome}"::text), \'\')::{alvo}'
                )
                cur.execute("RELEASE SAVEPOINT tipo_campo")
                aplicados[nome] = alvo
            except psycopg2.Error as e:
                cur.execute("ROLLBACK TO SAVEPOINT tipo_campo")
                cur.execute("RELEASE SAVEPOINT tipo_campo")
                avisos.append(
                    f"campo {nome!r}: o serviço declara {c['tipo_declarado']!r} (-> {alvo}) mas o dado não "
                    f"converte ({str(e).splitlines()[0][:120]}); a coluna ficou {atual}"
                )
    return aplicados, avisos


_EQUIVALENTES = {
    # `character varying` NÃO conta como `text`: o GDAL cria varchar com a largura da AMOSTRA que ele viu, e um
    # valor mais longo numa cópia seguinte seria recusado pelo banco. Um `xsd:string` declarado não tem largura,
    # então a coluna tem de ser `text` — o ALTER acontece de propósito.
    "text": {"text"},
    "integer": {"integer"},
    "bigint": {"bigint"},
    "double precision": {"double precision", "real", "numeric"},
    "boolean": {"boolean"},
    "date": {"date"},
    "timestamptz": {"timestamp with time zone"},
    "time": {"time without time zone"},
}


def _ja_e(atual: str, alvo: str) -> bool:
    return atual in _EQUIVALENTES.get(alvo, {alvo})


def _dados_do_item(*, conexao, colecao, campos, escritas, relatorio, tipo_geom, avisos, metadado_bytes,
                   tipos_aplicados, segundos_baixa, segundos_carga, job_id, limite, bbox, datahora,
                   tabela, schema, srid_origem, formato) -> dict:
    import datetime
    import hashlib

    return {
        "schema": schema, "tabela": tabela, "geometria": tipo_geom, "srid": 4326,
        "campos": [{"nome": c["nome"], "tipo": tipos_aplicados.get(c["nome"], c["tipo"]), "alias": c["origem"]}
                   for c in campos],
        # `hospedada`: depois da cópia o dado mora aqui — o enum do tipo camada_vetorial (migração 029) só tem
        # `hospedada`/`referenciada`, e chamar de referenciada uma tabela nossa seria mentir sobre onde ela está.
        # A origem externa fica inteira em `conexao` e em `procedencia`.
        "fonte": "hospedada",
        "conexao": {
            "conexao_id": str(conexao["id"]), "protocolo": conexao["tipo"], "url": conexao["url"],
            "colecao": colecao.nome, "colecao_titulo": colecao.titulo,
            "crs_nativo_declarado": colecao.crs_nativo, "srid_nativo": colecao.srid_nativo,
            "srid_entregue": srid_origem, "srid_gravado": 4326, "formato_recebido": formato,
            "job_id": job_id,
            "filtro": {"bbox": bbox, "datetime": datahora},
            "limite_declarado": limite, "limite_atingido": relatorio.limite_atingido,
            "ignora_paginacao": relatorio.ignora_paginacao, "repetiu_pagina": relatorio.repetiu_pagina,
            "paginas": relatorio.paginas, "bytes_baixados": relatorio.bytes,
            "declaradas_pelo_servico": relatorio.numero_matched, "copiadas": escritas,
            "tipos_declarados": {c["nome"]: c["tipo_declarado"] for c in campos},
            "origem_dos_tipos": sorted({c["origem_do_tipo"] for c in campos}) or None,
            "segundos_download": segundos_baixa, "segundos_carga": segundos_carga,
        },
        "procedencia": {
            "fonte": colecao.titulo or colecao.nome,
            "url": conexao["url"],
            "licenca": None,  # licença vem do L6-05 (publicar a conexão): aqui não se inventa uma
            "data_do_dado": None,
            "data_de_acesso": datetime.datetime.now(datetime.UTC).date().isoformat(),
            "metodo": f"cópia {conexao['tipo']} -> GeoJSON local -> ogr2ogr PostGIS "
                      f"(EPSG:{srid_origem} -> EPSG:4326), páginas por "
                      f"{'STARTINDEX/COUNT' if conexao['tipo'] == 'wfs' else 'limit + link rel=next'}",
            "confianca": "declarado" if any(c["origem_do_tipo"] != "amostra" for c in campos) else "inferido",
            "frescor": f"cópia de {datetime.datetime.now(datetime.UTC).date().isoformat()}; "
                       f"o serviço de origem pode ter mudado desde então",
            "sha256": hashlib.sha256(metadado_bytes).hexdigest() if metadado_bytes else None,
            "comando_reexecucao": f"POST /api/conexoes/{conexao['id']}/colecoes/{colecao.nome}/copiar",
            "limites": avisos or None,
            "responsavel": None,
        },
        "estatisticas": {"feicoes": escritas, "calculadas_em": None},
    }
