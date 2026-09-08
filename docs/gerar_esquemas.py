"""Gera `docs/esquemas/<tipo>-v<esquema_versao>.json` a partir de `plat.tipo_item` (item L5-05-documento-versoes;
mesma disciplina de `docs/gerar_limites.py`: o arquivo é o `repr()` do que o banco tem, nunca digitado de novo, e
`--check` falha se estiver desatualizado). Cobre só os tipos cuja família está em `app.catalogo.documento.
FAMILIAS_GRAFO` (hoje: app, painel) — é ali que o L5-05 declara "esquema publicado neste item"; os demais tipos
continuam servidos só por `GET /api/esquemas/{tipo}` (que lê a tabela direto, sem arquivo).

Versão HISTÓRICA (a anterior à vigente) nunca é sobrescrita por este gerador — só a numeração ATUAL de cada tipo
é regenerada a cada rodada; um `-v<N>.json` de uma versão que já saiu de circulação é arquivo morto, mantido à
mão pela migração que a superou (028_documento_grafo.sql deixou app-v1.json/painel-v1.json como registro do que
existia antes, escritos uma vez só, nunca regerados)."""

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
DESTINO = RAIZ / "docs" / "esquemas"


def _tipos_com_esquema_publicado() -> list[dict]:
    from app import db

    with db.db() as cur:
        cur.execute("SELECT nome, familia, esquema, esquema_versao FROM plat.tipo_item ORDER BY nome")
        linhas = [dict(r) for r in cur.fetchall()]
    from app.catalogo.documento import FAMILIAS_GRAFO

    return [r for r in linhas if r["familia"] in FAMILIAS_GRAFO]


def _sem_nome_de_trilha(texto: str) -> str:
    """O arquivo publicado fala do schema de PRODUÇÃO. Numa trilha isolada, `trilha_ambiente.sh` reescreve
    `plat.` para `plat_t<nome>.` no texto inteiro da migração — inclusive DENTRO das descrições do JSON Schema
    —, e sem esta normalização o gerador carimbaria o nome da trilha de quem rodou por último no documento
    (aconteceu: `painel-v3.json` chegou a esta passagem citando a trilha de outro item)."""
    return re.sub(r"\bplat_t[a-z0-9]+\.", "plat.", texto)


def gerar() -> dict[Path, str]:
    saida = {}
    for t in _tipos_com_esquema_publicado():
        caminho = DESTINO / f"{t['nome']}-v{t['esquema_versao']}.json"
        corpo = json.dumps(t["esquema"], ensure_ascii=False, indent=2, sort_keys=True)
        saida[caminho] = _sem_nome_de_trilha(corpo) + "\n"
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    arquivos = gerar()
    if args.check:
        divergentes = [
            c for c, conteudo in arquivos.items() if not c.is_file() or c.read_text(encoding="utf-8") != conteudo
        ]
        if divergentes:
            print("desatualizado, rode sem --check:", *[str(c) for c in divergentes], file=sys.stderr)
            return 1
        print(f"docs/esquemas em dia ({len(arquivos)} arquivo(s))")
        return 0
    DESTINO.mkdir(parents=True, exist_ok=True)
    for caminho, conteudo in arquivos.items():
        caminho.write_text(conteudo, encoding="utf-8")
    print(f"gerado(s): {', '.join(str(c.relative_to(RAIZ)) for c in arquivos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
