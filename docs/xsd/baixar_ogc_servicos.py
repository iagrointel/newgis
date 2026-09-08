"""Baixa e põe em cache local as XSD oficiais do OGC para WMS 1.3.0 e WMTS 1.0.0 — item
`L2-04-i-wms-wmts-sld`. Mesma máquina do `baixar_iso19139.py` (item L0-09): a fila segue todo
`schemaLocation`, grava sob `docs/xsd/cache/<host>/<caminho>` e reescreve as referências absolutas para
caminhos relativos dentro do cache, de modo que a validação nunca toque a rede.

Por que em cache e não pela URL: o teste do portão valida CADA `GetCapabilities` gerado contra a XSD
oficial; depender de `schemas.opengis.net` deixaria a suíte refém de rede e do sítio do OGC. As sementes
abaixo são as URLs canônicas citadas na própria especificação (WMS 1.3.0, OGC 06-042; WMTS 1.0.0,
OGC 07-057r7).

Uso: venv/bin/python docs/xsd/baixar_ogc_servicos.py [--forcar]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import baixar_iso19139 as base  # noqa: E402 - o caminho tem de entrar no sys.path antes do import

SEMENTES_OGC = (
    "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd",
    "https://schemas.opengis.net/wms/1.3.0/exceptions_1_3_0.xsd",
    "https://schemas.opengis.net/sld/1.1/sld_capabilities.xsd",
    "https://schemas.opengis.net/wmts/1.0/wmtsGetCapabilities_response.xsd",
    "https://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd",
)


def main() -> None:
    ap = argparse.ArgumentParser(description="cache offline das XSD de WMS 1.3.0, WMTS 1.0.0 e SLD 1.0")
    ap.add_argument("--forcar", action="store_true", help="rebaixa mesmo o que já está no cache")
    args = ap.parse_args()
    base.SEMENTES = SEMENTES_OGC
    mapa = base.baixar(args.forcar)
    base.gravar_manifesto(mapa)
    print(f"cache OGC pronto: {len(mapa)} arquivo(s) desta árvore em {base.CACHE}")


if __name__ == "__main__":
    main()
