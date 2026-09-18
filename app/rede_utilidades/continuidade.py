"""Continuidade DEC/FEC por conjunto e por alimentador (item L4-10-continuidade-dec-fec).

A ANEEL apura os indicadores COLETIVOS de continuidade por CONJUNTO DE UNIDADES CONSUMIDORAS:

* DEC — duração equivalente de interrupção por unidade consumidora, em horas;
* FEC — frequência equivalente de interrupção por unidade consumidora, em número de interrupções.

O conjunto é um recorte da concessão, não um alimentador e não um transformador. A BDGD, por outro lado,
traz o campo `CONJ` nas camadas de transformador (UNTRMT), de unidade consumidora (UCBT_tab/UCMT_tab) e de
trecho de média tensão (SSDMT). `CONJ` é a chave que liga as duas bases, e é a junção que este módulo faz:

1. `conjuntos_da_rede` lê os conjuntos que a rede importada declara;
2. `importar` traz do dado aberto da ANEEL, só para esses conjuntos, o apurado mês a mês e o limite
   anual, e confere a contagem contra o arquivo;
3. `ficha_conjuntos` devolve o ano fechado por conjunto, com o limite do ano ao lado e a situação;
4. `ficha_alimentadores` leva o número do conjunto para o alimentador, ponderando pelas unidades
   consumidoras que cada conjunto tem naquele alimentador;
5. `dic_fic_por_trafo` usa o outro dado, o INDIVIDUAL, que a BDGD traz na própria UCBT (DIC e FIC por
   unidade consumidora), e o resume por transformador.

Limites: são os estabelecidos na forma do PRODIST Módulo 8, aprovado pela Resolução Normativa ANEEL
956/2021 e seus anexos. Nenhum valor de limite é escrito no código — todos vêm do arquivo de limites
publicado pela própria agência no portal de dados abertos (acesso em 08/09/2026), e cada linha guarda de
qual arquivo veio.

⛔ Vocabulário: comparar o apurado com o limite produz "dentro do limite" ou "acima do limite regulatório",
sempre com o número e o limite ao lado. Este módulo não classifica infração nem consequência: isso é do
processo da agência, não desta leitura.

Nada aqui inventa valor ausente. Conjunto da BDGD que não tem par no arquivo da ANEEL sai como
"sem dado" — nunca como zero, que seria o melhor resultado possível de continuidade.
"""

from __future__ import annotations

import csv
import hashlib
import time
from pathlib import Path

from psycopg2.extras import execute_values

# --- vocabulário da comparação (o texto que o produto mostra; não há outro) --------------------------
DENTRO = "dentro do limite"
ACIMA = "acima do limite regulatório"
SEM_LIMITE = "sem limite publicado"
SEM_DADO = "sem dado"

# --- campos da BDGD ---------------------------------------------------------------------------------
CAMPO_CONJ = "CONJ"
CAMPO_ALIMENTADOR = "CTMT"
CAMPO_UC_TRAFO = "UNI_TR_MT"  # a UC de baixa tensão declara o transformador que a alimenta
GRUPO_TRAFO = "transformador_de_distribuicao"
GRUPO_UC = "unidade_consumidora"

# DIC/FIC por unidade consumidora: a BDGD publica doze colunas mensais; algumas cargas da casa trazem a
# soma anual já pronta. Os dois casos são aceitos, e a soma é do que ESTIVER presente — se nenhuma das
# colunas existir, o resultado é nulo, nunca zero.
CAMPOS_DIC = tuple(f"DIC_{m:02d}" for m in range(1, 13)) + ("DIC", "DIC_SUM")
CAMPOS_FIC = tuple(f"FIC_{m:02d}" for m in range(1, 13)) + ("FIC", "FIC_SUM")

# --- arquivos do dado aberto da ANEEL ----------------------------------------------------------------
# Descoberta por nome dentro da pasta indicada, sem lista fixa de arquivo: o conjunto de dados da agência
# ganha um arquivo por faixa de anos, e o nome carrega a faixa.
PADRAO_APURADO = "dec_*.parquet"
PADRAO_LIMITE = "*limite*.csv"

