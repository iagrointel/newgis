#!/usr/bin/env python3
"""Sintetiza um .osm XML válido (nós+vias com topologia por coordenada compartilhada) a partir do
GeoJSON de vias extraído por ogr2ogr (driver OSM do GDAL, layer 'lines', -where "highway IS NOT
NULL"). Não usa osmium/osmconvert (evita o consumo de memória do arquivo .pbf inteiro — o
osmium extract OOM-matou com até 2,4 GB de teto nesta máquina, RAM disponível ~2,5 GB); ogr2ogr
mede ~310 MB de RSS e já é o padrão usado no item L2-01-a. Item L2-11-c-rota-matriz-isocrona.

Uso: python3 gerar_osm_xml.py estradas_raw.geojson guarulhos.osm.xml
"""
import json
import re
import sys
import xml.sax.saxutils as sx

TAGS_OTHER = ("oneway", "maxspeed", "access", "junction", "bridge", "tunnel", "ref", "surface", "lanes")
HSTORE_RE = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')


def parse_other_tags(s):
    if not s:
        return {}
    out = {}
    for k, v in HSTORE_RE.findall(s):
        out[k.replace('\\"', '"')] = v.replace('\\"', '"')
    return out


def main(src, dst):
    with open(src) as f:
        data = json.load(f)

    nodes = {}  # (lon7, lat7) -> id sequencial
    node_lines = []
    way_lines = []
    next_node_id = 1
    n_ways = 0
    n_nodes_ref = 0

    def node_id_for(lon, lat):
        nonlocal next_node_id
        key = (round(lon, 7), round(lat, 7))
        nid = nodes.get(key)
        if nid is None:
            nid = next_node_id
            nodes[key] = nid
            next_node_id += 1
            node_lines.append(f'  <node id="{nid}" lat="{lat:.7f}" lon="{lon:.7f}"/>')
        return nid

    for feat in data["features"]:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        if gtype == "LineString":
            coord_lists = [geom["coordinates"]]
        elif gtype == "MultiLineString":
            coord_lists = geom["coordinates"]
        else:
            continue
        props = feat.get("properties") or {}
        osm_id = props.get("osm_id") or str(next_node_id + 1_000_000)
        highway = props.get("highway")
        if not highway:
            continue
        other = parse_other_tags(props.get("other_tags"))
        tags = {"highway": highway}
        name = props.get("name")
        if name:
            tags["name"] = name
        for k in TAGS_OTHER:
            if k in other and other[k]:
                tags[k] = other[k]

        for coords in coord_lists:
            if len(coords) < 2:
                continue
            refs = [node_id_for(lon, lat) for lon, lat in coords]
            n_nodes_ref += len(refs)
            way_id = f"{osm_id}_{len(way_lines)}" if len(coord_lists) > 1 else osm_id
            way_lines.append(f'  <way id="{way_id}">')
            for r in refs:
                way_lines.append(f'    <nd ref="{r}"/>')
            for k, v in tags.items():
                way_lines.append(f'    <tag k="{sx.escape(k)}" v="{sx.escape(str(v))}"/>')
            way_lines.append("  </way>")
            n_ways += 1

    with open(dst, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<osm version="0.6" generator="plataforma-enterprise-L2-11-c">\n')
        f.write("\n".join(node_lines))
        f.write("\n")
        f.write("\n".join(way_lines))
        f.write("\n</osm>\n")

    print(f"nós únicos: {len(nodes)} · vias: {n_ways} · refs de nó: {n_nodes_ref}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
