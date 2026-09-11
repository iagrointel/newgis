-- A migração 20260907T0245 criou `plat.camada_schema_prefixo()` — `d_` em produção e
-- `d_plat_t<trilha>_` numa instalação derivada — para impedir que uma trilha escreva no schema de dado
-- de outra (o defeito de raiz: 668 tabelas em `d_demo`, partilhado por todas as instalações).
--
-- Só que TREZE funções continuaram montando o nome à mão, como `'d_' || slug`. Em produção os dois
-- coincidem e ninguém percebe; numa instalação isolada a função cria `d_plat_tX_demo` e depois procura
-- `d_demo`, que está corretamente revogado. Resultado medido em 11/09/2026: `schema_sem_inquilino` e
-- `permission denied for schema d_demo` — falha segura, mas derruba ingestão, tiles, backup e medição
-- de uso de uma vez.
--
-- Esta migração reescreve, de forma reprodutível, toda função do schema que ainda tenha o literal.
-- Vale para instalação nova e para a que já existe. É idempotente: rodar de novo não acha nada.
-- ⚠ `camada_schema_prefixo` fica de fora de propósito: é ela que define o prefixo.
DO $$
-- ⚠ NÃO usar current_schema(): o aplicador roda com search_path largo e o laço acabava varrendo
-- funções de fora (erro real: "avg is an aggregate function"). O literal `plat` abaixo é
-- reescrito pelo tradutor da trilha para o schema da instalação, que é o padrão da casa.
DECLARE r record; def text; novo text; n int := 0; esquema text := 'plat';
BEGIN
  FOR r IN
    SELECT p.oid, p.proname
    FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = esquema
      -- `prokind='f'`: só função comum. `pg_get_functiondef` LEVANTA ERRO em agregação
      -- ("avg is an aggregate function") e em função de janela, e derruba a migração inteira.
      AND p.prokind = 'f'
      AND p.proname <> 'camada_schema_prefixo'
  LOOP
    -- ⚠ `pg_get_functiondef` fica AQUI, nunca no WHERE: no WHERE o planejador pode avaliá-la antes do
    -- filtro `prokind`, e ela LEVANTA ERRO em agregação ("avg is an aggregate function"), derrubando a
    -- migração inteira. Não há ordem de avaliação garantida em SQL. Medido em 11/09/2026.
    def := pg_get_functiondef(r.oid);
    IF def !~ '''d_''\s*\|\|' THEN
      CONTINUE;
    END IF;
    novo := regexp_replace(def, '''d_''(\s*\|\|)', esquema || '.camada_schema_prefixo()\1', 'g');
    IF novo <> def THEN
      EXECUTE novo;
      n := n + 1;
    END IF;
  END LOOP;
  RAISE NOTICE 'funcoes que passaram a usar camada_schema_prefixo(): %', n;
END $$;