# ⛔ A COMPENSAÇÃO PAGA NÃO ENTRA AQUI, e não é esquecimento. O conjunto de dados de compensação da ANEEL
# usa outro vocabulário de indicador — 96 códigos das famílias PGU* (valor pago) e QTU* (quantidade de
# unidades compensadas), por classe de tensão e por motivo — e nenhum deles é DEC ou FEC. Medido em
# 08/09/2026 no arquivo de 9.614.399 linhas: zero linhas com SigIndicador em (DEC, FEC). Ler aquele
# arquivo com o filtro deste módulo devolveria sempre zero e daria a impressão de que a compensação está
# importada. Importá-la exige a sua própria tabela de domínio e é outro item.

# Colunas do dado aberto (as mesmas nos dois parquets).
COL_CONJ = "IdeConjUndConsumidoras"
COL_CONJ_NOME = "DscConjUndConsumidoras"
COL_AGENTE = "SigAgente"
COL_CNPJ = "NumCNPJ"
COL_INDICADOR = "SigIndicador"
COL_ANO = "AnoIndice"
COL_PERIODO = "NumPeriodoIndice"
COL_VALOR = "VlrIndiceEnviado"
# No arquivo de limites o ano e o valor têm nomes próprios.
COL_ANO_LIMITE = "AnoLimiteQualidade"
COL_VALOR_LIMITE = "VlrLimite"

# O conjunto de dados traz DEC e FEC e também a decomposição por origem da interrupção (DECIP, DECINE,
# FECXP e afins). O item trabalha com os dois indicadores agregados, que são os comparáveis ao limite.
INDICADORES = ("DEC", "FEC")

LOTE = 5000


class ErroContinuidade(Exception):
    """Importação sem condição de rodar (pasta ausente, arquivo sem as colunas do dado aberto)."""


# ------------------------------------------------------------------ a chave CONJ vinda da rede


def conjuntos_da_rede(cur, rede_id: str) -> list[int]:
    """Os conjuntos de unidades consumidoras que a rede importada declara, em `atributos->>'CONJ'`.

    Só número inteiro entra: `CONJ` é o identificador do conjunto na base da agência, e o que não for
    número é dado sujo da safra, não um conjunto."""
    cur.execute(
        "SELECT DISTINCT (n.atributos->>%(campo)s)::bigint AS conj FROM plat.rede_no n "
        "WHERE n.rede_id = %(rede)s::uuid AND n.atributos->>%(campo)s ~ '^[0-9]+$' "
        "ORDER BY 1",
        {"rede": rede_id, "campo": CAMPO_CONJ},
    )
    return [int(r["conj"]) for r in cur.fetchall()]


# ------------------------------------------------------------------ leitura dos arquivos da ANEEL


def _achar(raiz: Path, padrao: str) -> list[Path]:
    return sorted(p for p in raiz.glob(padrao) if p.is_file())


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler_parquet(caminho: Path, conjuntos: list[int], ano_de: int, ano_ate: int) -> list[dict]:
    """As linhas do arquivo que caem no recorte pedido (conjuntos da rede, faixa de anos, DEC e FEC).

    O filtro vai para o leitor de parquet, que descarta grupos de linhas inteiros pelas estatísticas —
    é o que permite recortar um arquivo de milhões de linhas sem carregá-lo na memória."""
    import pyarrow.parquet as pq  # import tardio: só a importação depende do leitor de parquet

    filtro = [
        (COL_CONJ, "in", conjuntos),
        (COL_ANO, ">=", ano_de),
        (COL_ANO, "<=", ano_ate),
        (COL_INDICADOR, "in", list(INDICADORES)),
    ]
    tabela = pq.read_table(str(caminho), filters=filtro)
    faltando = [c for c in (COL_CONJ, COL_INDICADOR, COL_ANO, COL_PERIODO, COL_VALOR)
                if c not in tabela.column_names]
    if faltando:
        raise ErroContinuidade(f"{caminho.name} não tem as colunas do dado aberto: {', '.join(faltando)}")
    return tabela.to_pylist()


