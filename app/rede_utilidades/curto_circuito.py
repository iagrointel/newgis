"""Corrente de curto-circuito por barra e verificação de coordenação (item L4-27-curto-circuito-e-protecao).

O QUE ESTE MÓDULO CALCULA. Para cada barra do alimentador, a corrente de curto-circuito trifásica
(`ik3_a`) e a monofásica fase-terra (`ik1_a`), pelo método da fonte de tensão equivalente no ponto de
falta — a mesma forma da IEC 60909 e do estudo de falta do OpenDSS: a rede é reduzida a uma impedância
equivalente vista da barra em falta, e a corrente é a tensão equivalente dividida por essa impedância.
A ressalva de cabeçalho vale para tudo o que sai daqui: **é triagem, sinal, não prova** — o cadastro de
distribuição não traz catálogo de condutor nem impedância de dispersão de transformador, então as
premissas abaixo são DECLARADAS, e o número muda com elas.

DE ONDE VEM A REDE. Do MESMO modelo em memória que `opendss.montar_da_subrede` monta e que os
exportadores OpenDSS, pandapower e MATPOWER já usam (item L4-05-a/c). Não há segunda leitura do banco
nem segunda regra de conversão: barra, trecho, transformador e chave são decididos uma vez só.

AS PREMISSAS, uma por uma (todas saem gravadas ao lado do resultado, em `premissas`):

* `potencia_de_curto_mva` — a potência de curto-circuito da fonte, na barra do alimentador. É a única
  premissa OBRIGATÓRIA: sem ela não existe impedância de fonte, e uma fonte de impedância ZERO daria
  corrente infinita. Por isso `validar_premissas` RECUSA valor ausente, nulo, zero ou negativo, e recusa
  também impedância de fonte declarada como zero. Essa recusa é a refutação exigida do item.
* `relacao_x_r_fonte` — quanto a reatância da fonte vale sobre a resistência dela (padrão 10, típico de
  subestação de distribuição). Reparte o módulo da impedância da fonte entre parte real e imaginária.
* `fator_tensao_c` — o fator de tensão da fonte equivalente (o `c` da IEC 60909; padrão 1,05, que é o
  valor de corrente MÁXIMA para rede de média tensão). Multiplicar por 1,00 dá a leitura de corrente
  mínima; o valor escolhido sai gravado.
* `fator_sequencia_zero_linha` — quanto a impedância de sequência zero do trecho vale sobre a de
  sequência positiva (padrão 3,0). O cadastro não traz sequência zero; sem esta razão declarada não há
  corrente fase-terra nenhuma.
* `fator_sequencia_zero_fonte` — o mesmo para a impedância da fonte (padrão 1,0).
* `base_mva` — a base de potência do cálculo em por unidade (padrão 100). Não muda resultado nenhum;
  fica gravada porque toda impedância intermediária é reportada nela.

O QUE ESTE MÓDULO NÃO FAZ (limitações medidas, não desculpas):

1. **Impedância de trecho é a de REFERÊNCIA**, a mesma que o conector pandapower escreve
   (`pandapower_rede.IMPEDANCIA_REFERENCIA`), porque o pacote de ativos não tem catálogo de condutor.
   A corrente calculada é, portanto, a corrente de uma rede com condutor de referência — serve para
   ordenar barras e para conferir faixa de dispositivo, não para dimensionar equipamento.
2. **Reatância de dispersão do transformador é a de referência** (`pandapower_rede.VK_PERCENT_REFERENCIA`,
   7 %), pela mesma razão.
3. **Rede radial.** A impedância até a barra é a soma ao longo do caminho de menor impedância até a
   fonte. Onde a subrede tem laço, a corrente sai SUBESTIMADA (dois caminhos em paralelo dão impedância
   menor que um), e o resultado carrega o aviso `rede_com_laco` com quantos trechos sobraram fora da
   árvore. Resolver malha exige montar e inverter a matriz de admitância, que é o motor completo e não
   é este item.
4. **Sequência zero atravessando transformador.** O transformador de distribuição do pacote elétrico
   brasileiro é delta no primário e estrela aterrada no secundário: o delta bloqueia a sequência zero
   vinda da média tensão. Por isso, ao descer por um transformador, a impedância de sequência zero
   acumulada é ZERADA e passa a contar do próprio transformador para baixo. É o comportamento correto
   para essa ligação e ESTÁ ESCRITO aqui porque, para outra ligação, estaria errado.
5. **Desequilíbrio e ligação por fase** não entram: o cálculo é por sequências, com a rede tratada como
   equilibrada. Trecho monofásico entra com a mesma impedância do trifásico.
6. **Dispositivo é a chave de média tensão do pacote**, na barra em que ela está. A faixa de interrupção
   não é campo da BDGD: só existe se alguém a cadastrou na feição. Sem ela o veredito é `sem_dado` —
   nunca uma faixa suposta.

COORDENAÇÃO SIMPLES. Para cada barra, o dispositivo a montante é o primeiro dispositivo encontrado
andando da barra em falta para a fonte, começando pela barra ANTERIOR (dispositivo que está na própria
barra em falta não é "a montante" dela: a falta está nos terminais dele). O veredito compara a corrente
trifásica calculada com a faixa de interrupção cadastrada do dispositivo:

  `interrompe`             — a corrente cai dentro da faixa;
  `abaixo_da_faixa`        — abaixo do mínimo: o dispositivo não enxerga a falta;
  `acima_da_capacidade`    — acima do máximo: o dispositivo não interrompe essa corrente;
  `sem_dado`               — o dispositivo não tem faixa cadastrada;
  `sem_dispositivo_a_montante` — não há dispositivo entre a barra e a fonte.

Fontes declaradas no item: pandapower.readthedocs.io/en/latest/shortcircuit.html e
opendss.epri.com/opendss_documentation.html (acesso 2026-09-08).
"""

