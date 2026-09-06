-- 020_item_contagens_rows: `plat.item_contagens(uuid)` sempre devolve 0 ou 1 linha (SELECT de agregados, sem
-- FROM que multiplique), mas por ser função SQL de saída em TABLE o planejador estimava o default de 1.000 linhas
-- por chamada. Isso não afeta corretude (a rota de item único continua correta), mas inflava a estimativa de custo
-- de qualquer consulta que a chame — foi um dos dois fatores medidos por trás do piso de ~170-230 ms fixo por
-- chamada em GET /api/itens?tipo=mapa (ver 019: a causa principal ali foi movida para item_contagens_lote; esta
-- migração só corrige a estimativa da função de item único, que continua usada por GET /api/itens/{id}).
-- ALTER FUNCTION ... ROWS é idempotente (repetir não muda nada); sem `-- reaplicavel` porque não há CREATE aqui.
ALTER FUNCTION plat.item_contagens(uuid) ROWS 1;
