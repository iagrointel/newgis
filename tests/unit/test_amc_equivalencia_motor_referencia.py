"""Item L3-01-j: o motor multicritério genérico reproduz o motor logístico de referência da casa.

O motor de referência é um produto de OUTRO projeto desta casa, já materializado num schema próprio do
banco compartilhado. Aqui ele é lido SÓ para leitura e SÓ como oráculo: nenhuma linha é escrita, nenhuma
tabela é criada. O nome do schema NÃO está escrito neste repositório — vem da variável de ambiente
`PLAT_MOTOR_REFERENCIA_ESQUEMA`, porque o repositório é público e o schema carrega o nome de um cliente.
Sem a variável, os testes que precisam do oráculo são pulados com essa razão dita em voz alta.

O que se afirma, e o que cada teste prova:

1. `test_modelo_valido` — os 19 fatores do motor de referência estão reescritos no vocabulário do motor
   genérico (`docs/modelos/motor_logistico_referencia.json`), o documento passa no esquema
   `amc_modelo.v1` e os identificadores dos fatores são exatamente os 19 do motor de referência.
2. `test_celulas` — dado o MESMO valor por fator em cada uma das células, o combinador genérico
   (`app.amc.combinacao.combinar`) devolve, célula a célula, a mesma favorabilidade que a regra do motor
   de referência recalculada de forma independente em SQL (aritmética `numeric` do Postgres, não numpy).
3. `test_vetos_e_motivos_das_celulas` — o conjunto de células vetadas e o motivo de cada uma são os
   mesmos dos dois lados; veto entra como fração vetada 1, nunca como fator de nota baixa.
4. `test_feicoes` — o mesmo, feição a feição, com a nota multiplicada por (1 − fração vetada).
5. `test_agregacao_de_celulas_para_feicoes` — `app.amc.agregacao` reproduz a passagem célula → feição do
   motor de referência (média ponderada pela área de interseção sobre as células não vetadas, fração
   vetada por área, motivo da maior área vetada), comparada com a tabela de feições já materializada.
6. `test_transformacoes_do_valor_bruto` — para os fatores em que o valor BRUTO está materializado, a
   transformação declarada no modelo reproduz a favorabilidade do motor de referência a partir dele.

Tolerância do portão: |Δ| ≤ 0,5 ponto em pelo menos 99,5 % das unidades. As divergências que sobram são
listadas e explicadas na medida, nunca escondidas — a fonte esperada delas é a de armazenamento: o motor
de referência grava a nota por fator como inteiro (`smallint`) e a área de interseção como ponto
flutuante, então a mesma conta feita em `numeric` e em `float64` discorda no último dígito e, quando o
valor cai exatamente no meio, discorda em 1 ponto inteiro por causa da regra de desempate do
arredondamento (meio para longe do zero no banco, meio para o par no numpy).
"""

import io
import json
import os
import subprocess
import time

import numpy as np
import pytest

from app.amc import agregacao, combinacao, esquema
from app.amc import transformacoes as tr

ITEM = "L3-01-j"
TOLERANCIA = 0.5
EPSILON = 1e-9
PCT_MINIMO = 99.5
MODELO = "docs/modelos/motor_logistico_referencia.json"

# os 19 fatores disponíveis do motor de referência, na ordem em que ele os declara
FATORES = ["decl", "zon", "gru", "rod", "disp", "ener", "agua", "restr", "varzea", "press",
           "dens", "roubo", "trib", "renda", "rlapp", "polos", "se", "cluster", "mine"]

# perfis de peso usados na comparação. Pesos são escolha de quem decide, nunca medida nossa; aqui servem
# só para exercitar o combinador em três regimes diferentes (esparso, cheio e sorteado).
PERFIL_DECLARADO = {"zon": 5, "gru": 5, "rod": 4, "decl": 3, "disp": 3, "ener": 2, "agua": 1,
                    "restr": 3, "varzea": 2, "press": 1, "dens": 1, "cluster": 2, "se": 2,
                    "polos": 1, "mine": 5}
PERFIL_IGUAL = {f: 3 for f in FATORES}
PERFIL_SORTEADO = {f: int(v) for f, v in
                   zip(FATORES, np.random.default_rng(20260907).integers(0, 6, len(FATORES)), strict=True)}
