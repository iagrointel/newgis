"""MATPOWER caseformat versão 2 — escrita e leitura (item L4-05-c-pandapower-e-matpower).

Duas metades, e as duas são CONECTOR, não motor:

  * `texto_do_caso(modelo)` escreve o `.m` da subrede a partir do MESMO modelo em memória que os
    exportadores OpenDSS e pandapower usam (`opendss.montar_da_subrede`). Uma leitura do banco, uma
    regra de conversão, três formatos de saída.
  * `ler_caso(texto)` lê um `.m` do caseformat 2 e devolve as matrizes `bus`, `gen` e `branch` como
    listas de números, mais `baseMVA`. Serve para trazer para a plataforma um caso de transmissão que
    nasceu fora dela (o `case9` e o `case30` públicos, por exemplo).

Por que a leitura não usa uma biblioteca: o caseformat é um trecho de programa MATLAB, e ler MATLAB de
verdade exigiria o Octave ou o `matpowercaseframes` (que puxa pandas). O que este módulo lê é o
SUBCONJUNTO declarado abaixo — atribuições `mpc.<campo> = <número>` e `mpc.<campo> = [ ... ];` com
números separados por espaço e linhas terminadas em `;`. Tudo o que sair disso é recusado com o número
da linha, nunca adivinhado. É o mesmo princípio do importador do `.inp` do EPANET.

O caso do MATPOWER NÃO TEM COORDENADA: as matrizes `bus`, `branch` e `gen` não têm coluna de posição.
Por isso a importação grava a barra como objeto NÃO ESPACIAL (`plat.rede_no.geom` NULO, grupo de
geometria `sem_geometria` no pacote `transmissao-matpower`), e nunca como um ponto em (0, 0) — que é
uma coordenada real, no golfo da Guiné, e faria a barra aparecer no mapa como se tivesse sido medida.

Fontes: github.com/MATPOWER/matpower (`lib/caseformat.m`, matrizes e ordem das colunas),
matpower.org (manual do usuário), pandapower.readthedocs.io/en/latest/converter (conversor de leitura
usado na conferência cruzada da suíte).
"""

import math
import re

# Colunas do caseformat 2, na ordem. Quem lê o arquivo confere a QUANTIDADE contra estas listas.
COLUNAS_BUS = ("bus_i", "type", "Pd", "Qd", "Gs", "Bs", "area", "Vm", "Va", "baseKV", "zone",
               "Vmax", "Vmin")
COLUNAS_GEN = ("bus", "Pg", "Qg", "Qmax", "Qmin", "Vg", "mBase", "status", "Pmax", "Pmin",
               "Pc1", "Pc2", "Qc1min", "Qc1max", "Qc2min", "Qc2max", "ramp_agc", "ramp_10",
               "ramp_30", "ramp_q", "apf")
COLUNAS_BRANCH = ("fbus", "tbus", "r", "x", "b", "rateA", "rateB", "rateC", "ratio", "angle",
                  "status", "angmin", "angmax")
BASE_MVA_PADRAO = 100.0
FREQUENCIA_HZ = 60.0

# tensão máxima e mínima que a barra exportada declara. É DECLARAÇÃO de faixa operativa usual, não
# medida do cadastro: o arquivo da distribuidora não traz limite de tensão por barra.
VMAX_DECLARADO = 1.1
VMIN_DECLARADO = 0.9


