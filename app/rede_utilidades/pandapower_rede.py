"""Conversor de subrede para pandapower (item L4-05-c-pandapower-e-matpower).

O que este módulo é: um CONECTOR. Ele lê o MESMO modelo em memória que o exportador OpenDSS monta
(`opendss.montar_da_subrede`) e escreve o arquivo que o pandapower lê com `pandapower.from_json`. Não
existe segunda leitura do banco, nem segunda regra de conversão: barra, trecho, transformador e carga
são decididos uma vez só, em `opendss.py`, e daí saem dois formatos. Quem quiser conferir um contra o
outro está comparando o mesmo modelo escrito em duas línguas, não dois modelos.

Correspondência declarada:

  * `bus`      = barra do modelo (nó da topologia, com os terminais de chave fechada já fundidos);
  * `line`     = trecho da subrede com os dois nós na topologia;
  * `trafo`    = transformador de distribuição com os dois lados dentro do recorte;
  * `load`     = unidade consumidora e iluminação pública (potência ativa positiva);
  * `sgen`     = geração distribuída (a mesma que o OpenDSS recebe como carga negativa);
  * `ext_grid` = a barra da fonte, na tensão que o alimentador propaga.

Formato do arquivo: o serializador do pandapower (`pandapower.io_utils`) grava um objeto
`{"_module", "_class", "_object"}` onde cada tabela é um `DataFrame` do pandas em `orient="split"` com
os tipos ao lado. Este módulo escreve esse mesmo objeto com a biblioteca padrão — a plataforma NÃO
importa pandapower em tempo de execução (ver `requirements.txt`: o pacote entra só para a suíte
provar que o arquivo é lido e que o fluxo converge).

Fontes: pandapower.readthedocs.io (formato dos elementos e do fluxo de potência CA),
github.com/e2nIEE/pandapower (serialização), manual do OpenDSS (os valores padrão citados abaixo).
"""

import json
import math

# --- impedância de referência ---------------------------------------------------------------------
# O pacote de ativos não tem catálogo de condutor (é a limitação 1 do NAO_FAZ do exportador OpenDSS).
# O OpenDSS resolve isso em silêncio: um `Line` sem impedância declarada recebe os valores PADRÃO do
# motor. O pandapower não tem esse silêncio — sem r/x/c o fluxo nem roda. Então o conector ESCREVE os
# mesmos valores padrão do OpenDSS, nomeados, em vez de inventar um condutor: assim os dois arquivos
# exportados descrevem a mesma rede elétrica, e a comparação entre os dois motores é honesta.
# Valores padrão do objeto Line do OpenDSS (sequência positiva, por unidade de comprimento em km):
IMPEDANCIA_REFERENCIA = {
    "r_ohm_per_km": 0.058,
    "x_ohm_per_km": 0.1206,
    "c_nf_per_km": 3.4,
    "max_i_ka": 0.4,          # normamps padrão do OpenDSS: 400 A
}
# Valor padrão de XHL do objeto Transformer do OpenDSS, em por cento. Mesma razão: o arquivo da
# distribuidora não traz reatância de dispersão, e o pandapower exige `vk_percent`.
VK_PERCENT_REFERENCIA = 7.0

FATOR_DE_POTENCIA_MINIMO = 1e-6

RELATORIO_NAO_FAZ = """# O que este conector não faz

Este arquivo sai junto com todo modelo pandapower exportado. Ele vale JUNTO com o `NAO_FAZ.md` do
exportador OpenDSS: as duas saídas vêm do mesmo modelo em memória, então todas as limitações de lá
valem aqui. O que segue é o que muda por causa do formato.

1. **Impedância de linha.** O pacote de ativos não tem catálogo de condutor. Toda `line` sai com a
   impedância de REFERÊNCIA declarada em `pandapower_rede.IMPEDANCIA_REFERENCIA`, que é o valor padrão
   do objeto `Line` do OpenDSS. Ou seja: o perfil de tensão do fluxo NÃO é medição desta rede; ele
   prova que a topologia fecha e resolve, e permite comparar os dois motores sobre a mesma hipótese.
2. **Reatância de dispersão do transformador.** Mesma coisa: `vk_percent` sai com o padrão do OpenDSS
   (7 %). `vkr_percent` e `pfe_kw` saem do arquivo quando PER_TOT e PER_FER existem, e só então.
3. **Chave manobrável.** A chave fechada já foi fundida numa barra só no modelo, como no OpenDSS.
   Não sai `switch` no arquivo pandapower, então o modelo não permite abrir a chave dentro do
   pandapower. O estado de cada chave está em `resumo.json`.
4. **Desequilíbrio entre fases.** O fluxo de potência CA do pandapower (`runpp`) é EQUILIBRADO: ele
   resolve uma sequência positiva. A rede de distribuição da qual esta subrede sai é desequilibrada, e
   as fases declaradas por trecho (o bitmask A/B/C) NÃO são representadas — cada `line` entra com a
   quantidade de fases só no nome. Onde o desequilíbrio importa, o OpenDSS é o motor certo; este
   arquivo serve para trocar rede com quem trabalha em pandapower, não para substituir aquele.
5. **Curva de carga.** Os 864 pontos da curva anual não têm equivalente direto no `net` do pandapower
   (lá isso é `ConstControl` + `DFData`, que é código, não dado). Cada `load` sai com a POTÊNCIA MÉDIA
   do ano, a mesma que alimenta a curva no OpenDSS. A curva sai só no formato OpenDSS.
6. **Convergência.** O conector garante que o arquivo é LIDO pelo pandapower. Ele não promete que o
   fluxo converge: isso depende do cadastro e é medido caso a caso.
"""