PERFIS = {"declarado": PERFIL_DECLARADO, "iguais": PERFIL_IGUAL, "sorteado": PERFIL_SORTEADO}


def esquema_referencia() -> str:
    nome = os.environ.get("PLAT_MOTOR_REFERENCIA_ESQUEMA", "").strip()
    if not nome:
        pytest.skip("sem PLAT_MOTOR_REFERENCIA_ESQUEMA: o oráculo do motor logístico de referência vive "
                    "num schema cujo nome não pode ser escrito neste repositório")
    if not nome.replace("_", "").isalnum():
        pytest.fail("PLAT_MOTOR_REFERENCIA_ESQUEMA tem de ser um identificador simples")
    return nome


def copiar(sql: str) -> list[list[str]]:
    """Lê uma consulta SÓ DE LEITURA do oráculo em CSV. `sudo -u postgres` porque o schema do motor de
    referência é de outro projeto e a role da plataforma não tem (nem deve ter) acesso de escrita a ele."""
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-Atqc",
         f"SET statement_timeout='300s'; COPY ({sql}) TO STDOUT WITH (FORMAT csv, NULL '')"],
        capture_output=True, text=True, timeout=600, check=True,
    )
    import csv
    return list(csv.reader(io.StringIO(r.stdout)))


def numero(t: str) -> float:
    return float("nan") if t == "" else float(t)


def valores_sql(pesos: dict, colunas: list[str]) -> str:
    """Lista VALUES (peso, favorabilidade) para o oráculo somar em `numeric`, sem passar por numpy."""
    partes = [f"({float(pesos[f])}::numeric, {c}::numeric)" for f, c in zip(FATORES, colunas, strict=True)
              if pesos.get(f, 0)]
    return ", ".join(partes)


@pytest.fixture(scope="module")
def celulas():
    """Uma linha por célula: veto, motivo e as 19 favorabilidades do motor de referência."""
    e = esquema_referencia()
    cols = ", ".join(f"f_{f}" for f in FATORES)
    linhas = copiar(f"SELECT hex_id, veto, veto_motivo, {cols} FROM {e}.hex_fav ORDER BY hex_id")
    ids = [int(li[0]) for li in linhas]
    veto = np.array([li[1] == "t" for li in linhas])
    motivo = [li[2] or None for li in linhas]
    m = np.array([[numero(x) for x in li[3:]] for li in linhas], dtype=np.float64)
    return {"ids": ids, "veto": veto, "motivo": motivo, "fatores": m}


@pytest.fixture(scope="module")
def feicoes():
    e = esquema_referencia()
    cols = ", ".join(f"f_{f}" for f in FATORES)
    linhas = copiar(f"SELECT car_cod, pct_vetado, veto_principal, n_cel, {cols} "
                    f"FROM {e}.imoveis_fav ORDER BY car_cod")
    ids = [li[0] for li in linhas]
    pct = np.array([0.0 if li[1] == "" else float(li[1]) for li in linhas])
    m = np.array([[numero(x) for x in li[4:]] for li in linhas], dtype=np.float64)
    return {"ids": ids, "pct_vetado": pct, "veto_principal": [li[2] or None for li in linhas],
            "n_cel": [None if li[3] == "" else int(li[3]) for li in linhas], "fatores": m}


def combinar_perfil(matriz, pesos, fracao_vetada=None, motivo=None):
    w = [float(pesos.get(f, 0.0)) for f in FATORES]
    return combinacao.combinar(matriz, w, fracao_vetada=fracao_vetada, motivo_veto=motivo,
                               ids_fatores=FATORES)


def comparar(nosso: np.ndarray, oficial: np.ndarray) -> dict:
    """Percentual dentro da tolerância, tratando 'sem nota dos dois lados' como acordo."""
    ambos_nulos = np.isnan(nosso) & np.isnan(oficial)
    delta = np.abs(nosso - oficial)
    dentro = ambos_nulos | (delta <= TOLERANCIA + EPSILON)
    n = int(nosso.size)
    fora = np.nonzero(~dentro)[0]
    return {"n": n, "n_dentro": int(dentro.sum()), "pct": 100.0 * float(dentro.sum()) / n,
            "max_delta": float(np.nanmax(delta)) if n else 0.0, "indices_fora": fora,
            "ambos_nulos": int(ambos_nulos.sum())}