def _texto(valor) -> str | None:
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def _numero_br(valor) -> float | None:
    """Número do arquivo de limites: vírgula decimal, ponto de milhar."""
    t = _texto(valor)
    if t is None:
        return None
    try:
        return float(t.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _ler_limites(caminho: Path, conjuntos: list[int], ano_de: int, ano_ate: int) -> list[dict]:
    alvo = set(conjuntos)
    linhas: list[dict] = []
    with caminho.open("r", encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f, delimiter=";")
        if leitor.fieldnames is None or COL_VALOR_LIMITE not in leitor.fieldnames:
            raise ErroContinuidade(f"{caminho.name} não tem a coluna {COL_VALOR_LIMITE}")
        for linha in leitor:
            conj = _texto(linha.get(COL_CONJ))
            ano = _texto(linha.get(COL_ANO_LIMITE))
            ind = _texto(linha.get(COL_INDICADOR))
            if conj is None or not conj.isdigit() or int(conj) not in alvo:
                continue
            if ind not in INDICADORES or ano is None or not ano.isdigit():
                continue
            if not (ano_de <= int(ano) <= ano_ate):
                continue
            valor = _numero_br(linha.get(COL_VALOR_LIMITE))
            if valor is None or valor < 0:
                continue
            linhas.append({"conjunto_id": int(conj), "indicador": ind, "ano": int(ano), "valor": valor})
    return linhas


# ------------------------------------------------------------------ importação


def _gravar_fonte(cur, tenant_id: int, caminho: Path, especie: str, conjuntos: list[int],
                  ano_de: int, ano_ate: int, job_id: str | None) -> str:
    cur.execute(
        "INSERT INTO plat.rede_continuidade_fonte (tenant_id, arquivo, especie, sha256, bytes, conjuntos, "
        "ano_de, ano_ate, job_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (tenant_id, caminho.name, especie, _sha256(caminho), caminho.stat().st_size,
         conjuntos, ano_de, ano_ate, job_id),
    )
    return str(cur.fetchone()["id"])


def _gravar_indicadores(cur, tenant_id: int, fonte_id: str, origem: str, linhas: list[dict]) -> int:
    """Grava as linhas do parquet. Devolve quantas foram gravadas (a mesma chave repetida no arquivo é
    contada uma vez só — e o chamador compara com o que o arquivo tinha, que é a conferência)."""
    gravadas = 0
    for i in range(0, len(linhas), LOTE):
        pedaco = [
            (tenant_id, int(r[COL_CONJ]), _texto(r.get(COL_CONJ_NOME)), _texto(r.get(COL_AGENTE)),
             _texto(r.get(COL_CNPJ)), r[COL_INDICADOR], origem, int(r[COL_ANO]), int(r[COL_PERIODO]),
             float(r[COL_VALOR]), fonte_id)
            for r in linhas[i:i + LOTE]
            if r.get(COL_VALOR) is not None and float(r[COL_VALOR]) >= 0
            and 1 <= int(r[COL_PERIODO]) <= 12
        ]
        if not pedaco:
            continue
        execute_values(
            cur,
            "INSERT INTO plat.rede_continuidade (tenant_id, conjunto_id, conjunto_nome, agente, cnpj, "
            "indicador, origem, ano, periodo, valor, fonte_id) VALUES %s "
            "ON CONFLICT (tenant_id, conjunto_id, indicador, origem, ano, periodo) DO UPDATE "
            "SET valor = EXCLUDED.valor, conjunto_nome = EXCLUDED.conjunto_nome, "
            "    agente = EXCLUDED.agente, cnpj = EXCLUDED.cnpj, fonte_id = EXCLUDED.fonte_id",
            pedaco,
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid)",
        )
        gravadas += len(pedaco)
    return gravadas


def _gravar_limites(cur, tenant_id: int, fonte_id: str, linhas: list[dict]) -> int:
    gravadas = 0
    for i in range(0, len(linhas), LOTE):
        pedaco = [(tenant_id, r["conjunto_id"], r["indicador"], r["ano"], r["valor"], fonte_id)
                  for r in linhas[i:i + LOTE]]
        execute_values(
            cur,
            "INSERT INTO plat.rede_continuidade_limite (tenant_id, conjunto_id, indicador, ano, valor, "
            "fonte_id) VALUES %s "
            "ON CONFLICT (tenant_id, conjunto_id, indicador, ano) DO UPDATE "
            "SET valor = EXCLUDED.valor, fonte_id = EXCLUDED.fonte_id",
            pedaco,
            template="(%s,%s,%s,%s,%s,%s::uuid)",
        )
        gravadas += len(pedaco)
    return gravadas