import math
import time
from heapq import heappop, heappush

from app.rede_utilidades import opendss, pandapower_rede

# nomes aceitos para a faixa de interrupção do dispositivo, em ampere. Genéricos primeiro; a variante com
# o prefixo do grupo do pacote elétrico brasileiro depois (é assim que a importação BDGD nomeia coluna).
ATRIBUTOS_FAIXA_MIN = ("corrente_interrupcao_min_a", "unsemt_corrente_interrupcao_min_a")
ATRIBUTOS_FAIXA_MAX = ("corrente_interrupcao_max_a", "unsemt_corrente_interrupcao_max_a")

PREMISSAS_PADRAO = {
    "potencia_de_curto_mva": None,
    "relacao_x_r_fonte": 10.0,
    "fator_tensao_c": 1.05,
    "fator_sequencia_zero_linha": 3.0,
    "fator_sequencia_zero_fonte": 1.0,
    "base_mva": 100.0,
}
VEREDITOS = ("interrompe", "abaixo_da_faixa", "acima_da_capacidade", "sem_dado",
             "sem_dispositivo_a_montante")
# teto de corrente que ainda é número: acima disso a impedância é praticamente nula e o valor não
# significa nada. Serve de rede de segurança contra premissa absurda que passe pelas validações.
IK_MAXIMA_A = 1e9


