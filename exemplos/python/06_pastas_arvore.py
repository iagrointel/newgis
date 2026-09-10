# Árvore de pastas do inquilino, impressa com recuo (GET /api/pastas/arvore, escopo catalogo:ler)
from _apoio import chamar, exigir, exigir_chave


def imprimir(nos, nivel=0):
    for no in nos:
        print("  " * nivel + "- " + str(no.get("nome", "(sem nome)")))
        imprimir(no.get("filhas") or no.get("filhos") or [], nivel + 1)


exigir_chave()
status, _cab, corpo = chamar("/api/pastas/arvore")
exigir(status == 200, f"esperava 200 em /api/pastas/arvore, veio {status}: {corpo}")
raiz = corpo if isinstance(corpo, list) else corpo.get("pastas", [])
print(f"{len(raiz)} pasta(s) na raiz")
imprimir(raiz)