# Colunas e tipos de cada tabela, na ordem em que o pandapower 3.5 as cria. Escritos aqui porque a
# plataforma não importa pandapower: se a versão pinada mudar o esquema, o teste do item reprova.
_TABELAS: dict[str, list[tuple[str, str]]] = {
    "bus": [("name", "object"), ("vn_kv", "float64"), ("type", "object"), ("zone", "object"),
            ("in_service", "bool"), ("geo", "object")],
    "line": [("name", "object"), ("std_type", "object"), ("from_bus", "uint32"), ("to_bus", "uint32"),
             ("length_km", "float64"), ("r_ohm_per_km", "float64"), ("x_ohm_per_km", "float64"),
             ("c_nf_per_km", "float64"), ("g_us_per_km", "float64"), ("max_i_ka", "float64"),
             ("df", "float64"), ("parallel", "uint32"), ("type", "object"), ("in_service", "bool"),
             ("geo", "object")],
    "trafo": [("name", "object"), ("std_type", "object"), ("hv_bus", "uint32"), ("lv_bus", "uint32"),
              ("sn_mva", "float64"), ("vn_hv_kv", "float64"), ("vn_lv_kv", "float64"),
              ("vk_percent", "float64"), ("vkr_percent", "float64"), ("pfe_kw", "float64"),
              ("i0_percent", "float64"), ("shift_degree", "float64"), ("tap_side", "object"),
              ("tap_neutral", "float64"), ("tap_min", "float64"), ("tap_max", "float64"),
              ("tap_step_percent", "float64"), ("tap_step_degree", "float64"), ("tap_pos", "float64"),
              ("tap_changer_type", "object"), ("id_characteristic_table", "Int64"),
              ("tap_dependency_table", "bool"), ("parallel", "uint32"), ("df", "float64"),
              ("in_service", "bool")],
    "load": [("name", "object"), ("bus", "uint32"), ("p_mw", "float64"), ("q_mvar", "float64"),
             ("const_z_p_percent", "float64"), ("const_i_p_percent", "float64"),
             ("const_z_q_percent", "float64"), ("const_i_q_percent", "float64"), ("sn_mva", "float64"),
             ("scaling", "float64"), ("in_service", "bool"), ("type", "object")],
    "sgen": [("name", "object"), ("bus", "int64"), ("p_mw", "float64"), ("q_mvar", "float64"),
             ("min_q_mvar", "float64"), ("max_q_mvar", "float64"), ("sn_mva", "float64"),
             ("scaling", "float64"), ("controllable", "bool"),
             ("id_q_capability_characteristic", "Int64"), ("reactive_capability_curve", "bool"),
             ("curve_style", "object"), ("in_service", "bool"), ("type", "object"),
             ("current_source", "bool")],
    "ext_grid": [("name", "object"), ("bus", "uint32"), ("vm_pu", "float64"), ("va_degree", "float64"),
                 ("slack_weight", "float64"), ("in_service", "bool"), ("controllable", "bool")],
}


def _quadro(nome: str, linhas: list[list]) -> dict:
    """Uma tabela no formato que o leitor do pandapower espera: DataFrame em `orient="split"`."""
    colunas = [c for c, _ in _TABELAS[nome]]
    corpo = {"columns": colunas, "index": list(range(len(linhas))), "data": linhas}
    return {
        "_module": "pandas.core.frame", "_class": "DataFrame",
        "_object": json.dumps(corpo, ensure_ascii=False),
        "orient": "split", "dtype": {c: t for c, t in _TABELAS[nome]},
        "is_multiindex": False, "is_multicolumn": False,
    }


def _geo(coordenada) -> str | None:
    """Coordenada da barra no campo `geo` do pandapower 3.x, que é um GeoJSON em texto. Sem coordenada
    o campo fica NULO — nunca ponto (0, 0), que seria a Ilha Nula no golfo da Guiné."""
    if not coordenada:
        return None
    lon, lat = coordenada
    return json.dumps({"coordinates": [lon, lat], "type": "Point"})


def _q_mvar(kw: float, fator_de_potencia: float) -> float:
    """Potência reativa que corresponde à ativa e ao fator de potência declarado. O OpenDSS recebe
    `pf`; o pandapower recebe `q_mvar`, então a conta é feita aqui, uma vez."""
    fp = min(max(abs(float(fator_de_potencia)), FATOR_DE_POTENCIA_MINIMO), 1.0)
    if fp >= 1.0:
        return 0.0
    return (kw / 1000.0) * math.sqrt(1.0 - fp * fp) / fp