class ErroMatpower(Exception):
    """Arquivo recusado. Traz a linha onde o problema está, para que o conserto não seja adivinhação."""

    def __init__(self, codigo: str, mensagem: str, linha: int | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.linha = linha


# --- escrita -------------------------------------------------------------------------------------

def _numero(v) -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "0"
    return f"{float(v):.10g}"


def _matriz(nome: str, linhas: list[list], colunas: tuple[str, ...]) -> list[str]:
    saida = [f"%% {' '.join(colunas)}", f"mpc.{nome} = ["]
    for linha in linhas:
        saida.append("\t" + "\t".join(_numero(v) for v in linha) + ";")
    saida.append("];")
    return saida


def matrizes_do_modelo(modelo: dict, base_mva: float = BASE_MVA_PADRAO) -> dict:
    """Modelo em memória → matrizes `bus`, `gen` e `branch` do caseformat 2. Função pura.

    A conversão para POR UNIDADE é feita aqui e em nenhum outro lugar: a impedância do trecho está em
    ohm por quilômetro (a referência declarada em `pandapower_rede.IMPEDANCIA_REFERENCIA`, que é o
    padrão do motor OpenDSS) e a base da barra vem da tensão que o alimentador propaga.
    """
    from app.rede_utilidades import pandapower_rede as pp_mod

    barras = sorted(modelo["barras"])
    numero = {b: i + 1 for i, b in enumerate(barras)}      # MATPOWER numera a partir de 1
    fonte = modelo["barra_fonte"]

    demanda: dict[str, list[float]] = {b: [0.0, 0.0] for b in barras}
    for c in modelo["cargas"]:
        if c["barra"] not in demanda:
            continue
        kw = float(c["kw"])
        # geração distribuída entra como demanda NEGATIVA, exatamente como entra no OpenDSS (carga
        # negativa) e no pandapower (sgen). Nunca vira barra PV: o cadastro não diz tensão de
        # referência de gerador nenhum, e inventar isso mudaria o resultado do fluxo.
        demanda[c["barra"]][0] += kw / 1000.0
        demanda[c["barra"]][1] += pp_mod._q_mvar(kw, c["fator_de_potencia"])

    bus = []
    for b in barras:
        tipo = 3 if b == fonte else 1
        kv = float(modelo["barras"][b])
        bus.append([numero[b], tipo, demanda[b][0], demanda[b][1], 0.0, 0.0, 1,
                    float(modelo.get("pu_fonte", 1.0)) if b == fonte else 1.0, 0.0, kv, 1,
                    VMAX_DECLARADO, VMIN_DECLARADO])

    gen = []
    if fonte in numero:
        gen.append([numero[fonte], 0.0, 0.0, 9999.0, -9999.0, float(modelo.get("pu_fonte", 1.0)),
                    base_mva, 1, 9999.0, -9999.0] + [0.0] * 11)

    branch = []
    r_km = pp_mod.IMPEDANCIA_REFERENCIA["r_ohm_per_km"]
    x_km = pp_mod.IMPEDANCIA_REFERENCIA["x_ohm_per_km"]
    c_km = pp_mod.IMPEDANCIA_REFERENCIA["c_nf_per_km"]
    for t in modelo["linhas"]:
        if t["barra1"] not in numero or t["barra2"] not in numero:
            continue
        kv = float(modelo["barras"][t["barra1"]])
        if kv <= 0:
            continue
        z_base = kv * kv / base_mva
        km = float(t["comprimento_km"])
        b_shunt = 2.0 * math.pi * FREQUENCIA_HZ * (c_km * 1e-9 * km) * z_base
        branch.append([numero[t["barra1"]], numero[t["barra2"]], r_km * km / z_base,
                       x_km * km / z_base, b_shunt, 0.0, 0.0, 0.0, 0.0, 0.0, 1, -360.0, 360.0])
    for x in modelo["trafos"]:
        if x["barra_at"] not in numero or x["barra_bt"] not in numero:
            continue
        sn_mva = float(x["kva"]) / 1000.0
        if sn_mva <= 0:
            continue
        # impedância do transformador na base do SISTEMA: (vk/100) x baseMVA/snMVA
        z_pu = (pp_mod.VK_PERCENT_REFERENCIA / 100.0) * base_mva / sn_mva
        r_pu = 0.0 if x.get("resistencia_pc") is None else \
            (float(x["resistencia_pc"]) / 100.0) * base_mva / sn_mva
        r_pu = min(r_pu, z_pu)
        x_pu = math.sqrt(max(z_pu * z_pu - r_pu * r_pu, 0.0))
        branch.append([numero[x["barra_at"]], numero[x["barra_bt"]], r_pu, x_pu, 0.0,
                       sn_mva, 0.0, 0.0, 1.0, 0.0, 1, -360.0, 360.0])
    return {"baseMVA": base_mva, "bus": bus, "gen": gen, "branch": branch, "numero_da_barra": numero}


def texto_do_caso(modelo: dict, base_mva: float = BASE_MVA_PADRAO) -> str:
    """O arquivo `.m` do caseformat 2. O nome da função MATLAB é o nome saneado da subrede."""
    from app.rede_utilidades import opendss

    m = matrizes_do_modelo(modelo, base_mva)
    nome = opendss.sanear(modelo["nome"]).lower()
    linhas = [
        f"function mpc = {nome}",
        f"%{nome.upper()} caso de transmissão exportado da plataforma",
        "%   Item L4-05-c-pandapower-e-matpower. Leia NAO_FAZ.md antes de decidir qualquer coisa com",
        "%   este arquivo: a impedância de cada ramo é a de REFERÊNCIA (o padrão do motor OpenDSS), não",
        "%   a do condutor cadastrado, porque o pacote de ativos não tem catálogo de condutor.",
        "",
        "%% MATPOWER Case Format : Version 2",
        "mpc.version = '2';",
        "",
        "%%-----  Power Flow Data  -----%%",
        "%% system MVA base",
        f"mpc.baseMVA = {_numero(m['baseMVA'])};",
        "",
        "%% bus data",
    ]
    linhas += _matriz("bus", m["bus"], COLUNAS_BUS)
    linhas += ["", "%% generator data"]
    linhas += _matriz("gen", m["gen"], COLUNAS_GEN)
    linhas += ["", "%% branch data"]
    linhas += _matriz("branch", m["branch"], COLUNAS_BRANCH)
    linhas.append("")
    return "\n".join(linhas) + "\n"


# --- leitura -------------------------------------------------------------------------------------

_ESCALAR = re.compile(r"^\s*mpc\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*('?)([^';\[\]]+?)\2\s*;\s*$")
_ABRE = re.compile(r"^\s*mpc\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\[\s*(.*)$")
_NUMERO = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")
# `Inf` e `-Inf` são literais legítimos do MATLAB e aparecem em caso público do MATPOWER (limite de
# ângulo, por exemplo). `NaN` NÃO é aceito: um valor ausente escrito como NaN entraria no fluxo como
# número e o resultado sairia sem aviso.
_INFINITO = re.compile(r"^([-+]?)[Ii]nf$")


def _sem_comentario(linha: str) -> str:
    return linha.split("%", 1)[0]


def ler_caso(texto: str) -> dict:
    """`.m` do caseformat 2 → `{"baseMVA": float, "bus": [[...]], "gen": [[...]], "branch": [[...]]}`.

    Recusa (com a linha) o que não entende: matriz com número de colunas fora do caseformat, token que
    não é número, matriz aberta e não fechada. Nunca completa coluna que falta.
    """
    dados: dict = {}
    nome_aberto: str | None = None
    linhas_da_matriz: list[list[float]] = []
    parciais: list[str] = []
    linha_de_abertura = 0

    def fechar(numero_da_linha: int) -> None:
        nonlocal nome_aberto, linhas_da_matriz, parciais
        if parciais:
            raise ErroMatpower("matriz_linha_sem_ponto_e_virgula",
                               f"a matriz mpc.{nome_aberto} tem uma linha sem ';' antes do fecho",
                               numero_da_linha)
        dados[nome_aberto] = linhas_da_matriz
        nome_aberto, linhas_da_matriz, parciais = None, [], []

    def guardar(tokens: list[str], numero_da_linha: int) -> None:
        valores = []
        for t in tokens:
            infinito = _INFINITO.match(t)
            if infinito:
                valores.append(-math.inf if infinito.group(1) == "-" else math.inf)
                continue
            if not _NUMERO.match(t):
                raise ErroMatpower("valor_nao_numerico",
                                   f"a matriz mpc.{nome_aberto} tem o valor {t!r}, que não é número",
                                   numero_da_linha)
            valores.append(float(t))
        linhas_da_matriz.append(valores)

    for n, bruta in enumerate(texto.splitlines(), start=1):
        linha = _sem_comentario(bruta)
        if nome_aberto is None:
            m = _ABRE.match(linha)
            if m:
                nome_aberto, linhas_da_matriz, parciais = m.group(1), [], []
                linha_de_abertura = n
                resto = m.group(2)
            else:
                m = _ESCALAR.match(linha)
                if m:
                    # valor entre aspas fica TEXTO (mpc.version = '2' é a versão do formato, não o
                    # número dois); sem aspas e numérico vira número.
                    valor = m.group(3).strip()
                    dados[m.group(1)] = valor if m.group(2) else (
                        float(valor) if _NUMERO.match(valor) else valor)
                continue
        else:
            resto = linha
        # dentro de uma matriz: cada linha lógica termina em ';', e ']' fecha a matriz
        while resto:
            if "]" in resto and (";" not in resto or resto.index("]") < resto.index(";")):
                antes, resto = resto.split("]", 1)
                parciais.extend(antes.split())
                if parciais:
                    guardar(parciais, n)
                    parciais = []
                fechar(n)
                resto = ""
            elif ";" in resto:
                antes, resto = resto.split(";", 1)
                parciais.extend(antes.split())
                if parciais:
                    guardar(parciais, n)
                    parciais = []
            else:
                parciais.extend(resto.split())
                resto = ""
        if nome_aberto is None:
            continue
    if nome_aberto is not None:
        raise ErroMatpower("matriz_nao_fechada",
                           f"a matriz mpc.{nome_aberto} abre e não fecha", linha_de_abertura)

    for campo, colunas in (("bus", COLUNAS_BUS), ("gen", COLUNAS_GEN), ("branch", COLUNAS_BRANCH)):
        if campo not in dados:
            raise ErroMatpower("matriz_ausente", f"o caso não tem a matriz mpc.{campo}")
        for i, linha_lida in enumerate(dados[campo]):
            if len(linha_lida) < len(colunas):
                raise ErroMatpower(
                    "colunas_de_menos",
                    f"a linha {i + 1} de mpc.{campo} tem {len(linha_lida)} colunas e o caseformat 2 "
                    f"exige pelo menos {len(colunas)}")
    if "baseMVA" not in dados:
        raise ErroMatpower("base_mva_ausente", "o caso não declara mpc.baseMVA")
    if not dados["bus"]:
        raise ErroMatpower("caso_sem_barra", "o caso não tem nenhuma barra")
    return {"baseMVA": float(dados["baseMVA"]), "bus": dados["bus"], "gen": dados["gen"],
            "branch": dados["branch"],
            "versao": str(dados.get("version", "")).strip()}


def coluna(linha: list[float], colunas: tuple[str, ...], nome: str) -> float:
    return linha[colunas.index(nome)]
