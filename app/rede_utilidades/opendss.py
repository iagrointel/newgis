"""Conversor de subrede para OpenDSS (item L4-05-a-exportar-opendss).

O que este módulo é: um CONVERSOR. Ele lê o que a subrede já tem gravado — nós e trechos da topologia,
atributos das feições como vieram do arquivo — e escreve um circuito OpenDSS. Ele não estima parâmetro que
o arquivo não traz, não completa cadastro e não corrige rede. Tudo o que ele deixa de fazer está em
`RELATORIO_NAO_FAZ` e sai junto com a pasta exportada, no arquivo `NAO_FAZ.md`.

Correspondência declarada (é o que o teste do item confere, e o que o adversário deve reproduzir):

  * BARRA do circuito  = nó da topologia da subrede, com os dois terminais de uma chave FECHADA fundidos
    numa barra só (chave fechada ideal é eletricamente uma barra; ver a limitação 3 do relatório);
  * LINE do circuito   = trecho (feição de linha) da subrede que tem os dois nós na topologia;
  * TRANSFORMER        = transformador de distribuição da subrede (dois terminais, alta e baixa);
  * LOAD               = unidade consumidora (positiva) e geração distribuída (negativa, corrente constante).

Fontes: manual do OpenDSS (opendss.epri.com/opendss_documentation.html), dss-extensions.org,
PRODIST Módulo 7 (composição da carga) e o dicionário de dados da BDGD/ANEEL para os códigos de tensão.
"""

import hashlib
import math
from datetime import date

from app.rede_utilidades import unidades as unidades_mod

# --- códigos de tensão da BDGD (domínio TTEN do dicionário de dados da ANEEL) ---------------------------
# TEN_NOM, TEN_PRI, TEN_SEC e TEN_LIN_SE são CÓDIGOS, não quilovolts. O dicionário abaixo tem os 110 códigos
# do domínio (0 a 109, sem buraco) e foi conferido contra `bdgd2opendss` (Paulo Radatz, licença MIT,
# `src/bdgd2opendss/model/Converter.py::convert_tten`, lido em 2026-09-07) e contra o conversor da casa, que
# só tinha 13 códigos e por isso NÃO resolvia o código 63 (23,1 kV) presente na cooperativa de teste.
TENSAO_KV: dict[str, float] = {
    "0": 0.0, "1": 0.11, "2": 0.115, "3": 0.12, "4": 0.121, "5": 0.125, "6": 0.127, "7": 0.208, "8": 0.216,
    "9": 0.2165, "10": 0.22, "11": 0.23, "12": 0.231, "13": 0.24, "14": 0.254, "15": 0.38, "16": 0.4,
    "17": 0.44, "18": 0.48, "19": 0.5, "20": 0.6, "21": 0.75, "22": 1.0, "23": 2.3, "24": 3.2, "25": 3.6,
    "26": 3.785, "27": 3.8, "28": 3.848, "29": 3.985, "30": 4.16, "31": 4.2, "32": 4.207, "33": 4.368,
    "34": 4.56, "35": 5.0, "36": 6.0, "37": 6.6, "38": 6.93, "39": 7.96, "40": 8.67, "41": 11.4,
    "42": 11.9, "43": 12.0, "44": 12.6, "45": 12.7, "46": 13.2, "47": 13.337, "48": 13.53, "49": 13.8,
    "50": 13.86, "51": 14.14, "52": 14.19, "53": 14.4, "54": 14.835, "55": 15.0, "56": 15.2, "57": 19.053,
    "58": 19.919, "59": 21.0, "60": 21.5, "61": 22.0, "62": 23.0, "63": 23.1, "64": 23.827, "65": 24.0,
    "66": 24.2, "67": 25.0, "68": 25.8, "69": 27.0, "70": 30.0, "71": 33.0, "72": 34.5, "73": 36.0,
    "74": 38.0, "75": 40.0, "76": 44.0, "77": 45.0, "78": 45.4, "79": 48.0, "80": 60.0, "81": 66.0,
    "82": 69.0, "83": 72.5, "84": 88.0, "85": 88.2, "86": 92.0, "87": 100.0, "88": 120.0, "89": 121.0,
    "90": 123.0, "91": 131.6, "92": 131.63, "93": 131.635, "94": 138.0, "95": 145.0, "96": 230.0,
    "97": 345.0, "98": 500.0, "99": 750.0, "100": 1000.0, "101": 245.0, "102": 550.0, "103": 11.0,
    "104": 11.5, "105": 13.0, "106": 20.0, "107": 68.0, "108": 85.0, "109": 440.0,
}


