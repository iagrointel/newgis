# Busca por texto no catálogo, paginando de 20 em 20 (GET /api/itens?q=, escopo catalogo:ler)
import sys

from _apoio import chamar, exigir, exigir_chave

exigir_chave()
termo = sys.argv[1] if len(sys.argv) > 1 else "a"
vistos, deslocamento = 0, 0
while True:
    status, _cab, corpo = chamar(f"/api/itens?q={termo}&limite=20&deslocamento={deslocamento}")
    exigir(status == 200, f"esperava 200 na busca, veio {status}: {corpo}")
    pagina = corpo.get("itens", [])
    vistos += len(pagina)
    if len(pagina) < 20 or vistos >= 100:
        break
    deslocamento += 20
print(f"busca por {termo!r}: {vistos} item(ns) percorrido(s) em páginas de 20")
