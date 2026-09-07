-- limite_taxa: camada 2 (API por token/inquilino) do item L7-03-b-rate-limit-abuso. Janela DESLIZANTE
-- (mesmo desenho de plat.redefinicao_pedido/plat.redefinicao_solicitar da migração 047: uma linha por
-- pedido, COUNT sobre os últimos N segundos), não janela fixa — evita a rajada dobrada na borda de um
-- minuto que uma janela fixa permitiria. `chave` identifica QUEM está sendo limitado (hoje:
-- "tenant:<id>" para o limite por inquilino/plano, ADR desta trilha seção 3); `escopo` identifica QUAL
-- limite ("api", "tiles", ...), porque o mesmo inquilino tem tetos diferentes por escopo (limites.py).
-- Só a função SECURITY DEFINER lê/grava; plat_app não recebe privilégio direto na tabela (mesmo padrão
-- de plat.redefinicao_pedido) — ninguém além da função pode inflar ou zerar o próprio contador.
CREATE TABLE IF NOT EXISTS plat.limite_taxa_pedido (
  id          bigserial PRIMARY KEY,
  chave       text NOT NULL,
  escopo      text NOT NULL,
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_limite_taxa_pedido_chave_escopo_em
  ON plat.limite_taxa_pedido (chave, escopo, criado_em DESC);

ALTER TABLE plat.limite_taxa_pedido ENABLE ROW LEVEL SECURITY;
-- sem policy: ninguém além do dono (postgres/SECURITY DEFINER) lê ou grava linha nesta tabela — mesmo
-- espírito de plat.redefinicao_pedido, mas aqui nem RLS por tenant faria sentido: uma requisição de
-- IP ainda sem inquilino resolvido (camada 1) também pode usar esta tabela no futuro (escopo "pre_auth").
REVOKE ALL ON plat.limite_taxa_pedido FROM plat_app;
REVOKE ALL ON plat.limite_taxa_pedido FROM PUBLIC;

-- plat.limite_taxa_verificar: incrementa e decide em UMA operação. O comentário original desta função
-- dizia que SELECT+INSERT "dentro da mesma transação curta" bastava para nunca abrir corrida — ERRADO,
-- achado pelo adversário do turno (refutação real, ver laco/handoffs/T5/L7-03-b-rate-limit-abuso.md):
-- sob READ COMMITTED (padrão do Postgres) duas transações concorrentes fazem o MESMO SELECT count()
-- (nenhuma ainda viu o INSERT da outra, que só aparece depois do commit), as duas passam pelo `IF n >=
-- p_max`, e as duas inserem — o teto configurado é ultrapassado. MEDIDO pelo adversário: com pool de 2
-- conexões, teto 20 furado para 21 em 2 de 3 rodadas; com pool de 8, furado para 23 em 1 de 5.
-- Conserto: `pg_advisory_xact_lock` na chave (chave, escopo), travado ANTES do SELECT e liberado
-- automaticamente no fim da transação (a mesma transação curta de `with db.db()`, ver app/db.py) —
-- serializa toda chamada concorrente para a MESMA (chave, escopo), sem lock de tabela nem de linha (uma
-- chave nova, sem linha ainda, não tem o que travar por FOR UPDATE). Chamadas de (chave, escopo)
-- DIFERENTES nunca se bloqueiam entre si (hash de 64 bits, hashtextextended, colisão desprezível e sem
-- consequência real — na pior hipótese duas chaves diferentes serializam à toa por um instante, nunca
-- erram o teto). Faxina oportunista (achado da própria implementação, mesmo truque usado alhures na
-- casa para não precisar de um job periódico novo: 1 em 200 chamadas apaga o que já saiu de TODAS as
-- janelas prováveis, 1 dia de folga) evita que a tabela cresça sem limite.
CREATE OR REPLACE FUNCTION plat.limite_taxa_verificar(p_chave text, p_escopo text, p_janela_s int, p_max int)
RETURNS TABLE (permitido boolean, restante int, expira_em timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; mais_antigo timestamptz;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_chave || '|' || p_escopo, 0));
  IF random() < 0.005 THEN
    DELETE FROM plat.limite_taxa_pedido WHERE criado_em < now() - interval '1 day';
  END IF;
  SELECT count(*), min(criado_em) INTO n, mais_antigo FROM plat.limite_taxa_pedido
    WHERE chave = p_chave AND escopo = p_escopo AND criado_em > now() - make_interval(secs => p_janela_s);
  IF n >= p_max THEN
    RETURN QUERY SELECT false, 0, coalesce(mais_antigo, now()) + make_interval(secs => p_janela_s);
    RETURN;
  END IF;
  INSERT INTO plat.limite_taxa_pedido(chave, escopo) VALUES (p_chave, p_escopo);
  RETURN QUERY SELECT true, greatest(p_max - n - 1, 0), now() + make_interval(secs => p_janela_s);
END $$;

-- plat.limite_taxa_contagem: só para teste/observabilidade (o adversário confere sem reimplementar a
-- janela em Python); não é usada pelo caminho de decisão acima.
CREATE OR REPLACE FUNCTION plat.limite_taxa_contagem(p_chave text, p_escopo text, p_janela_s int)
RETURNS int LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(*)::int FROM plat.limite_taxa_pedido
    WHERE chave = p_chave AND escopo = p_escopo AND criado_em > now() - make_interval(secs => p_janela_s);
$$;
