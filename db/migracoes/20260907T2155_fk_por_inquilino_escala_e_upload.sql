-- 20260907T2155_fk_por_inquilino_escala_e_upload: continuação de 20260906T1847_fk_por_inquilino_classe.
--
-- Aquela migração converteu 44 chaves estrangeiras simples em compostas (tenant_id, id) e deixou
-- escrito que as FKs apontando para tabelas ainda inexistentes na base ficariam para quem mesclasse
-- as trilhas correspondentes. As tabelas `plat.escala_*` (multiescala) e a FK `plat.upload.arquivo_id`
-- entraram em master depois, com FK simples, e a trava `tests/api/test_fk_composta_por_inquilino.py`
-- passou a acusar 19 casos. Esta migração fecha esses 19, com o MESMO ON DELETE de cada original
-- (lido de pg_constraint.confdeltype antes da troca: `c` = CASCADE nas ligações internas do
-- multiescala e em upload->item; NO ACTION nas três que apontam para usuario).
--
-- Idempotente: o UNIQUE confere pg_constraint antes de criar e cada FK é DROP IF EXISTS + ADD.

DO $$
DECLARE alvo text;
BEGIN
  FOREACH alvo IN ARRAY ARRAY['escala_conjunto', 'escala_grade', 'escala_fator', 'escala_celula',
                              'escala_execucao'] LOOP
    IF EXISTS (SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid = t.relnamespace
               WHERE n.nspname = 'plat' AND t.relname = alvo)
       AND NOT EXISTS (
      SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
      WHERE n.nspname = 'plat' AND t.relname = alvo AND c.conname = alvo || '_tenant_id_id_key'
    ) THEN
      EXECUTE format('ALTER TABLE plat.%I ADD CONSTRAINT %I UNIQUE (tenant_id, id)', alvo, alvo || '_tenant_id_id_key');
    END IF;
  END LOOP;
END $$;

