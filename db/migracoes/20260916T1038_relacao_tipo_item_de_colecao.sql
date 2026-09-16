-- 20260916T1038_relacao_tipo_item_de_colecao: item L5-04-c-temas-capa-colecao. O extrator de relação
-- `app/catalogo/relacoes.py::_colecao` (commit a05a101bc, "extrator de coleção sincroniza item_de_colecao do
-- corpo") sincroniza `plat.item_relacao` com tipo `item_de_colecao`, mas essa migração NUNCA foi escrita — sem
-- a linha em `plat.relacao_tipo`, o gatilho `plat.tg_item_relacao` (011_catalogo.sql, FK de `item_relacao.tipo`)
-- não teria como aceitar a relação (ForeignKeyViolation, mesma classe de defeito do achado do evento
-- `itens/metadado_importar` nesta mesma rodada). Só que o sintoma medido foi outro: `_colecao` nunca chegou a
-- rodar porque `EXTRATORES` (mesmo arquivo) também não tinha a entrada `'colecao': _colecao` — outra perda da
-- mesma fusão. As duas foram restauradas juntas nesta rodada (relacoes.py + esta migração).
--
-- `origem_familias = {documento}` (é a família de `colecao`); `destino_familias` deliberadamente amplo — uma
-- coleção cita QUALQUER item do catálogo por uuid (item L5-04-c: "itens citados por uuid"), mesmo desenho de
-- `anexo_de_item` (011_catalogo.sql). Idempotente (ON CONFLICT DO UPDATE, mesmo padrão da 011). Sem BEGIN/COMMIT.
INSERT INTO plat.relacao_tipo (nome, descricao, origem_familias, destino_familias, arrasta_dono, apaga_junto) VALUES
  ('item_de_colecao', 'coleção cita item do catálogo (capa/metadados/itens do corpo)',
   '{documento}', '{documento,app,painel,mapa,camada,raster,arquivo,rede,formulario,fluxo}', false, false)
ON CONFLICT (nome) DO UPDATE SET descricao = EXCLUDED.descricao, origem_familias = EXCLUDED.origem_familias,
  destino_familias = EXCLUDED.destino_familias, arrasta_dono = EXCLUDED.arrasta_dono, apaga_junto = EXCLUDED.apaga_junto;