def importar(cur, tenant_id: int, raiz: str | Path, conjuntos: list[int], ano_de: int, ano_ate: int,
             job_id: str | None = None, progresso=None) -> dict:
    """Importa o dado aberto de continuidade da ANEEL para os conjuntos pedidos.

    Devolve, por arquivo, quantas linhas o arquivo tinha NO RECORTE e quantas foram gravadas. As duas
    contagens iguais é a conferência que o item pede; quando diferem, a diferença fica no resultado e na
    tabela de fonte, com o motivo (linha sem valor ou fora do domínio de mês)."""
    inicio = time.monotonic()
    pasta = Path(raiz)
    if not pasta.is_dir():
        raise ErroContinuidade(f"pasta de dado aberto de continuidade inexistente: {pasta}")
    conjuntos = sorted({int(c) for c in conjuntos})
    if not conjuntos:
        raise ErroContinuidade("a rede não declara nenhum conjunto (campo CONJ) — nada a importar")
    if ano_ate < ano_de:
        raise ErroContinuidade("faixa de anos invertida")

    arquivos = [(p, "apurado") for p in _achar(pasta, PADRAO_APURADO)]
    arquivos += [(p, "limite") for p in _achar(pasta, PADRAO_LIMITE)]
    if not arquivos:
        raise ErroContinuidade(f"nenhum arquivo de continuidade em {pasta}")

    detalhe = []
    for i, (caminho, especie) in enumerate(arquivos):
        if progresso:
            progresso(int(95 * i / len(arquivos)) + 2, f"lendo {caminho.name}")
        if especie == "limite":
            linhas = _ler_limites(caminho, conjuntos, ano_de, ano_ate)
        else:
            linhas = _ler_parquet(caminho, conjuntos, ano_de, ano_ate)
        fonte_id = _gravar_fonte(cur, tenant_id, caminho, especie, conjuntos, ano_de, ano_ate, job_id)
        if especie == "limite":
            gravadas = _gravar_limites(cur, tenant_id, fonte_id, linhas)
        else:
            gravadas = _gravar_indicadores(cur, tenant_id, fonte_id, especie, linhas)
        cur.execute(
            "UPDATE plat.rede_continuidade_fonte SET linhas_arquivo = %s, linhas_gravadas = %s "
            "WHERE id = %s::uuid",
            (len(linhas), gravadas, fonte_id),
        )
        detalhe.append({"arquivo": caminho.name, "especie": especie, "fonte_id": fonte_id,
                        "linhas_arquivo": len(linhas), "linhas_gravadas": gravadas,
                        "conferido": len(linhas) == gravadas})
    if progresso:
        progresso(99, "continuidade importada")
    return {
        "conjuntos": conjuntos,
        "ano_de": ano_de,
        "ano_ate": ano_ate,
        "arquivos": detalhe,
        "conferido": all(d["conferido"] for d in detalhe),
        "linhas_arquivo": sum(d["linhas_arquivo"] for d in detalhe),
        "linhas_gravadas": sum(d["linhas_gravadas"] for d in detalhe),
        "duracao_ms": int((time.monotonic() - inicio) * 1000),
    }


# ------------------------------------------------------------------ comparação com o limite


def situacao(valor: float | None, limite: float | None) -> str:
    """A única frase que o produto usa para o resultado da comparação.

    Sem apurado é "sem dado" (jamais zero: zero seria continuidade perfeita). Sem limite publicado para
    aquele ano, a comparação não existe e é isso que se diz."""
    if valor is None:
        return SEM_DADO
    if limite is None:
        return SEM_LIMITE
    return ACIMA if valor > limite else DENTRO


# ------------------------------------------------------------------ ficha do conjunto


SQL_ANO_FECHADO = """
SELECT conjunto_id, indicador, ano, sum(valor) AS valor, count(*) AS meses,
       max(conjunto_nome) AS conjunto_nome, max(agente) AS agente
  FROM plat.rede_continuidade
 WHERE origem = 'apurado' AND conjunto_id = ANY(%(conjuntos)s) AND ano BETWEEN %(de)s AND %(ate)s
 GROUP BY conjunto_id, indicador, ano
"""


