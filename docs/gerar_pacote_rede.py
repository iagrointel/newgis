"""Gera `docs/PACOTE_REDE.md` a partir dos pacotes entregues em `app/rede_utilidades/pacotes/` (item
L4-01-a-pacote-de-ativos). Mesma disciplina de `docs/gerar_limites.py`: o documento é o `repr()` do dado, nunca
digitado de novo, e `--check` falha se estiver desatualizado. É aqui que vive o mapeamento COLUNA A COLUNA
prometido pelo portão do item — e é do próprio dado que sai a marca de o que foi conferido contra extração real
e o que é só declarado.

  venv/bin/python docs/gerar_pacote_rede.py            # escreve
  venv/bin/python docs/gerar_pacote_rede.py --check    # confere (o teste chama assim)
"""

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
DESTINO = RAIZ / "docs" / "PACOTE_REDE.md"

CABECALHO = """# Pacote de ativos da rede de utilidades

Documento gerado de `app/rede_utilidades/pacotes/*.json` por `docs/gerar_pacote_rede.py`. Não edite à mão: mude
o pacote e rode o gerador.

Um pacote de ativos descreve o ESQUEMA de uma rede — redes de domínio, tiers, grupos e tipos de ativo,
categorias, atributos e configurações de terminal — como dado versionado, não como código. O mesmo formato serve
para elétrica, água, gás, esgoto e telecom; é ele que se importa e se exporta entre inquilinos
(`POST`/`GET /api/rede/{rede_id}/pacote`). O contrato do formato está no ADR 0019.

Coluna **conferida**: `sim` quando a coluna de origem foi lida numa extração real do esquema citado; `não`
quando a coluna vem do documento da fonte e ainda não foi vista em dado real. Nenhum atributo com `não` deve ser
usado para decidir carga de dado sem antes conferir o dicionário da entrega.
"""


def _pacotes() -> list[dict]:
    from app.rede_utilidades import instalados
    from app.rede_utilidades import pacote as pacote_mod

    saida = []
    for _codigo, ficha in sorted(instalados.catalogo().items()):
        saida.append({"ficha": ficha, "doc": pacote_mod.ler(ficha["arquivo"].read_bytes())})
    return saida


def _tabela(linhas: list[list[str]], titulos: list[str]) -> list[str]:
    partes = ["| " + " | ".join(titulos) + " |", "|" + "|".join(["---"] * len(titulos)) + "|"]
    partes += ["| " + " | ".join(c.replace("|", "\\|") for c in linha) + " |" for linha in linhas]
    return partes


def gerar_markdown() -> str:
    partes = [CABECALHO]
    for entrada in _pacotes():
        ficha, doc = entrada["ficha"], entrada["doc"]
        meta = doc["pacote"]
        partes.append(f"\n## `{meta['codigo']}` — {meta['nome']}\n")
        partes.append(f"{meta.get('descricao', '')}\n")
        partes += _tabela(
            [
                ["versão do pacote", meta["versao"]],
                ["versão do esquema", str(doc["esquema_versao"])],
                ["disciplina", meta["disciplina"]],
                ["fonte", meta.get("fonte", "—")],
                ["tamanho", f"{ficha['bytes']} bytes"],
                ["sha256", f"`{ficha['sha256']}`"],
            ],
            ["campo", "valor"],
        )
        partes.append("\n### Redes de domínio e tiers\n")
        tiers_por_dominio: dict = {}
        for t in doc["tiers"]:
            tiers_por_dominio.setdefault(t["dominio"], []).append(t)
        linhas = []
        for d in sorted(doc["dominios"], key=lambda x: x["ordem"]):
            for t in sorted(tiers_por_dominio.get(d["codigo"], []), key=lambda x: x["ordem"]):
                linhas.append([f"`{d['codigo']}`", d["tipo"], f"`{t['codigo']}`", str(t["ordem"]), t["tipo"],
                               t.get("descricao", "")])
        partes += _tabela(linhas, ["domínio", "tipo do domínio", "tier", "ordem", "tipo do tier", "o que é"])

        partes.append("\n### Categorias de rede\n")
        partes += _tabela(
            [[f"`{c['codigo']}`", c["nome"], c.get("descricao", "")] for c in doc["categorias"]],
            ["categoria", "nome", "o que significa no traçado"],
        )

        partes.append("\n### Configurações de terminal\n")
        linhas = []
        for t in doc["terminais"]:
            terminais = ", ".join(f"{x['id']}={x['nome']}" for x in t["terminais"]) or "—"
            caminhos = ", ".join(f"{c['de']}→{c['para']} ({c['nome']})" for c in t["caminhos_validos"]) or "—"
            linhas.append([f"`{t['codigo']}`", t["nome"], terminais, caminhos])
        partes += _tabela(linhas, ["configuração", "nome", "terminais", "caminhos válidos"])

        partes.append("\n### Grupos e tipos de ativo\n")
        linhas = []
        grupos = {g["codigo"]: g for g in doc["grupos"]}
        for t in doc["tipos"]:
            g = grupos[t["grupo"]]
            linhas.append([
                f"`{g['codigo']}`", g["geometria"], ", ".join(g["camadas_fonte"]) or "—",
                str(t["codigo"]), f"`{t['chave']}`", t["nome"], t["tier"],
                ", ".join(t["categorias"]) or "—", ", ".join(t["codigos_fonte"]) or "—",
            ])
        partes += _tabela(
            linhas,
            ["grupo", "geometria", "camada de origem", "código do tipo", "chave", "nome", "tier", "categorias",
             "códigos na fonte"],
        )

        partes.append("\n### Atributos: mapeamento coluna a coluna\n")
        linhas = []
        for a in doc["atributos"]:
            o = a.get("origem") or {}
            linhas.append([
                o.get("camada", "—"), f"`{o.get('coluna', '—')}`", f"`{a['grupo']}`", f"`{a['codigo']}`",
                a["nome"], a["tipo_dado"], a["unidade"] or "—", "sim" if a["obrigatorio"] else "não",
                "sim" if o.get("conferida") else "não", o.get("nota", ""),
            ])
        partes += _tabela(
            linhas,
            ["camada de origem", "coluna", "grupo", "atributo", "nome", "tipo", "unidade", "obrigatório",
             "conferida", "observação"],
        )
        conferidas = sum(1 for a in doc["atributos"] if (a.get("origem") or {}).get("conferida"))
        partes.append(
            f"\nTotal: {len(doc['atributos'])} atributos, {conferidas} com origem conferida em extração real e "
            f"{len(doc['atributos']) - conferidas} declarados da fonte sem conferência.\n"
        )

        partes.append("\n### Regras de conexão\n")
        partes += _tabela(
            [[r["tipo"], f"`{r['de']}`", f"`{r['para']}`", r.get("descricao", "")] for r in doc["regras"]],
            ["tipo de regra", "de", "para", "o que diz"],
        )
    return "\n".join(partes) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="não escreve; sai != 0 se PACOTE_REDE.md desatualizado")
    args = ap.parse_args()
    novo = gerar_markdown()
    if args.check:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != novo:
            print("docs/PACOTE_REDE.md desatualizado; rode: venv/bin/python docs/gerar_pacote_rede.py",
                  file=sys.stderr)
            raise SystemExit(1)
        return
    DESTINO.write_text(novo, encoding="utf-8")
    print(f"escrito: {DESTINO}")


if __name__ == "__main__":
    main()
