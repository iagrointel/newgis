-- 20260916T0020_fk_composta_por_inquilino_lote2 (item F2-FK151): chave estrangeira COMPOSTA
-- (tenant_id, ...) nas 150 FKs simples achadas fora de `plat.rede_*` (já composta em
-- 20260906T1815) e fora do lote 1 (`20260906T1847_fk_por_inquilino_classe.sql`, 44 FKs, turno 3) —
-- mesma classe A1 do adversário do L4-01-a: `plat_app`, autenticado no inquilino B, conseguia gravar
-- uma linha SUA (tenant_id = B) apontando para o `id` de uma linha de OUTRO inquilino, porque a FK só
-- confere que o id existe em algum lugar da tabela alvo, nunca que é do mesmo tenant_id.
--
-- Origem: `tests/api/test_fk_composta_por_inquilino.py` reprovava com 151 achados nesta base (a
-- varredura cobre o schema inteiro, não só as tabelas já tratadas nos dois lotes anteriores — cada
-- item novo do produto que repita o padrão simples cai nela). Classificação das 151:
--
--   (a) 142 referências de DADO do inquilino (item_id, camada_id, conexao_id, execucao_id, fila_id,
--       modelo_id, chamado_id, roteiro_id, alvo_id, ...) e colunas de autoria/ator (criado_por,
--       atualizado_por, publicado_por, exposto_por, assinado_por, resolvido_por, aberto_por,
--       fechado_por, enviado_por, construido_por, instalado_por, autor_id, e usuario_id nas 9 tabelas
--       onde é "quem fez" — agenda_aviso, campo_coleta, campo_visita, exportacao_inquilino,
--       geoparquet_job, intercambio_lote_importacao, notificacao, rede_tracado_execucao,
--       tabela_vista) — CONFERIDO no código (`grep -rn contexto_leitura app/`, só 11 arquivos:
--       auth/rotas_log.py, auth/rotas_plataforma.py, auth/sessao.py, catalogo/rotas_itens.py, os 4 de
--       imagens/, relacionamentos/rotas.py, telemetria.py, widgets/rotas.py) que NENHUM caminho de
--       ESCRITA destas 142 passa por `auth.contexto_leitura()` (o contexto cross-tenant do
--       superadmin, D20): todas gravam com `auth.contexto()`/`auth.usuario_id` de sessão normal, onde
--       usuario e tenant da sessão sempre coincidem — compor é seguro e fecha o oráculo de existência
--       também para estas colunas de autoria. Composta por este script.
--   (b) 1 coluna de autoria com risco REAL comprovado — `chamado_comentario.autor_id`: a rota
--       operador (`app/chamados/rotas.py::operador_responder`, POST /api/chamados/operador/{id}/
--       comentarios, `autenticado(superadmin=True, so_sessao=True)`) chama
--       `plat.chamado_operador_responder` (`20260908T2230_chamados_suporte.sql`), que grava
--       `chamado_comentario` com `tenant_id` do chamado (inquilino do CLIENTE) e `autor_id` do
--       OPERADOR DA PLATAFORMA — que legitimamente mora em OUTRO inquilino. Mesma classe exata do que
--       reverteu `item.criado_por/apagado_por/modificado_por` em `20260915T2349_fk_autoria_ator_fora_
--       do_inquilino.sql`. NÃO composta; registrada em `PERMITIDAS` (mesmo teste) com a razão; ganha
--       `ON DELETE SET NULL` abaixo (não tinha nenhuma ação antes — RESTRICT implícito, que travaria
--       o apagamento de um operador com histórico de resposta).
--   (c) 8 `dono_id` (amc_preset, campo_fila, campo_roteiro, fluxo_fonte, modelo3d, odk_ponte,
--       rede_config_tracado, replica) — CONFERIDO no código (`grep -rn dono_id app/` de cada tabela):
--       todos gravados com `auth.usuario_id`/`plat.usuario_atual()` de sessão normal, nunca de corpo
--       de requisição; mesmo padrão que `016_catalogo_apagar_usuario.sql` e o gatilho `tg_item_antes`
--       já impõem para `item.dono_id` (`usuario_de_outro_inquilino` barra qualquer dono de outro
--       inquilino). Compor é seguro e correto — dono é sempre do inquilino. Composta por este script.
--
-- Gerado por `db/gerar_fk_composta.py` (reexecutável: lê `pg_constraint` ao vivo, filtra pela MESMA
-- `PERMITIDAS` do teste — fonte única do que não compor — e reemite DROP/ADD idempotente; rodar de
-- novo sem achados não imprime nada). UNIQUE (tenant_id, <colunas do alvo>) em cada tabela-alvo vem
-- primeiro (porta para a FK composta; `amc_modelo_versao` já tinha chave natural (modelo_id,
-- versao_hash), a UNIQUE nova é (tenant_id, modelo_id, versao_hash)). ON DELETE de cada FK preserva a
-- ação original (SET NULL com lista de coluna quando a ação já era SET NULL — sintaxe do Postgres 15+,
-- mesma da 20260906T1815/1847 — para nunca zerar `tenant_id`, que é NOT NULL). Idempotente: todo
-- DROP CONSTRAINT é IF EXISTS e o bloco de UNIQUE confere `pg_constraint` antes de criar.
--
-- Reproduzir:
--   bash /home/dev/plataforma/laco/trilha_ambiente.sh uniao /home/dev/plataforma/wt/f2fk151
--   venv/bin/pytest tests/api/test_fk_composta_por_inquilino.py -q

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'agenda' AND c.conname = 'agenda_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.agenda ADD CONSTRAINT agenda_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'amc_conjunto_unidade' AND c.conname = 'amc_conjunto_unidade_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.amc_conjunto_unidade ADD CONSTRAINT amc_conjunto_unidade_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'amc_execucao' AND c.conname = 'amc_execucao_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.amc_execucao ADD CONSTRAINT amc_execucao_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'amc_modelo' AND c.conname = 'amc_modelo_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.amc_modelo ADD CONSTRAINT amc_modelo_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'amc_modelo_versao' AND c.conname = 'amc_modelo_versao_tenant_id_modelo_id_versao_hash_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.amc_modelo_versao ADD CONSTRAINT amc_modelo_versao_tenant_id_modelo_id_versao_hash_key UNIQUE (tenant_id, modelo_id, versao_hash)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'campo_alvo' AND c.conname = 'campo_alvo_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.campo_alvo ADD CONSTRAINT campo_alvo_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'campo_fila' AND c.conname = 'campo_fila_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.campo_fila ADD CONSTRAINT campo_fila_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'campo_roteiro' AND c.conname = 'campo_roteiro_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.campo_roteiro ADD CONSTRAINT campo_roteiro_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'campo_visita' AND c.conname = 'campo_visita_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.campo_visita ADD CONSTRAINT campo_visita_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'chamado' AND c.conname = 'chamado_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.chamado ADD CONSTRAINT chamado_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'conexao' AND c.conname = 'conexao_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.conexao ADD CONSTRAINT conexao_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'dominio' AND c.conname = 'dominio_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.dominio ADD CONSTRAINT dominio_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'fluxo_fonte' AND c.conname = 'fluxo_fonte_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.fluxo_fonte ADD CONSTRAINT fluxo_fonte_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'formulario' AND c.conname = 'formulario_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.formulario ADD CONSTRAINT formulario_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'grupo' AND c.conname = 'grupo_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.grupo ADD CONSTRAINT grupo_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'intercambio_lote_importacao' AND c.conname = 'intercambio_lote_importacao_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.intercambio_lote_importacao ADD CONSTRAINT intercambio_lote_importacao_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'item' AND c.conname = 'item_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.item ADD CONSTRAINT item_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'migracao_inventario' AND c.conname = 'migracao_inventario_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.migracao_inventario ADD CONSTRAINT migracao_inventario_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'modelo3d' AND c.conname = 'modelo3d_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.modelo3d ADD CONSTRAINT modelo3d_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'odk_ponte' AND c.conname = 'odk_ponte_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.odk_ponte ADD CONSTRAINT odk_ponte_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'parcela' AND c.conname = 'parcela_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.parcela ADD CONSTRAINT parcela_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'parcela_linha' AND c.conname = 'parcela_linha_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.parcela_linha ADD CONSTRAINT parcela_linha_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'parcela_ponto' AND c.conname = 'parcela_ponto_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.parcela_ponto ADD CONSTRAINT parcela_ponto_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'parcela_registro' AND c.conname = 'parcela_registro_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.parcela_registro ADD CONSTRAINT parcela_registro_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'provedor_oidc' AND c.conname = 'provedor_oidc_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.provedor_oidc ADD CONSTRAINT provedor_oidc_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'provedor_saml' AND c.conname = 'provedor_saml_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.provedor_saml ADD CONSTRAINT provedor_saml_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede' AND c.conname = 'rede_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.rede ADD CONSTRAINT rede_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_feicao' AND c.conname = 'rede_feicao_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.rede_feicao ADD CONSTRAINT rede_feicao_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_regra' AND c.conname = 'rede_regra_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_tipo' AND c.conname = 'rede_tipo_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.rede_tipo ADD CONSTRAINT rede_tipo_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_uc' AND c.conname = 'rede_uc_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.rede_uc ADD CONSTRAINT rede_uc_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'replica' AND c.conname = 'replica_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.replica ADD CONSTRAINT replica_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'token_servico' AND c.conname = 'token_servico_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.token_servico ADD CONSTRAINT token_servico_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'usuario' AND c.conname = 'usuario_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.usuario ADD CONSTRAINT usuario_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'versao' AND c.conname = 'versao_tenant_id_id_key'
  ) THEN
    EXECUTE 'ALTER TABLE plat.versao ADD CONSTRAINT versao_tenant_id_id_key UNIQUE (tenant_id, id)';
  END IF;