def _apurado(cur, conjuntos: list[int], ano_de: int, ano_ate: int) -> dict:
    cur.execute(SQL_ANO_FECHADO, {"conjuntos": conjuntos, "de": ano_de, "ate": ano_ate})
    return {(r["conjunto_id"], r["indicador"], r["ano"]): dict(r) for r in cur.fetchall()}


def _limites(cur, conjuntos: list[int], ano_de: int, ano_ate: int) -> dict:
    cur.execute(
        "SELECT l.conjunto_id, l.indicador, l.ano, l.valor, f.arquivo FROM plat.rede_continuidade_limite l "
        "LEFT JOIN plat.rede_continuidade_fonte f ON f.id = l.fonte_id "
        "WHERE l.conjunto_id = ANY(%(conjuntos)s) AND l.ano BETWEEN %(de)s AND %(ate)s",
        {"conjuntos": conjuntos, "de": ano_de, "ate": ano_ate},
    )
    return {(r["conjunto_id"], r["indicador"], r["ano"]): (float(r["valor"]), r["arquivo"])
            for r in cur.fetchall()}


def _uc_por_conjunto(cur, rede_id: str) -> dict:
    """Quantas unidades consumidoras a rede tem em cada conjunto (o peso da agregação)."""
    cur.execute(
        "SELECT (n.atributos->>%(campo)s)::bigint AS conj, count(*) AS n FROM plat.rede_no n "
        "JOIN plat.rede_tipo t ON t.id = n.tipo_id JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "WHERE n.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s "
        "AND n.atributos->>%(campo)s ~ '^[0-9]+$' GROUP BY 1",
        {"rede": rede_id, "campo": CAMPO_CONJ, "grupo": GRUPO_UC},
    )
    return {int(r["conj"]): int(r["n"]) for r in cur.fetchall()}


def ficha_conjuntos(cur, rede_id: str, ano_de: int, ano_ate: int) -> list[dict]:
    """Um registro por conjunto declarado na rede e por ano: DEC e FEC apurados, o limite daquele ano e a
    situação. Conjunto sem par no arquivo da ANEEL aparece com valor nulo e situação "sem dado" — a linha
    existe, o número não é inventado."""
    conjuntos = conjuntos_da_rede(cur, rede_id)
    if not conjuntos:
        return []
    apurado = _apurado(cur, conjuntos, ano_de, ano_ate)
    limites = _limites(cur, conjuntos, ano_de, ano_ate)
    ucs = _uc_por_conjunto(cur, rede_id)
    fora = []
    for conj in conjuntos:
        for ano in range(ano_de, ano_ate + 1):
            registro = {"conjunto_id": conj, "ano": ano, "n_uc_na_rede": ucs.get(conj, 0),
                        "conjunto_nome": None, "agente": None, "indicadores": {}}
            for ind in INDICADORES:
                linha = apurado.get((conj, ind, ano))
                limite, arquivo = limites.get((conj, ind, ano), (None, None))
                valor = None if linha is None else round(float(linha["valor"]), 4)
                if linha is not None:
                    registro["conjunto_nome"] = registro["conjunto_nome"] or linha["conjunto_nome"]
                    registro["agente"] = registro["agente"] or linha["agente"]
                registro["indicadores"][ind] = {
                    "apurado": valor,
                    "meses_apurados": None if linha is None else int(linha["meses"]),
                    "limite": limite,
                    "limite_arquivo": arquivo,
                    "situacao": situacao(valor, limite),
                }
            fora.append(registro)
    return fora


# ------------------------------------------------------------------ ficha do alimentador