-- ===== alvo: escala_fator =====
ALTER TABLE plat.escala_amostra DROP CONSTRAINT IF EXISTS escala_amostra_fator_id_fkey;
ALTER TABLE plat.escala_amostra DROP CONSTRAINT IF EXISTS escala_amostra_tenant_fator_fkey;
ALTER TABLE plat.escala_amostra ADD CONSTRAINT escala_amostra_tenant_fator_fkey
  FOREIGN KEY (tenant_id, fator_id) REFERENCES plat.escala_fator (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_bloco DROP CONSTRAINT IF EXISTS escala_bloco_fator_id_fkey;
ALTER TABLE plat.escala_bloco DROP CONSTRAINT IF EXISTS escala_bloco_tenant_fator_fkey;
ALTER TABLE plat.escala_bloco ADD CONSTRAINT escala_bloco_tenant_fator_fkey
  FOREIGN KEY (tenant_id, fator_id) REFERENCES plat.escala_fator (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_execucao_fator DROP CONSTRAINT IF EXISTS escala_execucao_fator_fator_id_fkey;
ALTER TABLE plat.escala_execucao_fator DROP CONSTRAINT IF EXISTS escala_execucao_fator_tenant_fator_fkey;
ALTER TABLE plat.escala_execucao_fator ADD CONSTRAINT escala_execucao_fator_tenant_fator_fkey
  FOREIGN KEY (tenant_id, fator_id) REFERENCES plat.escala_fator (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_fator_celula DROP CONSTRAINT IF EXISTS escala_fator_celula_fator_id_fkey;
ALTER TABLE plat.escala_fator_celula DROP CONSTRAINT IF EXISTS escala_fator_celula_tenant_fator_fkey;
ALTER TABLE plat.escala_fator_celula ADD CONSTRAINT escala_fator_celula_tenant_fator_fkey
  FOREIGN KEY (tenant_id, fator_id) REFERENCES plat.escala_fator (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: escala_grade =====
ALTER TABLE plat.escala_celula DROP CONSTRAINT IF EXISTS escala_celula_grade_id_fkey;
ALTER TABLE plat.escala_celula DROP CONSTRAINT IF EXISTS escala_celula_tenant_grade_fkey;
ALTER TABLE plat.escala_celula ADD CONSTRAINT escala_celula_tenant_grade_fkey
  FOREIGN KEY (tenant_id, grade_id) REFERENCES plat.escala_grade (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_grade_id_fkey;
ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_tenant_grade_fkey;
ALTER TABLE plat.escala_execucao ADD CONSTRAINT escala_execucao_tenant_grade_fkey
  FOREIGN KEY (tenant_id, grade_id) REFERENCES plat.escala_grade (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_grade DROP CONSTRAINT IF EXISTS escala_grade_grade_pai_id_fkey;
ALTER TABLE plat.escala_grade DROP CONSTRAINT IF EXISTS escala_grade_tenant_grade_pai_fkey;
ALTER TABLE plat.escala_grade ADD CONSTRAINT escala_grade_tenant_grade_pai_fkey
  FOREIGN KEY (tenant_id, grade_pai_id) REFERENCES plat.escala_grade (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: escala_conjunto =====
ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_conjunto_id_fkey;
ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_tenant_conjunto_fkey;
ALTER TABLE plat.escala_execucao ADD CONSTRAINT escala_execucao_tenant_conjunto_fkey
  FOREIGN KEY (tenant_id, conjunto_id) REFERENCES plat.escala_conjunto (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_grade DROP CONSTRAINT IF EXISTS escala_grade_conjunto_id_fkey;
ALTER TABLE plat.escala_grade DROP CONSTRAINT IF EXISTS escala_grade_tenant_conjunto_fkey;
ALTER TABLE plat.escala_grade ADD CONSTRAINT escala_grade_tenant_conjunto_fkey
  FOREIGN KEY (tenant_id, conjunto_id) REFERENCES plat.escala_conjunto (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: escala_celula =====
ALTER TABLE plat.escala_fator_celula DROP CONSTRAINT IF EXISTS escala_fator_celula_celula_id_fkey;
ALTER TABLE plat.escala_fator_celula DROP CONSTRAINT IF EXISTS escala_fator_celula_tenant_celula_fkey;
ALTER TABLE plat.escala_fator_celula ADD CONSTRAINT escala_fator_celula_tenant_celula_fkey
  FOREIGN KEY (tenant_id, celula_id) REFERENCES plat.escala_celula (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_resultado DROP CONSTRAINT IF EXISTS escala_resultado_celula_id_fkey;
ALTER TABLE plat.escala_resultado DROP CONSTRAINT IF EXISTS escala_resultado_tenant_celula_fkey;
ALTER TABLE plat.escala_resultado ADD CONSTRAINT escala_resultado_tenant_celula_fkey
  FOREIGN KEY (tenant_id, celula_id) REFERENCES plat.escala_celula (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: escala_execucao =====
ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_execucao_pai_id_fkey;
ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_tenant_execucao_pai_fkey;
ALTER TABLE plat.escala_execucao ADD CONSTRAINT escala_execucao_tenant_execucao_pai_fkey
  FOREIGN KEY (tenant_id, execucao_pai_id) REFERENCES plat.escala_execucao (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_execucao_fator DROP CONSTRAINT IF EXISTS escala_execucao_fator_execucao_id_fkey;
ALTER TABLE plat.escala_execucao_fator DROP CONSTRAINT IF EXISTS escala_execucao_fator_tenant_execucao_fkey;
ALTER TABLE plat.escala_execucao_fator ADD CONSTRAINT escala_execucao_fator_tenant_execucao_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.escala_execucao (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_fator_celula DROP CONSTRAINT IF EXISTS escala_fator_celula_execucao_id_fkey;
ALTER TABLE plat.escala_fator_celula DROP CONSTRAINT IF EXISTS escala_fator_celula_tenant_execucao_fkey;
ALTER TABLE plat.escala_fator_celula ADD CONSTRAINT escala_fator_celula_tenant_execucao_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.escala_execucao (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.escala_resultado DROP CONSTRAINT IF EXISTS escala_resultado_execucao_id_fkey;
ALTER TABLE plat.escala_resultado DROP CONSTRAINT IF EXISTS escala_resultado_tenant_execucao_fkey;
ALTER TABLE plat.escala_resultado ADD CONSTRAINT escala_resultado_tenant_execucao_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.escala_execucao (tenant_id, id) ON DELETE CASCADE;

-- ===== alvo: usuario =====
ALTER TABLE plat.escala_conjunto DROP CONSTRAINT IF EXISTS escala_conjunto_dono_id_fkey;
ALTER TABLE plat.escala_conjunto DROP CONSTRAINT IF EXISTS escala_conjunto_tenant_dono_fkey;
ALTER TABLE plat.escala_conjunto ADD CONSTRAINT escala_conjunto_tenant_dono_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_dono_id_fkey;
ALTER TABLE plat.escala_execucao DROP CONSTRAINT IF EXISTS escala_execucao_tenant_dono_fkey;
ALTER TABLE plat.escala_execucao ADD CONSTRAINT escala_execucao_tenant_dono_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);

ALTER TABLE plat.escala_fator DROP CONSTRAINT IF EXISTS escala_fator_dono_id_fkey;
ALTER TABLE plat.escala_fator DROP CONSTRAINT IF EXISTS escala_fator_tenant_dono_fkey;
ALTER TABLE plat.escala_fator ADD CONSTRAINT escala_fator_tenant_dono_fkey
  FOREIGN KEY (tenant_id, dono_id) REFERENCES plat.usuario (tenant_id, id);

-- ===== alvo: item =====
ALTER TABLE plat.upload DROP CONSTRAINT IF EXISTS upload_arquivo_id_fkey;
ALTER TABLE plat.upload DROP CONSTRAINT IF EXISTS upload_tenant_arquivo_fkey;
ALTER TABLE plat.upload ADD CONSTRAINT upload_tenant_arquivo_fkey
  FOREIGN KEY (tenant_id, arquivo_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;
