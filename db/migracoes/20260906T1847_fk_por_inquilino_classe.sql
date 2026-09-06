-- 20260906T1847_fk_por_inquilino_classe: chave estrangeira COMPOSTA (tenant_id, id) nas 44 FKs simples
-- do resto do schema `plat` achadas pela trava `tests/api/test_fk_composta_por_inquilino.py` (item
-- FK-CLASSE-CONSERTO, turno 3, 06/09/2026) — mesma classe do achado A1 de L4-01-a-pacote-de-ativos,
-- só que fora de `plat.rede_*` (já consertada em 20260906T1815_rede_fk_por_inquilino.sql, NÃO tocada aqui).
--
-- Cada FK aqui ligava duas tabelas que TÊM tenant_id usando só `id`: a RLS (`USING tenant_id = tenant_atual()`)
-- não filtra a leitura da tabela ALVO durante a checagem da FK — o Postgres resolve a FK como superusuário
-- por baixo da política. Resultado medido (mesma classe do A1): `plat_app` autenticado como o inquilino B
-- consegue gravar uma linha SUA (tenant_id = B) cuja FK aponta para uma linha de OUTRO inquilino (A), e o
-- fato de a gravação aceitar (uuid/id de A) ou recusar (id inventado) vira oráculo de existência.
--
-- Conserto: toda tabela alvo ganha `UNIQUE (tenant_id, id)` (trivial — id já é único sozinho) e toda FK
-- passa a ser `(tenant_id, xxx_id) REFERENCES alvo (tenant_id, id)`, com o MESMO ON DELETE de antes (ver
-- levantamento em handoffs/T3/FK-CLASSE-CONSERTO.md). Idempotente: DROP CONSTRAINT IF EXISTS + ADD, e o
-- bloco de UNIQUE confere pg_constraint antes de criar. As 11 FKs da mesma varredura que apontam para
-- tabelas ainda inexistentes nesta base (exportacao, geocodificacao*, raster_item, raster_colecao, e as
-- 2 de `rede.dono_id/importado_por -> usuario`, que dependem de migração de OUTRA trilha ainda não
-- mesclada) não estão aqui — ficam para quem mesclar aquela trilha, seguindo este mesmo padrão; não
-- foram postas como exceção permanente na trava (dívida não cresce).

DO $$
DECLARE alvo text;
BEGIN
  FOREACH alvo IN ARRAY ARRAY['usuario', 'papel_personalizado', 'item', 'grupo', 'pasta', 'categoria',
                              'compartilhamento_link', 'conexao', 'job', 'token_servico'] LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
      WHERE n.nspname = 'plat' AND t.relname = alvo AND c.conname = alvo || '_tenant_id_id_key'
    ) THEN
      EXECUTE format('ALTER TABLE plat.%I ADD CONSTRAINT %I UNIQUE (tenant_id, id)', alvo, alvo || '_tenant_id_id_key');
    END IF;
  END LOOP;
END $$;

-- ===== alvo: usuario (23 FKs) =====
ALTER TABLE plat.agenda DROP CONSTRAINT IF EXISTS agenda_usuario_id_fkey;
ALTER TABLE plat.agenda DROP CONSTRAINT IF EXISTS agenda_tenant_usuario_fkey;
ALTER TABLE plat.agenda ADD CONSTRAINT agenda_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.arquivo DROP CONSTRAINT IF EXISTS arquivo_criado_por_fkey;
ALTER TABLE plat.arquivo DROP CONSTRAINT IF EXISTS arquivo_tenant_criado_por_fkey;
ALTER TABLE plat.arquivo ADD CONSTRAINT arquivo_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.compartilhamento_link DROP CONSTRAINT IF EXISTS compartilhamento_link_criado_por_fkey;
ALTER TABLE plat.compartilhamento_link DROP CONSTRAINT IF EXISTS compartilhamento_link_tenant_criado_por_fkey;
ALTER TABLE plat.compartilhamento_link ADD CONSTRAINT compartilhamento_link_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);

