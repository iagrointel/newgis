"""Leitura e escrita do arquivo EPANET `.inp` (item L4-05-d-epanet-inp; ADR 20260907T1629).

Duas funções puras, sem banco, sem rede: `ler_inp(texto) -> DocumentoEpanet` (o `.inp` inteiro numa estrutura
Python) e `escrever_inp(doc) -> str` (a volta). A cláusula central do portão do item é a IDA E VOLTA: um doc
lido e escrito de novo tem de valer o mesmo doc — mesmas seções, mesmas contagens, mesmos campos — mesmo que o
texto byte a byte mude (ordem de token, espaçamento). `montar_feicoes()`/`extrair_doc()` fazem a ponte com o
modelo de feições da rede de utilidades (`plat.rede_feicao_ponto`/`rede_feicao_linha`, item L4-01-b): o .inp vai
para lá e volta de lá — nunca guardamos o arquivo recebido para "exportar de volta o mesmo arquivo" (a mesma
regra do pacote de ativos, `pacote.py`, linha 4-7 do docstring).

Seções cobertas (as declaradas no item): JUNCTIONS, RESERVOIRS, TANKS, PIPES, PUMPS, VALVES, COORDINATES,
VERTICES, PATTERNS, CURVES, OPTIONS. Seções fora do escopo (CONTROLS, RULES, DEMANDS, EMITTERS, QUALITY,
SOURCES, REACTIONS, MIXING, ENERGY, TIMES além de Duration, BACKDROP, LABELS, TAGS, ...) são ignoradas com um
aviso (uma vez por seção, não uma vez por linha) — nunca derrubam a importação.

Fronteira honesta (registrada, não escondida): PUMPS e VALVES são LINKS do EPANET — não têm coordenada própria
(o arquivo nunca traz `[COORDINATES]` para um ID de bomba/válvula). O pacote de ativos `agua-epanet` os modela
como PONTO de dois terminais (mesma convenção do transformador da rede elétrica: um dispositivo que CORTA um
trecho). Sem uma coordenada própria no arquivo, este importador usa o PONTO MÉDIO de Node1/Node2 como a posição
do dispositivo — uma aproximação declarada, não uma medição: a topologia derivada (item L4-01-b) só liga esse
ponto a um trecho por coincidência geométrica dentro da tolerância da rede, e o ponto médio não coincide com
nem Node1 nem Node2, então bomba/válvula tende a ficar como NÓ ÓRFÃO da topologia — a ligação real fica só nos
atributos (`bomba_no_1`/`bomba_no_2`, `valvula_no_1`/`valvula_no_2`), nunca inventada na geometria. Registrado
em `docs/adr/20260907T1629-epanet-inp.md` seção "limitação".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SECOES_SUPORTADAS = (
    "JUNCTIONS", "RESERVOIRS", "TANKS", "PIPES", "PUMPS", "VALVES",
    "COORDINATES", "VERTICES", "PATTERNS", "CURVES", "OPTIONS", "TITLE",
)
# tipo de válvula (codigos_fonte do pacote agua-epanet) -> tipo_codigo do grupo "valvula"
TIPO_VALVULA = {"PRV": 1, "PSV": 2, "PBV": 3, "FCV": 4, "TCV": 5, "GPV": 6}
CODIGO_VALVULA = {v: k for k, v in TIPO_VALVULA.items()}


class ErroInp(Exception):
    """Arquivo `.inp` recusado: a mensagem aponta a seção e, quando possível, a linha do texto enviado."""


@dataclass
class DocumentoEpanet:
    titulo: list[str] = field(default_factory=list)
    junctions: list[dict] = field(default_factory=list)
    reservoirs: list[dict] = field(default_factory=list)
    tanks: list[dict] = field(default_factory=list)
    pipes: list[dict] = field(default_factory=list)
    pumps: list[dict] = field(default_factory=list)
    valves: list[dict] = field(default_factory=list)
    coordinates: dict[str, tuple[float, float]] = field(default_factory=dict)
    vertices: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    patterns: dict[str, list[float]] = field(default_factory=dict)
    curves: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    secoes_ignoradas: dict[str, int] = field(default_factory=dict)

    def contagens(self) -> dict:
        return {
            "junctions": len(self.junctions), "reservoirs": len(self.reservoirs), "tanks": len(self.tanks),
            "pipes": len(self.pipes), "pumps": len(self.pumps), "valves": len(self.valves),
            "coordinates": len(self.coordinates), "vertices": len(self.vertices),
            "patterns": len(self.patterns), "curves": len(self.curves),
        }


def _sem_comentario(linha: str) -> str:
    i = linha.find(";")
    return linha if i < 0 else linha[:i]


def _tokens(linha: str) -> list[str]:
    return _sem_comentario(linha).split()


def _num(v: str, contexto: str) -> float:
    try:
        return float(v)
    except ValueError as e:
        raise ErroInp(f"{contexto}: valor numérico esperado, veio {v!r}") from e


def ler_inp(texto: str) -> DocumentoEpanet:
    """Faz um passe único pelo texto. Nunca lança por seção desconhecida (vira aviso); lança `ErroInp` só quando
    uma linha de seção CONHECIDA não tem os campos mínimos ou um campo numérico obrigatório não é número."""
    doc = DocumentoEpanet()
    secao: str | None = None
    for n, bruto in enumerate(texto.splitlines(), start=1):
        crua = bruto.strip()
        if not crua or crua.startswith(";"):
            continue
        m = re.match(r"^\[([A-Za-z0-9_]+)\]", crua)
        if m:
            secao = m.group(1).upper()
            if secao not in SECOES_SUPORTADAS and secao != "END":
                doc.secoes_ignoradas[secao] = doc.secoes_ignoradas.get(secao, 0)
            continue
        if secao is None or secao == "END":
            continue
        if secao == "TITLE":
            if crua:
                doc.titulo.append(bruto.rstrip("\n"))
            continue
        tk = _tokens(crua)
        if not tk:
            continue
        ctx = f"[{secao}] linha {n}"
        if secao in doc.secoes_ignoradas:
            doc.secoes_ignoradas[secao] += 1
            continue
        if secao == "JUNCTIONS":
            if len(tk) < 2:
                raise ErroInp(f"{ctx}: JUNCTIONS exige ao menos ID e Elev ({crua!r})")
            doc.junctions.append({
                "id": tk[0], "elev": _num(tk[1], ctx),
                "demand": _num(tk[2], ctx) if len(tk) > 2 else 0.0,
                "pattern": tk[3] if len(tk) > 3 else None,
            })
        elif secao == "RESERVOIRS":
            if len(tk) < 2:
                raise ErroInp(f"{ctx}: RESERVOIRS exige ao menos ID e Head ({crua!r})")
            doc.reservoirs.append({"id": tk[0], "head": _num(tk[1], ctx), "pattern": tk[2] if len(tk) > 2 else None})
        elif secao == "TANKS":
            if len(tk) < 6:
                raise ErroInp(f"{ctx}: TANKS exige ID Elevation InitLevel MinLevel MaxLevel Diameter ({crua!r})")
            doc.tanks.append({
                "id": tk[0], "elevation": _num(tk[1], ctx), "init_level": _num(tk[2], ctx),
                "min_level": _num(tk[3], ctx), "max_level": _num(tk[4], ctx), "diameter": _num(tk[5], ctx),
                "min_vol": _num(tk[6], ctx) if len(tk) > 6 and tk[6] != "*" else 0.0,
                "vol_curve": tk[7] if len(tk) > 7 and tk[7] not in ("*",) else None,
                "overflow": tk[8].upper() == "YES" if len(tk) > 8 else None,
            })
        elif secao == "PIPES":
            if len(tk) < 6:
                raise ErroInp(f"{ctx}: PIPES exige ID Node1 Node2 Length Diameter Roughness ({crua!r})")
            doc.pipes.append({
                "id": tk[0], "node1": tk[1], "node2": tk[2], "length": _num(tk[3], ctx),
                "diameter": _num(tk[4], ctx), "roughness": _num(tk[5], ctx),
                "minor_loss": _num(tk[6], ctx) if len(tk) > 6 else 0.0,
                "status": tk[7] if len(tk) > 7 else "Open",
            })
        elif secao == "PUMPS":
            if len(tk) < 3:
                raise ErroInp(f"{ctx}: PUMPS exige ID Node1 Node2 ({crua!r})")
            reg = {"id": tk[0], "node1": tk[1], "node2": tk[2], "head_curve": None, "power": None,
                   "pattern": None, "speed": None}
            i = 3
            while i < len(tk):
                chave = tk[i].upper()
                if i + 1 >= len(tk):
                    raise ErroInp(f"{ctx}: parâmetro {chave!r} de PUMPS sem valor")
                valor = tk[i + 1]
                if chave == "HEAD":
                    reg["head_curve"] = valor
                elif chave == "POWER":
                    reg["power"] = _num(valor, ctx)
                elif chave == "PATTERN":
                    reg["pattern"] = valor
                elif chave == "SPEED":
                    reg["speed"] = _num(valor, ctx)
                else:
                    doc.avisos.append(f"{ctx}: parâmetro de bomba {chave!r} não reconhecido, ignorado")
                i += 2
            doc.pumps.append(reg)
        elif secao == "VALVES":
            if len(tk) < 5:
                raise ErroInp(f"{ctx}: VALVES exige ID Node1 Node2 Diameter Type Setting ({crua!r})")
            tipo = tk[4].upper()
            if tipo not in TIPO_VALVULA:
                raise ErroInp(f"{ctx}: tipo de válvula {tipo!r} desconhecido (esperava um de {sorted(TIPO_VALVULA)})")
            doc.valves.append({
                "id": tk[0], "node1": tk[1], "node2": tk[2], "diameter": _num(tk[3], ctx), "type": tipo,
                "setting": _num(tk[5], ctx) if len(tk) > 5 else 0.0,
                "minor_loss": _num(tk[6], ctx) if len(tk) > 6 else 0.0,
            })
        elif secao == "COORDINATES":
            if len(tk) < 3:
                raise ErroInp(f"{ctx}: COORDINATES exige NodeID X Y ({crua!r})")
            doc.coordinates[tk[0]] = (_num(tk[1], ctx), _num(tk[2], ctx))
        elif secao == "VERTICES":
            if len(tk) < 3:
                raise ErroInp(f"{ctx}: VERTICES exige LinkID X Y ({crua!r})")
            doc.vertices.setdefault(tk[0], []).append((_num(tk[1], ctx), _num(tk[2], ctx)))
        elif secao == "PATTERNS":
            if len(tk) < 2:
                raise ErroInp(f"{ctx}: PATTERNS exige PatternID e ao menos um multiplicador ({crua!r})")
            doc.patterns.setdefault(tk[0], []).extend(_num(v, ctx) for v in tk[1:])
        elif secao == "CURVES":
            if len(tk) < 3:
                raise ErroInp(f"{ctx}: CURVES exige CurveID X Y ({crua!r})")
            doc.curves.setdefault(tk[0], []).append((_num(tk[1], ctx), _num(tk[2], ctx)))
        elif secao == "OPTIONS":
            doc.options[tk[0].upper()] = " ".join(tk[1:])
    for secao, n_linhas in doc.secoes_ignoradas.items():
        doc.avisos.append(f"seção [{secao}] fora do escopo deste conector: {n_linhas} linha(s) ignorada(s)")
    return doc


# --------------------------------------------------------------------------------------------------- escrita

def _fmt(v) -> str:
    if isinstance(v, float):
        # `repr` do float do Python é a representação DECIMAL MAIS CURTA que lê de volta o mesmo float (desde o
        # PEP 3101/`repr` novo do 3.1) — ida e volta exata mesmo em coordenada UTM de 7+ dígitos (`%g` com uma
        # contagem fixa de dígitos significativos arredondava 8252603.78 para 8252600.0; achado deste item).
        if v == int(v) and abs(v) < 1e16:
            return str(int(v))
        return repr(v)
    return str(v)


def escrever_inp(doc: DocumentoEpanet) -> str:
    """A volta de `ler_inp`. Determinística (mesma entrada -> mesmo texto); ordem de seções fixa; uma linha em
    branco entre seções (convenção EPANET, aceita por `wntr`/pelo próprio EPANET)."""
    partes: list[str] = []

    def secao(nome: str, cabecalho: str | None, linhas: list[str]):
        partes.append(f"[{nome}]")
        if cabecalho:
            partes.append(cabecalho)
        partes.extend(linhas)
        partes.append("")

    secao("TITLE", None, list(doc.titulo) or [])
    # PATTERNS e CURVES vêm ANTES de quem as referencia (JUNCTIONS/TANKS por Pattern/VolCurve, PUMPS por HEAD):
    # o EPANET oficial aceita qualquer ordem (dois passes), mas `wntr` (usado na cláusula de simulação do
    # portão) lê num passe só e falha em "curve_name not found" se a bomba aparece antes da curva — achado
    # deste item, `test_wntr_simula_o_inp_exportado`.
    secao("PATTERNS", ";ID              Multipliers", [
        f" {pid} " + " ".join(_fmt(m) for m in mults) for pid, mults in doc.patterns.items()
    ])
    linhas_curvas = []
    for cid, pontos in doc.curves.items():
        for x, y in pontos:
            linhas_curvas.append(f" {cid:<16} {_fmt(x):<12} {_fmt(y)}")
    secao("CURVES", ";ID              X-Value     Y-Value", linhas_curvas)
    secao("JUNCTIONS", ";ID              Elev        Demand      Pattern", [
        f" {j['id']:<16} {_fmt(j['elev']):<11} {_fmt(j.get('demand') or 0.0):<11} {j['pattern'] or ''}".rstrip()
        for j in doc.junctions
    ])
    secao("RESERVOIRS", ";ID              Head        Pattern", [
        f" {r['id']:<16} {_fmt(r['head']):<11} {r['pattern'] or ''}".rstrip() for r in doc.reservoirs
    ])
    cabecalho_tanks = (";ID              Elevation   InitLevel   MinLevel    MaxLevel    Diameter    MinVol      "
                       "VolCurve")
    secao("TANKS", cabecalho_tanks, [
        (f" {t['id']:<16} {_fmt(t['elevation']):<11} {_fmt(t['init_level']):<11} {_fmt(t['min_level']):<11} "
         f"{_fmt(t['max_level']):<11} {_fmt(t['diameter']):<11} {_fmt(t.get('min_vol') or 0.0):<11} "
         f"{t.get('vol_curve') or ''}").rstrip()
        for t in doc.tanks
    ])
    secao("PIPES", ";ID       Node1        Node2        Length      Diameter  Roughness  MinorLoss  Status", [
        (f" {p['id']:<8} {p['node1']:<12} {p['node2']:<12} {_fmt(p['length']):<11} {_fmt(p['diameter']):<9} "
         f"{_fmt(p['roughness']):<10} {_fmt(p.get('minor_loss') or 0.0):<10} {p.get('status') or 'Open'}")
        for p in doc.pipes
    ])
    linhas_pumps = []
    for b in doc.pumps:
        camp = [b["id"], b["node1"], b["node2"]]
        if b.get("head_curve"):
            camp += ["HEAD", b["head_curve"]]
        if b.get("power") is not None:
            camp += ["POWER", _fmt(b["power"])]
        if b.get("pattern"):
            camp += ["PATTERN", b["pattern"]]
        if b.get("speed") is not None:
            camp += ["SPEED", _fmt(b["speed"])]
        linhas_pumps.append(" " + " ".join(camp))
    secao("PUMPS", ";ID              Node1           Node2           Parameters", linhas_pumps)
    secao("VALVES", ";ID       Node1        Node2        Diameter  Type  Setting  MinorLoss", [
        (f" {v['id']:<8} {v['node1']:<12} {v['node2']:<12} {_fmt(v['diameter']):<9} {v['type']:<5} "
         f"{_fmt(v.get('setting') or 0.0):<8} {_fmt(v.get('minor_loss') or 0.0)}")
        for v in doc.valves
    ])
    secao("COORDINATES", ";Node            X-Coord          Y-Coord", [
        f" {nid:<16} {_fmt(x):<16} {_fmt(y)}" for nid, (x, y) in doc.coordinates.items()
    ])
    linhas_vertices = []
    for lid, pontos in doc.vertices.items():
        for x, y in pontos:
            linhas_vertices.append(f" {lid:<16} {_fmt(x):<16} {_fmt(y)}")
    secao("VERTICES", ";Link            X-Coord          Y-Coord", linhas_vertices)
    opcoes = dict(doc.options)
    opcoes.setdefault("UNITS", "LPS")
    opcoes.setdefault("HEADLOSS", "H-W")
    secao("OPTIONS", None, [f" {k.title():<12}{v}" for k, v in opcoes.items()])
    secao("TIMES", None, [" Duration           0"])
    secao("REPORT", None, [" Status             No"])
    partes.append("[END]")
    partes.append("")
    return "\n".join(partes)