def montar_net(modelo: dict, coordenadas: dict[str, tuple[float, float]] | None = None) -> dict:
    """Modelo em memória (o de `opendss.montar_da_subrede`) → objeto `pandapowerNet` serializado.

    `coordenadas` é opcional: barra → (longitude, latitude) em WGS84. Barra sem coordenada sai com
    `geo` nulo. Função pura: não toca banco nem disco.
    """
    coordenadas = coordenadas or {}
    barras = sorted(modelo["barras"])                       # ordem estável: o arquivo é reproduzível
    indice = {b: i for i, b in enumerate(barras)}

    bus = [[b, float(modelo["barras"][b]), "b", None, True, _geo(coordenadas.get(b))] for b in barras]

    line = []
    for t in modelo["linhas"]:
        if t["barra1"] not in indice or t["barra2"] not in indice:
            continue
        line.append([
            f"{t['nome']} ({len(t['fases'])}f)", None, indice[t["barra1"]], indice[t["barra2"]],
            float(t["comprimento_km"]),
            IMPEDANCIA_REFERENCIA["r_ohm_per_km"], IMPEDANCIA_REFERENCIA["x_ohm_per_km"],
            IMPEDANCIA_REFERENCIA["c_nf_per_km"], 0.0, IMPEDANCIA_REFERENCIA["max_i_ka"],
            1.0, 1, "ol", True, None,
        ])

    trafo = []
    for x in modelo["trafos"]:
        if x["barra_at"] not in indice or x["barra_bt"] not in indice:
            continue
        kva = float(x["kva"])
        trafo.append([
            x["codigo"], None, indice[x["barra_at"]], indice[x["barra_bt"]], kva / 1000.0,
            float(x["kv_at"]), float(x["kv_bt"]), VK_PERCENT_REFERENCIA,
            0.0 if x.get("resistencia_pc") is None else float(x["resistencia_pc"]),
            # perda de ferro: o modelo guarda POR CENTO da potência aparente (100*P/(1000*kVA));
            # o pandapower quer quilowatt. P_kW = por_cento/100 * kVA.
            0.0 if x.get("perda_ferro_pc") is None else float(x["perda_ferro_pc"]) * kva / 100.0,
            0.0, 0.0, None, None, None, None, None, None, None, None, None, False, 1, 1.0, True,
        ])

    load, sgen = [], []
    for c in modelo["cargas"]:
        if c["barra"] not in indice:
            continue
        kw = float(c["kw"])
        if kw < 0:
            sgen.append([c["nome"], indice[c["barra"]], -kw / 1000.0,
                         _q_mvar(-kw, c["fator_de_potencia"]), None, None, None, 1.0, False,
                         None, False, None, True, "wye", True])
        else:
            load.append([c["nome"], indice[c["barra"]], kw / 1000.0,
                         _q_mvar(kw, c["fator_de_potencia"]),
                         0.0, 0.0, 0.0, 0.0, None, 1.0, True, "wye"])

    fonte = modelo["barra_fonte"]
    ext_grid = []
    if fonte in indice:
        ext_grid.append(["fonte", indice[fonte], float(modelo.get("pu_fonte", 1.0)), 0.0, 1.0,
                         True, False])

    objeto: dict = {nome: _quadro(nome, linhas) for nome, linhas in
                    (("bus", bus), ("line", line), ("trafo", trafo), ("load", load),
                     ("sgen", sgen), ("ext_grid", ext_grid))}
    objeto.update({
        "version": "3.5.4", "format_version": "3.1.0",
        "converged": False, "OPF_converged": False,
        "name": str(modelo["nome"]), "f_hz": 60.0, "sn_mva": 1.0,
    })
    return {"_module": "pandapower.auxiliary", "_class": "pandapowerNet", "_object": objeto}


def conferencia(modelo: dict, net: dict) -> dict:
    """Contagem lado a lado: o que o modelo tem e o que o arquivo pandapower levou. A cláusula do
    portão do item é que bus = barras, line = trechos e trafo = transformadores."""
    obj = net["_object"]

    def n(tabela: str) -> int:
        return len(json.loads(obj[tabela]["_object"])["data"])

    c = modelo["conferencia"]
    return {
        "bus": n("bus"), "barras_esperadas": c["barras_esperadas"],
        "line": n("line"), "linhas_esperadas": c["linhas_esperadas"],
        "trafo": n("trafo"), "transformadores_esperados": c["transformadores"],
        "load": n("load"), "cargas_esperadas": c["cargas"],
        "sgen": n("sgen"), "geracao_distribuida_esperada": c["geracao_distribuida"],
        "ext_grid": n("ext_grid"),
        "impedancia_de_referencia": dict(IMPEDANCIA_REFERENCIA),
        "vk_percent_de_referencia": VK_PERCENT_REFERENCIA,
        "barras_com_coordenada": sum(
            1 for linha in json.loads(obj["bus"]["_object"])["data"] if linha[5] is not None),
    }


def texto(net: dict) -> str:
    """O arquivo `.json` que `pandapower.from_json` lê."""
    return json.dumps(net, ensure_ascii=False, indent=1, allow_nan=False) + "\n"