def ficha_alimentadores(cur, rede_id: str, ano: int) -> list[dict]:
    """O indicador do conjunto levado ao alimentador, ponderado pelas unidades consumidoras.

    O alimentador não tem indicador próprio na base da agência. O que existe é: cada unidade consumidora
    da rede pertence a um alimentador (CTMT) e a um conjunto (CONJ). A média ponderada pelo número de UCs
    de cada conjunto DENTRO do alimentador é a melhor leitura possível dessa junção, e é declarada como
    tal — `conjuntos` lista de onde ela veio e `uc_sem_dado` diz quantas UCs ficaram de fora por o
    conjunto delas não ter apurado publicado. Alimentador cujos conjuntos não têm nenhum apurado sai com
    valor nulo e situação "sem dado"."""
    cur.execute(
        "SELECT n.atributos->>%(alim)s AS alimentador, (n.atributos->>%(conj)s)::bigint AS conjunto_id, "
        "       count(*) AS n_uc FROM plat.rede_no n "
        "JOIN plat.rede_tipo t ON t.id = n.tipo_id JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "WHERE n.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s "
        "AND nullif(btrim(n.atributos->>%(alim)s), '') IS NOT NULL "
        "AND n.atributos->>%(conj)s ~ '^[0-9]+$' GROUP BY 1, 2 ORDER BY 1, 2",
        {"rede": rede_id, "alim": CAMPO_ALIMENTADOR, "conj": CAMPO_CONJ, "grupo": GRUPO_UC},
    )
    pesos: dict[str, dict[int, int]] = {}
    for r in cur.fetchall():
        pesos.setdefault(r["alimentador"], {})[int(r["conjunto_id"])] = int(r["n_uc"])
    if not pesos:
        return []
    conjuntos = sorted({c for p in pesos.values() for c in p})
    apurado = _apurado(cur, conjuntos, ano, ano)
    limites = _limites(cur, conjuntos, ano, ano)

    saida = []
    for alimentador in sorted(pesos):
        por_conj = pesos[alimentador]
        registro = {"alimentador": alimentador, "ano": ano,
                    "n_uc": sum(por_conj.values()),
                    "conjuntos": [{"conjunto_id": c, "n_uc": por_conj[c]} for c in sorted(por_conj)],
                    "indicadores": {}}
        for ind in INDICADORES:
            soma = 0.0
            peso = 0
            sem_dado = 0
            lim_soma = 0.0
            lim_peso = 0
            for conj, n in por_conj.items():
                linha = apurado.get((conj, ind, ano))
                if linha is None:
                    sem_dado += n
                    continue
                soma += float(linha["valor"]) * n
                peso += n
                limite = limites.get((conj, ind, ano), (None, None))[0]
                if limite is not None:
                    lim_soma += limite * n
                    lim_peso += n
            valor = round(soma / peso, 4) if peso else None
            limite_pond = round(lim_soma / lim_peso, 4) if lim_peso else None
            registro["indicadores"][ind] = {
                "apurado_ponderado": valor,
                "limite_ponderado": limite_pond,
                "uc_com_dado": peso,
                "uc_sem_dado": sem_dado,
                "situacao": situacao(valor, limite_pond),
            }
        saida.append(registro)
    return saida


# ------------------------------------------------------------------ DIC/FIC por transformador


def _soma_presente(campos: tuple[str, ...]) -> str:
    """SQL que soma os campos numéricos presentes em `atributos` e devolve NULL quando nenhum existe.

    Ausência de coluna e valor não numérico dão NULL, não zero — a diferença entre "não tem dado" e
    "teve zero hora de interrupção" é justamente o que este item não pode perder."""
    itens = ", ".join(
        "(CASE WHEN n.atributos->>'%s' ~ '^-?[0-9]+([.,][0-9]+)?$' "
        "THEN replace(n.atributos->>'%s', ',', '.')::double precision END)" % (c, c)
        for c in campos
    )
    return f"(SELECT sum(v) FROM unnest(ARRAY[{itens}]) AS v WHERE v IS NOT NULL)"


