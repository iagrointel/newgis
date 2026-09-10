#!/usr/bin/env python3
"""Gera o extrato OSM sintético `taquari_power.osm` usado pelo teste do conector
power=* (item L4-05-g-osm-power). Não baixa nada da internet: os nós/vias abaixo foram
desenhados a mão dentro (e um pouco fora) do polígono de Taquari-RS (`taquari_limite.geojson`,
IBGE 2022), cobrindo cada ramo do mapeamento declarado em `app/rede_utilidades/osm_power.py` --
via power=line/minor_line cortada por nó tipado, torre/poste fixados no trecho (sem cortar),
ativo avulso sem via, ponto fora do recorte, área de subestação com junção dentro e uma relação
power=* (não importada nesta passagem, só contada).

Uso: python3 gerar_osm_power.py > taquari_power.osm
"""

NODES = [
    # id, lon, lat, tags
    (1, -51.840, -29.750, {}),                          # ponta da via A, dentro
    (2, -51.835, -29.746, {"power": "tower"}),           # torre sobre a via A, não corta
    (3, -51.830, -29.742, {"power": "substation"}),      # nó de subestação, corta a via A
    (4, -51.826, -29.738, {}),                           # junção compartilhada A/B, dentro
    (5, -51.822, -29.735, {"power": "pole"}),            # poste sobre a via B, não corta
    (6, -51.818, -29.732, {"power": "transformer"}),     # transformador, corta a via B
    (7, -51.850, -29.760, {"power": "transformer"}),     # avulso: sem via de rede tocando
    (8, -52.050, -29.550, {}),                           # ponta da via C, fora do recorte
    (9, -52.000, -29.580, {"power": "tower"}),           # torre sobre a via C, fora -> desvio
    (10, -51.900, -29.650, {}),                          # vértice intermediário da via C, fora
    (11, -51.850, -29.700, {}),                          # ponta da via C, dentro
    # cerca da área de subestação, envolvendo n4 (a junção anônima compartilhada pelas vias A e B --
    # é ela, não um nó já tipado, que a área liga: o pacote só tem regra de conectividade entre o
    # tipo do TRECHO e o tipo do ativo da área, nunca ativo-ativo)
    (12, -51.8265, -29.7375, {}),
    (13, -51.8255, -29.7375, {}),
    (14, -51.8255, -29.7385, {}),
    (15, -51.8265, -29.7385, {}),
]

WAY_A = (101, [1, 2, 3, 4], {"power": "line", "voltage": "13800"})
WAY_B = (102, [4, 5, 6], {"power": "minor_line", "voltage": "220"})
WAY_C = (103, [8, 9, 10, 11], {"power": "line", "voltage": "13800"})
WAY_AREA = (104, [12, 13, 14, 15, 12], {"power": "substation", "area": "yes"})
RELACAO = (201, {"type": "multipolygon", "power": "substation"}, [(104, "outer", "way")])


def _tags(d: dict) -> str:
    return "".join(f'    <tag k="{k}" v="{v}"/>\n' for k, v in d.items())


def gerar() -> str:
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<osm version="0.6" generator="gerar_osm_power.py (item L4-05-g-osm-power)">']
    for nid, lon, lat, tags in NODES:
        if tags:
            linhas.append(f'  <node id="{nid}" lat="{lat}" lon="{lon}">')
            linhas.append(_tags(tags).rstrip("\n"))
            linhas.append("  </node>")
        else:
            linhas.append(f'  <node id="{nid}" lat="{lat}" lon="{lon}"/>')
    for wid, refs, tags in (WAY_A, WAY_B, WAY_C, WAY_AREA):
        linhas.append(f'  <way id="{wid}">')
        for r in refs:
            linhas.append(f'    <nd ref="{r}"/>')
        linhas.append(_tags(tags).rstrip("\n"))
        linhas.append("  </way>")
    rid, rtags, membros = RELACAO
    linhas.append(f'  <relation id="{rid}">')
    for ref, role, tipo in membros:
        linhas.append(f'    <member type="{tipo}" ref="{ref}" role="{role}"/>')
    linhas.append(_tags(rtags).rstrip("\n"))
    linhas.append("  </relation>")
    linhas.append("</osm>")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    import sys

    sys.stdout.write(gerar())