def test_modelo_valido(medida):
    definicao = json.loads(open(MODELO, encoding="utf-8").read())
    assert esquema.violacoes(definicao) == []
    ids = [f["id"] for f in definicao["fatores"]]
    assert ids == FATORES, "o modelo tem de trazer os 19 fatores do motor de referência, na ordem"
    assert len(definicao["restricoes"]) >= 1
    medida(ITEM)("modelo_fatores", len(ids), "fatores",
                 f"pytest tests/unit/test_amc_equivalencia_motor_referencia.py::test_modelo_valido "
                 f"(sha do modelo: {esquema.hash_modelo(definicao)[:16]})")


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_celulas(celulas, perfil, medida):
    """Célula a célula: nosso combinador contra a regra do motor de referência recalculada em SQL."""
    e = esquema_referencia()
    pesos = PERFIS[perfil]
    cols = [f"f_{f}" for f in FATORES]
    t0 = time.perf_counter()
    oraculo = copiar(
        f"SELECT h.hex_id, CASE WHEN h.veto THEN 0 ELSE o.fav END FROM {e}.hex_fav h "
        f"CROSS JOIN LATERAL (SELECT sum(w*f)/nullif(sum(w) FILTER (WHERE f IS NOT NULL),0) AS fav "
        f"FROM (VALUES {valores_sql(pesos, cols)}) AS t(w,f)) o ORDER BY h.hex_id")
    t_oraculo = time.perf_counter() - t0
    assert [int(li[0]) for li in oraculo] == celulas["ids"]
    oficial = np.array([numero(li[1]) for li in oraculo])

    t1 = time.perf_counter()
    r = combinar_perfil(celulas["fatores"], pesos,
                        fracao_vetada=celulas["veto"].astype(float), motivo=celulas["motivo"])
    t_nosso = time.perf_counter() - t1

    c = comparar(r.fav, oficial)
    fora = [{"unidade": celulas["ids"][i], "nosso": None if np.isnan(r.fav[i]) else round(float(r.fav[i]), 6),
             "referencia": None if np.isnan(oficial[i]) else round(float(oficial[i]), 6),
             "vetada": bool(celulas["veto"][i])} for i in c["indices_fora"][:20]]
    medida(ITEM)(f"celulas_pct_dentro_de_{TOLERANCIA}_{perfil}", round(c["pct"], 6), "%",
                 f"pytest tests/unit/test_amc_equivalencia_motor_referencia.py::test_celulas[{perfil}] "
                 f"(n={c['n']}, max|delta|={c['max_delta']:.3e}, fora={len(c['indices_fora'])})")
    medida(ITEM)(f"celulas_divergencias_{perfil}", fora, "lista",
                 "as primeiras 20 células fora da tolerância; lista vazia = nenhuma")
    medida(ITEM)(f"celulas_segundos_{perfil}",
                 {"combinador_generico": round(t_nosso, 4), "oraculo_sql": round(t_oraculo, 4),
                  "carga_1min": os.getloadavg()[0], "medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                 "s", "time.perf_counter em volta de app.amc.combinacao.combinar e do oráculo")
    assert c["pct"] >= PCT_MINIMO, (f"perfil {perfil}: só {c['pct']:.4f}% das {c['n']} células ficaram a "
                                    f"≤ {TOLERANCIA} da nota do motor de referência; exemplos: {fora[:3]}")


def test_vetos_e_motivos_das_celulas(celulas, medida):
    pesos = PERFIL_DECLARADO
    r = combinar_perfil(celulas["fatores"], pesos,
                        fracao_vetada=celulas["veto"].astype(float), motivo=celulas["motivo"])
    iguais = int((r.vetado == celulas["veto"]).sum())
    tem_dado = ~np.all(np.isnan(celulas["fatores"]), axis=1)
    motivos_iguais = sum(1 for i, m in enumerate(r.motivo)
                         if (m or None) == (celulas["motivo"][i] if celulas["veto"][i] else None))
    zeradas = int(((r.fav == 0.0) & celulas["veto"] & tem_dado).sum())
    medida(ITEM)("celulas_veto_identico", iguais == len(celulas["ids"]), "booleano",
                 f"{iguais} de {len(celulas['ids'])} células com o mesmo sinal de veto")
    medida(ITEM)("celulas_motivo_identico", motivos_iguais == len(celulas["ids"]), "booleano",
                 f"{motivos_iguais} de {len(celulas['ids'])} células com o mesmo motivo")
    medida(ITEM)("celulas_vetadas", int(celulas["veto"].sum()), "células",
                 "veto entra como fração vetada 1, nunca como fator de nota baixa")
    assert iguais == len(celulas["ids"])
    assert motivos_iguais == len(celulas["ids"])
    assert zeradas == int((celulas["veto"] & tem_dado).sum())


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_feicoes(feicoes, perfil, medida):
    e = esquema_referencia()
    pesos = PERFIS[perfil]
    cols = [f"f_{f}" for f in FATORES]
    oraculo = copiar(
        f"SELECT i.car_cod, o.fav * (1 - coalesce(i.pct_vetado,0)::numeric) FROM {e}.imoveis_fav i "
        f"CROSS JOIN LATERAL (SELECT sum(w*f)/nullif(sum(w) FILTER (WHERE f IS NOT NULL),0) AS fav "
        f"FROM (VALUES {valores_sql(pesos, cols)}) AS t(w,f)) o ORDER BY i.car_cod")
    assert [li[0] for li in oraculo] == feicoes["ids"]
    oficial = np.array([numero(li[1]) for li in oraculo])
    r = combinar_perfil(feicoes["fatores"], pesos, fracao_vetada=feicoes["pct_vetado"])
    c = comparar(r.fav, oficial)
    fora = [{"unidade": feicoes["ids"][i], "nosso": None if np.isnan(r.fav[i]) else round(float(r.fav[i]), 6),
             "referencia": None if np.isnan(oficial[i]) else round(float(oficial[i]), 6)}
            for i in c["indices_fora"][:20]]
    medida(ITEM)(f"feicoes_pct_dentro_de_{TOLERANCIA}_{perfil}", round(c["pct"], 6), "%",
                 f"pytest tests/unit/test_amc_equivalencia_motor_referencia.py::test_feicoes[{perfil}] "
                 f"(n={c['n']}, max|delta|={c['max_delta']:.3e}, fora={len(c['indices_fora'])})")
    medida(ITEM)(f"feicoes_divergencias_{perfil}", fora, "lista", "as primeiras 20 feições fora da tolerância")
    assert c["pct"] >= PCT_MINIMO, f"perfil {perfil}: {c['pct']:.4f}% das {c['n']} feições; exemplos {fora[:3]}"


@pytest.fixture(scope="module")
def pares(celulas, feicoes):
    """Pares feição × célula com a área de interseção, lidos do oráculo (só leitura)."""
    e = esquema_referencia()
    linhas = copiar(f"SELECT i.car_cod, h.hex_id, ST_Area(ST_Intersection(i.geom, h.geom_utm)) "
                    f"FROM {e}.imoveis_candidatos i JOIN {e}.hex h ON ST_Intersects(i.geom, h.geom_utm)")
    pos_feicao = {c: i for i, c in enumerate(feicoes["ids"])}
    pos_celula = {h: i for i, h in enumerate(celulas["ids"])}
    idx, area, lin_cel = [], [], []
    for car, hexid, a in linhas:
        i, j = pos_feicao.get(car), pos_celula.get(int(hexid))
        if i is None or j is None:
            continue
        idx.append(i)
        area.append(float(a))
        lin_cel.append(j)
    lin_cel = np.array(lin_cel)
    return {"indice_feicao": np.array(idx), "areas": np.array(area), "linha_celula": lin_cel}


def test_agregacao_de_celulas_para_feicoes(celulas, feicoes, pares, medida):
    """A passagem célula → feição do motor genérico reproduz a do motor de referência."""
    j = pares["linha_celula"]
    t0 = time.perf_counter()
    ag = agregacao.agregar_por_feicao(
        pares["indice_feicao"], pares["areas"], celulas["fatores"][j],
        vetado=celulas["veto"][j], motivo_celula=[celulas["motivo"][k] for k in j],
        n_feicoes=len(feicoes["ids"]), arredondar=True)
    segundos = time.perf_counter() - t0

    # fração vetada: o motor de referência força 1 quando o veto é por atributo da própria feição
    # (não por área de célula), então a comparação roda nas feições em que ele NÃO forçou.
    forcada = feicoes["pct_vetado"] >= 1.0
    d_pct = np.abs(ag.fracao_vetada - feicoes["pct_vetado"])
    dentro_pct = (~forcada & (d_pct <= 1e-6)) | forcada
    medida(ITEM)("feicoes_fracao_vetada_pct_igual", round(100.0 * float(dentro_pct.sum()) / dentro_pct.size, 6),
                 "%", f"n={dentro_pct.size}, forçadas por atributo da feição={int(forcada.sum())}")

    # fator a fator. O motor de referência só deriva DA GRADE os dez fatores abaixo; os outros nove ele
    # calcula direto na feição (tabela própria por imóvel, fração de inundação por imóvel, veredito por
    # imóvel). Comparar a agregação naqueles nove mediria a fonte, não a agregação — por isso eles saem,
    # com a razão nomeada e a evidência medida em `test_fatores_que_a_referencia_nao_agrega`.
    resultado = {}
    for k, f in enumerate(FATORES):
        if f not in AGREGADOS_DA_GRADE:
            continue
        c = comparar(ag.fatores[:, k], feicoes["fatores"][:, k])
        resultado[f] = round(c["pct"], 6)
    medida(ITEM)("agregacao_pct_por_fator", resultado, "%",
                 "pytest tests/unit/test_amc_equivalencia_motor_referencia.py::"
                 "test_agregacao_de_celulas_para_feicoes")
    medida(ITEM)("agregacao_fora_de_escopo", NAO_AGREGADOS, "texto",
                 "fatores cuja nota por feição o motor de referência NÃO obtém da média das células")
    medida(ITEM)("agregacao_segundos", {"valor": round(segundos, 4), "pares": int(pares["areas"].size),
                                        "carga_1min": os.getloadavg()[0]}, "s",
                 "app.amc.agregacao.agregar_por_feicao sobre todos os pares feição-célula")

    piores = sorted(resultado.items(), key=lambda x: x[1])[:3]
    assert all(v >= PCT_MINIMO for v in resultado.values()), f"fatores abaixo de {PCT_MINIMO}%: {piores}"
    assert float(dentro_pct.sum()) / dentro_pct.size >= PCT_MINIMO / 100.0


# fator -> (coluna do valor bruto, id do fator no modelo). Só os fatores cujo valor BRUTO está
# materializado no motor de referência E cuja transformação é de uma variável só.
AGREGADOS_DA_GRADE = ("decl", "zon", "gru", "rod", "disp", "ener", "agua", "restr", "press", "dens")

# os nove fatores que o motor de referência calcula DIRETO na feição. `coluna_propria` é onde a evidência
# disso está: quando existe uma tabela por imóvel com o mesmo fator, a igualdade entre as duas é a prova
# de que a nota da feição veio de lá e não da grade.
NAO_AGREGADOS = {
    "roubo": "tabela própria por imóvel (densidade de ocorrência calculada no imóvel, não na célula)",
    "trib": "tabela própria por imóvel (índice tributário do município do imóvel)",
    "renda": "tabela própria por imóvel (percentil de renda dos setores do imóvel)",
    "polos": "tabela própria por imóvel (distância e contagem a partir do próprio imóvel)",
    "se": "tabela própria por imóvel (distância à subestação a partir do próprio imóvel)",
    "cluster": "tabela própria por imóvel (área construída e contagem no raio do próprio imóvel)",
    "rlapp": "tabela própria por imóvel; a grade não carrega este fator (todas as células nulas)",
    "varzea": "fração de inundação medida NO IMÓVEL, com a mesma regra declarada de faixas",
    "mine": "veredito do imóvel (cadastro mineiro mais série de satélite), não média de células",
}
COM_TABELA_PROPRIA = ("roubo", "trib", "renda", "polos", "se", "cluster", "rlapp")

BRUTOS = {"decl": "v_slope", "rod": "v_dist_rod", "agua": "v_app30", "press": "v_durb"}


def test_transformacoes_do_valor_bruto(medida):
    """A transformação declarada no modelo reproduz a favorabilidade do motor de referência a partir do
    valor bruto, nos fatores em que o bruto está materializado."""
    e = esquema_referencia()
    definicao = json.loads(open(MODELO, encoding="utf-8").read())
    por_id = {f["id"]: f for f in definicao["fatores"]}
    resultado = {}
    for fator, coluna in sorted(BRUTOS.items()):
        linhas = copiar(f"SELECT {coluna}, f_{fator} FROM {e}.hex_fav "
                        f"WHERE {coluna} IS NOT NULL AND f_{fator} IS NOT NULL")
        assert linhas, f"{coluna}/f_{fator} sem linha preenchida"
        t = por_id[fator]["transformacao"]
        bruto = [li[0] for li in linhas] if t["tipo"] == "categoria" else [float(li[0]) for li in linhas]
        if t["tipo"] == "categoria":
            bruto = ["True" if b == "t" else "False" for b in bruto]
        oficial = np.array([float(li[1]) for li in linhas])
        nosso = tr.transformar(bruto, t)
        # o motor de referência guarda a nota como inteiro; a tolerância de 0,5 do portão é exatamente o
        # que separa a nossa nota contínua do inteiro gravado, então a comparação roda SEM arredondar
        c = comparar(nosso, oficial)
        resultado[fator] = {"pct": round(c["pct"], 6), "n": c["n"], "max_delta": round(c["max_delta"], 6)}
    medida(ITEM)("transformacao_do_bruto_pct", resultado, "%",
                 "pytest tests/unit/test_amc_equivalencia_motor_referencia.py::"
                 "test_transformacoes_do_valor_bruto")
    medida(ITEM)("transformacao_do_bruto_fora_de_escopo",
                 sorted(set(FATORES) - set(BRUTOS)), "lista",
                 "fatores cujo valor bruto não está materializado no motor de referência, ou cuja regra "
                 "compõe mais de uma variável antes de virar nota: a transformação declarada no modelo é "
                 "a identidade sobre um valor que já chega em escala de favorabilidade")
    baixos = {k: v for k, v in resultado.items() if v["pct"] < PCT_MINIMO}
    assert not baixos, f"transformação declarada não reproduz o bruto em: {baixos}"


def test_fatores_que_a_referencia_nao_agrega(medida):
    """Evidência de que os nove fatores fora da agregação vêm de uma medida POR FEIÇÃO do próprio motor de
    referência, não da grade: a nota da feição bate com a tabela por imóvel dele (sete fatores), com a
    regra declarada aplicada à fração de inundação do imóvel (varzea) e com o veredito do imóvel (mine)."""
    e = esquema_referencia()
    cols = ", ".join(f"count(*) FILTER (WHERE i.f_{f} IS NOT DISTINCT FROM x.f_{f})"
                     for f in COM_TABELA_PROPRIA)
    linha = copiar(f"SELECT count(*), {cols} FROM {e}.imoveis_fav i "
                   f"JOIN {e}.imovel_fatores_extra x USING (car_cod)")[0]
    total = int(linha[0])
    igual_tabela = {f: int(v) for f, v in zip(COM_TABELA_PROPRIA, linha[1:], strict=True)}

    varzea = copiar(
        f"SELECT count(*), count(*) FILTER (WHERE f_varzea IS NOT DISTINCT FROM "
        f"CASE WHEN v_inund_pct IS NULL THEN NULL WHEN v_inund_pct >= 0.5 THEN 10 "
        f"WHEN v_inund_pct >= 0.10 THEN 40 WHEN v_inund_pct > 0 THEN 80 ELSE 100 END) "
        f"FROM {e}.imoveis_fav")[0]
    mine = copiar(f"SELECT count(*), count(*) FILTER (WHERE f_mine IS NOT DISTINCT FROM "
                  f"coalesce(f_mine_ver, f_mine_cel)) FROM {e}.imoveis_fav")[0]

    medida(ITEM)("nao_agregados_evidencia",
                 {"feicoes": total, "igual_a_tabela_por_imovel": igual_tabela,
                  "varzea_pela_regra_no_imovel": [int(varzea[0]), int(varzea[1])],
                  "mine_pelo_veredito": [int(mine[0]), int(mine[1])]}, "feições",
                 "pytest tests/unit/test_amc_equivalencia_motor_referencia.py::"
                 "test_fatores_que_a_referencia_nao_agrega")
    for f, n in igual_tabela.items():
        assert n == total, f"fator {f}: {n} de {total} feições batem com a tabela por imóvel"
    assert int(varzea[1]) == int(varzea[0])
    assert int(mine[1]) == int(mine[0])
