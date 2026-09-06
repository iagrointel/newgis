# Vocabulário de categorias do inquilino (GET /api/categorias, escopo catalogo:ler)
from _apoio import chamar, exigir, exigir_chave

exigir_chave()
status, _cab, corpo = chamar("/api/categorias")
exigir(status == 200, f"esperava 200 em /api/categorias, veio {status}: {corpo}")
lista = corpo if isinstance(corpo, list) else corpo.get("categorias", [])
print(f"{len(lista)} categoria(s)")
for c in lista[:20]:
    print("  " + (c.get("nome") if isinstance(c, dict) else str(c)))