class ErroCurto(Exception):
    """Premissa que falta ou não fecha. Quem chama traduz para o erro da API (422)."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _positivo(valor, nome: str, codigo: str) -> float:
    n = opendss._numero(valor)
    if n is None:
        raise ErroCurto(codigo, f"{nome} não é número")
    if n <= 0:
        raise ErroCurto(codigo, f"{nome} tem de ser maior que zero (veio {n})")
    return n


def validar_premissas(pedidas: dict | None) -> dict:
    """Completa o que falta com o padrão e RECUSA o que não fecha.

    A recusa que o item exige: fonte sem potência de curto-circuito declarada, ou com potência zero, é
    uma fonte de impedância NULA — corrente infinita em toda barra. Não há valor padrão razoável para
    isso (depende da subestação), então não se inventa um: recusa-se, dizendo o nome do que falta."""
    pedidas = dict(pedidas or {})
    desconhecidas = sorted(set(pedidas) - set(PREMISSAS_PADRAO))
    if desconhecidas:
        raise ErroCurto("premissa_desconhecida",
                        "premissa que este cálculo não conhece: " + ", ".join(desconhecidas))
    p = {k: pedidas.get(k, v) for k, v in PREMISSAS_PADRAO.items()}
    if p["potencia_de_curto_mva"] is None:
        raise ErroCurto(
            "impedancia_de_fonte_ausente",
            "declare potencia_de_curto_mva: sem a potência de curto-circuito da fonte a impedância dela "
            "é nula e a corrente calculada seria infinita")
    p["potencia_de_curto_mva"] = _positivo(
        p["potencia_de_curto_mva"], "potencia_de_curto_mva", "impedancia_de_fonte_nula")
    p["relacao_x_r_fonte"] = _positivo(p["relacao_x_r_fonte"], "relacao_x_r_fonte", "premissa_invalida")
    p["fator_tensao_c"] = _positivo(p["fator_tensao_c"], "fator_tensao_c", "premissa_invalida")
    p["fator_sequencia_zero_linha"] = _positivo(
        p["fator_sequencia_zero_linha"], "fator_sequencia_zero_linha", "premissa_invalida")
    p["fator_sequencia_zero_fonte"] = _positivo(
        p["fator_sequencia_zero_fonte"], "fator_sequencia_zero_fonte", "premissa_invalida")
    p["base_mva"] = _positivo(p["base_mva"], "base_mva", "premissa_invalida")
    if p["fator_tensao_c"] > 2.0:
        raise ErroCurto("premissa_invalida",
                        "fator_tensao_c acima de 2,0 não é fator de tensão de norma nenhuma")
    p["impedancia_da_fonte_pu"] = p["base_mva"] / p["potencia_de_curto_mva"]
    return p


def _impedancia_da_fonte(premissas: dict) -> complex:
    """Impedância da fonte em por unidade na base do cálculo. |z| = base/Sk"; a relação X/R declarada
    reparte o módulo entre resistência e reatância."""
    modulo = premissas["impedancia_da_fonte_pu"]
    xr = premissas["relacao_x_r_fonte"]
    r = modulo / math.sqrt(1.0 + xr * xr)
    return complex(r, xr * r)


def _z_linha_pu(comprimento_km: float, kv: float, base_mva: float) -> complex:
    """Impedância de sequência positiva do trecho, em por unidade. Os ohms por quilômetro são os de
    REFERÊNCIA (limitação 1 do cabeçalho): o pacote de ativos não tem catálogo de condutor."""
    z_ohm = complex(pandapower_rede.IMPEDANCIA_REFERENCIA["r_ohm_per_km"],
                    pandapower_rede.IMPEDANCIA_REFERENCIA["x_ohm_per_km"]) * comprimento_km
    return z_ohm * base_mva / (kv * kv)


def _z_trafo_pu(trafo: dict, base_mva: float) -> complex:
    """Impedância do transformador em por unidade na base do cálculo. `vk_percent` é o de referência
    (limitação 2); a parte resistiva vem de `resistencia_pc`, que a importação calcula das perdas do
    arquivo quando elas existem, e é zero quando não existem."""
    sn_mva = float(trafo["kva"]) / 1000.0
    vk = pandapower_rede.VK_PERCENT_REFERENCIA / 100.0
    vkr = float(trafo.get("resistencia_pc") or 0.0) / 100.0
    vkr = min(vkr, vk)                       # resistência não passa da impedância total
    x = math.sqrt(max(vk * vk - vkr * vkr, 0.0))
    return complex(vkr, x) * base_mva / sn_mva


def _arvore(modelo: dict, premissas: dict) -> tuple[dict, dict, int]:
    """Caminho de menor impedância da fonte a cada barra (Dijkstra pelo módulo da impedância acumulada).

    Devolve `(acumulado, chegada, arestas_fora_da_arvore)`, onde `acumulado[barra] = (z1, z0)` em por
    unidade e `chegada[barra]` é a barra anterior no caminho. `arestas_fora_da_arvore` conta os trechos
    e transformadores que não entraram na árvore: é a medida do laço (limitação 3)."""
    base = premissas["base_mva"]
    k0_linha = premissas["fator_sequencia_zero_linha"]
    barras = modelo["barras"]
    vizinhos: dict[str, list[tuple[str, complex, complex, bool]]] = {}

    def ligar(a: str, b: str, z1: complex, z0: complex, atravessa_trafo: bool) -> None:
        vizinhos.setdefault(a, []).append((b, z1, z0, atravessa_trafo))
        vizinhos.setdefault(b, []).append((a, z1, z0, atravessa_trafo))

    ligacoes = 0
    for t in modelo["linhas"]:
        kv = barras.get(t["barra1"]) or barras.get(t["barra2"])
        if not kv or kv <= 0:
            continue
        z1 = _z_linha_pu(float(t["comprimento_km"]), float(kv), base)
        ligar(t["barra1"], t["barra2"], z1, z1 * k0_linha, False)
        ligacoes += 1
    for x in modelo["trafos"]:
        z1 = _z_trafo_pu(x, base)
        ligar(x["barra_at"], x["barra_bt"], z1, z1, True)
        ligacoes += 1

    fonte = modelo["barra_fonte"]
    z1_fonte = _impedancia_da_fonte(premissas)
    z0_fonte = z1_fonte * premissas["fator_sequencia_zero_fonte"]
    acumulado: dict[str, tuple[complex, complex]] = {fonte: (z1_fonte, z0_fonte)}
    chegada: dict[str, str | None] = {fonte: None}
    fila: list[tuple[float, str]] = [(abs(z1_fonte), fonte)]
    fechadas: set[str] = set()
    while fila:
        _, atual = heappop(fila)
        if atual in fechadas:
            continue
        fechadas.add(atual)
        z1_atual, z0_atual = acumulado[atual]
        for prox, z1, z0, atravessa_trafo in vizinhos.get(atual, ()):
            # o delta do primário bloqueia a sequência zero da média tensão: descer pelo transformador
            # ZERA o acumulado de sequência zero (limitação 4 do cabeçalho).
            novo = (z1_atual + z1, z0 if atravessa_trafo else z0_atual + z0)
            if prox not in acumulado or abs(novo[0]) < abs(acumulado[prox][0]) - 1e-15:
                acumulado[prox] = novo
                chegada[prox] = atual
                heappush(fila, (abs(novo[0]), prox))
    fora = max(ligacoes - max(len(acumulado) - 1, 0), 0)
    return acumulado, chegada, fora


def _faixa(atributos: dict) -> tuple[float | None, float | None]:
    minimo = opendss._numero(opendss.atributo(atributos or {}, *ATRIBUTOS_FAIXA_MIN))
    maximo = opendss._numero(opendss.atributo(atributos or {}, *ATRIBUTOS_FAIXA_MAX))
    if minimo is not None and minimo < 0:
        minimo = None
    if maximo is not None and maximo <= 0:
        maximo = None
    if minimo is not None and maximo is not None and minimo > maximo:
        return None, None            # faixa invertida no cadastro não é faixa: vira sem dado
    return minimo, maximo


def _veredito(ik_a: float | None, minimo: float | None, maximo: float | None) -> str:
    if minimo is None and maximo is None:
        return "sem_dado"
    if ik_a is None:
        return "sem_dado"
    if minimo is not None and ik_a < minimo:
        return "abaixo_da_faixa"
    if maximo is not None and ik_a > maximo:
        return "acima_da_capacidade"
    return "interrompe"


def calcular(modelo: dict, premissas: dict) -> dict:
    """Corrente de curto por barra e coordenação por dispositivo, sobre o modelo em memória.

    Função pura: não toca banco nem disco. `premissas` já veio de `validar_premissas`."""
    inicio = time.perf_counter()
    c = premissas["fator_tensao_c"]
    base = premissas["base_mva"]
    acumulado, chegada, fora_da_arvore = _arvore(modelo, premissas)

    def corrente(kv: float, z1: complex, z0: complex) -> tuple[float | None, float | None]:
        """Trifásica e fase-terra na barra, em ampere. `Ibase = base_mva*1000/(√3·kV)`."""
        if not kv or kv <= 0:
            return None, None
        i_base = base * 1000.0 / (math.sqrt(3.0) * kv)
        z1_mod, z_terra = abs(z1), abs(2.0 * z1 + z0)
        ik3 = None if z1_mod <= 0 else min(c * i_base / z1_mod, IK_MAXIMA_A)
        ik1 = None if z_terra <= 0 else min(3.0 * c * i_base / z_terra, IK_MAXIMA_A)
        return ik3, ik1

    barras = []
    sem_caminho = 0
    for nome in sorted(modelo["barras"]):
        kv = opendss._numero(modelo["barras"][nome])
        z = acumulado.get(nome)
        if z is None:
            sem_caminho += 1
            barras.append({"barra": nome, "kv": kv, "alcancada": False, "ik3_a": None, "ik1_a": None,
                           "z1_pu_r": None, "z1_pu_x": None, "z0_pu_r": None, "z0_pu_x": None})
            continue
        z1, z0 = z
        ik3, ik1 = corrente(kv, z1, z0)
        barras.append({
            "barra": nome, "kv": kv, "alcancada": True,
            "ik3_a": None if ik3 is None else round(ik3, 3),
            "ik1_a": None if ik1 is None else round(ik1, 3),
            "z1_pu_r": round(z1.real, 9), "z1_pu_x": round(z1.imag, 9),
            "z0_pu_r": round(z0.real, 9), "z0_pu_x": round(z0.imag, 9),
        })
    ik3_por_barra = {b["barra"]: b["ik3_a"] for b in barras}

    # dispositivo por barra: a chave está na barra em que os seus nós caíram depois da fusão
    por_barra: dict[str, list[dict]] = {}
    for chave in modelo.get("chaves", ()):
        for barra in chave.get("barras") or ():
            por_barra.setdefault(barra, []).append(chave)

    def montante(barra: str) -> dict | None:
        """Primeiro dispositivo andando da barra para a fonte, SEM contar a própria barra em falta."""
        visto = {barra}
        atual = chegada.get(barra)
        while atual is not None and atual not in visto:
            visto.add(atual)
            se_houver = por_barra.get(atual)
            if se_houver:
                return se_houver[0]
            atual = chegada.get(atual)
        return None

    dispositivos = []
    for b in barras:
        chave = montante(b["barra"]) if b["alcancada"] else None
        if chave is None:
            dispositivos.append({"barra": b["barra"], "feicao_id": None, "codigo": None, "tipo": None,
                                 "estado": None, "barra_do_dispositivo": None,
                                 "ik3_a": b["ik3_a"], "faixa_min_a": None, "faixa_max_a": None,
                                 "veredito": "sem_dispositivo_a_montante"})
            continue
        minimo, maximo = _faixa(chave.get("atributos") or {})
        barra_do_dispositivo = (chave.get("barras") or [None])[0]
        dispositivos.append({
            "barra": b["barra"], "feicao_id": chave.get("feicao_id"),
            "codigo": None if chave.get("codigo") is None else str(chave["codigo"]),
            "tipo": chave.get("tipo"), "estado": chave.get("estado"),
            "barra_do_dispositivo": barra_do_dispositivo,
            "ik3_a": b["ik3_a"], "faixa_min_a": minimo, "faixa_max_a": maximo,
            "veredito": _veredito(b["ik3_a"], minimo, maximo),
        })

    avisos = []
    if fora_da_arvore:
        avisos.append({
            "codigo": "rede_com_laco",
            "mensagem": "a subrede tem trecho fora da árvore de menor impedância: onde há laço a "
                        "corrente sai subestimada, porque este cálculo soma ao longo de um caminho só",
            "quantidade": fora_da_arvore})
    if sem_caminho:
        avisos.append({
            "codigo": "barra_sem_caminho_ate_a_fonte",
            "mensagem": "barra que não chega à fonte pela topologia: sai sem corrente, nunca com zero",
            "quantidade": sem_caminho})
    alcancadas = [b for b in barras if b["alcancada"] and b["ik3_a"] is not None]
    contagem_veredito: dict[str, int] = {}
    for d in dispositivos:
        contagem_veredito[d["veredito"]] = contagem_veredito.get(d["veredito"], 0) + 1
    return {
        "barras": barras, "dispositivos": dispositivos, "avisos": avisos,
        "premissas": {k: v for k, v in premissas.items()},
        "resumo": {
            "barras": len(barras), "barras_alcancadas": len(alcancadas),
            "barra_fonte": modelo["barra_fonte"], "kv_fonte": modelo["kv_fonte"],
            "ik3_maxima_a": max((b["ik3_a"] for b in alcancadas), default=None),
            "ik3_minima_a": min((b["ik3_a"] for b in alcancadas), default=None),
            "arestas_fora_da_arvore": fora_da_arvore,
            "dispositivos_por_veredito": contagem_veredito,
            "impedancia_de_referencia": dict(pandapower_rede.IMPEDANCIA_REFERENCIA),
            "vk_percent_de_referencia": pandapower_rede.VK_PERCENT_REFERENCIA,
        },
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
        "ik3_por_barra": ik3_por_barra,
    }


def _no_id(barra: str) -> str | None:
    """O nome da barra é `b` + o identificador do nó sem hífen (`opendss._barra`). Aqui se desfaz isso,
    para que a camada leia a coordenada de `plat.rede_topo_no`. Barra que não tem essa forma (nunca
    acontece hoje, mas o nome é texto) devolve nulo em vez de um identificador inventado."""
    if not barra or len(barra) != 33 or barra[0] != "b":
        return None
    corpo = barra[1:]
    try:
        int(corpo, 16)
    except ValueError:
        return None
    return f"{corpo[:8]}-{corpo[8:12]}-{corpo[12:16]}-{corpo[16:20]}-{corpo[20:]}"


def modelo_da_subrede(cur, rede_id: str, nome: str, tier: str | None, ano: int | None,
                      jusante: bool) -> tuple[dict, dict]:
    """Mesma preparação de `subredes.exportar_dss`/`exportar_equilibrada`, reusada inteira: o modelo do
    curto é o MESMO que os exportadores usam. Pública porque o fluxo de potência (item L4-07) parte deste
    mesmo modelo — dois cálculos elétricos sobre a mesma leitura do banco, nunca duas leituras."""
    from datetime import datetime, timezone

    from app.erros import ErroAPI
    from app.rede_utilidades import controladores, subredes

    s = subredes.por_nome(cur, rede_id, nome, tier)
    if s["atualizado_em"] is None:
        raise ErroAPI(409, "subrede_nunca_atualizada",
                      "esta subrede ainda não foi atualizada: não há elementos gravados para calcular")
    dela = [c for c in controladores.listar_controladores(cur, rede_id, 1000)
            if c["subrede_id"] == str(s["id"])]
    s = dict(s)
    s["propagados"] = (dict(s["resumo"] or {})).get("propagados") or {}
    ids = [str(s["id"])]
    if jusante:
        ids = opendss.subredes_de_jusante(cur, rede_id, ids, s["tier_ordem"])
    try:
        modelo = opendss.montar_da_subrede(
            cur, rede_id, s, dela, ano if ano is not None else datetime.now(timezone.utc).year, ids)
    except opendss.ErroConversao as e:
        raise ErroAPI(422, e.codigo, e.mensagem) from e
    return s, modelo


def calcular_e_gravar(cur, tenant_id: int, rede_id: str, nome: str, premissas_pedidas: dict | None,
                      tier: str | None = None, ano: int | None = None, jusante: bool = False) -> dict:
    """Calcula o curto da subrede e grava a execução, as barras e os dispositivos. Cálculo novo da mesma
    subrede substitui o anterior (uma execução viva por subrede)."""
    import json

    premissas = validar_premissas(premissas_pedidas)
    s, modelo = modelo_da_subrede(cur, rede_id, nome, tier, ano, jusante)
    saida = calcular(modelo, premissas)

    cur.execute("DELETE FROM plat.rede_curto_execucao WHERE subrede_id = %s::uuid", (str(s["id"]),))
    cur.execute(
        "INSERT INTO plat.rede_curto_execucao "
        "(tenant_id, rede_id, subrede_id, subrede_nome, premissas, resumo, avisos, barras, duracao_ms) "
        "VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s) RETURNING id",
        (tenant_id, rede_id, str(s["id"]), s["nome"],
         json.dumps(saida["premissas"], ensure_ascii=False),
         json.dumps(saida["resumo"], ensure_ascii=False),
         json.dumps(saida["avisos"], ensure_ascii=False),
         len(saida["barras"]), saida["duracao_ms"]))
    execucao_id = str(cur.fetchone()["id"])

    cur.executemany(
        "INSERT INTO plat.rede_curto_barra (tenant_id, execucao_id, barra, no_id, kv, alcancada, "
        "ik3_a, ik1_a, z1_pu_r, z1_pu_x, z0_pu_r, z0_pu_x) "
        "VALUES (%(t)s, %(e)s::uuid, %(barra)s, %(no)s::uuid, %(kv)s, %(alc)s, %(ik3)s, %(ik1)s, "
        "%(z1r)s, %(z1x)s, %(z0r)s, %(z0x)s)",
        [{"t": tenant_id, "e": execucao_id, "barra": b["barra"], "no": _no_id(b["barra"]), "kv": b["kv"],
          "alc": b["alcancada"], "ik3": b["ik3_a"], "ik1": b["ik1_a"], "z1r": b["z1_pu_r"],
          "z1x": b["z1_pu_x"], "z0r": b["z0_pu_r"], "z0x": b["z0_pu_x"]} for b in saida["barras"]])
    cur.executemany(
        "INSERT INTO plat.rede_curto_dispositivo (tenant_id, execucao_id, barra, no_id, feicao_id, "
        "codigo, tipo, estado, ik3_a, faixa_min_a, faixa_max_a, veredito) "
        "VALUES (%(t)s, %(e)s::uuid, %(barra)s, %(no)s::uuid, %(f)s::uuid, %(cod)s, %(tipo)s, "
        "%(estado)s, %(ik3)s, %(min)s, %(max)s, %(v)s)",
        [{"t": tenant_id, "e": execucao_id, "barra": d["barra"],
          "no": _no_id(d["barra_do_dispositivo"] or ""), "f": d["feicao_id"], "cod": d["codigo"],
          "tipo": d["tipo"], "estado": d["estado"], "ik3": d["ik3_a"], "min": d["faixa_min_a"],
          "max": d["faixa_max_a"], "v": d["veredito"]} for d in saida["dispositivos"]])
    return {"execucao_id": execucao_id, "subrede": s["nome"], "tier": s["tier"],
            "premissas": saida["premissas"], "resumo": saida["resumo"], "avisos": saida["avisos"],
            "barras": len(saida["barras"]), "duracao_ms": saida["duracao_ms"]}


# Descrição das colunas da tabela, para o painel ligar um elemento a esta fonte sem que ninguém escreva
# rótulo à mão (mesmo padrão de `resumos.COLUNAS`).
COLUNAS = [
    {"codigo": "barra", "nome": "Barra", "tipo": "texto", "unidade": None},
    {"codigo": "kv", "nome": "Tensão de base", "tipo": "numero", "unidade": "kV"},
    {"codigo": "ik3_a", "nome": "Curto trifásico", "tipo": "numero", "unidade": "A"},
    {"codigo": "ik1_a", "nome": "Curto fase-terra", "tipo": "numero", "unidade": "A"},
    {"codigo": "alcancada", "nome": "Chega à fonte", "tipo": "booleano", "unidade": None},
    {"codigo": "dispositivo_codigo", "nome": "Dispositivo a montante", "tipo": "texto", "unidade": None},
    {"codigo": "faixa_min_a", "nome": "Faixa mínima de interrupção", "tipo": "numero", "unidade": "A"},
    {"codigo": "faixa_max_a", "nome": "Faixa máxima de interrupção", "tipo": "numero", "unidade": "A"},
    {"codigo": "veredito", "nome": "Coordenação", "tipo": "texto", "unidade": None},
]


def _execucao(cur, rede_id: str, nome: str) -> dict:
    from app.erros import ErroAPI

    cur.execute(
        "SELECT id, subrede_id, subrede_nome, premissas, resumo, avisos, barras, duracao_ms, calculado_em "
        "FROM plat.rede_curto_execucao WHERE rede_id = %s::uuid AND subrede_nome = %s",
        (rede_id, nome))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "curto_nao_calculado",
                      "esta subrede ainda não teve o curto-circuito calculado")
    return dict(r)


def _linhas(cur, execucao_id: str) -> list[dict]:
    cur.execute(
        "SELECT b.barra, b.no_id, b.kv, b.alcancada, b.ik3_a, b.ik1_a, b.z1_pu_r, b.z1_pu_x, "
        "       b.z0_pu_r, b.z0_pu_x, d.codigo AS dispositivo_codigo, d.tipo AS dispositivo_tipo, "
        "       d.estado AS dispositivo_estado, d.feicao_id AS dispositivo_feicao_id, "
        "       d.faixa_min_a, d.faixa_max_a, d.veredito "
        "FROM plat.rede_curto_barra b "
        "LEFT JOIN plat.rede_curto_dispositivo d ON d.execucao_id = b.execucao_id AND d.barra = b.barra "
        "WHERE b.execucao_id = %s::uuid ORDER BY b.ik3_a DESC NULLS LAST, b.barra",
        (execucao_id,))
    return [{k: (str(v) if k.endswith("_id") and v is not None else v) for k, v in dict(r).items()}
            for r in cur.fetchall()]


def tabela(cur, rede_id: str, nome: str) -> dict:
    """A tabela do resultado: colunas descritas, linhas ordenadas da maior corrente para a menor, e as
    premissas do cálculo ao lado — o número nunca sai sem a hipótese que o produziu."""
    e = _execucao(cur, rede_id, nome)
    from app.auth.sessao import iso

    return {"subrede": e["subrede_nome"], "execucao_id": str(e["id"]),
            "calculado_em": iso(e["calculado_em"]), "premissas": e["premissas"],
            "resumo": e["resumo"], "avisos": e["avisos"], "duracao_ms": e["duracao_ms"],
            "colunas": COLUNAS, "linhas": _linhas(cur, str(e["id"]))}


def camada(cur, rede_id: str, nome: str) -> dict:
    """O MESMO resultado como camada: um ponto por barra, com a corrente e o veredito de coordenação nas
    propriedades. A coordenada vem de `plat.rede_topo_no` na hora da leitura, nunca de cópia gravada.
    Barra sem nó com geometria não vira feição — nunca ponto (0, 0)."""
    e = _execucao(cur, rede_id, nome)
    cur.execute(
        "SELECT b.barra, b.kv, b.ik3_a, b.ik1_a, b.alcancada, ST_X(n.geom) AS lon, ST_Y(n.geom) AS lat, "
        "       d.codigo AS dispositivo_codigo, d.faixa_min_a, d.faixa_max_a, d.veredito "
        "FROM plat.rede_curto_barra b "
        "JOIN plat.rede_topo_no n ON n.id = b.no_id "
        "LEFT JOIN plat.rede_curto_dispositivo d ON d.execucao_id = b.execucao_id AND d.barra = b.barra "
        "WHERE b.execucao_id = %s::uuid ORDER BY b.barra",
        (str(e["id"]),))
    feicoes = []
    for r in cur.fetchall():
        d = dict(r)
        lon, lat = d.pop("lon"), d.pop("lat")
        feicoes.append({"type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                        "properties": d})
    return {"type": "FeatureCollection", "features": feicoes,
            "subrede": e["subrede_nome"], "premissas": e["premissas"],
            "barras_sem_coordenada": int(e["barras"]) - len(feicoes)}
