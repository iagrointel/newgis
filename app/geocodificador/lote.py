"""Job `geocodificacao.lote` (item L2-11-a-geocodificacao-csv): pega a tabela que o usuário enviou (CSV/TXT/
XLSX), aplica o mapeamento de colunas que ele confirmou, geocodifica LINHA A LINHA com o motor do item
L2-11-b (`app.geocodificador.motor`, o mesmo de `POST /api/geocodificar`), grava uma linha de resultado por
linha do arquivo com pontuação e tipo de acerto, e publica os pontos como camada nova do inquilino com as
colunas de qualidade.

Três invariantes que este job existe para garantir:

  1. **Linha ruim não derruba o trabalho todo.** Toda linha vira uma linha em `plat.geocodificacao_linha`.
     Linha com coluna faltando, número sem dígito, célula gigante ou endereço vazio fica com
     `estado='malformada'` e o motivo em português; linha que o motor não resolveu fica `estado='pendente'`.
     O job só falha por motivo que impede o lote inteiro (arquivo acima do teto, arquivo ilegível, mapeamento
     que não bate com o cabeçalho, cota do inquilino).
  2. **Ponto no centro do município nunca se disfarça de endereço.** O `tipo_acerto` do motor vem gravado na
     linha E na coluna `geo_tipo_acerto` da camada; `aproximado_no_municipio` é justamente o recuo que põe o
     ponto no centróide, e ele chega à tela e ao mapa com esse nome e com o aviso do motor.
  3. **Coordenada de máquina e coordenada de humano nunca se confundem.** `origem` é 'automatica' quando o
     motor resolveu e 'manual' quando alguém arrastou o ponto na tela de revisão; `regeocodificar` refaz
     SÓ as pendentes e nunca sobrescreve uma linha de origem manual.

A camada publicada é reescrita a partir de `plat.geocodificacao_linha` (fonte única da verdade) a cada
execução — inclusive depois de uma re-geocodificação — para nunca existir ponto na camada que não exista na
tabela de resultado.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid

import psycopg2.extras
from pydantic import BaseModel

from app import limites, objetos
from app import versao as app_versao
from app.catalogo import procedencia as mod_procedencia
from app.geocodificador import motor, tabela
from app.geocodificador.normalizacao import analisar_linha_unica, expandir_abreviacoes
from app.ingestao.inspecionar import tabela_de
from app.jobs.registro import Cancelado, FalhaDefinitiva, tarefa

TIPOS_PRECISOS = ("numero_exato", "interpolado_na_face")
TIPO_CENTROIDE = "aproximado_no_municipio"
EPSILON_EXTENT = 1e-6  # grau (~11 cm): folga da envoltória de camada com um ponto só (ver _sincronizar_camada)
COLUNAS_CAMADA = (
    "linha", "endereco_entrada", "endereco_casado", "logradouro", "numero", "bairro", "municipio", "uf",
    "cep", "geo_score", "geo_tipo_acerto", "geo_origem", "geo_municipio_cod", "geo_avisos",
)


class LoteParametros(BaseModel):
    geocodificacao_id: uuid.UUID
    so_pendentes: bool = False


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def campos_do_endereco(campos: dict) -> dict:
    """Campos da linha do arquivo -> argumentos do motor. `endereco` (coluna única) é analisado pelo MESMO
    analisador da rota de um endereço (`normalizacao.analisar_linha_unica`); campo estruturado tem prioridade
    sobre o que o analisador tirou da linha única, igual à rota."""
    logradouro = campos.get("logradouro")
    numero = campos.get("numero")
    bairro = campos.get("bairro")
    municipio = campos.get("municipio")
    uf = campos.get("uf")
    cep = campos.get("cep")
    if campos.get("endereco"):
        livre = analisar_linha_unica(campos["endereco"])
        logradouro = logradouro or livre.logradouro
        numero = numero if numero is not None else livre.numero
        bairro = bairro or livre.bairro
        municipio = municipio or livre.municipio
        uf = uf or livre.uf
        cep = cep or livre.cep
    if cep:
        so_digito = "".join(c for c in str(cep) if c.isdigit())
        cep = so_digito if len(so_digito) == 8 else None
    if uf:
        uf = str(uf).upper()[:2]
    if logradouro:
        logradouro = expandir_abreviacoes(str(logradouro))
    return {"logradouro": logradouro or None, "numero": numero, "bairro": bairro or None,
            "municipio": municipio or None, "uf": uf or None, "cep": cep}


def _texto_entrada(campos: dict) -> str:
    if campos.get("endereco"):
        return str(campos["endereco"])[:limites.GEOCOD_CAMPO_TEXTO_MAX]
    partes = []
    if campos.get("logradouro"):
        partes.append(str(campos["logradouro"]) + (f", {campos['numero']}" if campos.get("numero") else ""))
    for chave in ("bairro", "municipio", "uf", "cep"):
        if campos.get(chave):
            partes.append(str(campos[chave]))
    return ", ".join(partes)[:limites.GEOCOD_CAMPO_TEXTO_MAX]


def geocodificar_linha(cur, linha: tabela.LinhaTabela, cache) -> dict:
    """Uma linha do arquivo -> um dicionário pronto para gravar. Nunca levanta: erro do motor vira estado
    'pendente' com o motivo (o lote continua)."""
    base = {
        "n": linha.n, "entrada": linha.campos, "endereco": None, "lon": None, "lat": None, "score": None,
        "tipo_acerto": None, "origem": None, "estado": "pendente", "motivo": linha.motivo,
        "avisos": list(linha.avisos), "cod_municipio": None, "municipio": None, "uf": None,
        "texto_entrada": _texto_entrada(linha.campos),
    }
    if linha.motivo:
        base["estado"] = "malformada"
        return base
    argumentos = campos_do_endereco(linha.campos)
    if not any([argumentos["logradouro"], argumentos["bairro"], argumentos["municipio"], argumentos["cep"]]):
        base["estado"] = "malformada"
        base["motivo"] = "nenhum campo de endereço utilizável depois da leitura da linha"
        return base
    try:
        candidatos = motor.buscar(cur, max_locations=1, cache=cache, **argumentos)
    except motor.InconsistenciaEndereco as e:
        base["motivo"] = e.mensagem
        base["avisos"].append(e.codigo)
        return base
    if not candidatos:
        base["motivo"] = ("nenhum lugar da base de endereços instalada corresponde a esta linha "
                          "(UF/município não instalado, ou logradouro/bairro sem semelhança suficiente)")
        return base
    c = candidatos[0]
    base.update({
        "endereco": c.endereco, "lon": c.lon, "lat": c.lat, "score": c.score, "tipo_acerto": c.tipo_acerto,
        "origem": "automatica", "estado": "resolvida", "motivo": None,
        "avisos": base["avisos"] + list(c.avisos), "cod_municipio": c.cod_municipio, "municipio": c.municipio,
        "uf": c.uf,
    })
    return base


def _gravar_linhas(cur, geocodificacao_id: str, tenant_id: int, blocos: list[dict]) -> None:
    """Grava um bloco de linhas num único INSERT ... VALUES com N tuplas.

    Por que NÃO `psycopg2.extras.execute_values` aqui: ele monta a consulta em BYTES e chama
    `cur.execute(b'...')`. O cursor desta casa (`app.schema_ambiente.CursorSchemaAmbiente`) só reescreve
    `plat.` -> `plat_t<trilha>` quando a consulta é `str`; com bytes ela passa direto e o job tenta escrever
    no schema `plat` de produção (MEDIDO nesta sessão: `permission denied for schema plat` no primeiro job
    de verdade). A consulta é montada como `str` com marcadores `%s`, que é o caminho que a reescrita cobre.
    """
    if not blocos:
        return
    tupla = "(%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
    valores = ", ".join([tupla] * len(blocos))
    parametros: list = []
    for b in blocos:
        parametros += [geocodificacao_id, b["n"], tenant_id, _jsonb(b["entrada"]), b["endereco"], b["lon"],
                        b["lat"], b["score"], b["tipo_acerto"], b["origem"], b["estado"], b["motivo"],
                        _jsonb(b["avisos"]), b["cod_municipio"], b["municipio"], b["uf"]]
    cur.execute(
        "INSERT INTO plat.geocodificacao_linha (geocodificacao_id, n, tenant_id, entrada, endereco, lon, lat, "
        "  score, tipo_acerto, origem, estado, motivo, avisos, cod_municipio, municipio, uf, atualizado_em) "
        f"VALUES {valores} "
        "ON CONFLICT (geocodificacao_id, n) DO UPDATE SET entrada = EXCLUDED.entrada, "
        "  endereco = EXCLUDED.endereco, lon = EXCLUDED.lon, lat = EXCLUDED.lat, score = EXCLUDED.score, "
        "  tipo_acerto = EXCLUDED.tipo_acerto, origem = EXCLUDED.origem, estado = EXCLUDED.estado, "
        "  motivo = EXCLUDED.motivo, avisos = EXCLUDED.avisos, cod_municipio = EXCLUDED.cod_municipio, "
        "  municipio = EXCLUDED.municipio, uf = EXCLUDED.uf, atualizado_em = now() "
        # a linha de origem MANUAL nunca é sobrescrita por uma execução automática (invariante 3 do módulo)
        "WHERE plat.geocodificacao_linha.origem IS DISTINCT FROM 'manual'",
        parametros,
    )


def _em_blocos(gerador, tamanho: int):
    """Agrupa o gerador de linhas em blocos de `tamanho`. As exceções que impedem o lote inteiro
    (`LinhasDemais`, leitura quebrada no meio) viram FalhaDefinitiva aqui, com a mensagem original."""
    bloco = []
    while True:
        try:
            linha = next(gerador)
        except StopIteration:
            break
        except tabela.LinhasDemais as e:
            raise FalhaDefinitiva(str(e)) from e
        except (ValueError, UnicodeDecodeError) as e:
            raise FalhaDefinitiva(f"leitura da tabela interrompida: {e}") from e
        bloco.append(linha)
        if len(bloco) >= tamanho:
            yield bloco
            bloco = []
    if bloco:
        yield bloco


def _base_enderecos(cur) -> dict:
    """Ficha de proveniência da base de endereços usada (o item pede: 'ficha de proveniência com a versão da
    base de endereços'). Lida de `plat.geo_instalacao`, escrita pelo instalador por UF do item L2-11-b."""
    cur.execute(
        "SELECT sigla, fonte_url, linhas, municipios, sha256_zip, instalado_em FROM plat.geo_instalacao "
        "ORDER BY sigla"
    )
    ufs = [
        {"uf": r["sigla"], "fonte_url": r["fonte_url"], "enderecos": r["linhas"], "municipios": r["municipios"],
         "sha256_zip": r["sha256_zip"],
         "instalado_em": r["instalado_em"].isoformat() if r["instalado_em"] else None}
        for r in cur.fetchall()
    ]
    return {
        "base": "CNEFE 2022 (IBGE), Cadastro Nacional de Endereços para Fins Estatísticos",
        "ufs_instaladas": ufs,
        "enderecos_instalados": sum(u["enderecos"] or 0 for u in ufs),
        "comando_reexecucao": "venv/bin/python3 scripts/geocodificador_instalar_uf.py --uf <SIGLA>",
    }


def _criar_tabela_camada(cur, schema: str, nome_tabela: str) -> None:
    cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{nome_tabela}" CASCADE')
    cur.execute(
        f'CREATE TABLE "{schema}"."{nome_tabela}" ('
        "  fid bigserial PRIMARY KEY,"
        "  linha integer NOT NULL,"
        "  endereco_entrada text,"
        "  endereco_casado text,"
        "  logradouro text,"
        "  numero text,"
        "  bairro text,"
        "  municipio text,"
        "  uf text,"
        "  cep text,"
        "  geo_score double precision,"
        "  geo_tipo_acerto text,"
        "  geo_origem text,"
        "  geo_municipio_cod integer,"
        "  geo_avisos text,"
        "  geom geometry(Point, 4326)"
        ")"
    )


def _sincronizar_camada(cur, schema: str, nome_tabela: str, geocodificacao_id: str) -> dict:
    """Reescreve os pontos da camada a partir de plat.geocodificacao_linha (fonte única da verdade). Só linha
    RESOLVIDA vira ponto: pendente e malformada não entram na camada — ficam na tela de revisão."""
    cur.execute(f'DELETE FROM "{schema}"."{nome_tabela}"')
    cur.execute(
        f'INSERT INTO "{schema}"."{nome_tabela}" '
        f'  (linha, endereco_entrada, endereco_casado, logradouro, numero, bairro, municipio, uf, cep, '
        f'   geo_score, geo_tipo_acerto, geo_origem, geo_municipio_cod, geo_avisos, geom) '
        "SELECT l.n, "
        "  coalesce(l.entrada->>'endereco', concat_ws(', ', l.entrada->>'logradouro', l.entrada->>'numero', "
        "    l.entrada->>'bairro', l.entrada->>'municipio', l.entrada->>'uf')), "
        "  l.endereco, l.entrada->>'logradouro', l.entrada->>'numero', l.entrada->>'bairro', "
        "  coalesce(l.municipio, l.entrada->>'municipio'), coalesce(l.uf, l.entrada->>'uf'), "
        "  l.entrada->>'cep', l.score, l.tipo_acerto, l.origem, l.cod_municipio, "
        "  array_to_string(ARRAY(SELECT jsonb_array_elements_text(l.avisos)), ' | '), "
        "  ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326) "
        "FROM plat.geocodificacao_linha l "
        "WHERE l.geocodificacao_id = %s::uuid AND l.estado = 'resolvida' AND l.lon IS NOT NULL",
        (geocodificacao_id,),
    )
    cur.execute(
        f'SELECT count(*) AS feicoes, ST_XMin(ST_Extent(geom)) AS x1, ST_YMin(ST_Extent(geom)) AS y1, '
        f'ST_XMax(ST_Extent(geom)) AS x2, ST_YMax(ST_Extent(geom)) AS y2 FROM "{schema}"."{nome_tabela}"'
    )
    r = cur.fetchone()
    extent = None
    if r["x1"] is not None:
        # camada de UM ponto (ou de pontos alinhados) dá uma envoltória degenerada, e
        # `plat.item.item_extent_check` exige `ST_IsValid(extent)` — um "polígono" de área zero é inválido
        # (MEDIDO nesta sessão: o primeiro lote de 2 linhas com 1 resolvida falhou aí). Por isso a envoltória
        # ganha uma folga de EPSILON_EXTENT grau (~11 cm) em cada eixo que ficou sem dimensão. É folga de
        # ENQUADRAMENTO do mapa, não medição: a coordenada do ponto continua exata na camada.
        x1, y1, x2, y2 = r["x1"], r["y1"], r["x2"], r["y2"]
        if x2 - x1 < EPSILON_EXTENT:
            x1, x2 = x1 - EPSILON_EXTENT, x2 + EPSILON_EXTENT
        if y2 - y1 < EPSILON_EXTENT:
            y1, y2 = y1 - EPSILON_EXTENT, y2 + EPSILON_EXTENT
        extent = [max(-180.0, x1), max(-90.0, y1), min(180.0, x2), min(90.0, y2)]
    return {"feicoes": int(r["feicoes"]), "extent": extent}


def _resumo(cur, geocodificacao_id: str) -> dict:
    cur.execute(
        "SELECT estado, origem, tipo_acerto, count(*) AS n FROM plat.geocodificacao_linha "
        "WHERE geocodificacao_id = %s::uuid GROUP BY estado, origem, tipo_acerto",
        (geocodificacao_id,),
    )
    por_tipo: dict[str, int] = {}
    contagens = {"resolvidas": 0, "pendentes": 0, "malformadas": 0, "manuais": 0, "total": 0}
    for r in cur.fetchall():
        n = int(r["n"])
        contagens["total"] += n
        contagens[{"resolvida": "resolvidas", "pendente": "pendentes",
                   "malformada": "malformadas"}[r["estado"]]] += n
        if r["origem"] == "manual":
            contagens["manuais"] += n
        if r["tipo_acerto"]:
            por_tipo[r["tipo_acerto"]] = por_tipo.get(r["tipo_acerto"], 0) + n
    contagens["por_tipo_acerto"] = por_tipo
    contagens["precisos"] = sum(por_tipo.get(t, 0) for t in TIPOS_PRECISOS)
    contagens["no_centroide_do_municipio"] = por_tipo.get(TIPO_CENTROIDE, 0)
    return contagens


@tarefa(
    nome="geocodificacao.lote",
    descricao="Geocodifica a tabela enviada (CSV/XLSX) e publica os pontos como camada com colunas de qualidade",
    parametros=LoteParametros,
    pesado=True,
    memoria_mb=768,
    timeout_s=7200,
    tentativas=1,
    chave=lambda p: f"geocodificacao:{p.get('geocodificacao_id')}",
    perfil_minimo="editor",
)
def geocodificacao_lote(ctx, geocodificacao_id: uuid.UUID, so_pendentes: bool = False) -> dict:
    gid = str(geocodificacao_id)
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.geocodificacao WHERE id = %s::uuid", (gid,))
        lote = cur.fetchone()
        if lote is None:
            raise FalhaDefinitiva("geocodificação inexistente")
        if lote["estado"] not in ("na_fila", "rodando"):
            raise FalhaDefinitiva(f"geocodificação em estado {lote['estado']!r}; esperava 'na_fila'")
        cur.execute("SELECT dados, criado_em FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'",
                     (lote["arquivo_id"],))
        arq = cur.fetchone()
        if arq is None:
            raise FalhaDefinitiva("o arquivo de origem não existe mais")
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        slug = cur.fetchone()["slug"]
        cur.execute(
            "UPDATE plat.geocodificacao SET estado = 'rodando', erro = NULL, job_id = %s::uuid, "
            "atualizado_em = now() WHERE id = %s::uuid", (str(ctx.job_id), gid))
        pendentes_antes = set()
        if so_pendentes:
            cur.execute(
                "SELECT n FROM plat.geocodificacao_linha WHERE geocodificacao_id = %s::uuid "
                "AND estado <> 'resolvida' AND origem IS DISTINCT FROM 'manual'", (gid,))
            pendentes_antes = {int(r["n"]) for r in cur.fetchall()}

    schema = f"d_{slug}"
    item_id = str(lote["item_id"]) if lote["item_id"] else str(uuid.uuid4())
    nome_tabela = tabela_de(item_id)
    tabela_ja_existia = bool(lote["item_id"])

    try:
        ctx.progresso(3, "baixando o arquivo")
        dados = objetos.ler(arq["dados"]["chave"])
        sha_real = hashlib.sha256(dados).hexdigest()
        if sha_real != arq["dados"]["sha256"]:
            raise FalhaDefinitiva("arquivo corrompido: sha256 divergente do gravado no upload")
        ctx.entrada(lote["arquivo_id"], sha_real, "tabela de endereços")
        try:
            tabela.conferir_tamanho(len(dados))
        except tabela.ArquivoGrandeDemais as e:
            raise FalhaDefinitiva(str(e)) from e

        ctx.progresso(6, "lendo a tabela")
        mapeamento = lote["mapeamento"] or {}
        total_estimado = tabela.total_estimado(dados)
        try:
            gerador = tabela.linhas(dados, mapeamento)
        except (tabela.ArquivoIlegivel, ValueError) as e:
            raise FalhaDefinitiva(str(e)) from e

        cache = motor.CacheLote()
        lidas = 0
        pulou = 0
        inicio = time.monotonic()
        # UMA transação por bloco de GEOCOD_LOTE_GRAVACAO linhas, nunca uma transação para o arquivo
        # inteiro: com 200 mil linhas isso seria uma transação de horas segurando o banco, e nada do
        # trabalho já feito apareceria na tela de revisão antes do fim. Assim o progresso é real (as linhas
        # já gravadas ficam visíveis) e um cancelamento no meio deixa gravado o que já rodou.
        # O cache do lote é de PROCESSO, então atravessa os blocos sem depender da transação.
        for pedaco in _em_blocos(gerador, limites.GEOCOD_LOTE_GRAVACAO):
            bloco = []
            with ctx.db() as cur:
                for linha in pedaco:
                    lidas += 1
                    if so_pendentes and linha.n not in pendentes_antes:
                        pulou += 1
                        continue
                    bloco.append(geocodificar_linha(cur, linha, cache))
                if bloco:
                    _gravar_linhas(cur, gid, ctx.tenant_id, bloco)
            pct = 6 + int(80 * min(1.0, lidas / total_estimado)) if total_estimado else 6
            ctx.progresso(min(86, pct), f"{lidas} de ~{total_estimado} linhas lidas")
            ctx.verificar()
        segundos = time.monotonic() - inicio
        geocodificadas = lidas - pulou

        ctx.progresso(88, "publicando a camada de pontos")
        with ctx.db() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            if not tabela_ja_existia:
                _criar_tabela_camada(cur, schema, nome_tabela)
            estat = _sincronizar_camada(cur, schema, nome_tabela, gid)
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, nome_tabela, 4326, "Point", ctx.usuario_id))
            cur.execute(f'ANALYZE "{schema}"."{nome_tabela}"')
            cur.execute('SELECT pg_total_relation_size(%s::regclass) AS b',
                         (f'"{schema}"."{nome_tabela}"',))
            tamanho_bytes = int(cur.fetchone()["b"])
            contagens = _resumo(cur, gid)
            base = _base_enderecos(cur)

        resumo = dict(contagens)
        resumo["segundos"] = round(segundos, 2)
        resumo["linhas_geocodificadas_nesta_execucao"] = geocodificadas
        resumo["segundos_por_1000"] = round(segundos / geocodificadas * 1000, 1) if geocodificadas else None
        resumo["cache_taxa_acerto"] = round(cache.taxa_acerto(), 3)
        resumo["so_pendentes"] = bool(so_pendentes)

        procedencia = mod_procedencia.normalizar({
            "fonte": (arq["dados"] or {}).get("nome_original"),
            "url": None, "licenca": None, "data_do_dado": None,
            "data_de_acesso": arq["criado_em"].date().isoformat() if arq["criado_em"] else None,
            "gerador": f"plat geocodificacao.lote {app_versao.versao()}",
            "sha256": sha_real,
            "comando_reexecucao": (f"POST /api/geocodificacoes/{gid}/regeocodificar "
                                    "(base: scripts/geocodificador_instalar_uf.py --uf <SIGLA>)"),
            "metodo": "geocodificador próprio sobre CNEFE 2022 (IBGE) — hierarquia de recuo com tipo de acerto",
            "confianca": None,
            "limites": [
                "coordenada de face de quadra do CNEFE, não de porta: 'numero_exato' é o ponto do IBGE para "
                "aquele número, não o centro do lote",
                "linha com tipo de acerto 'aproximado_no_municipio' está no centróide do município, não no "
                "endereço",
                "ponto com geo_origem='manual' foi arrastado por uma pessoa na tela de revisão, não medido",
            ],
            "frescor": base["base"], "proxima_verificacao": None, "responsavel": None,
            "origem": {"fonte": "declarado", "data_de_acesso": "medido", "gerador": "medido",
                        "sha256": "medido", "metodo": "medido", "limites": "declarado"},
            "job_id": str(ctx.job_id), "geocodificacao_id": gid,
            "base_enderecos": base,
        })
        item_dados = {
            "schema": schema, "tabela": nome_tabela, "geometria": "Point", "srid": 4326,
            "campos": [{"nome": c, "tipo": "text", "alias": c} for c in COLUNAS_CAMADA],
            "fonte": "hospedada", "procedencia": procedencia,
            "estatisticas": {"feicoes": estat["feicoes"], "extent_nativo": estat["extent"],
                              "por_campo": {}, "calculadas_em": None},
            "geocodificacao": {"geocodificacao_id": gid, "job_id": str(ctx.job_id), "resumo": resumo,
                                "base_enderecos": base},
        }
        titulo = lote["titulo"][:250]
        extent = estat["extent"]
        with ctx.db() as cur:
            if tabela_ja_existia:
                cur.execute(
                    "UPDATE plat.item SET dados = %s, tamanho_bytes = %s, modificado_por = %s, "
                    "extent = " + ("ST_MakeEnvelope(%s,%s,%s,%s,4326)" if extent else "NULL")
                    + ", extent_origem = %s WHERE id = %s::uuid",
                    [_jsonb(item_dados), tamanho_bytes, ctx.usuario_id] + (extent if extent else [])
                    + [("dado" if extent else None), item_id],
                )
            else:
                cur.execute(
                    "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                    "extent, extent_origem, criado_por, modificado_por) "
                    "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, "
                    + ("ST_MakeEnvelope(%s,%s,%s,%s,4326)" if extent else "NULL") + ", %s, %s, %s)",
                    [item_id, ctx.tenant_id, titulo, ctx.usuario_id, _jsonb(item_dados), tamanho_bytes]
                    + (extent if extent else []) + [("dado" if extent else None), ctx.usuario_id,
                                                     ctx.usuario_id],
                )
                cur.execute(
                    "INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id) "
                    "VALUES (%s::uuid, %s::uuid, 'arquivo_de_camada', %s) ON CONFLICT DO NOTHING",
                    (lote["arquivo_id"], item_id, ctx.tenant_id),
                )
            cur.execute(
                "UPDATE plat.geocodificacao SET estado = 'concluida', item_id = %s::uuid, "
                "linhas_total = %s, resolvidas = %s, pendentes = %s, malformadas = %s, manuais = %s, "
                "resumo = %s, base_enderecos = %s, erro = NULL, atualizado_em = now() WHERE id = %s::uuid",
                (item_id, contagens["total"], contagens["resolvidas"], contagens["pendentes"],
                 contagens["malformadas"], contagens["manuais"], _jsonb(resumo), _jsonb(base), gid),
            )
            cur.execute(
                "SELECT plat.evento_registrar('geocodificacoes/concluir', 'item', %s, %s::jsonb, NULL, NULL)",
                (item_id, json.dumps({"geocodificacao_id": gid, "job_id": str(ctx.job_id),
                                       "linhas": contagens["total"]}, default=str)),
            )
        ctx.progresso(100, "concluído")
        return {"item_id": item_id, "geocodificacao_id": gid, "resumo": resumo}
    except Cancelado:
        _limpar_orfao(ctx, schema, nome_tabela, item_id, tabela_ja_existia)
        _marcar(ctx, gid, "cancelada", "cancelamento solicitado")
        raise
    except FalhaDefinitiva as e:
        _limpar_orfao(ctx, schema, nome_tabela, item_id, tabela_ja_existia)
        _marcar(ctx, gid, "falhou", str(e))
        raise


def _marcar(ctx, gid: str, estado: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.geocodificacao SET estado = %s, erro = %s, atualizado_em = now() "
            "WHERE id = %s::uuid AND estado NOT IN ('concluida','falhou','cancelada')",
            (estado, erro[:2000], gid),
        )


def _limpar_orfao(ctx, schema: str, nome_tabela: str, item_id: str, ja_existia: bool) -> None:
    """Execução que falhou ANTES de publicar não pode deixar tabela nem item pela metade. Só a PRIMEIRA
    execução limpa: quando a camada já existia (re-geocodificação), derrubá-la apagaria o trabalho anterior,
    inclusive os pontos arrastados à mão."""
    if ja_existia:
        return
    with ctx.db() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{nome_tabela}" CASCADE')
        cur.execute("DELETE FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,))
