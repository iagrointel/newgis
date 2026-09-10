# Coleções do catálogo externo OGC API Records (GET /ogc/records/collections, escopo catalogo:ler)
from _apoio import chamar, exigir, exigir_chave

exigir_chave()
status, _cab, corpo = chamar("/ogc/records/collections")
exigir(status == 200, f"esperava 200 em /ogc/records/collections, veio {status}: {corpo}")
colecoes = corpo.get("collections", [])
print(f"{len(colecoes)} coleção(ões) publicada(s) em OGC API Records")
for c in colecoes:
    print(f"  {c.get('id')}: {c.get('title', '')}")