END $$;
ALTER TABLE plat.acervo_arquivo_exposto DROP CONSTRAINT IF EXISTS acervo_arquivo_exposto_exposto_por_fkey;
ALTER TABLE plat.acervo_arquivo_exposto DROP CONSTRAINT IF EXISTS acervo_arquivo_exposto_tenant_exposto_por_fkey;
ALTER TABLE plat.acervo_arquivo_exposto ADD CONSTRAINT acervo_arquivo_exposto_tenant_exposto_por_fkey
  FOREIGN KEY (tenant_id, exposto_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (exposto_por);
ALTER TABLE plat.acervo_arquivo_exposto DROP CONSTRAINT IF EXISTS acervo_arquivo_exposto_item_id_fkey;
ALTER TABLE plat.acervo_arquivo_exposto DROP CONSTRAINT IF EXISTS acervo_arquivo_exposto_tenant_item_id_fkey;
ALTER TABLE plat.acervo_arquivo_exposto ADD CONSTRAINT acervo_arquivo_exposto_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.acervo_assinatura DROP CONSTRAINT IF EXISTS acervo_assinatura_assinado_por_fkey;
ALTER TABLE plat.acervo_assinatura DROP CONSTRAINT IF EXISTS acervo_assinatura_tenant_assinado_por_fkey;
ALTER TABLE plat.acervo_assinatura ADD CONSTRAINT acervo_assinatura_tenant_assinado_por_fkey
  FOREIGN KEY (tenant_id, assinado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (assinado_por);
ALTER TABLE plat.agenda_aviso DROP CONSTRAINT IF EXISTS agenda_aviso_agenda_id_fkey;
ALTER TABLE plat.agenda_aviso DROP CONSTRAINT IF EXISTS agenda_aviso_tenant_agenda_id_fkey;
ALTER TABLE plat.agenda_aviso ADD CONSTRAINT agenda_aviso_tenant_agenda_id_fkey
  FOREIGN KEY (tenant_id, agenda_id) REFERENCES plat.agenda (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.agenda_aviso DROP CONSTRAINT IF EXISTS agenda_aviso_usuario_id_fkey;
ALTER TABLE plat.agenda_aviso DROP CONSTRAINT IF EXISTS agenda_aviso_tenant_usuario_id_fkey;
ALTER TABLE plat.agenda_aviso ADD CONSTRAINT agenda_aviso_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.agol_publicacao DROP CONSTRAINT IF EXISTS agol_publicacao_item_id_fkey;
ALTER TABLE plat.agol_publicacao DROP CONSTRAINT IF EXISTS agol_publicacao_tenant_item_id_fkey;
ALTER TABLE plat.agol_publicacao ADD CONSTRAINT agol_publicacao_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_conjunto_unidade DROP CONSTRAINT IF EXISTS amc_conjunto_unidade_criado_por_fkey;
ALTER TABLE plat.amc_conjunto_unidade DROP CONSTRAINT IF EXISTS amc_conjunto_unidade_tenant_criado_por_fkey;
ALTER TABLE plat.amc_conjunto_unidade ADD CONSTRAINT amc_conjunto_unidade_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_conjunto_id_fkey;
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_tenant_conjunto_id_fkey;
ALTER TABLE plat.amc_execucao ADD CONSTRAINT amc_execucao_tenant_conjunto_id_fkey
  FOREIGN KEY (tenant_id, conjunto_id) REFERENCES plat.amc_conjunto_unidade (tenant_id, id) ON DELETE RESTRICT;
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_criado_por_fkey;
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_tenant_criado_por_fkey;
ALTER TABLE plat.amc_execucao ADD CONSTRAINT amc_execucao_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_modelo_id_fkey;
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_tenant_modelo_id_fkey;
ALTER TABLE plat.amc_execucao ADD CONSTRAINT amc_execucao_tenant_modelo_id_fkey
  FOREIGN KEY (tenant_id, modelo_id) REFERENCES plat.amc_modelo (tenant_id, id);
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_modelo_id_versao_hash_fkey;
ALTER TABLE plat.amc_execucao DROP CONSTRAINT IF EXISTS amc_execucao_tenant_modelo_id_versao_hash_fkey;
ALTER TABLE plat.amc_execucao ADD CONSTRAINT amc_execucao_tenant_modelo_id_versao_hash_fkey
  FOREIGN KEY (tenant_id, modelo_id, versao_hash) REFERENCES plat.amc_modelo_versao (tenant_id, modelo_id, versao_hash);
ALTER TABLE plat.amc_fator_bruto DROP CONSTRAINT IF EXISTS amc_fator_bruto_execucao_id_fkey;
ALTER TABLE plat.amc_fator_bruto DROP CONSTRAINT IF EXISTS amc_fator_bruto_tenant_execucao_id_fkey;
ALTER TABLE plat.amc_fator_bruto ADD CONSTRAINT amc_fator_bruto_tenant_execucao_id_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.amc_execucao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_modelo DROP CONSTRAINT IF EXISTS amc_modelo_atualizado_por_fkey;
ALTER TABLE plat.amc_modelo DROP CONSTRAINT IF EXISTS amc_modelo_tenant_atualizado_por_fkey;
ALTER TABLE plat.amc_modelo ADD CONSTRAINT amc_modelo_tenant_atualizado_por_fkey
  FOREIGN KEY (tenant_id, atualizado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (atualizado_por);
ALTER TABLE plat.amc_modelo DROP CONSTRAINT IF EXISTS amc_modelo_criado_por_fkey;
ALTER TABLE plat.amc_modelo DROP CONSTRAINT IF EXISTS amc_modelo_tenant_criado_por_fkey;
ALTER TABLE plat.amc_modelo ADD CONSTRAINT amc_modelo_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.amc_modelo_versao DROP CONSTRAINT IF EXISTS amc_modelo_versao_criado_por_fkey;
ALTER TABLE plat.amc_modelo_versao DROP CONSTRAINT IF EXISTS amc_modelo_versao_tenant_criado_por_fkey;
ALTER TABLE plat.amc_modelo_versao ADD CONSTRAINT amc_modelo_versao_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.amc_modelo_versao DROP CONSTRAINT IF EXISTS amc_modelo_versao_modelo_id_fkey;
ALTER TABLE plat.amc_modelo_versao DROP CONSTRAINT IF EXISTS amc_modelo_versao_tenant_modelo_id_fkey;
ALTER TABLE plat.amc_modelo_versao ADD CONSTRAINT amc_modelo_versao_tenant_modelo_id_fkey
  FOREIGN KEY (tenant_id, modelo_id) REFERENCES plat.amc_modelo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_preset DROP CONSTRAINT IF EXISTS amc_preset_dono_id_fkey;
ALTER TABLE plat.amc_preset DROP CONSTRAINT IF EXISTS amc_preset_tenant_dono_id_fkey;
ALTER TABLE plat.amc_preset ADD CONSTRAINT amc_preset_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.amc_resultado DROP CONSTRAINT IF EXISTS amc_resultado_execucao_id_fkey;
ALTER TABLE plat.amc_resultado DROP CONSTRAINT IF EXISTS amc_resultado_tenant_execucao_id_fkey;
ALTER TABLE plat.amc_resultado ADD CONSTRAINT amc_resultado_tenant_execucao_id_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.amc_execucao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_resultado_camada DROP CONSTRAINT IF EXISTS amc_resultado_camada_criado_por_fkey;
ALTER TABLE plat.amc_resultado_camada DROP CONSTRAINT IF EXISTS amc_resultado_camada_tenant_criado_por_fkey;
ALTER TABLE plat.amc_resultado_camada ADD CONSTRAINT amc_resultado_camada_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.amc_resultado_camada DROP CONSTRAINT IF EXISTS amc_resultado_camada_execucao_id_fkey;
ALTER TABLE plat.amc_resultado_camada DROP CONSTRAINT IF EXISTS amc_resultado_camada_tenant_execucao_id_fkey;
ALTER TABLE plat.amc_resultado_camada ADD CONSTRAINT amc_resultado_camada_tenant_execucao_id_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.amc_execucao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_resultado_camada DROP CONSTRAINT IF EXISTS amc_resultado_camada_item_id_fkey;
ALTER TABLE plat.amc_resultado_camada DROP CONSTRAINT IF EXISTS amc_resultado_camada_tenant_item_id_fkey;
ALTER TABLE plat.amc_resultado_camada ADD CONSTRAINT amc_resultado_camada_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_resultado_raster DROP CONSTRAINT IF EXISTS amc_resultado_raster_criado_por_fkey;
ALTER TABLE plat.amc_resultado_raster DROP CONSTRAINT IF EXISTS amc_resultado_raster_tenant_criado_por_fkey;
ALTER TABLE plat.amc_resultado_raster ADD CONSTRAINT amc_resultado_raster_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.amc_resultado_raster DROP CONSTRAINT IF EXISTS amc_resultado_raster_execucao_id_fkey;
ALTER TABLE plat.amc_resultado_raster DROP CONSTRAINT IF EXISTS amc_resultado_raster_tenant_execucao_id_fkey;
ALTER TABLE plat.amc_resultado_raster ADD CONSTRAINT amc_resultado_raster_tenant_execucao_id_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.amc_execucao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_resultado_raster DROP CONSTRAINT IF EXISTS amc_resultado_raster_item_id_fkey;
ALTER TABLE plat.amc_resultado_raster DROP CONSTRAINT IF EXISTS amc_resultado_raster_tenant_item_id_fkey;
ALTER TABLE plat.amc_resultado_raster ADD CONSTRAINT amc_resultado_raster_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.amc_unidade DROP CONSTRAINT IF EXISTS amc_unidade_conjunto_id_fkey;
ALTER TABLE plat.amc_unidade DROP CONSTRAINT IF EXISTS amc_unidade_tenant_conjunto_id_fkey;
ALTER TABLE plat.amc_unidade ADD CONSTRAINT amc_unidade_tenant_conjunto_id_fkey
  FOREIGN KEY (tenant_id, conjunto_id) REFERENCES plat.amc_conjunto_unidade (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_autor_id_fkey;
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_tenant_autor_id_fkey;
ALTER TABLE plat.anotacao_feicao ADD CONSTRAINT anotacao_feicao_tenant_autor_id_fkey
  FOREIGN KEY (tenant_id, autor_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_camada_id_fkey;
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_tenant_camada_id_fkey;
ALTER TABLE plat.anotacao_feicao ADD CONSTRAINT anotacao_feicao_tenant_camada_id_fkey
  FOREIGN KEY (tenant_id, camada_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_grupo_id_fkey;
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_tenant_grupo_id_fkey;
ALTER TABLE plat.anotacao_feicao ADD CONSTRAINT anotacao_feicao_tenant_grupo_id_fkey
  FOREIGN KEY (tenant_id, grupo_id) REFERENCES plat.grupo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_resolvido_por_fkey;
ALTER TABLE plat.anotacao_feicao DROP CONSTRAINT IF EXISTS anotacao_feicao_tenant_resolvido_por_fkey;
ALTER TABLE plat.anotacao_feicao ADD CONSTRAINT anotacao_feicao_tenant_resolvido_por_fkey
  FOREIGN KEY (tenant_id, resolvido_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.camada_copia_versao DROP CONSTRAINT IF EXISTS camada_copia_versao_conexao_id_fkey;
ALTER TABLE plat.camada_copia_versao DROP CONSTRAINT IF EXISTS camada_copia_versao_tenant_conexao_id_fkey;
ALTER TABLE plat.camada_copia_versao ADD CONSTRAINT camada_copia_versao_tenant_conexao_id_fkey
  FOREIGN KEY (tenant_id, conexao_id) REFERENCES plat.conexao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.camada_subtipo DROP CONSTRAINT IF EXISTS camada_subtipo_item_id_fkey;
ALTER TABLE plat.camada_subtipo DROP CONSTRAINT IF EXISTS camada_subtipo_tenant_item_id_fkey;
ALTER TABLE plat.camada_subtipo ADD CONSTRAINT camada_subtipo_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.camada_versao DROP CONSTRAINT IF EXISTS camada_versao_camada_id_fkey;
ALTER TABLE plat.camada_versao DROP CONSTRAINT IF EXISTS camada_versao_tenant_camada_id_fkey;
ALTER TABLE plat.camada_versao ADD CONSTRAINT camada_versao_tenant_camada_id_fkey
  FOREIGN KEY (tenant_id, camada_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.campo_alvo DROP CONSTRAINT IF EXISTS campo_alvo_fila_id_fkey;
ALTER TABLE plat.campo_alvo DROP CONSTRAINT IF EXISTS campo_alvo_tenant_fila_id_fkey;
ALTER TABLE plat.campo_alvo ADD CONSTRAINT campo_alvo_tenant_fila_id_fkey
  FOREIGN KEY (tenant_id, fila_id) REFERENCES plat.campo_fila (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.campo_coleta DROP CONSTRAINT IF EXISTS campo_coleta_usuario_id_fkey;
ALTER TABLE plat.campo_coleta DROP CONSTRAINT IF EXISTS campo_coleta_tenant_usuario_id_fkey;
ALTER TABLE plat.campo_coleta ADD CONSTRAINT campo_coleta_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.campo_fila DROP CONSTRAINT IF EXISTS campo_fila_camada_id_fkey;
ALTER TABLE plat.campo_fila DROP CONSTRAINT IF EXISTS campo_fila_tenant_camada_id_fkey;
ALTER TABLE plat.campo_fila ADD CONSTRAINT campo_fila_tenant_camada_id_fkey
  FOREIGN KEY (tenant_id, camada_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.campo_fila DROP CONSTRAINT IF EXISTS campo_fila_criado_por_fkey;
ALTER TABLE plat.campo_fila DROP CONSTRAINT IF EXISTS campo_fila_tenant_criado_por_fkey;
ALTER TABLE plat.campo_fila ADD CONSTRAINT campo_fila_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.campo_fila DROP CONSTRAINT IF EXISTS campo_fila_dono_id_fkey;
ALTER TABLE plat.campo_fila DROP CONSTRAINT IF EXISTS campo_fila_tenant_dono_id_fkey;
ALTER TABLE plat.campo_fila ADD CONSTRAINT campo_fila_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.campo_roteiro DROP CONSTRAINT IF EXISTS campo_roteiro_dono_id_fkey;
ALTER TABLE plat.campo_roteiro DROP CONSTRAINT IF EXISTS campo_roteiro_tenant_dono_id_fkey;
ALTER TABLE plat.campo_roteiro ADD CONSTRAINT campo_roteiro_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.campo_roteiro DROP CONSTRAINT IF EXISTS campo_roteiro_fila_id_fkey;
ALTER TABLE plat.campo_roteiro DROP CONSTRAINT IF EXISTS campo_roteiro_tenant_fila_id_fkey;
ALTER TABLE plat.campo_roteiro ADD CONSTRAINT campo_roteiro_tenant_fila_id_fkey
  FOREIGN KEY (tenant_id, fila_id) REFERENCES plat.campo_fila (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.campo_roteiro_parada DROP CONSTRAINT IF EXISTS campo_roteiro_parada_alvo_id_fkey;
ALTER TABLE plat.campo_roteiro_parada DROP CONSTRAINT IF EXISTS campo_roteiro_parada_tenant_alvo_id_fkey;
ALTER TABLE plat.campo_roteiro_parada ADD CONSTRAINT campo_roteiro_parada_tenant_alvo_id_fkey
  FOREIGN KEY (tenant_id, alvo_id) REFERENCES plat.campo_alvo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.campo_roteiro_parada DROP CONSTRAINT IF EXISTS campo_roteiro_parada_roteiro_id_fkey;
ALTER TABLE plat.campo_roteiro_parada DROP CONSTRAINT IF EXISTS campo_roteiro_parada_tenant_roteiro_id_fkey;
ALTER TABLE plat.campo_roteiro_parada ADD CONSTRAINT campo_roteiro_parada_tenant_roteiro_id_fkey
  FOREIGN KEY (tenant_id, roteiro_id) REFERENCES plat.campo_roteiro (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_alvo_id_fkey;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_tenant_alvo_id_fkey;
ALTER TABLE plat.campo_visita ADD CONSTRAINT campo_visita_tenant_alvo_id_fkey
  FOREIGN KEY (tenant_id, alvo_id) REFERENCES plat.campo_alvo (tenant_id, id) ON DELETE SET NULL (alvo_id);
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_camada_id_fkey;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_tenant_camada_id_fkey;
ALTER TABLE plat.campo_visita ADD CONSTRAINT campo_visita_tenant_camada_id_fkey
  FOREIGN KEY (tenant_id, camada_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_fila_id_fkey;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_tenant_fila_id_fkey;
ALTER TABLE plat.campo_visita ADD CONSTRAINT campo_visita_tenant_fila_id_fkey
  FOREIGN KEY (tenant_id, fila_id) REFERENCES plat.campo_fila (tenant_id, id) ON DELETE SET NULL (fila_id);
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_roteiro_id_fkey;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_tenant_roteiro_id_fkey;
ALTER TABLE plat.campo_visita ADD CONSTRAINT campo_visita_tenant_roteiro_id_fkey
  FOREIGN KEY (tenant_id, roteiro_id) REFERENCES plat.campo_roteiro (tenant_id, id) ON DELETE SET NULL (roteiro_id);
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_usuario_id_fkey;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_tenant_usuario_id_fkey;
ALTER TABLE plat.campo_visita ADD CONSTRAINT campo_visita_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.campo_visita_foto DROP CONSTRAINT IF EXISTS campo_visita_foto_criado_por_fkey;
ALTER TABLE plat.campo_visita_foto DROP CONSTRAINT IF EXISTS campo_visita_foto_tenant_criado_por_fkey;
ALTER TABLE plat.campo_visita_foto ADD CONSTRAINT campo_visita_foto_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.campo_visita_foto DROP CONSTRAINT IF EXISTS campo_visita_foto_visita_id_fkey;
ALTER TABLE plat.campo_visita_foto DROP CONSTRAINT IF EXISTS campo_visita_foto_tenant_visita_id_fkey;
ALTER TABLE plat.campo_visita_foto ADD CONSTRAINT campo_visita_foto_tenant_visita_id_fkey
  FOREIGN KEY (tenant_id, visita_id) REFERENCES plat.campo_visita (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.chamado DROP CONSTRAINT IF EXISTS chamado_aberto_por_fkey;
ALTER TABLE plat.chamado DROP CONSTRAINT IF EXISTS chamado_tenant_aberto_por_fkey;
ALTER TABLE plat.chamado ADD CONSTRAINT chamado_tenant_aberto_por_fkey
  FOREIGN KEY (tenant_id, aberto_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.chamado DROP CONSTRAINT IF EXISTS chamado_fechado_por_fkey;
ALTER TABLE plat.chamado DROP CONSTRAINT IF EXISTS chamado_tenant_fechado_por_fkey;
ALTER TABLE plat.chamado ADD CONSTRAINT chamado_tenant_fechado_por_fkey
  FOREIGN KEY (tenant_id, fechado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.chamado_anexo DROP CONSTRAINT IF EXISTS chamado_anexo_chamado_id_fkey;
ALTER TABLE plat.chamado_anexo DROP CONSTRAINT IF EXISTS chamado_anexo_tenant_chamado_id_fkey;
ALTER TABLE plat.chamado_anexo ADD CONSTRAINT chamado_anexo_tenant_chamado_id_fkey
  FOREIGN KEY (tenant_id, chamado_id) REFERENCES plat.chamado (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.chamado_anexo DROP CONSTRAINT IF EXISTS chamado_anexo_enviado_por_fkey;
ALTER TABLE plat.chamado_anexo DROP CONSTRAINT IF EXISTS chamado_anexo_tenant_enviado_por_fkey;
ALTER TABLE plat.chamado_anexo ADD CONSTRAINT chamado_anexo_tenant_enviado_por_fkey
  FOREIGN KEY (tenant_id, enviado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.chamado_comentario DROP CONSTRAINT IF EXISTS chamado_comentario_chamado_id_fkey;
ALTER TABLE plat.chamado_comentario DROP CONSTRAINT IF EXISTS chamado_comentario_tenant_chamado_id_fkey;
ALTER TABLE plat.chamado_comentario ADD CONSTRAINT chamado_comentario_tenant_chamado_id_fkey
  FOREIGN KEY (tenant_id, chamado_id) REFERENCES plat.chamado (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.conexao_arquivo DROP CONSTRAINT IF EXISTS conexao_arquivo_conexao_id_fkey;
ALTER TABLE plat.conexao_arquivo DROP CONSTRAINT IF EXISTS conexao_arquivo_tenant_conexao_id_fkey;
ALTER TABLE plat.conexao_arquivo ADD CONSTRAINT conexao_arquivo_tenant_conexao_id_fkey
  FOREIGN KEY (tenant_id, conexao_id) REFERENCES plat.conexao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.conexao_camada DROP CONSTRAINT IF EXISTS conexao_camada_conexao_id_fkey;
ALTER TABLE plat.conexao_camada DROP CONSTRAINT IF EXISTS conexao_camada_tenant_conexao_id_fkey;
ALTER TABLE plat.conexao_camada ADD CONSTRAINT conexao_camada_tenant_conexao_id_fkey
  FOREIGN KEY (tenant_id, conexao_id) REFERENCES plat.conexao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.dominio DROP CONSTRAINT IF EXISTS dominio_atualizado_por_fkey;
ALTER TABLE plat.dominio DROP CONSTRAINT IF EXISTS dominio_tenant_atualizado_por_fkey;
ALTER TABLE plat.dominio ADD CONSTRAINT dominio_tenant_atualizado_por_fkey
  FOREIGN KEY (tenant_id, atualizado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (atualizado_por);
ALTER TABLE plat.dominio DROP CONSTRAINT IF EXISTS dominio_criado_por_fkey;
ALTER TABLE plat.dominio DROP CONSTRAINT IF EXISTS dominio_tenant_criado_por_fkey;
ALTER TABLE plat.dominio ADD CONSTRAINT dominio_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.dominio_campo DROP CONSTRAINT IF EXISTS dominio_campo_dominio_id_fkey;
ALTER TABLE plat.dominio_campo DROP CONSTRAINT IF EXISTS dominio_campo_tenant_dominio_id_fkey;
ALTER TABLE plat.dominio_campo ADD CONSTRAINT dominio_campo_tenant_dominio_id_fkey
  FOREIGN KEY (tenant_id, dominio_id) REFERENCES plat.dominio (tenant_id, id) ON DELETE RESTRICT;
ALTER TABLE plat.dominio_campo DROP CONSTRAINT IF EXISTS dominio_campo_item_id_fkey;
ALTER TABLE plat.dominio_campo DROP CONSTRAINT IF EXISTS dominio_campo_tenant_item_id_fkey;
ALTER TABLE plat.dominio_campo ADD CONSTRAINT dominio_campo_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.dominio_valor DROP CONSTRAINT IF EXISTS dominio_valor_dominio_id_fkey;
ALTER TABLE plat.dominio_valor DROP CONSTRAINT IF EXISTS dominio_valor_tenant_dominio_id_fkey;
ALTER TABLE plat.dominio_valor ADD CONSTRAINT dominio_valor_tenant_dominio_id_fkey
  FOREIGN KEY (tenant_id, dominio_id) REFERENCES plat.dominio (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.exportacao_inquilino DROP CONSTRAINT IF EXISTS exportacao_inquilino_arquivo_item_id_fkey;
ALTER TABLE plat.exportacao_inquilino DROP CONSTRAINT IF EXISTS exportacao_inquilino_tenant_arquivo_item_id_fkey;
ALTER TABLE plat.exportacao_inquilino ADD CONSTRAINT exportacao_inquilino_tenant_arquivo_item_id_fkey
  FOREIGN KEY (tenant_id, arquivo_item_id) REFERENCES plat.item (tenant_id, id) ON DELETE SET NULL (arquivo_item_id);
ALTER TABLE plat.exportacao_inquilino DROP CONSTRAINT IF EXISTS exportacao_inquilino_usuario_id_fkey;
ALTER TABLE plat.exportacao_inquilino DROP CONSTRAINT IF EXISTS exportacao_inquilino_tenant_usuario_id_fkey;
ALTER TABLE plat.exportacao_inquilino ADD CONSTRAINT exportacao_inquilino_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.fluxo_fonte DROP CONSTRAINT IF EXISTS fluxo_fonte_dono_id_fkey;
ALTER TABLE plat.fluxo_fonte DROP CONSTRAINT IF EXISTS fluxo_fonte_tenant_dono_id_fkey;
ALTER TABLE plat.fluxo_fonte ADD CONSTRAINT fluxo_fonte_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.fluxo_metrica DROP CONSTRAINT IF EXISTS fluxo_metrica_fonte_id_fkey;
ALTER TABLE plat.fluxo_metrica DROP CONSTRAINT IF EXISTS fluxo_metrica_tenant_fonte_id_fkey;
ALTER TABLE plat.fluxo_metrica ADD CONSTRAINT fluxo_metrica_tenant_fonte_id_fkey
  FOREIGN KEY (tenant_id, fonte_id) REFERENCES plat.fluxo_fonte (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.formulario DROP CONSTRAINT IF EXISTS formulario_camada_id_fkey;
ALTER TABLE plat.formulario DROP CONSTRAINT IF EXISTS formulario_tenant_camada_id_fkey;
ALTER TABLE plat.formulario ADD CONSTRAINT formulario_tenant_camada_id_fkey
  FOREIGN KEY (tenant_id, camada_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.formulario DROP CONSTRAINT IF EXISTS formulario_criado_por_fkey;
ALTER TABLE plat.formulario DROP CONSTRAINT IF EXISTS formulario_tenant_criado_por_fkey;
ALTER TABLE plat.formulario ADD CONSTRAINT formulario_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.formulario_versao DROP CONSTRAINT IF EXISTS formulario_versao_criado_por_fkey;
ALTER TABLE plat.formulario_versao DROP CONSTRAINT IF EXISTS formulario_versao_tenant_criado_por_fkey;
ALTER TABLE plat.formulario_versao ADD CONSTRAINT formulario_versao_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.formulario_versao DROP CONSTRAINT IF EXISTS formulario_versao_formulario_id_fkey;
ALTER TABLE plat.formulario_versao DROP CONSTRAINT IF EXISTS formulario_versao_tenant_formulario_id_fkey;
ALTER TABLE plat.formulario_versao ADD CONSTRAINT formulario_versao_tenant_formulario_id_fkey
  FOREIGN KEY (tenant_id, formulario_id) REFERENCES plat.formulario (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.geocodificacao_lote DROP CONSTRAINT IF EXISTS geocodificacao_lote_item_id_fkey;
ALTER TABLE plat.geocodificacao_lote DROP CONSTRAINT IF EXISTS geocodificacao_lote_tenant_item_id_fkey;
ALTER TABLE plat.geocodificacao_lote ADD CONSTRAINT geocodificacao_lote_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.geoparquet_job DROP CONSTRAINT IF EXISTS geoparquet_job_catalogo_item_id_fkey;
ALTER TABLE plat.geoparquet_job DROP CONSTRAINT IF EXISTS geoparquet_job_tenant_catalogo_item_id_fkey;
ALTER TABLE plat.geoparquet_job ADD CONSTRAINT geoparquet_job_tenant_catalogo_item_id_fkey
  FOREIGN KEY (tenant_id, catalogo_item_id) REFERENCES plat.item (tenant_id, id) ON DELETE SET NULL (catalogo_item_id);
ALTER TABLE plat.geoparquet_job DROP CONSTRAINT IF EXISTS geoparquet_job_item_id_fkey;
ALTER TABLE plat.geoparquet_job DROP CONSTRAINT IF EXISTS geoparquet_job_tenant_item_id_fkey;
ALTER TABLE plat.geoparquet_job ADD CONSTRAINT geoparquet_job_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.geoparquet_job DROP CONSTRAINT IF EXISTS geoparquet_job_usuario_id_fkey;
ALTER TABLE plat.geoparquet_job DROP CONSTRAINT IF EXISTS geoparquet_job_tenant_usuario_id_fkey;
ALTER TABLE plat.geoparquet_job ADD CONSTRAINT geoparquet_job_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.importacao DROP CONSTRAINT IF EXISTS importacao_lote_id_fkey;
ALTER TABLE plat.importacao DROP CONSTRAINT IF EXISTS importacao_tenant_lote_id_fkey;
ALTER TABLE plat.importacao ADD CONSTRAINT importacao_tenant_lote_id_fkey
  FOREIGN KEY (tenant_id, lote_id) REFERENCES plat.intercambio_lote_importacao (tenant_id, id);
ALTER TABLE plat.intercambio_exportacao DROP CONSTRAINT IF EXISTS intercambio_exportacao_item_arquivo_fkey;
ALTER TABLE plat.intercambio_exportacao DROP CONSTRAINT IF EXISTS intercambio_exportacao_tenant_item_arquivo_fkey;
ALTER TABLE plat.intercambio_exportacao ADD CONSTRAINT intercambio_exportacao_tenant_item_arquivo_fkey
  FOREIGN KEY (tenant_id, item_arquivo) REFERENCES plat.item (tenant_id, id) ON DELETE SET NULL (item_arquivo);
ALTER TABLE plat.intercambio_exportacao DROP CONSTRAINT IF EXISTS intercambio_exportacao_item_origem_fkey;
ALTER TABLE plat.intercambio_exportacao DROP CONSTRAINT IF EXISTS intercambio_exportacao_tenant_item_origem_fkey;
ALTER TABLE plat.intercambio_exportacao ADD CONSTRAINT intercambio_exportacao_tenant_item_origem_fkey
  FOREIGN KEY (tenant_id, item_origem) REFERENCES plat.item (tenant_id, id) ON DELETE SET NULL (item_origem);
ALTER TABLE plat.intercambio_lote_importacao DROP CONSTRAINT IF EXISTS intercambio_lote_importacao_usuario_id_fkey;
ALTER TABLE plat.intercambio_lote_importacao DROP CONSTRAINT IF EXISTS intercambio_lote_importacao_tenant_usuario_id_fkey;
ALTER TABLE plat.intercambio_lote_importacao ADD CONSTRAINT intercambio_lote_importacao_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.item_publicacao DROP CONSTRAINT IF EXISTS item_publicacao_item_id_fkey;
ALTER TABLE plat.item_publicacao DROP CONSTRAINT IF EXISTS item_publicacao_tenant_item_id_fkey;
ALTER TABLE plat.item_publicacao ADD CONSTRAINT item_publicacao_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.item_publicacao DROP CONSTRAINT IF EXISTS item_publicacao_publicado_por_fkey;
ALTER TABLE plat.item_publicacao DROP CONSTRAINT IF EXISTS item_publicacao_tenant_publicado_por_fkey;
ALTER TABLE plat.item_publicacao ADD CONSTRAINT item_publicacao_tenant_publicado_por_fkey
  FOREIGN KEY (tenant_id, publicado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.item_publicacao DROP CONSTRAINT IF EXISTS item_publicacao_token_id_fkey;
ALTER TABLE plat.item_publicacao DROP CONSTRAINT IF EXISTS item_publicacao_tenant_token_id_fkey;
ALTER TABLE plat.item_publicacao ADD CONSTRAINT item_publicacao_tenant_token_id_fkey
  FOREIGN KEY (tenant_id, token_id) REFERENCES plat.token_servico (tenant_id, id) ON DELETE SET NULL (token_id);
ALTER TABLE plat.migracao_clone DROP CONSTRAINT IF EXISTS migracao_clone_conexao_id_fkey;
ALTER TABLE plat.migracao_clone DROP CONSTRAINT IF EXISTS migracao_clone_tenant_conexao_id_fkey;
ALTER TABLE plat.migracao_clone ADD CONSTRAINT migracao_clone_tenant_conexao_id_fkey
  FOREIGN KEY (tenant_id, conexao_id) REFERENCES plat.conexao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.migracao_clone DROP CONSTRAINT IF EXISTS migracao_clone_criado_por_fkey;
ALTER TABLE plat.migracao_clone DROP CONSTRAINT IF EXISTS migracao_clone_tenant_criado_por_fkey;
ALTER TABLE plat.migracao_clone ADD CONSTRAINT migracao_clone_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.migracao_grupo DROP CONSTRAINT IF EXISTS migracao_grupo_inventario_id_fkey;
ALTER TABLE plat.migracao_grupo DROP CONSTRAINT IF EXISTS migracao_grupo_tenant_inventario_id_fkey;
ALTER TABLE plat.migracao_grupo ADD CONSTRAINT migracao_grupo_tenant_inventario_id_fkey
  FOREIGN KEY (tenant_id, inventario_id) REFERENCES plat.migracao_inventario (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.migracao_inventario DROP CONSTRAINT IF EXISTS migracao_inventario_conexao_id_fkey;
ALTER TABLE plat.migracao_inventario DROP CONSTRAINT IF EXISTS migracao_inventario_tenant_conexao_id_fkey;
ALTER TABLE plat.migracao_inventario ADD CONSTRAINT migracao_inventario_tenant_conexao_id_fkey
  FOREIGN KEY (tenant_id, conexao_id) REFERENCES plat.conexao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.migracao_inventario DROP CONSTRAINT IF EXISTS migracao_inventario_criado_por_fkey;
ALTER TABLE plat.migracao_inventario DROP CONSTRAINT IF EXISTS migracao_inventario_tenant_criado_por_fkey;
ALTER TABLE plat.migracao_inventario ADD CONSTRAINT migracao_inventario_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.migracao_item DROP CONSTRAINT IF EXISTS migracao_item_inventario_id_fkey;
ALTER TABLE plat.migracao_item DROP CONSTRAINT IF EXISTS migracao_item_tenant_inventario_id_fkey;
ALTER TABLE plat.migracao_item ADD CONSTRAINT migracao_item_tenant_inventario_id_fkey
  FOREIGN KEY (tenant_id, inventario_id) REFERENCES plat.migracao_inventario (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.migracao_usuario DROP CONSTRAINT IF EXISTS migracao_usuario_inventario_id_fkey;
ALTER TABLE plat.migracao_usuario DROP CONSTRAINT IF EXISTS migracao_usuario_tenant_inventario_id_fkey;
ALTER TABLE plat.migracao_usuario ADD CONSTRAINT migracao_usuario_tenant_inventario_id_fkey
  FOREIGN KEY (tenant_id, inventario_id) REFERENCES plat.migracao_inventario (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.modelo3d DROP CONSTRAINT IF EXISTS modelo3d_dono_id_fkey;
ALTER TABLE plat.modelo3d DROP CONSTRAINT IF EXISTS modelo3d_tenant_dono_id_fkey;
ALTER TABLE plat.modelo3d ADD CONSTRAINT modelo3d_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.modelo3d_elemento DROP CONSTRAINT IF EXISTS modelo3d_elemento_modelo_id_fkey;
ALTER TABLE plat.modelo3d_elemento DROP CONSTRAINT IF EXISTS modelo3d_elemento_tenant_modelo_id_fkey;
ALTER TABLE plat.modelo3d_elemento ADD CONSTRAINT modelo3d_elemento_tenant_modelo_id_fkey
  FOREIGN KEY (tenant_id, modelo_id) REFERENCES plat.modelo3d (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.notebook_uso DROP CONSTRAINT IF EXISTS notebook_uso_token_id_fkey;
ALTER TABLE plat.notebook_uso DROP CONSTRAINT IF EXISTS notebook_uso_tenant_token_id_fkey;
ALTER TABLE plat.notebook_uso ADD CONSTRAINT notebook_uso_tenant_token_id_fkey
  FOREIGN KEY (tenant_id, token_id) REFERENCES plat.token_servico (tenant_id, id) ON DELETE SET NULL (token_id);
ALTER TABLE plat.notificacao DROP CONSTRAINT IF EXISTS notificacao_usuario_id_fkey;
ALTER TABLE plat.notificacao DROP CONSTRAINT IF EXISTS notificacao_tenant_usuario_id_fkey;
ALTER TABLE plat.notificacao ADD CONSTRAINT notificacao_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.odk_envio DROP CONSTRAINT IF EXISTS odk_envio_ponte_id_fkey;
ALTER TABLE plat.odk_envio DROP CONSTRAINT IF EXISTS odk_envio_tenant_ponte_id_fkey;
ALTER TABLE plat.odk_envio ADD CONSTRAINT odk_envio_tenant_ponte_id_fkey
  FOREIGN KEY (tenant_id, ponte_id) REFERENCES plat.odk_ponte (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.odk_ponte DROP CONSTRAINT IF EXISTS odk_ponte_conexao_id_fkey;
ALTER TABLE plat.odk_ponte DROP CONSTRAINT IF EXISTS odk_ponte_tenant_conexao_id_fkey;
ALTER TABLE plat.odk_ponte ADD CONSTRAINT odk_ponte_tenant_conexao_id_fkey
  FOREIGN KEY (tenant_id, conexao_id) REFERENCES plat.conexao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.odk_ponte DROP CONSTRAINT IF EXISTS odk_ponte_dono_id_fkey;
ALTER TABLE plat.odk_ponte DROP CONSTRAINT IF EXISTS odk_ponte_tenant_dono_id_fkey;
ALTER TABLE plat.odk_ponte ADD CONSTRAINT odk_ponte_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.odk_ponte DROP CONSTRAINT IF EXISTS odk_ponte_formulario_id_fkey;
ALTER TABLE plat.odk_ponte DROP CONSTRAINT IF EXISTS odk_ponte_tenant_formulario_id_fkey;
ALTER TABLE plat.odk_ponte ADD CONSTRAINT odk_ponte_tenant_formulario_id_fkey
  FOREIGN KEY (tenant_id, formulario_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.oidc_transacao DROP CONSTRAINT IF EXISTS oidc_transacao_provedor_id_fkey;
ALTER TABLE plat.oidc_transacao DROP CONSTRAINT IF EXISTS oidc_transacao_tenant_provedor_id_fkey;
ALTER TABLE plat.oidc_transacao ADD CONSTRAINT oidc_transacao_tenant_provedor_id_fkey
  FOREIGN KEY (tenant_id, provedor_id) REFERENCES plat.provedor_oidc (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.pacote_modelo DROP CONSTRAINT IF EXISTS pacote_modelo_publicado_por_fkey;
ALTER TABLE plat.pacote_modelo DROP CONSTRAINT IF EXISTS pacote_modelo_tenant_publicado_por_fkey;
ALTER TABLE plat.pacote_modelo ADD CONSTRAINT pacote_modelo_tenant_publicado_por_fkey
  FOREIGN KEY (tenant_id, publicado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.parcela DROP CONSTRAINT IF EXISTS parcela_criada_por_registro_fkey;
ALTER TABLE plat.parcela DROP CONSTRAINT IF EXISTS parcela_tenant_criada_por_registro_fkey;
ALTER TABLE plat.parcela ADD CONSTRAINT parcela_tenant_criada_por_registro_fkey
  FOREIGN KEY (tenant_id, criada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela DROP CONSTRAINT IF EXISTS parcela_retirada_por_registro_fkey;
ALTER TABLE plat.parcela DROP CONSTRAINT IF EXISTS parcela_tenant_retirada_por_registro_fkey;
ALTER TABLE plat.parcela ADD CONSTRAINT parcela_tenant_retirada_por_registro_fkey
  FOREIGN KEY (tenant_id, retirada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_criada_por_registro_fkey;
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_tenant_criada_por_registro_fkey;
ALTER TABLE plat.parcela_conexao ADD CONSTRAINT parcela_conexao_tenant_criada_por_registro_fkey
  FOREIGN KEY (tenant_id, criada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_de_ponto_id_fkey;
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_tenant_de_ponto_id_fkey;
ALTER TABLE plat.parcela_conexao ADD CONSTRAINT parcela_conexao_tenant_de_ponto_id_fkey
  FOREIGN KEY (tenant_id, de_ponto_id) REFERENCES plat.parcela_ponto (tenant_id, id);
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_para_ponto_id_fkey;
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_tenant_para_ponto_id_fkey;
ALTER TABLE plat.parcela_conexao ADD CONSTRAINT parcela_conexao_tenant_para_ponto_id_fkey
  FOREIGN KEY (tenant_id, para_ponto_id) REFERENCES plat.parcela_ponto (tenant_id, id);
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_conexao DROP CONSTRAINT IF EXISTS parcela_conexao_tenant_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_conexao ADD CONSTRAINT parcela_conexao_tenant_retirada_por_registro_fkey
  FOREIGN KEY (tenant_id, retirada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_criada_por_registro_fkey;
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_tenant_criada_por_registro_fkey;
ALTER TABLE plat.parcela_linha ADD CONSTRAINT parcela_linha_tenant_criada_por_registro_fkey
  FOREIGN KEY (tenant_id, criada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_de_ponto_id_fkey;
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_tenant_de_ponto_id_fkey;
ALTER TABLE plat.parcela_linha ADD CONSTRAINT parcela_linha_tenant_de_ponto_id_fkey
  FOREIGN KEY (tenant_id, de_ponto_id) REFERENCES plat.parcela_ponto (tenant_id, id);
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_para_ponto_id_fkey;
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_tenant_para_ponto_id_fkey;
ALTER TABLE plat.parcela_linha ADD CONSTRAINT parcela_linha_tenant_para_ponto_id_fkey
  FOREIGN KEY (tenant_id, para_ponto_id) REFERENCES plat.parcela_ponto (tenant_id, id);
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_linha DROP CONSTRAINT IF EXISTS parcela_linha_tenant_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_linha ADD CONSTRAINT parcela_linha_tenant_retirada_por_registro_fkey
  FOREIGN KEY (tenant_id, retirada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_linha_parcela DROP CONSTRAINT IF EXISTS parcela_linha_parcela_linha_id_fkey;
ALTER TABLE plat.parcela_linha_parcela DROP CONSTRAINT IF EXISTS parcela_linha_parcela_tenant_linha_id_fkey;
ALTER TABLE plat.parcela_linha_parcela ADD CONSTRAINT parcela_linha_parcela_tenant_linha_id_fkey
  FOREIGN KEY (tenant_id, linha_id) REFERENCES plat.parcela_linha (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.parcela_linha_parcela DROP CONSTRAINT IF EXISTS parcela_linha_parcela_parcela_id_fkey;
ALTER TABLE plat.parcela_linha_parcela DROP CONSTRAINT IF EXISTS parcela_linha_parcela_tenant_parcela_id_fkey;
ALTER TABLE plat.parcela_linha_parcela ADD CONSTRAINT parcela_linha_parcela_tenant_parcela_id_fkey
  FOREIGN KEY (tenant_id, parcela_id) REFERENCES plat.parcela (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.parcela_ponto DROP CONSTRAINT IF EXISTS parcela_ponto_criada_por_registro_fkey;
ALTER TABLE plat.parcela_ponto DROP CONSTRAINT IF EXISTS parcela_ponto_tenant_criada_por_registro_fkey;
ALTER TABLE plat.parcela_ponto ADD CONSTRAINT parcela_ponto_tenant_criada_por_registro_fkey
  FOREIGN KEY (tenant_id, criada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_ponto DROP CONSTRAINT IF EXISTS parcela_ponto_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_ponto DROP CONSTRAINT IF EXISTS parcela_ponto_tenant_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_ponto ADD CONSTRAINT parcela_ponto_tenant_retirada_por_registro_fkey
  FOREIGN KEY (tenant_id, retirada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_semente DROP CONSTRAINT IF EXISTS parcela_semente_criada_por_registro_fkey;
ALTER TABLE plat.parcela_semente DROP CONSTRAINT IF EXISTS parcela_semente_tenant_criada_por_registro_fkey;
ALTER TABLE plat.parcela_semente ADD CONSTRAINT parcela_semente_tenant_criada_por_registro_fkey
  FOREIGN KEY (tenant_id, criada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.parcela_semente DROP CONSTRAINT IF EXISTS parcela_semente_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_semente DROP CONSTRAINT IF EXISTS parcela_semente_tenant_retirada_por_registro_fkey;
ALTER TABLE plat.parcela_semente ADD CONSTRAINT parcela_semente_tenant_retirada_por_registro_fkey
  FOREIGN KEY (tenant_id, retirada_por_registro) REFERENCES plat.parcela_registro (tenant_id, id);
ALTER TABLE plat.provedor_oidc DROP CONSTRAINT IF EXISTS provedor_oidc_atualizado_por_fkey;
ALTER TABLE plat.provedor_oidc DROP CONSTRAINT IF EXISTS provedor_oidc_tenant_atualizado_por_fkey;
ALTER TABLE plat.provedor_oidc ADD CONSTRAINT provedor_oidc_tenant_atualizado_por_fkey
  FOREIGN KEY (tenant_id, atualizado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (atualizado_por);
ALTER TABLE plat.provedor_oidc DROP CONSTRAINT IF EXISTS provedor_oidc_criado_por_fkey;
ALTER TABLE plat.provedor_oidc DROP CONSTRAINT IF EXISTS provedor_oidc_tenant_criado_por_fkey;
ALTER TABLE plat.provedor_oidc ADD CONSTRAINT provedor_oidc_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.provedor_saml DROP CONSTRAINT IF EXISTS provedor_saml_atualizado_por_fkey;
ALTER TABLE plat.provedor_saml DROP CONSTRAINT IF EXISTS provedor_saml_tenant_atualizado_por_fkey;
ALTER TABLE plat.provedor_saml ADD CONSTRAINT provedor_saml_tenant_atualizado_por_fkey
  FOREIGN KEY (tenant_id, atualizado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (atualizado_por);
ALTER TABLE plat.provedor_saml DROP CONSTRAINT IF EXISTS provedor_saml_criado_por_fkey;
ALTER TABLE plat.provedor_saml DROP CONSTRAINT IF EXISTS provedor_saml_tenant_criado_por_fkey;
ALTER TABLE plat.provedor_saml ADD CONSTRAINT provedor_saml_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.provedor_sso DROP CONSTRAINT IF EXISTS provedor_sso_atualizado_por_fkey;
ALTER TABLE plat.provedor_sso DROP CONSTRAINT IF EXISTS provedor_sso_tenant_atualizado_por_fkey;
ALTER TABLE plat.provedor_sso ADD CONSTRAINT provedor_sso_tenant_atualizado_por_fkey
  FOREIGN KEY (tenant_id, atualizado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (atualizado_por);
ALTER TABLE plat.provedor_sso DROP CONSTRAINT IF EXISTS provedor_sso_criado_por_fkey;
ALTER TABLE plat.provedor_sso DROP CONSTRAINT IF EXISTS provedor_sso_tenant_criado_por_fkey;
ALTER TABLE plat.provedor_sso ADD CONSTRAINT provedor_sso_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_regra_fkey;
ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_tenant_regra_id_fkey;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_regra_id_fkey
  FOREIGN KEY (tenant_id, regra_id) REFERENCES plat.rede_regra (tenant_id, id) ON DELETE SET NULL (regra_id);
ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_regra_fkey;
ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_tenant_regra_id_fkey;
ALTER TABLE plat.rede_conexao ADD CONSTRAINT rede_conexao_tenant_regra_id_fkey
  FOREIGN KEY (tenant_id, regra_id) REFERENCES plat.rede_regra (tenant_id, id) ON DELETE SET NULL (regra_id);
ALTER TABLE plat.rede_config_tracado DROP CONSTRAINT IF EXISTS rede_config_tracado_dono_id_fkey;
ALTER TABLE plat.rede_config_tracado DROP CONSTRAINT IF EXISTS rede_config_tracado_tenant_dono_id_fkey;
ALTER TABLE plat.rede_config_tracado ADD CONSTRAINT rede_config_tracado_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.rede_controlador DROP CONSTRAINT IF EXISTS rede_controlador_criado_por_fkey;
ALTER TABLE plat.rede_controlador DROP CONSTRAINT IF EXISTS rede_controlador_tenant_criado_por_fkey;
ALTER TABLE plat.rede_controlador ADD CONSTRAINT rede_controlador_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.rede_feicao DROP CONSTRAINT IF EXISTS rede_feicao_criado_por_fkey;
ALTER TABLE plat.rede_feicao DROP CONSTRAINT IF EXISTS rede_feicao_tenant_criado_por_fkey;
ALTER TABLE plat.rede_feicao ADD CONSTRAINT rede_feicao_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.rede_feicao_ligacao DROP CONSTRAINT IF EXISTS rede_feicao_ligacao_de_feicao_id_fkey;
ALTER TABLE plat.rede_feicao_ligacao DROP CONSTRAINT IF EXISTS rede_feicao_ligacao_tenant_de_feicao_id_fkey;
ALTER TABLE plat.rede_feicao_ligacao ADD CONSTRAINT rede_feicao_ligacao_tenant_de_feicao_id_fkey
  FOREIGN KEY (tenant_id, de_feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_feicao_ligacao DROP CONSTRAINT IF EXISTS rede_feicao_ligacao_para_feicao_id_fkey;
ALTER TABLE plat.rede_feicao_ligacao DROP CONSTRAINT IF EXISTS rede_feicao_ligacao_tenant_para_feicao_id_fkey;
ALTER TABLE plat.rede_feicao_ligacao ADD CONSTRAINT rede_feicao_ligacao_tenant_para_feicao_id_fkey
  FOREIGN KEY (tenant_id, para_feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_feicao_ligacao DROP CONSTRAINT IF EXISTS rede_feicao_ligacao_rede_id_fkey;
ALTER TABLE plat.rede_feicao_ligacao DROP CONSTRAINT IF EXISTS rede_feicao_ligacao_tenant_rede_id_fkey;
ALTER TABLE plat.rede_feicao_ligacao ADD CONSTRAINT rede_feicao_ligacao_tenant_rede_id_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_importacao_epanet DROP CONSTRAINT IF EXISTS rede_importacao_epanet_criado_por_fkey;
ALTER TABLE plat.rede_importacao_epanet DROP CONSTRAINT IF EXISTS rede_importacao_epanet_tenant_criado_por_fkey;
ALTER TABLE plat.rede_importacao_epanet ADD CONSTRAINT rede_importacao_epanet_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.rede_medicao_ativo DROP CONSTRAINT IF EXISTS rede_medicao_ativo_atualizado_por_fkey;
ALTER TABLE plat.rede_medicao_ativo DROP CONSTRAINT IF EXISTS rede_medicao_ativo_tenant_atualizado_por_fkey;
ALTER TABLE plat.rede_medicao_ativo ADD CONSTRAINT rede_medicao_ativo_tenant_atualizado_por_fkey
  FOREIGN KEY (tenant_id, atualizado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.rede_tipo_restricao DROP CONSTRAINT IF EXISTS rede_tipo_restricao_rede_id_fkey;
ALTER TABLE plat.rede_tipo_restricao DROP CONSTRAINT IF EXISTS rede_tipo_restricao_tenant_rede_id_fkey;
ALTER TABLE plat.rede_tipo_restricao ADD CONSTRAINT rede_tipo_restricao_tenant_rede_id_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_tipo_restricao DROP CONSTRAINT IF EXISTS rede_tipo_restricao_tipo_id_fkey;
ALTER TABLE plat.rede_tipo_restricao DROP CONSTRAINT IF EXISTS rede_tipo_restricao_tenant_tipo_id_fkey;
ALTER TABLE plat.rede_tipo_restricao ADD CONSTRAINT rede_tipo_restricao_tenant_tipo_id_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_resumo DROP CONSTRAINT IF EXISTS rede_topo_resumo_construido_por_fkey;
ALTER TABLE plat.rede_topo_resumo DROP CONSTRAINT IF EXISTS rede_topo_resumo_tenant_construido_por_fkey;
ALTER TABLE plat.rede_topo_resumo ADD CONSTRAINT rede_topo_resumo_tenant_construido_por_fkey
  FOREIGN KEY (tenant_id, construido_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.rede_tracado_execucao DROP CONSTRAINT IF EXISTS rede_tracado_execucao_usuario_id_fkey;
ALTER TABLE plat.rede_tracado_execucao DROP CONSTRAINT IF EXISTS rede_tracado_execucao_tenant_usuario_id_fkey;
ALTER TABLE plat.rede_tracado_execucao ADD CONSTRAINT rede_tracado_execucao_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.rede_uc_consumo DROP CONSTRAINT IF EXISTS rede_uc_consumo_uc_id_fkey;
ALTER TABLE plat.rede_uc_consumo DROP CONSTRAINT IF EXISTS rede_uc_consumo_tenant_uc_id_fkey;
ALTER TABLE plat.rede_uc_consumo ADD CONSTRAINT rede_uc_consumo_tenant_uc_id_fkey
  FOREIGN KEY (tenant_id, uc_id) REFERENCES plat.rede_uc (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.relacionamento DROP CONSTRAINT IF EXISTS relacionamento_criado_por_fkey;
ALTER TABLE plat.relacionamento DROP CONSTRAINT IF EXISTS relacionamento_tenant_criado_por_fkey;
ALTER TABLE plat.relacionamento ADD CONSTRAINT relacionamento_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.relacionamento_junc DROP CONSTRAINT IF EXISTS relacionamento_junc_criado_por_fkey;
ALTER TABLE plat.relacionamento_junc DROP CONSTRAINT IF EXISTS relacionamento_junc_tenant_criado_por_fkey;
ALTER TABLE plat.relacionamento_junc ADD CONSTRAINT relacionamento_junc_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);
ALTER TABLE plat.replica DROP CONSTRAINT IF EXISTS replica_dono_id_fkey;
ALTER TABLE plat.replica DROP CONSTRAINT IF EXISTS replica_tenant_dono_id_fkey;
ALTER TABLE plat.replica ADD CONSTRAINT replica_tenant_dono_id_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.replica_camada DROP CONSTRAINT IF EXISTS replica_camada_replica_id_fkey;
ALTER TABLE plat.replica_camada DROP CONSTRAINT IF EXISTS replica_camada_tenant_replica_id_fkey;
ALTER TABLE plat.replica_camada ADD CONSTRAINT replica_camada_tenant_replica_id_fkey
  FOREIGN KEY (tenant_id, replica_id) REFERENCES plat.replica (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.replica_sincronizacao DROP CONSTRAINT IF EXISTS replica_sincronizacao_replica_id_fkey;
ALTER TABLE plat.replica_sincronizacao DROP CONSTRAINT IF EXISTS replica_sincronizacao_tenant_replica_id_fkey;
ALTER TABLE plat.replica_sincronizacao ADD CONSTRAINT replica_sincronizacao_tenant_replica_id_fkey
  FOREIGN KEY (tenant_id, replica_id) REFERENCES plat.replica (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.saml_sessao DROP CONSTRAINT IF EXISTS saml_sessao_provedor_id_fkey;
ALTER TABLE plat.saml_sessao DROP CONSTRAINT IF EXISTS saml_sessao_tenant_provedor_id_fkey;
ALTER TABLE plat.saml_sessao ADD CONSTRAINT saml_sessao_tenant_provedor_id_fkey
  FOREIGN KEY (tenant_id, provedor_id) REFERENCES plat.provedor_saml (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.saml_transacao DROP CONSTRAINT IF EXISTS saml_transacao_provedor_id_fkey;
ALTER TABLE plat.saml_transacao DROP CONSTRAINT IF EXISTS saml_transacao_tenant_provedor_id_fkey;
ALTER TABLE plat.saml_transacao ADD CONSTRAINT saml_transacao_tenant_provedor_id_fkey
  FOREIGN KEY (tenant_id, provedor_id) REFERENCES plat.provedor_saml (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.simbolo_upload DROP CONSTRAINT IF EXISTS simbolo_upload_criado_por_fkey;
ALTER TABLE plat.simbolo_upload DROP CONSTRAINT IF EXISTS simbolo_upload_tenant_criado_por_fkey;
ALTER TABLE plat.simbolo_upload ADD CONSTRAINT simbolo_upload_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.site_publicado DROP CONSTRAINT IF EXISTS site_publicado_item_id_fkey;
ALTER TABLE plat.site_publicado DROP CONSTRAINT IF EXISTS site_publicado_tenant_item_id_fkey;
ALTER TABLE plat.site_publicado ADD CONSTRAINT site_publicado_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.site_publicado DROP CONSTRAINT IF EXISTS site_publicado_publicado_por_fkey;
ALTER TABLE plat.site_publicado DROP CONSTRAINT IF EXISTS site_publicado_tenant_publicado_por_fkey;
ALTER TABLE plat.site_publicado ADD CONSTRAINT site_publicado_tenant_publicado_por_fkey
  FOREIGN KEY (tenant_id, publicado_por) REFERENCES plat.usuario (tenant_id, id);
ALTER TABLE plat.tabela_vista DROP CONSTRAINT IF EXISTS tabela_vista_item_id_fkey;
ALTER TABLE plat.tabela_vista DROP CONSTRAINT IF EXISTS tabela_vista_tenant_item_id_fkey;
ALTER TABLE plat.tabela_vista ADD CONSTRAINT tabela_vista_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.tabela_vista DROP CONSTRAINT IF EXISTS tabela_vista_usuario_id_fkey;
ALTER TABLE plat.tabela_vista DROP CONSTRAINT IF EXISTS tabela_vista_tenant_usuario_id_fkey;
ALTER TABLE plat.tabela_vista ADD CONSTRAINT tabela_vista_tenant_usuario_id_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.tile_leitura DROP CONSTRAINT IF EXISTS tile_leitura_token_id_fkey;
ALTER TABLE plat.tile_leitura DROP CONSTRAINT IF EXISTS tile_leitura_tenant_token_id_fkey;
ALTER TABLE plat.tile_leitura ADD CONSTRAINT tile_leitura_tenant_token_id_fkey
  FOREIGN KEY (tenant_id, token_id) REFERENCES plat.token_servico (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.versao DROP CONSTRAINT IF EXISTS versao_item_id_fkey;
ALTER TABLE plat.versao DROP CONSTRAINT IF EXISTS versao_tenant_item_id_fkey;
ALTER TABLE plat.versao ADD CONSTRAINT versao_tenant_item_id_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.versao DROP CONSTRAINT IF EXISTS versao_pai_fkey;
ALTER TABLE plat.versao DROP CONSTRAINT IF EXISTS versao_tenant_pai_fkey;
ALTER TABLE plat.versao ADD CONSTRAINT versao_tenant_pai_fkey
  FOREIGN KEY (tenant_id, pai) REFERENCES plat.versao (tenant_id, id) ON DELETE SET NULL (pai);
ALTER TABLE plat.versao_conflito DROP CONSTRAINT IF EXISTS versao_conflito_versao_id_fkey;
ALTER TABLE plat.versao_conflito DROP CONSTRAINT IF EXISTS versao_conflito_tenant_versao_id_fkey;
ALTER TABLE plat.versao_conflito ADD CONSTRAINT versao_conflito_tenant_versao_id_fkey
  FOREIGN KEY (tenant_id, versao_id) REFERENCES plat.versao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.widget_externo DROP CONSTRAINT IF EXISTS widget_externo_instalado_por_fkey;
ALTER TABLE plat.widget_externo DROP CONSTRAINT IF EXISTS widget_externo_tenant_instalado_por_fkey;
ALTER TABLE plat.widget_externo ADD CONSTRAINT widget_externo_tenant_instalado_por_fkey
  FOREIGN KEY (tenant_id, instalado_por) REFERENCES plat.usuario (tenant_id, id);

-- classe (b), fora do gerador (não composta de propósito — ver nota acima): chamado_comentario.autor_id
-- não tinha ON DELETE (RESTRICT implícito); ganha SET NULL, mesmo tratamento do precedente
-- 20260915T2349 (item.criado_por/apagado_por/modificado_por). Coluna já é NOT NULL... UNSET para
-- permitir o NULL do SET NULL (mesma receita de 016_catalogo_apagar_usuario.sql em compartilhamento_link).
ALTER TABLE plat.chamado_comentario ALTER COLUMN autor_id DROP NOT NULL;
ALTER TABLE plat.chamado_comentario DROP CONSTRAINT IF EXISTS chamado_comentario_autor_id_fkey;
ALTER TABLE plat.chamado_comentario ADD CONSTRAINT chamado_comentario_autor_id_fkey
  FOREIGN KEY (autor_id) REFERENCES plat.usuario (id) ON DELETE SET NULL;
