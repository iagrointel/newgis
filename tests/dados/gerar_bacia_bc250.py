"""Extrai UMA bacia (um componente conexo da drenagem) da Base Cartográfica Contínua 1:250.000 do IBGE
(BC250, dado aberto) já carregada no acervo da casa, e grava o recorte em `tests/dados/bacia_bc250.json`
para o teste do item L4-18-rede-simples-trace-network.

Por que um arquivo em vez de ler a tabela no teste: `public.hidro_nacional_bc250` (1.599.240 trechos) é um
ativo do acervo, sem privilégio de leitura para a role da aplicação (`plat_app`) — dar esse privilégio
mudaria o banco compartilhado da casa por causa de um teste. O recorte fica no repositório com a procedência
escrita (tabela de origem, retângulo, data, contagem e sha256 do arquivo gerado), e o teste o carrega pela
mesma rota pública que qualquer camada do inquilino usaria.

Rodar (exige ler o acervo, portanto como postgres; o destino aceita caminho, porque a role postgres nao
escreve no diretorio do repositorio):
    sudo -u postgres <repo>/venv/bin/python tests/dados/gerar_bacia_bc250.py /tmp/bacia_bc250.json
    mv /tmp/bacia_bc250.json tests/dados/bacia_bc250.json
"""

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

TABELA = "public.hidro_nacional_bc250"
BBOX = (-44.8, -20.6, -44.0, -20.0)  # alto rio Grande / alto São Francisco, MG
SAIDA = Path(__file__).resolve().parent / "bacia_bc250.json"
CASAS = 6  # ~11 cm no equador: preserva a coincidência exata dos vértices do BC250


def _consultar(sql: str) -> list[str]:
    saida = subprocess.run(["psql", "-d", "iagro_sat", "-tAF", "\x1f", "-c", sql],
                           capture_output=True, text=True, check=True)
    return [linha for linha in saida.stdout.splitlines() if linha]


def _arredondar(coordenadas: list) -> list:
    return [[round(float(x), CASAS), round(float(y), CASAS)] for x, y in coordenadas]


def main(argv: list[str]) -> int:
    saida = Path(argv[1]) if len(argv) > 1 else SAIDA
    sql = (
        "SELECT ogc_fid, coalesce(nome, ''), coalesce(tipotrecho, ''), coalesce(regime, ''), "
        "ST_AsGeoJSON((ST_Dump(geom)).geom, 7) "
        f"FROM {TABELA} WHERE geom && ST_MakeEnvelope({BBOX[0]}, {BBOX[1]}, {BBOX[2]}, {BBOX[3]}, 4326)"
    )
    trechos = []
    for linha in _consultar(sql):
        ogc_fid, nome, tipo, regime, geojson = linha.split("\x1f")
        coordenadas = _arredondar(json.loads(geojson)["coordinates"])
        if len(coordenadas) < 2:
            continue
        trechos.append({"ogc_fid": int(ogc_fid), "nome": nome, "tipotrecho": tipo, "regime": regime,
                        "coordenadas": coordenadas})

    # componente conexo por coincidência EXATA de ponta (o BC250 compartilha o vértice do nó de drenagem)
    por_ponta = defaultdict(list)
    for i, t in enumerate(trechos):
        por_ponta[tuple(t["coordenadas"][0])].append(i)
        por_ponta[tuple(t["coordenadas"][-1])].append(i)
    vizinhos = defaultdict(set)
    for indices in por_ponta.values():
        for a in indices:
            for b in indices:
                if a != b:
                    vizinhos[a].add(b)
    visto, componentes = set(), []
    for i in range(len(trechos)):
        if i in visto:
            continue
        pilha, comp = [i], []
        visto.add(i)
        while pilha:
            v = pilha.pop()
            comp.append(v)
            for w in vizinhos[v]:
                if w not in visto:
                    visto.add(w)
                    pilha.append(w)
        componentes.append(comp)
    maior = max(componentes, key=len)
    bacia = [trechos[i] for i in sorted(maior, key=lambda i: trechos[i]["ogc_fid"])]

    doc = {
        "fonte": {
            "nome": "IBGE — Base Cartografica Continua do Brasil 1:250.000 (BC250), trecho de drenagem",
            "tabela_no_acervo": TABELA,
            "linhas_na_tabela": int(_consultar(f"SELECT count(*) FROM {TABELA}")[0]),
            "retangulo_4326": list(BBOX),
            "recorte": "maior componente conexo do retangulo (uma bacia), por coincidencia exata de ponta",
            "casas_decimais": CASAS,
            "extraido_em": datetime.now(UTC).date().isoformat(),
            "gerador": "tests/dados/gerar_bacia_bc250.py",
        },
        "trechos_no_retangulo": len(trechos),
        "componentes_no_retangulo": len(componentes),
        "trechos": bacia,
    }
    bruto = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    saida.write_bytes(bruto)
    print(f"{saida}: {len(bacia)} trechos de {len(trechos)} no retangulo, "
          f"{len(componentes)} componentes, {len(bruto)} bytes, sha256 {hashlib.sha256(bruto).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