class ErroConversao(Exception):
    """Falha alta do conversor: o dado que falta é estrutural e escrever um valor inventado no lugar seria
    entregar um modelo que parece certo. Quem chama traduz para o erro da API."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def kv_do_codigo(valor, campo: str) -> float:
    """Código do domínio TTEN → kV. Levanta quando o código falta ou não está no domínio: uma tensão
    inventada muda o resultado do fluxo de potência inteiro."""
    if valor is None or str(valor).strip() == "":
        raise ErroConversao("tensao_ausente", f"{campo} não está preenchido: sem ele não há tensão de base")
    chave = str(valor).strip()
    if chave.endswith(".0"):
        chave = chave[:-2]
    if chave not in TENSAO_KV:
        raise ErroConversao(
            "tensao_codigo_desconhecido",
            f"{campo} = {valor!r} não é código do domínio TTEN da BDGD (0 a 109)",
        )
    return TENSAO_KV[chave]


def sanear(nome) -> str:
    """Nome aceito pelo OpenDSS: letra, dígito e sublinhado. Nome vazio é erro de quem chama, não silêncio."""
    limpo = "".join(c if (c.isascii() and (c.isalnum() or c == "_")) else "_" for c in str(nome))
    return limpo or "_"


def fases_do_bitmask(bitmask) -> list[int]:
    """Bitmask A=1, B=2, C=4 → nós OpenDSS [1, 2, 3]. Sem fase declarada o conversor assume as três e
    CONTA a suposição (o chamador soma em `avisos`), nunca a esconde."""
    if not bitmask:
        return [1, 2, 3]
    return [n for n, bit in ((1, 1), (2, 2), (3, 4)) if int(bitmask) & bit]


# --- curva de carga: 24 h × 3 tipos de dia × 12 meses = 864 pontos (PRODIST Módulo 7) -------------------
# Feriado nacional conta como domingo, como no Módulo 7 e nas Regras de Prestação; a lista abaixo é só a
# parte FIXA do calendário (as móveis dependem da Páscoa e são calculadas).
FERIADOS_FIXOS = ((1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25))
TIPOS_DE_DIA = ("DU", "SA", "DO")
PONTOS_DA_CURVA = 24 * 3 * 12


def _pascoa(ano: int) -> date:
    """Domingo de Páscoa pelo algoritmo de Meeus/Jones/Butcher (calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    mes = (h + ll - 7 * m + 114) // 31
    dia = ((h + ll - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def dias_por_tipo(ano: int) -> list[tuple[int, int, int]]:
    """(dias úteis, sábados, domingos-e-feriados) de cada um dos 12 meses do ano."""
    pascoa = _pascoa(ano)
    moveis = {pascoa.toordinal() - 48, pascoa.toordinal() - 47, pascoa.toordinal() - 2,
              pascoa.toordinal() + 60}
    fora = {(date.fromordinal(o).month, date.fromordinal(o).day) for o in moveis} | set(FERIADOS_FIXOS)
    saida = []
    for mes in range(1, 13):
        du = sa = do = 0
        dia = date(ano, mes, 1)
        while dia.month == mes:
            if (mes, dia.day) in fora or dia.weekday() == 6:
                do += 1
            elif dia.weekday() == 5:
                sa += 1
            else:
                du += 1
            dia = date.fromordinal(dia.toordinal() + 1)
        saida.append((du, sa, do))
    return saida


def curva_864(energia_mensal_kwh: list[float], ano: int,
              forma_horaria: dict[str, list[float]] | None = None) -> list[float]:
    """Os 864 pontos da curva anual, na ordem (mês 1..12) × (DU, SA, DO) × (hora 0..23), em POTÊNCIA
    RELATIVA à média anual — é o que o OpenDSS espera num `Loadshape` usado com `kw` médio.

    `energia_mensal_kwh` tem 12 valores (kWh do mês). `forma_horaria` é a forma do dia por tipo de dia
    (24 valores cada, escala livre); sem ela o dia é plano, e a curva só varia de mês para mês — que é
    exatamente o que o dado permite dizer quando não há curva típica de carga no acervo.

    A conta conserva energia: a soma de (potência × horas do bloco) sobre os 864 blocos é a energia anual.
    """
    if len(energia_mensal_kwh) != 12:
        raise ErroConversao("curva_meses", "a energia mensal tem de ter 12 valores")
    forma = {t: list(forma_horaria[t]) if forma_horaria and t in forma_horaria else [1.0] * 24
             for t in TIPOS_DE_DIA}
    for t, v in forma.items():
        if len(v) != 24:
            raise ErroConversao("curva_horas", f"a forma do dia {t} tem de ter 24 valores")
    calendario = dias_por_tipo(ano)
    horas_ano = sum(24 * sum(m) for m in calendario)
    energia_ano = sum(float(e or 0.0) for e in energia_mensal_kwh)
    media_kw = energia_ano / horas_ano if horas_ano else 0.0

    pontos: list[float] = []
    for mes in range(12):
        du, sa, do = calendario[mes]
        dias = {"DU": du, "SA": sa, "DO": do}
        # energia do mês repartida entre os tipos de dia na proporção de (nº de dias × área da forma)
        peso = {t: dias[t] * sum(forma[t]) for t in TIPOS_DE_DIA}
        total = sum(peso.values())
        e_mes = float(energia_mensal_kwh[mes] or 0.0)
        for t in TIPOS_DE_DIA:
            if not dias[t] or total <= 0 or media_kw <= 0:
                pontos.extend([0.0] * 24)
                continue
            e_tipo = e_mes * peso[t] / total
            # dentro do tipo de dia: a energia se reparte entre as 24 horas na proporção da forma
            area = sum(forma[t]) * dias[t]
            pontos.extend((e_tipo * forma[t][h] / area) / media_kw for h in range(24))
    return pontos


def horas_dos_pontos(ano: int) -> list[float]:
    """Quantas horas cada um dos 864 pontos representa no ano — o par da `curva_864`, para conferir
    energia (Σ potência × horas) sem repetir a regra do calendário."""
    calendario = dias_por_tipo(ano)
    horas = []
    for mes in range(12):
        du, sa, do = calendario[mes]
        for dias in (du, sa, do):
            horas.extend([float(dias)] * 24)
    return horas


# --- o que este conversor NÃO faz (sai como NAO_FAZ.md dentro da pasta exportada) -----------------------
RELATORIO_NAO_FAZ = """# O que este conversor não faz

Este arquivo sai junto com todo circuito exportado. Ele existe porque um modelo de rede que não diz o que
deixou de fora é lido como se estivesse completo.

1. **Impedância de condutor.** O pacote de ativos da plataforma não tem catálogo de condutor (o SEGCON da
   BDGD, com R1, X1 e corrente máxima). Cada `Line` sai com o comprimento geodésico medido e o número de
   fases, e com a impedância PADRÃO do OpenDSS. O código do condutor do arquivo vai como comentário na
   linha, para conferência. Nenhum valor de impedância é estimado aqui.
2. **Reatância de dispersão do transformador.** Não vem do arquivo. O `Transformer` sai sem `xhl` e fica com
   o padrão do OpenDSS. As perdas de ferro e totais, essas sim, saem de PER_FER e PER_TOT quando existem.
3. **Chave como objeto manobrável.** A chave FECHADA vira uma barra só (os dois terminais fundidos), que é o
   equivalente elétrico de uma chave ideal fechada. Não sai um `Line ... switch=yes`, então o circuito
   exportado não permite ABRIR a chave dentro do OpenDSS. A chave ABERTA sai sem elemento nenhum: o lado de
   jusante fica ilhado, e é isso que o arquivo diz. O estado de cada chave está em `resumo.json`.
4. **Curva de carga típica.** A curva de 864 pontos (24 h × 3 tipos de dia × 12 meses) tem a forma do dia
   PLANA quando o acervo não traz curva típica de carga por classe de consumo (a CRVCRG da BDGD). Nesse caso
   a curva só varia de mês para mês, e é o que o dado permite afirmar.
5. **Energia mensal.** Quando a unidade consumidora só tem a energia anual, os 12 meses recebem energia
   proporcional às horas do mês. Variação mensal medida só aparece se o acervo tiver ENE_01..ENE_12.
   A UNIDADE da energia (quilowatt-hora ou megawatt-hora) não é assumida do dicionário da BDGD: vem do que
   a importação mediu no arquivo e gravou na auditoria. Quando a rede não tem importação registrada, o
   valor entra como está e `resumo.json` diz `origem: nao_medida` no bloco `unidades` — nesse caso a carga
   pode estar mil vezes fora, e está escrito que pode.
6. **Regulador de tensão, banco de capacitores e proteção.** Não são convertidos. Aparecem contados em
   `resumo.json` como elementos ignorados.
7. **Equilíbrio, ajuste e calibração.** O conversor não ajusta carga para fechar o balanço de energia do
   alimentador, não corrige fase e não move carga órfã para o transformador. O que estiver inconsistente no
   cadastro chega inconsistente no modelo, contado em `resumo.json`.
8. **Convergência.** O conversor garante que o circuito COMPILA. Ele não promete que o fluxo de potência
   converge: isso depende do cadastro e é medido caso a caso.
"""


def _numero(valor):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(n) or math.isinf(n) else n


def linhas_do_circuito(modelo: dict) -> dict[str, str]:
    """Modelo em memória → arquivos do circuito, nome do arquivo para conteúdo. Função pura: não toca banco
    nem disco, o que a torna testável sozinha."""
    nome = sanear(modelo["nome"])
    mestre = [
        f"! circuito {nome} exportado da plataforma (item L4-05-a-exportar-opendss)",
        "! leia NAO_FAZ.md antes de usar este modelo para decidir qualquer coisa",
        "Clear",
        f"New Circuit.{nome} bus1={modelo['barra_fonte']} basekv={modelo['kv_fonte']:.5f} "
        f"pu={modelo.get('pu_fonte', 1.0):.5f} phases=3",
        "Redirect Curvas.dss",
        "Redirect Linhas.dss",
        "Redirect Transformadores.dss",
        "Redirect Cargas.dss",
        "Set voltagebases=["
        + " ".join(f"{v:g}" for v in sorted({round(v, 5) for v in modelo["barras"].values()})) + "]",
        "Calcvoltagebases",
        "Set mode=yearly stepsize=1h number=1",
    ]

    curvas = ["! curva de 864 pontos: 12 meses x 3 tipos de dia (DU, SA, DO) x 24 horas"]
    for nome_curva, pontos in sorted(modelo["curvas"].items()):
        curvas.append(f"New Loadshape.{nome_curva} npts={len(pontos)} interval=1 mult=("
                      + " ".join(f"{p:.6f}" for p in pontos) + ")")

    linhas = ["! uma Line por trecho da subrede; length em km, comprimento geodésico medido na geometria"]
    for t in modelo["linhas"]:
        nos = "".join(f".{n}" for n in t["fases"])
        comentario = f"  ! condutor={t['condutor']}" if t.get("condutor") else ""
        linhas.append(f"New Line.{t['nome']} bus1={t['barra1']}{nos} bus2={t['barra2']}{nos} "
                      f"phases={len(t['fases'])} length={t['comprimento_km']:.6f} units=km{comentario}")

    trafos = ["! um Transformer por transformador de distribuição da subrede"]
    for x in modelo["trafos"]:
        perdas = ""
        if x.get("perda_ferro_pc") is not None:
            perdas += f" %noloadloss={x['perda_ferro_pc']:.4f}"
        cabeca = (f"New Transformer.{x['nome']} phases={x['fases']} windings=2"
                  f" kvas=[{x['kva']:g} {x['kva']:g}]{perdas}")
        resistencia = "" if x.get("resistencia_pc") is None else f" %r={x['resistencia_pc'] / 2:.4f}"
        trafos.append(cabeca)
        trafos.append(f"~ wdg=1 bus={x['barra_at']}{x['nos_at']} conn={x['ligacao_at']} "
                      f"kv={x['kv_at']:.5f}{resistencia}")
        trafos.append(f"~ wdg=2 bus={x['barra_bt']}{x['nos_bt']} conn={x['ligacao_bt']} "
                      f"kv={x['kv_bt']:.5f}{resistencia}")

    cargas = ["! Load por unidade consumidora; a geração distribuída entra como carga NEGATIVA de corrente",
              "! constante (model=5), que é como a casa modela injeção sem travar o fluxo em rede fraca"]
    for c in modelo["cargas"]:
        nos = "".join(f".{n}" for n in c["fases_nos"])
        cargas.append(
            f"New Load.{c['nome']} bus1={c['barra']}{nos} phases={c['fases']} conn={c['ligacao']} "
            f"kv={c['kv']:.5f} kw={c['kw']:.6f} pf={c['fator_de_potencia']:g} model={c['modelo']} "
            f"vminpu={c['vminpu']:g} vmaxpu={c['vmaxpu']:g} yearly={c['curva']}"
        )

    return {
        "Master.dss": "\n".join(mestre) + "\n",
        "Curvas.dss": "\n".join(curvas) + "\n",
        "Linhas.dss": "\n".join(linhas) + "\n",
        "Transformadores.dss": "\n".join(trafos) + "\n",
        "Cargas.dss": "\n".join(cargas) + "\n",
        "NAO_FAZ.md": RELATORIO_NAO_FAZ,
    }


# --- leitura da subrede gravada -------------------------------------------------------------------------
# Grupos do pacote `eletrica-br` que o conversor sabe converter; o resto sai contado em `ignorados`.
GRUPOS_TRECHO = ("trecho_de_media_tensao", "trecho_de_baixa_tensao", "ramal_de_ligacao")
GRUPOS_CHAVE = ("chave_de_media_tensao",)
GRUPO_TRAFO = "transformador_de_distribuicao"
GRUPOS_CARGA = ("unidade_consumidora", "ponto_de_iluminacao_publica")
GRUPO_GERACAO = "geracao_distribuida"
# a mesma chave aparece com e sem o prefixo da camada BDGD conforme quem carregou a feição (o importador
# usa o código do pacote, `untrmt_pot_nom`; a carga de medição usa o nome cru da coluna, `pot_nom`).
def atributo(atributos: dict, *nomes: str):
    for n in nomes:
        if n in atributos and atributos[n] not in (None, ""):
            return atributos[n]
    return None


class _Fusao:
    """Conjuntos disjuntos sobre os nós: chave fechada funde os dois terminais numa barra só."""

    def __init__(self):
        self.pai: dict[str, str] = {}

    def achar(self, x: str) -> str:
        self.pai.setdefault(x, x)
        raiz = x
        while self.pai[raiz] != raiz:
            raiz = self.pai[raiz]
        while self.pai[x] != raiz:
            self.pai[x], x = raiz, self.pai[x]
        return raiz

    def unir(self, a: str, b: str) -> None:
        ra, rb = self.achar(a), self.achar(b)
        if ra != rb:
            self.pai[rb] = ra


def _barra(no_id: str) -> str:
    return "b" + str(no_id).replace("-", "")


_SQL_TRECHOS = """
SELECT e.feicao_id, a.no_origem_id, a.no_destino_id, a.comprimento_m, l.fase_bitmask, l.atributos,
       g.codigo AS grupo
FROM plat.rede_subrede_elemento e
JOIN plat.rede_feicao_linha l ON l.id = e.feicao_id
LEFT JOIN plat.rede_topo_aresta a ON a.rede_id = %(rede)s::uuid AND a.origem_id = e.feicao_id
LEFT JOIN plat.rede_tipo tp ON tp.id = e.tipo_id
LEFT JOIN plat.rede_grupo g ON g.id = tp.grupo_id
WHERE e.subrede_id = ANY(%(subs)s::uuid[]) AND e.geometria = 'linha'
ORDER BY e.feicao_id
"""

_SQL_PONTOS = """
SELECT e.feicao_id, e.terminal_num, n.id AS no_id, p.fase_bitmask, p.atributos,
       g.codigo AS grupo, tp.chave AS tipo_chave
FROM plat.rede_subrede_elemento e
JOIN plat.rede_feicao_ponto p ON p.id = e.feicao_id
LEFT JOIN plat.rede_topo_no n ON n.rede_id = %(rede)s::uuid AND n.origem_id = e.feicao_id
     AND n.terminal_num IS NOT DISTINCT FROM e.terminal_num
LEFT JOIN plat.rede_tipo tp ON tp.id = e.tipo_id
LEFT JOIN plat.rede_grupo g ON g.id = tp.grupo_id
WHERE e.subrede_id = ANY(%(subs)s::uuid[]) AND e.geometria = 'ponto'
ORDER BY e.feicao_id, e.terminal_num
"""


def subredes_de_jusante(cur, rede_id: str, ids: list[str], ordem_do_tier: int) -> list[str]:
    """As subredes de tier INFERIOR que penduram nas subredes `ids` — o transformador de distribuição é
    fronteira de tier, e quem pede o alimentador inteiro quer o que vem depois dele. Desce tier a tier
    enquanto achar subrede nova; a busca é pela feição do controlador, que é o mesmo dispositivo que já é
    membro da subrede de cima."""
    conhecidos = list(ids)
    while True:
        cur.execute(
            "SELECT DISTINCT c.subrede_id FROM plat.rede_controlador c "
            "JOIN plat.rede_tier t ON t.id = c.tier_id "
            "WHERE c.rede_id = %s::uuid AND t.ordem > %s AND c.feicao_id IS NOT NULL "
            "AND c.feicao_id IN (SELECT feicao_id FROM plat.rede_subrede_elemento "
            "                    WHERE subrede_id = ANY(%s::uuid[]))",
            (rede_id, ordem_do_tier, conhecidos),
        )
        novos = [str(r["subrede_id"]) for r in cur.fetchall() if str(r["subrede_id"]) not in conhecidos]
        if not novos:
            return conhecidos
        conhecidos.extend(novos)


def _tensao_por_barra(barras: set[str], adjacencia: dict[str, set[str]], barra_fonte: str,
                      kv_fonte: float, trafos: list[dict]) -> dict[str, float]:
    """kV de linha de cada barra: a fonte impõe a sua, a linha propaga a mesma, o transformador troca pela
    tensão do secundário. Roda por componentes ligadas por LINHA e atravessa transformador; repete enquanto
    houver componente nova alcançada."""
    kv: dict[str, float] = {}

    def espalhar(inicio: str, valor: float) -> None:
        fila = [inicio]
        kv[inicio] = valor
        while fila:
            u = fila.pop()
            for v in adjacencia.get(u, ()):
                if v not in kv:
                    kv[v] = valor
                    fila.append(v)

    if barra_fonte in barras:
        espalhar(barra_fonte, kv_fonte)
    mudou = True
    while mudou:
        mudou = False
        for x in trafos:
            if x["barra_at"] in kv and x["barra_bt"] not in kv:
                espalhar(x["barra_bt"], x["kv_bt"])
                mudou = True
    return kv


def montar_da_subrede(cur, rede_id: str, subrede: dict, controladores_da: list[dict], ano: int,
                      subredes_ids: list[str] | None = None) -> dict:
    """Lê os elementos gravados da subrede e monta o modelo em memória. `subrede` e `controladores_da` vêm
    de quem chama (`subredes.exportar_dss`), para não repetir a busca por nome nem a regra de recusa.
    `subredes_ids` é o conjunto de subredes que entra no circuito (a pedida e, se quem chama quiser, as de
    jusante); o padrão é só a pedida."""
    ids = list(subredes_ids or [str(subrede["id"])])
    # unidade da energia: medida no arquivo pela importação e lida da auditoria (item L4-01-e). O
    # dicionário da BDGD declara ENE_SUM em megawatt-hora, mas o extrato de referência da casa vem em
    # quilowatt-hora; multiplicar por mil de cabeça (o que este conversor fazia) errava a carga por mil.
    fatores = unidades_mod.fatores_da_rede(cur, rede_id)
    parametros = {"rede": rede_id, "subs": ids}
    cur.execute(_SQL_TRECHOS, parametros)
    trechos = [dict(r) for r in cur.fetchall()]
    cur.execute(_SQL_PONTOS, parametros)
    pontos = [dict(r) for r in cur.fetchall()]
    fator_energia = fatores["ene"]["fator_para_base"]

    avisos: dict[str, int] = {}
    ignorados: dict[str, int] = {}

    def avisar(chave: str, quantos: int = 1) -> None:
        avisos[chave] = avisos.get(chave, 0) + quantos

    # 1. fusão de barra pelas chaves fechadas (limitação 3 do relatório)
    fusao = _Fusao()
    por_feicao: dict[str, list[dict]] = {}
    for p in pontos:
        por_feicao.setdefault(str(p["feicao_id"]), []).append(p)
    chaves = []
    for feicao_id, linhas_da_feicao in sorted(por_feicao.items()):
        if linhas_da_feicao[0]["grupo"] not in GRUPOS_CHAVE:
            continue
        nos = [str(x["no_id"]) for x in linhas_da_feicao if x["no_id"]]
        estado_bruto = atributo(linhas_da_feicao[0]["atributos"] or {}, "unsemt_p_n_ope", "p_n_ope")
        if estado_bruto is None:
            avisar("chave_sem_estado_declarado")
            fechada = True
        else:
            fechada = str(estado_bruto).strip().upper().startswith("F")
        chaves.append({"feicao_id": feicao_id, "tipo": linhas_da_feicao[0]["tipo_chave"],
                       "estado": "fechada" if fechada else "aberta", "nos": nos,
                       "codigo": atributo(linhas_da_feicao[0]["atributos"] or {}, "unsemt_cod_id", "cod_id"),
                       # os atributos da feição seguem com a chave porque quem consome o modelo precisa
                       # deles sem voltar ao banco (item L4-27: a faixa de interrupção do dispositivo)
                       "atributos": linhas_da_feicao[0]["atributos"] or {}})
        if fechada and len(nos) == 2:
            fusao.unir(nos[0], nos[1])
        elif not fechada:
            avisar("chave_aberta_deixa_trecho_ilhado")
    # a barra de cada chave só existe depois que TODA fusão por chave fechada foi feita, por isso esta
    # segunda passada. Chave fechada tem os dois terminais na mesma barra; chave aberta tem duas.
    for c in chaves:
        c["barras"] = sorted({_barra(fusao.achar(n)) for n in c["nos"]})

    # 2. barras e linhas
    nos_da_subrede: set[str] = set()
    linhas_modelo = []
    trechos_sem_no = 0
    for i, t in enumerate(trechos):
        if t["grupo"] not in GRUPOS_TRECHO:
            ignorados[str(t["grupo"])] = ignorados.get(str(t["grupo"]), 0) + 1
            continue
        if not t["no_origem_id"] or not t["no_destino_id"]:
            trechos_sem_no += 1
            continue
        a, b = str(t["no_origem_id"]), str(t["no_destino_id"])
        nos_da_subrede.update((a, b))
        barra1, barra2 = _barra(fusao.achar(a)), _barra(fusao.achar(b))
        if barra1 == barra2:
            avisar("trecho_entre_terminais_da_mesma_chave")
            continue
        fases = fases_do_bitmask(t["fase_bitmask"])
        if not t["fase_bitmask"]:
            avisar("trecho_sem_fase_declarada")
        comprimento = _numero(t["comprimento_m"]) or 0.0
        atributos = t["atributos"] or {}
        linhas_modelo.append({
            "nome": f"t{i}", "barra1": barra1, "barra2": barra2, "fases": fases,
            "comprimento_km": max(comprimento, 0.001) / 1000.0,
            "condutor": atributo(atributos, "ssdmt_tip_cnd", "ssdbt_tip_cnd", "ramlig_tip_cnd", "tip_cnd"),
            "feicao_id": str(t["feicao_id"]),
        })
    for p in pontos:
        if p["no_id"]:
            nos_da_subrede.add(str(p["no_id"]))

    # 3. tensão da fonte: do que a subrede propagou ou do controlador, nunca adivinhada
    fonte = next((c for c in controladores_da if c["papel"] == "fonte"), None) or (
        controladores_da[0] if controladores_da else None)
    if fonte is None:
        raise ErroConversao("subrede_sem_controlador",
                            "a subrede não tem controlador: sem ele não há barra de fonte nem tensão de base")
    no_fonte = fonte.get("no_id")
    if no_fonte is None:
        raise ErroConversao("controlador_sem_no",
                            "o controlador da subrede não tem nó na topologia: reconstrua a topologia")
    barra_fonte = _barra(fusao.achar(no_fonte))
    atributos_fonte = {}
    if fonte.get("feicao_id"):
        cur.execute("SELECT atributos FROM plat.rede_feicao_ponto WHERE id = %s::uuid", (fonte["feicao_id"],))
        r = cur.fetchone()
        atributos_fonte = (r["atributos"] if r else {}) or {}
    codigo_tensao = atributo(dict(subrede.get("propagados") or {}), "ctmt_ten_nom", "ten_nom") or \
        atributo(atributos_fonte, "ctmt_ten_nom", "ten_nom")
    kv_fonte = kv_do_codigo(codigo_tensao, "a tensão nominal do alimentador (TEN_NOM)")

    # 4. transformadores: dois terminais, alta e baixa. Sem POT_NOM o conversor PARA (escrever 0 kVA daria
    #    um modelo que compila e mente).
    trafos_modelo = []
    for feicao_id, linhas_da_feicao in sorted(por_feicao.items()):
        if linhas_da_feicao[0]["grupo"] != GRUPO_TRAFO:
            continue
        atributos = linhas_da_feicao[0]["atributos"] or {}
        codigo = atributo(atributos, "untrmt_cod_id", "cod_id") or feicao_id
        por_terminal = {x["terminal_num"]: x for x in linhas_da_feicao if x["no_id"]}
        if 1 not in por_terminal or 2 not in por_terminal:
            # o transformador é a fronteira entre o tier de média e o de baixa: com só um lado dentro do
            # recorte pedido ele não vira objeto. Quem quer o alimentador inteiro pede `jusante=true`.
            avisar("trafo_com_um_lado_fora_do_recorte")
            continue
        kva = _numero(atributo(atributos, "untrmt_pot_nom", "pot_nom"))
        if kva is None or kva <= 0:
            raise ErroConversao(
                "trafo_sem_potencia",
                f"o transformador {codigo} não tem POT_NOM: o conversor não escreve 0 kVA no lugar",
            )
        kv_bt = kv_do_codigo(atributo(atributos, "untrmt_ten_lin_se", "ten_lin_se"),
                             f"a tensão do secundário (TEN_LIN_SE) do transformador {codigo}")
        fases_at = fases_do_bitmask(linhas_da_feicao[0]["fase_bitmask"])
        perda_ferro = _numero(atributo(atributos, "untrmt_per_fer", "per_fer"))
        perda_total = _numero(atributo(atributos, "untrmt_per_tot", "per_tot"))
        resistencia = None
        if perda_ferro is not None and perda_total is not None:
            if perda_total > perda_ferro:
                resistencia = 100.0 * (perda_total - perda_ferro) / (1000.0 * kva)
            else:
                avisar("trafo_perda_total_menor_que_a_de_ferro")
        trafos_modelo.append({
            "nome": f"x{len(trafos_modelo)}", "codigo": str(codigo),
            "barra_at": _barra(fusao.achar(str(por_terminal[1]["no_id"]))),
            "barra_bt": _barra(fusao.achar(str(por_terminal[2]["no_id"]))),
            "kva": kva, "kv_bt": kv_bt, "kv_at": None,
            "fases": 3 if len(fases_at) == 3 else 1,
            "nos_at": ".1.2.3" if len(fases_at) == 3 else f".{fases_at[0]}",
            "nos_bt": ".1.2.3.0" if len(fases_at) == 3 else ".1.0",
            "ligacao_at": "delta" if len(fases_at) == 3 else "wye",
            "ligacao_bt": "wye",
            "perda_ferro_pc": None if perda_ferro is None else 100.0 * perda_ferro / (1000.0 * kva),
            "resistencia_pc": resistencia,
        })

    # 5. tensão de cada barra (a fonte impõe; a linha propaga; o transformador troca)
    adjacencia: dict[str, set[str]] = {}
    for t in linhas_modelo:
        adjacencia.setdefault(t["barra1"], set()).add(t["barra2"])
        adjacencia.setdefault(t["barra2"], set()).add(t["barra1"])
    barras = {_barra(fusao.achar(n)) for n in nos_da_subrede}
    kv_por_barra = _tensao_por_barra(barras, adjacencia, barra_fonte, kv_fonte, trafos_modelo)
    for x in trafos_modelo:
        x["kv_at"] = kv_por_barra.get(x["barra_at"])
        if x["kv_at"] is None:
            raise ErroConversao(
                "trafo_fora_da_arvore",
                f"o transformador {x['codigo']} está numa parte da subrede que não chega à fonte: não há "
                "tensão de base para o primário",
            )
        if x["fases"] == 1:
            # monofásico: o primário vê tensão de fase, não de linha
            x["kv_at"] = x["kv_at"] / math.sqrt(3.0)
    sem_tensao = len(barras - set(kv_por_barra))
    if sem_tensao:
        avisar("barra_sem_tensao_de_base", sem_tensao)

    # 6. cargas (unidade consumidora e iluminação pública) e geração distribuída
    cargas_modelo = []
    curvas: dict[str, list[float]] = {}
    horas = horas_dos_pontos(ano)

    def nome_da_curva(energia_mensal: list[float]) -> str:
        total = sum(energia_mensal)
        forma = tuple(round(e / total, 6) for e in energia_mensal) if total > 0 else tuple([0.0] * 12)
        # chave determinística (nunca `hash()`, que muda a cada processo): a própria forma, arredondada
        chave = "c" + hashlib.sha1(repr(forma).encode("utf-8")).hexdigest()[:10]
        if chave not in curvas:
            curvas[chave] = curva_864(list(forma) if total > 0 else [1.0] * 12, ano)
        return chave

    def energia_mensal_kwh(atributos: dict, prefixos: tuple[str, ...]) -> tuple[list[float], bool]:
        """Energia do mês em quilowatt-hora. Os valores do arquivo (ENE_01..12, ou ENE_SUM quando os doze
        meses não vêm) são multiplicados pelo fator que a IMPORTAÇÃO mediu — 1 se o arquivo está em
        quilowatt-hora, 1.000 se está em megawatt-hora. Sem importação registrada o fator é 1 e o
        `resumo.json` do circuito diz que a unidade não foi medida."""
        mensal = [_numero(atributo(atributos, *(f"{p}ene_{m:02d}" for p in prefixos))) for m in range(1, 13)]
        if all(v is not None for v in mensal):
            return [float(v) * fator_energia for v in mensal], True
        anual = _numero(atributo(atributos, *(f"{p}ene_sum" for p in prefixos)))
        if anual is None:
            return [0.0] * 12, False
        total_horas = sum(horas) * 1.0
        anual_kwh = anual * fator_energia
        return [anual_kwh * (sum(horas[m * 72:(m + 1) * 72]) / total_horas) for m in range(12)], False

    for _feicao_id, linhas_da_feicao in sorted(por_feicao.items()):
        grupo = linhas_da_feicao[0]["grupo"]
        if grupo not in GRUPOS_CARGA and grupo != GRUPO_GERACAO:
            if grupo not in GRUPOS_CHAVE and grupo != GRUPO_TRAFO:
                ignorados[str(grupo)] = ignorados.get(str(grupo), 0) + 1
            continue
        linha = linhas_da_feicao[0]
        if not linha["no_id"]:
            avisar("carga_sem_no")
            continue
        barra = _barra(fusao.achar(str(linha["no_id"])))
        kv_barra = kv_por_barra.get(barra)
        if kv_barra is None or kv_barra <= 0:
            avisar("carga_sem_tensao_de_base")
            continue
        atributos = linha["atributos"] or {}
        geracao = grupo == GRUPO_GERACAO
        prefixos = ("ugbt_", "ugmt_", "") if geracao else ("ucbt_", "ucmt_", "pip_", "")
        mensal, medida = energia_mensal_kwh(atributos, prefixos)
        if not medida and sum(mensal) == 0:
            avisar("carga_sem_energia_declarada")
        kw_medio = sum(mensal) / sum(horas) if sum(horas) else 0.0
        fases = fases_do_bitmask(linha["fase_bitmask"])
        if len(fases) == 3:
            n_fases, kv_carga, ligacao = 3, kv_barra, "wye"
        elif len(fases) == 2:
            n_fases, kv_carga, ligacao = 1, kv_barra, "delta"
        else:
            n_fases, kv_carga, ligacao = 1, kv_barra / math.sqrt(3.0), "wye"
        cargas_modelo.append({
            "nome": ("g" if geracao else "u") + str(len(cargas_modelo)),
            "barra": barra, "fases_nos": fases, "fases": n_fases, "ligacao": ligacao, "kv": kv_carga,
            # geração distribuída: carga NEGATIVA de corrente constante (model=5)
            "kw": -kw_medio if geracao else kw_medio,
            "fator_de_potencia": 1.0 if geracao else 0.92,
            "modelo": 5 if geracao else 1,
            "vminpu": 0.5 if geracao else 0.92, "vmaxpu": 1.5 if geracao else 1.25,
            "curva": nome_da_curva(mensal),
            "energia_mensal_medida": medida,
        })
    return {
        "nome": subrede["nome"], "ano": ano, "subredes": ids,
        "barra_fonte": barra_fonte, "kv_fonte": kv_fonte, "pu_fonte": 1.0,
        "codigo_tensao_nominal": str(codigo_tensao),
        "barras": kv_por_barra, "linhas": linhas_modelo, "trafos": trafos_modelo,
        "cargas": cargas_modelo, "curvas": curvas, "chaves": chaves,
        "conferencia": {
            "nos_da_subrede": len(nos_da_subrede),
            "fusoes_por_chave_fechada": len(nos_da_subrede) - len(barras),
            "barras_esperadas": len(barras),
            "trechos_da_subrede": sum(1 for t in trechos if t["grupo"] in GRUPOS_TRECHO),
            "trechos_sem_no_na_topologia": trechos_sem_no,
            "linhas_esperadas": len(linhas_modelo),
            "transformadores": len(trafos_modelo),
            "cargas": sum(1 for c in cargas_modelo if c["kw"] >= 0),
            "geracao_distribuida": sum(1 for c in cargas_modelo if c["kw"] < 0),
        },
        "unidades": {familia: {"unidade_do_arquivo": f.get("unidade"), "base": f["base"],
                               "fator_para_base": f["fator_para_base"], "origem": f["origem"],
                               "declarada_no_dicionario": f["declarada"]}
                     for familia, f in fatores.items()},
        "avisos": avisos, "ignorados": ignorados,
    }