ALTER TABLE plat.conexao DROP CONSTRAINT IF EXISTS conexao_dono_id_fkey;
ALTER TABLE plat.conexao DROP CONSTRAINT IF EXISTS conexao_tenant_dono_fkey;
ALTER TABLE plat.conexao ADD CONSTRAINT conexao_tenant_dono_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.convite DROP CONSTRAINT IF EXISTS convite_criado_por_fkey;
ALTER TABLE plat.convite DROP CONSTRAINT IF EXISTS convite_tenant_criado_por_fkey;
ALTER TABLE plat.convite ADD CONSTRAINT convite_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.convite DROP CONSTRAINT IF EXISTS convite_usuario_criado_id_fkey;
ALTER TABLE plat.convite DROP CONSTRAINT IF EXISTS convite_tenant_usuario_criado_fkey;
ALTER TABLE plat.convite ADD CONSTRAINT convite_tenant_usuario_criado_fkey
  FOREIGN KEY (tenant_id, usuario_criado_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.favorito DROP CONSTRAINT IF EXISTS favorito_usuario_id_fkey;
ALTER TABLE plat.favorito DROP CONSTRAINT IF EXISTS favorito_tenant_usuario_fkey;
ALTER TABLE plat.favorito ADD CONSTRAINT favorito_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.grupo DROP CONSTRAINT IF EXISTS grupo_dono_id_fkey;
ALTER TABLE plat.grupo DROP CONSTRAINT IF EXISTS grupo_tenant_dono_fkey;
ALTER TABLE plat.grupo ADD CONSTRAINT grupo_tenant_dono_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.grupo_membro DROP CONSTRAINT IF EXISTS grupo_membro_convidado_por_fkey;
ALTER TABLE plat.grupo_membro DROP CONSTRAINT IF EXISTS grupo_membro_tenant_convidado_por_fkey;
ALTER TABLE plat.grupo_membro ADD CONSTRAINT grupo_membro_tenant_convidado_por_fkey
  FOREIGN KEY (tenant_id, convidado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (convidado_por);
ALTER TABLE plat.grupo_membro DROP CONSTRAINT IF EXISTS grupo_membro_usuario_id_fkey;
ALTER TABLE plat.grupo_membro DROP CONSTRAINT IF EXISTS grupo_membro_tenant_usuario_fkey;
ALTER TABLE plat.grupo_membro ADD CONSTRAINT grupo_membro_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.importacao DROP CONSTRAINT IF EXISTS importacao_usuario_id_fkey;
ALTER TABLE plat.importacao DROP CONSTRAINT IF EXISTS importacao_tenant_usuario_fkey;
ALTER TABLE plat.importacao ADD CONSTRAINT importacao_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_apagado_por_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_apagado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_tenant_apagado_por_fkey
  FOREIGN KEY (tenant_id, apagado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (apagado_por);
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_criado_por_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_criado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_dono_id_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_dono_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_tenant_dono_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_modificado_por_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_modificado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_tenant_modificado_por_fkey
  FOREIGN KEY (tenant_id, modificado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (modificado_por);

ALTER TABLE plat.job DROP CONSTRAINT IF EXISTS job_usuario_id_fkey;
ALTER TABLE plat.job DROP CONSTRAINT IF EXISTS job_tenant_usuario_fkey;
ALTER TABLE plat.job ADD CONSTRAINT job_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.papel_personalizado DROP CONSTRAINT IF EXISTS papel_personalizado_criado_por_fkey;
ALTER TABLE plat.papel_personalizado DROP CONSTRAINT IF EXISTS papel_personalizado_tenant_criado_por_fkey;
ALTER TABLE plat.papel_personalizado ADD CONSTRAINT papel_personalizado_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);

ALTER TABLE plat.pasta DROP CONSTRAINT IF EXISTS pasta_dono_id_fkey;
ALTER TABLE plat.pasta DROP CONSTRAINT IF EXISTS pasta_tenant_dono_fkey;
ALTER TABLE plat.pasta ADD CONSTRAINT pasta_tenant_dono_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.provedor_ldap DROP CONSTRAINT IF EXISTS provedor_ldap_atualizado_por_fkey;
ALTER TABLE plat.provedor_ldap DROP CONSTRAINT IF EXISTS provedor_ldap_tenant_atualizado_por_fkey;
ALTER TABLE plat.provedor_ldap ADD CONSTRAINT provedor_ldap_tenant_atualizado_por_fkey
  FOREIGN KEY (tenant_id, atualizado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (atualizado_por);
ALTER TABLE plat.provedor_ldap DROP CONSTRAINT IF EXISTS provedor_ldap_criado_por_fkey;
ALTER TABLE plat.provedor_ldap DROP CONSTRAINT IF EXISTS provedor_ldap_tenant_criado_por_fkey;
ALTER TABLE plat.provedor_ldap ADD CONSTRAINT provedor_ldap_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);

ALTER TABLE plat.redefinicao_senha DROP CONSTRAINT IF EXISTS redefinicao_senha_usuario_id_fkey;
ALTER TABLE plat.redefinicao_senha DROP CONSTRAINT IF EXISTS redefinicao_senha_tenant_usuario_fkey;
ALTER TABLE plat.redefinicao_senha ADD CONSTRAINT redefinicao_senha_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.sessao DROP CONSTRAINT IF EXISTS sessao_usuario_id_fkey;
ALTER TABLE plat.sessao DROP CONSTRAINT IF EXISTS sessao_tenant_usuario_fkey;
ALTER TABLE plat.sessao ADD CONSTRAINT sessao_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.token_servico DROP CONSTRAINT IF EXISTS token_servico_usuario_id_fkey;
ALTER TABLE plat.token_servico DROP CONSTRAINT IF EXISTS token_servico_tenant_usuario_fkey;
ALTER TABLE plat.token_servico ADD CONSTRAINT token_servico_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.upload DROP CONSTRAINT IF EXISTS upload_usuario_id_fkey;
ALTER TABLE plat.upload DROP CONSTRAINT IF EXISTS upload_tenant_usuario_fkey;
ALTER TABLE plat.upload ADD CONSTRAINT upload_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);

-- ===== alvo: papel_personalizado (2 FKs) =====
ALTER TABLE plat.convite DROP CONSTRAINT IF EXISTS convite_papel_id_fkey;
ALTER TABLE plat.convite DROP CONSTRAINT IF EXISTS convite_tenant_papel_fkey;
ALTER TABLE plat.convite ADD CONSTRAINT convite_tenant_papel_fkey
  FOREIGN KEY (tenant_id, papel_id) REFERENCES plat.papel_personalizado (tenant_id, id);

ALTER TABLE plat.usuario DROP CONSTRAINT IF EXISTS usuario_papel_id_fkey;
ALTER TABLE plat.usuario DROP CONSTRAINT IF EXISTS usuario_tenant_papel_fkey;
ALTER TABLE plat.usuario ADD CONSTRAINT usuario_tenant_papel_fkey
  FOREIGN KEY (tenant_id, papel_id) REFERENCES plat.papel_personalizado (tenant_id, id);

-- ===== alvo: item (8 FKs) =====
ALTER TABLE plat.compartilhamento_link DROP CONSTRAINT IF EXISTS compartilhamento_link_item_id_fkey;
ALTER TABLE plat.compartilhamento_link DROP CONSTRAINT IF EXISTS compartilhamento_link_tenant_item_fkey;
ALTER TABLE plat.compartilhamento_link ADD CONSTRAINT compartilhamento_link_tenant_item_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.compartilhamento_link_item DROP CONSTRAINT IF EXISTS compartilhamento_link_item_item_id_fkey;
ALTER TABLE plat.compartilhamento_link_item DROP CONSTRAINT IF EXISTS compartilhamento_link_item_tenant_item_fkey;
ALTER TABLE plat.compartilhamento_link_item ADD CONSTRAINT compartilhamento_link_item_tenant_item_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.favorito DROP CONSTRAINT IF EXISTS favorito_item_id_fkey;
ALTER TABLE plat.favorito DROP CONSTRAINT IF EXISTS favorito_tenant_item_fkey;
ALTER TABLE plat.favorito ADD CONSTRAINT favorito_tenant_item_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.importacao DROP CONSTRAINT IF EXISTS importacao_arquivo_id_fkey;
ALTER TABLE plat.importacao DROP CONSTRAINT IF EXISTS importacao_tenant_arquivo_fkey;
ALTER TABLE plat.importacao ADD CONSTRAINT importacao_tenant_arquivo_fkey
  FOREIGN KEY (tenant_id, arquivo_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.item_grupo DROP CONSTRAINT IF EXISTS item_grupo_item_id_fkey;
ALTER TABLE plat.item_grupo DROP CONSTRAINT IF EXISTS item_grupo_tenant_item_fkey;
ALTER TABLE plat.item_grupo ADD CONSTRAINT item_grupo_tenant_item_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.item_relacao DROP CONSTRAINT IF EXISTS item_relacao_destino_fkey;
ALTER TABLE plat.item_relacao DROP CONSTRAINT IF EXISTS item_relacao_tenant_destino_fkey;
ALTER TABLE plat.item_relacao ADD CONSTRAINT item_relacao_tenant_destino_fkey
  FOREIGN KEY (tenant_id, destino) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.item_relacao DROP CONSTRAINT IF EXISTS item_relacao_origem_fkey;
ALTER TABLE plat.item_relacao DROP CONSTRAINT IF EXISTS item_relacao_tenant_origem_fkey;
ALTER TABLE plat.item_relacao ADD CONSTRAINT item_relacao_tenant_origem_fkey
  FOREIGN KEY (tenant_id, origem) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.item_versao DROP CONSTRAINT IF EXISTS item_versao_item_id_fkey;
ALTER TABLE plat.item_versao DROP CONSTRAINT IF EXISTS item_versao_tenant_item_fkey;
ALTER TABLE plat.item_versao ADD CONSTRAINT item_versao_tenant_item_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.upload DROP CONSTRAINT IF EXISTS upload_arquivo_id_fkey;
ALTER TABLE plat.upload DROP CONSTRAINT IF EXISTS upload_tenant_arquivo_fkey;
ALTER TABLE plat.upload ADD CONSTRAINT upload_tenant_arquivo_fkey
  FOREIGN KEY (tenant_id, arquivo_id) REFERENCES plat.item (tenant_id, id);

-- ===== alvo: grupo (2 FKs) =====
ALTER TABLE plat.grupo_membro DROP CONSTRAINT IF EXISTS grupo_membro_grupo_id_fkey;
ALTER TABLE plat.grupo_membro DROP CONSTRAINT IF EXISTS grupo_membro_tenant_grupo_fkey;
ALTER TABLE plat.grupo_membro ADD CONSTRAINT grupo_membro_tenant_grupo_fkey
  FOREIGN KEY (tenant_id, grupo_id) REFERENCES plat.grupo (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.item_grupo DROP CONSTRAINT IF EXISTS item_grupo_grupo_id_fkey;
ALTER TABLE plat.item_grupo DROP CONSTRAINT IF EXISTS item_grupo_tenant_grupo_fkey;
ALTER TABLE plat.item_grupo ADD CONSTRAINT item_grupo_tenant_grupo_fkey
  FOREIGN KEY (tenant_id, grupo_id) REFERENCES plat.grupo (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: pasta (2 FKs, uma self) =====
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_pasta_id_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_pasta_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_tenant_pasta_fkey
  FOREIGN KEY (tenant_id, pasta_id) REFERENCES plat.pasta (tenant_id, id) ON DELETE SET NULL (pasta_id);

ALTER TABLE plat.pasta DROP CONSTRAINT IF EXISTS pasta_pai_id_fkey;
ALTER TABLE plat.pasta DROP CONSTRAINT IF EXISTS pasta_tenant_pai_fkey;
ALTER TABLE plat.pasta ADD CONSTRAINT pasta_tenant_pai_fkey
  FOREIGN KEY (tenant_id, pai_id) REFERENCES plat.pasta (tenant_id, id) ON DELETE RESTRICT;

-- ===== alvo: categoria (self) =====
ALTER TABLE plat.categoria DROP CONSTRAINT IF EXISTS categoria_pai_id_fkey;
ALTER TABLE plat.categoria DROP CONSTRAINT IF EXISTS categoria_tenant_pai_fkey;
ALTER TABLE plat.categoria ADD CONSTRAINT categoria_tenant_pai_fkey
  FOREIGN KEY (tenant_id, pai_id) REFERENCES plat.categoria (tenant_id, id) ON DELETE RESTRICT;

-- ===== alvo: compartilhamento_link =====
ALTER TABLE plat.compartilhamento_link_item DROP CONSTRAINT IF EXISTS compartilhamento_link_item_link_id_fkey;
ALTER TABLE plat.compartilhamento_link_item DROP CONSTRAINT IF EXISTS compartilhamento_link_item_tenant_link_fkey;
ALTER TABLE plat.compartilhamento_link_item ADD CONSTRAINT compartilhamento_link_item_tenant_link_fkey
  FOREIGN KEY (tenant_id, link_id) REFERENCES plat.compartilhamento_link (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: conexao =====
ALTER TABLE plat.conexao_saude_historico DROP CONSTRAINT IF EXISTS conexao_saude_historico_conexao_id_fkey;
ALTER TABLE plat.conexao_saude_historico DROP CONSTRAINT IF EXISTS conexao_saude_historico_tenant_conexao_fkey;
ALTER TABLE plat.conexao_saude_historico ADD CONSTRAINT conexao_saude_historico_tenant_conexao_fkey
  FOREIGN KEY (tenant_id, conexao_id) REFERENCES plat.conexao (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: job =====
ALTER TABLE plat.job_log DROP CONSTRAINT IF EXISTS job_log_job_id_fkey;
ALTER TABLE plat.job_log DROP CONSTRAINT IF EXISTS job_log_tenant_job_fkey;
ALTER TABLE plat.job_log ADD CONSTRAINT job_log_tenant_job_fkey
  FOREIGN KEY (tenant_id, job_id) REFERENCES plat.job (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: token_servico (self) =====
ALTER TABLE plat.token_servico DROP CONSTRAINT IF EXISTS token_servico_renovado_por_fkey;
ALTER TABLE plat.token_servico DROP CONSTRAINT IF EXISTS token_servico_tenant_renovado_por_fkey;
ALTER TABLE plat.token_servico ADD CONSTRAINT token_servico_tenant_renovado_por_fkey
  FOREIGN KEY (tenant_id, renovado_por) REFERENCES plat.token_servico (tenant_id, id);
