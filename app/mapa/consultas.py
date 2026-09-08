"""SQL compartilhado entre `app/mapa/rotas.py` (L2-01-mapa-web) e `app/mapa/popup.py` (L2-01-d):
extraído para cá só para os dois módulos poderem importar um do outro sem ciclo (`popup.py` usa a
ficha completa da camada; `rotas.py` acrescentou o `popup` normalizado à mesma ficha)."""

SQL_CAMADA = """
SELECT i.id, i.titulo, i.descricao, i.dados, i.criado_em
FROM plat.item i
WHERE i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
"""
