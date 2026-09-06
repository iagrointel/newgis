-- 032_ingestao_arquivo_cascade: corrige plat.importacao.arquivo_id (item L0-04-ingest-vetor, migração 029 —
-- JÁ APLICADA, por isso corrige numa migração nova em vez de editar a 029). Achado por outra trilha (L5-05):
-- a FK sem ON DELETE quebrava o teardown de `_expurgar_zt` (tests/api/catalogo/conftest.py, fixture
-- COMPARTILHADA por muitas suítes) sempre que um item `arquivo` de teste tinha uma importação vinculada —
-- `plat.item_expurgar` não conseguia apagar o item, com `ForeignKeyViolation`.
--
-- Decisão: ON DELETE CASCADE (não SET NULL). Motivo: `plat.importacao` é registro de UM PASSO do fluxo de
-- ingestão (inspecionar → confirmar → carregar), não o registro de proveniência definitivo — esse já é
-- copiado para `plat.item.dados.procedencia`/`dados.importacao` da CAMADA no fim da carga (seção 6.3 do ADR
-- 0005), que sobrevive independente de `plat.importacao` existir. Se o arquivo de origem é apagado (usuário
-- ou lixeira), a importação que dependia dele deixa de fazer sentido como registro isolado — apagá-la junto
-- é coerente com `arquivo_de_camada` (`plat.relacao_tipo`, `apaga_junto = true` já vigente desde a 011) e evita
-- a alternativa (SET NULL) que deixaria `plat.importacao` com uma referência vazia e sem sentido de auditoria
-- (a coluna é NOT NULL de propósito: toda importação nasce de um arquivo, nunca no vácuo).
ALTER TABLE plat.importacao DROP CONSTRAINT IF EXISTS importacao_arquivo_id_fkey;
ALTER TABLE plat.importacao
  ADD CONSTRAINT importacao_arquivo_id_fkey FOREIGN KEY (arquivo_id) REFERENCES plat.item(id) ON DELETE CASCADE;
