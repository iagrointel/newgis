-- 20260907T1124_upload_arquivo_cascade: mesma classe de defeito já corrigida em 032_ingestao_arquivo_cascade.sql
-- para `plat.importacao.arquivo_id`, achada agora em `plat.upload.arquivo_id` (item L0-04-a-upload-arquivo,
-- migração 046 — JÁ APLICADA, por isso corrige aqui em vez de editar a 046): a FK sem `ON DELETE` bloqueava o
-- teardown de `_expurgar_zt` (tests/api/catalogo/conftest.py, fixture COMPARTILHADA por muitas suítes) sempre
-- que um item `arquivo` de teste tinha um upload concluído ligado a ele —
-- `plat.item_expurgar` não conseguia apagar o item, com `ForeignKeyViolation: ... is still referenced from
-- table "upload"`. Isolado nesta verificação: `tests/unit/test_where_ast.py` (que não toca banco nenhum)
-- aparecia como ERRO na suíte inteira só porque essa fixture de teardown, compartilhada, quebrava mais cedo
-- num item deixado por `tests/api/uploads/test_uploads.py` — "contaminação entre testes" que na verdade era
-- este FK faltando, não estado sujo de verdade.
--
-- Decisão: ON DELETE CASCADE (mesmo raciocínio da 032, não SET NULL): `plat.upload` é o registro do PROCESSO
-- de envio (partes, progresso, prazo), não a proveniência definitiva do arquivo — essa já foi copiada para
-- `plat.item.dados` (`chave`, `sha256`, `bytes`, `content_type`, `nome_original`) por `_criar_item_arquivo`
-- (app/uploads/rotas.py) no momento da conclusão, e o evento `uploads/concluir` fica em `plat.evento`
-- independente do item existir. Se o item chega a ser apagado (usuário ou expurgo da lixeira), o registro de
-- processo do upload que o criou deixa de ter função de auditoria isolada — apagá-lo junto evita a alternativa
-- (SET NULL) que deixaria a linha com `arquivo_id` vazio e `estado='concluido'` sem link, o que não descreve
-- nenhum estado real do fluxo (worker/tela nunca esperam um upload concluído sem arquivo).
ALTER TABLE plat.upload DROP CONSTRAINT IF EXISTS upload_arquivo_id_fkey;
ALTER TABLE plat.upload
  ADD CONSTRAINT upload_arquivo_id_fkey FOREIGN KEY (arquivo_id) REFERENCES plat.item(id) ON DELETE CASCADE;
