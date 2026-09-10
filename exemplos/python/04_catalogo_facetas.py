# Contagem por tipo e por categoria, para montar um filtro (GET /api/itens/facetas, escopo catalogo:ler)
from _apoio import chamar, exigir, exigir_chave

exigir_chave()
status, _cab, corpo = chamar("/api/itens/facetas")
exigir(status == 200, f"esperava 200 em /api/itens/facetas, veio {status}: {corpo}")
exigir(isinstance(corpo, dict), f"esperava um objeto de facetas, veio {type(corpo).__name__}")
for nome, valores in corpo.items():
    if isinstance(valores, list):
        print(f"{nome}: {len(valores)} valor(es) distinto(s)")
