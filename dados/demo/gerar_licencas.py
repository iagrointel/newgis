#!/usr/bin/env python3
"""Gera dados/demo/LICENCAS.md a partir de dados/demo/catalogo.json.

O portao de pronto do item L7-01-c-dado-demonstracao exige a licenca de cada dado escrita neste
arquivo, com URL. Nunca escrever LICENCAS.md a mao: o catalogo.json e a fonte de verdade (e' o que
`plat demo semear` le), e este gerador garante que o documento nunca diverge dele.
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CATALOGO = RAIZ / "catalogo.json"
SAIDA = RAIZ / "LICENCAS.md"


def gerar() -> str:
    dados = json.loads(CATALOGO.read_text(encoding="utf-8"))
    linhas = [
        "# Licencas do pacote de dado de demonstracao",
        "",
        "Gerado por `dados/demo/gerar_licencas.py` a partir de `dados/demo/catalogo.json`. "
        "Nao editar a mao: editar o catalogo e rodar o gerador de novo.",
        "",
        f"Total de arquivos: {len(dados['itens'])}. "
        f"Tamanho somado: {sum(i['bytes'] for i in dados['itens']) / (1024 * 1024):.2f} MB "
        "(teto do item: 300 MB).",
        "",
    ]
    for item in dados["itens"]:
        linhas += [
            f"## {item['titulo']}",
            "",
            f"- **Arquivo**: `dados/demo/arquivos/{item['arquivo']}` "
            f"({item['bytes']:,} bytes, sha256 `{item['sha256']}`)",
            f"- **Inquilino de demonstracao**: `{item['inquilino']}`",
            f"- **Orgao/fonte**: {item['fonte']} ({item['orgao']})",
            f"- **Endereco**: {item['url']}",
            f"- **Licenca**: {item['licenca']}",
            f"- **Data de acesso**: {item['data_acesso']}",
            f"- **Resumo**: {item['resumo']}",
            "",
        ]
    linhas += [
        "## Nota sobre nomes proprios",
        "",
        "Nenhum arquivo deste pacote cita nome de cliente, parceiro ou piloto da casa "
        "(conferido por `tests/api/test_dado_demo_l7.py::test_nenhum_nome_de_cliente_parceiro_ou_piloto`, "
        "que abre inclusive o conteudo dos `.zip`). Os orgaos citados (IBGE, DNIT, ANA, INMET, "
        "OpenStreetMap Foundation, ESA/Copernicus) sao fontes de dado aberto, nao clientes ou parceiros "
        "comerciais da iAgroSat.",
        "",
    ]
    return "\n".join(linhas)


if __name__ == "__main__":
    SAIDA.write_text(gerar(), encoding="utf-8")
    print(f"escrito {SAIDA} ({SAIDA.stat().st_size} bytes)")
