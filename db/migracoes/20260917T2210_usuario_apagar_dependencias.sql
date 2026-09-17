-- 20260917T2210_usuario_apagar_dependencias — apagar usuário com as dependências resolvidas (ensaio da união).
--
-- O DEFEITO, medido em 17/09/2026 no ensaio de migrações (laco/ENSAIO_MIGRACOES_20260917.md):
-- `install.sh` (bloco de resíduo zt-*), `laco/trilha_ambiente.sh` (passo "d. ambiente de teste + admins
-- semeados") e `db/homolog_bootstrap.sh` terminam a limpeza com
--     DELETE FROM plat.usuario WHERE login LIKE 'zt%';
-- Isso funcionava quando 16 tabelas apontavam para `plat.usuario` sem cascata. Depois da união são 59, e o
-- comando passou a parar com
--     update or delete on table "usuario" violates foreign key constraint "job_tenant_usuario_fkey"
--     update or delete on table "usuario" violates foreign key constraint "exportacao_usuario_id_fkey"
-- porque o usuário de teste pertence a um inquilino que NÃO é zt-* (demo/demo2) e por isso não foi apagado
-- por `plat.tenant_apagar_interno`; a linha filha (job, exportação) sobrevive e trava o DELETE.
--
-- POR QUE UMA FUNÇÃO E NÃO 59 `ON DELETE CASCADE`: pôr cascata nessas 59 chaves mudaria o comportamento de
-- PRODUÇÃO — apagar um usuário passaria a apagar silenciosamente os jobs, exportações, chamados e anotações
-- dele. A recusa do banco é a proteção certa para o dado real. O que faltava era um caminho EXPLÍCITO para
-- quem quer mesmo remover um usuário e as suas pontas soltas. Mesmo desenho já usado em
-- `plat.tenant_apagar_interno`: varredura do catálogo, em passes, com a ordem de FK fechando sozinha.
--
-- REGRA DE DESTRUIÇÃO MÍNIMA: coluna que aceita NULL vira NULL (a linha de negócio fica, perde o autor);
-- coluna NOT NULL obriga a apagar a linha filha. Chave composta (tenant_id, usuario_id) -> (tenant_id, id)
-- é resolvida pela posição de `id` em confkey, nunca pelo nome da coluna.
--
-- ⚠ NÃO é para uso da aplicação: `plat_app` não recebe EXECUTE (o admin de um inquilino apagaria a trilha
-- de outro pelo API). Só postgres, como em tenant_apagar_interno.

CREATE OR REPLACE FUNCTION plat.usuario_apagar_interno(p_ids int[]) RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
  r record; passo int; restantes int; total int := 0; n int;
BEGIN
  IF p_ids IS NULL OR cardinality(p_ids) = 0 THEN RETURN 0; END IF;

  -- auto-referência do próprio usuário (papel) e quem o convidou: resolvidas antes da varredura
  UPDATE plat.usuario SET papel_id = NULL WHERE id = ANY(p_ids) AND papel_id IS NOT NULL;

  -- o gatilho do último admin recusaria apagar o admin de um inquilino que continua existindo; desligado só
  -- aqui, na mesma transação (DDL transacional: volta sozinho se algo falhar). Nunca por GUC.
  ALTER TABLE plat.usuario DISABLE TRIGGER usuario_ultimo_admin;

  FOR passo IN 1..6 LOOP
    restantes := 0;
    FOR r IN
      SELECT c.conname,
             cl.relname AS tabela,
             a.attname  AS coluna,
             a.attnotnull AS obrigatoria
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
        -- posição de `id` entre as colunas referenciadas; a coluna de origem é a da MESMA posição
        JOIN LATERAL (
          SELECT c.conkey[i] AS attnum
            FROM generate_subscripts(c.confkey, 1) i
           WHERE c.confkey[i] = (SELECT attnum FROM pg_attribute
                                  WHERE attrelid = 'plat.usuario'::regclass AND attname = 'id')
        ) pos ON true
        JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attnum = pos.attnum
       WHERE c.contype = 'f'
         AND c.confrelid = 'plat.usuario'::regclass
         AND n.nspname = 'plat'
         AND cl.relkind IN ('r', 'p')
         AND cl.relname <> 'usuario'
         -- partição não é apagada pelo nome: o pai responde por ela
         AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = cl.oid)
       ORDER BY cl.relname, a.attname
    LOOP
      BEGIN
        IF r.obrigatoria THEN
          EXECUTE format('DELETE FROM plat.%I WHERE %I = ANY($1)', r.tabela, r.coluna) USING p_ids;
        ELSE
          EXECUTE format('UPDATE plat.%I SET %I = NULL WHERE %I = ANY($1)', r.tabela, r.coluna, r.coluna)
            USING p_ids;
        END IF;
        GET DIAGNOSTICS n = ROW_COUNT;
        total := total + n;
      EXCEPTION WHEN foreign_key_violation THEN
        -- filha da filha ainda presente; fecha no próximo passe
        restantes := restantes + 1;
      END;
    END LOOP;
    EXIT WHEN restantes = 0;
  END LOOP;

  IF restantes > 0 THEN
    ALTER TABLE plat.usuario ENABLE TRIGGER usuario_ultimo_admin;
    RAISE EXCEPTION 'usuario_com_dependencias' USING
      DETAIL = format('%s chave(s) estrangeira(s) ainda apontando para os usuários %s', restantes, p_ids);
  END IF;

  DELETE FROM plat.usuario WHERE id = ANY(p_ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  ALTER TABLE plat.usuario ENABLE TRIGGER usuario_ultimo_admin;
  RETURN n;
END $$;

COMMENT ON FUNCTION plat.usuario_apagar_interno(int[]) IS
  'Apaga usuários resolvendo antes as dependências: coluna que aceita NULL vira NULL, coluna NOT NULL apaga a linha filha. Uso de instalação/limpeza (postgres), nunca da aplicação.';

REVOKE EXECUTE ON FUNCTION plat.usuario_apagar_interno(int[]) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.usuario_apagar_interno(int[]) FROM plat_app;

-- ---------------------------------------------------------------- envoltório por padrão de login
-- ⚠ Medido no ensaio: chamar a função acima com uma subconsulta sobre a própria tabela —
--     SELECT plat.usuario_apagar_interno(array(SELECT id FROM plat.usuario WHERE login LIKE 'zt%'))
-- falha com "cannot ALTER TABLE usuario because it is being used by active queries in this session":
-- a varredura do SELECT externo ainda está aberta quando a função tenta desligar o gatilho. Os ids têm de
-- ser materializados ANTES da chamada. Este envoltório faz isso e é o que os scripts devem usar.
CREATE OR REPLACE FUNCTION plat.usuario_apagar_por_login(p_padrao text) RETURNS int
LANGUAGE plpgsql AS $$
DECLARE ids int[];
BEGIN
  IF p_padrao IS NULL OR btrim(p_padrao) = '' OR p_padrao = '%' THEN
    RAISE EXCEPTION 'padrao_de_login_vazio' USING
      DETAIL = 'apagar por "%" removeria todos os usuários da instalação';
  END IF;
  SELECT array_agg(id) INTO ids FROM plat.usuario WHERE login LIKE p_padrao;
  RETURN plat.usuario_apagar_interno(coalesce(ids, '{}'::int[]));
END $$;

COMMENT ON FUNCTION plat.usuario_apagar_por_login(text) IS
  'Apaga os usuários cujo login casa com o padrão, resolvendo antes as dependências. Recusa padrão vazio ou "%". Uso de instalação/limpeza (postgres), nunca da aplicação.';

REVOKE EXECUTE ON FUNCTION plat.usuario_apagar_por_login(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.usuario_apagar_por_login(text) FROM plat_app;