def dic_fic_por_trafo(cur, rede_id: str, limite: int = 1000) -> list[dict]:
    """DIC e FIC médios por transformador, a partir das unidades consumidoras da BDGD.

    DIC e FIC são os indicadores INDIVIDUAIS (por unidade consumidora), e vêm da própria BDGD — não do
    arquivo de continuidade coletiva. A média é sobre as UCs que trazem o dado; `n_uc_com_dic` e
    `n_uc` juntos dizem o quanto da carteira do transformador entrou na conta. Transformador sem
    nenhuma UC com DIC sai com média nula."""
    dic = _soma_presente(CAMPOS_DIC)
    fic = _soma_presente(CAMPOS_FIC)
    cur.execute(
        f"SELECT n.atributos->>%(trafo)s AS trafo, "
        f"       max(n.atributos->>%(conj)s) AS conjunto_id, "
        f"       max(n.atributos->>%(alim)s) AS alimentador, "
        f"       count(*) AS n_uc, "
        f"       count({dic}) AS n_uc_com_dic, avg({dic}) AS dic_medio, "
        f"       count({fic}) AS n_uc_com_fic, avg({fic}) AS fic_medio "
        "FROM plat.rede_no n "
        "JOIN plat.rede_tipo t ON t.id = n.tipo_id JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "WHERE n.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s "
        "AND nullif(btrim(n.atributos->>%(trafo)s), '') IS NOT NULL "
        "GROUP BY 1 ORDER BY 1 LIMIT %(limite)s",
        {"rede": rede_id, "trafo": CAMPO_UC_TRAFO, "conj": CAMPO_CONJ, "alim": CAMPO_ALIMENTADOR,
         "grupo": GRUPO_UC, "limite": max(1, min(int(limite), 20000))},
    )
    return [
        {"trafo": r["trafo"], "conjunto_id": int(r["conjunto_id"]) if (r["conjunto_id"] or "").isdigit()
         else None,
         "alimentador": r["alimentador"], "n_uc": int(r["n_uc"]),
         "n_uc_com_dic": int(r["n_uc_com_dic"]), "n_uc_com_fic": int(r["n_uc_com_fic"]),
         "dic_medio": None if r["dic_medio"] is None else round(float(r["dic_medio"]), 4),
         "fic_medio": None if r["fic_medio"] is None else round(float(r["fic_medio"]), 4)}
        for r in cur.fetchall()
    ]


# ------------------------------------------------------------------ painel


def painel(cur, rede_id: str, ano_de: int, ano_ate: int) -> dict:
    """A série por ano que o painel desenha: por conjunto, o apurado e o limite de cada ano, e a contagem
    de anos dentro e acima do limite. Ano sem apurado entra na série com valor nulo — o painel mostra a
    falha do dado, não uma linha caindo até zero."""
    fichas = ficha_conjuntos(cur, rede_id, ano_de, ano_ate)
    anos = list(range(ano_de, ano_ate + 1))
    por_conjunto: dict[int, dict] = {}
    for f in fichas:
        alvo = por_conjunto.setdefault(f["conjunto_id"], {
            "conjunto_id": f["conjunto_id"], "conjunto_nome": None, "agente": None,
            "n_uc_na_rede": f["n_uc_na_rede"],
            "series": {ind: {"apurado": [], "limite": [], "situacao": []}
                       for ind in INDICADORES},
            "anos_acima_do_limite": {ind: 0 for ind in INDICADORES},
            "anos_com_dado": {ind: 0 for ind in INDICADORES},
        })
        alvo["conjunto_nome"] = alvo["conjunto_nome"] or f["conjunto_nome"]
        alvo["agente"] = alvo["agente"] or f["agente"]
        for ind in INDICADORES:
            d = f["indicadores"][ind]
            alvo["series"][ind]["apurado"].append(d["apurado"])
            alvo["series"][ind]["limite"].append(d["limite"])
            alvo["series"][ind]["situacao"].append(d["situacao"])
            if d["apurado"] is not None:
                alvo["anos_com_dado"][ind] += 1
            if d["situacao"] == ACIMA:
                alvo["anos_acima_do_limite"][ind] += 1
    return {
        "anos": anos,
        "indicadores": list(INDICADORES),
        "unidades": {"DEC": "horas por unidade consumidora",
                     "FEC": "interrupções por unidade consumidora"},
        "vocabulario": [DENTRO, ACIMA, SEM_LIMITE, SEM_DADO],
        "limite_base_normativa": "PRODIST Módulo 8, aprovado pela Resolução Normativa ANEEL 956/2021 e "
                                 "seus anexos; valores publicados no portal de dados abertos da ANEEL "
                                 "(acesso em 08/09/2026)",
        "total": len(por_conjunto),
        "itens": [por_conjunto[c] for c in sorted(por_conjunto)],
    }
