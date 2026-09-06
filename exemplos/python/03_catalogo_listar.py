# Primeiros itens do catálogo do inquilino (GET /api/itens, escopo catalogo:ler)
from _apoio import chamar, exigir, exigir_chave

exigir_chave()
status, _cab, corpo = chamar("/api/itens?limite=5")
exigir(status == 200, f"esperava 200 em /api/itens, veio {status}: {corpo}")
itens = corpo.get("itens", corpo if isinstance(corpo, list) else [])
print(f"total no catálogo: {corpo.get('total', len(itens))}; mostrando {len(itens)}")
for item in itens:
    print(f"  {item.get('tipo', '?'):14s} {item.get('titulo', '(sem título)')}")
