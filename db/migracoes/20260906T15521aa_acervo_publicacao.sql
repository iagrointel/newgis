-- 20260906T15521aa_acervo_publicacao: publicação SEM CÓPIA das camadas do acervo da casa
-- (item L6-01-b-view-so-leitura; depende de 027_acervo_camada.sql, item L6-01-a-registro, ENTREGUE).
--
-- O que este arquivo cria: o schema `plat_acervo` onde moram as views publicadas, o papel dono dessas views
-- (`plat_acervo_publicador`), a tabela de ASSINATURA por inquilino, a função de porteiro
-- `plat.acervo_pode_ler(camada)` que entra no WHERE de cada view, e o registro do que foi publicado
-- (`plat.acervo_publicacao`, escrito por scripts/acervo_publicar.py, que roda como postgres).
-- As views em si NÃO são criadas aqui: são derivadas da lista branca de colunas de `plat.acervo_camada`, que
-- muda a cada varredura da casa; quem as cria é o script.
--
-- REFUTAÇÃO REGISTRADA (medida em 06/09/2026, não opinião): a hipótese do item pedia view
-- `SECURITY INVOKER`. `SECURITY INVOKER` faz o Postgres checar o privilégio da TABELA DE BASE contra quem
-- chama (plat_app); o mesmo portão do item proíbe qualquer GRANT direto de tabela `public` a plat_app. As
-- duas cláusulas não podem valer juntas. Medido:
--   CREATE VIEW ... WITH (security_invoker = true) sobre public.car_area_imovel, GRANT SELECT da view a
--   plat_app  ->  SET ROLE plat_app; SELECT ... = ERROR: permission denied for table car_area_imovel.
-- Portanto a view fica no modo PADRÃO (security definer): o privilégio da tabela de base é o do DONO da view,
-- `plat_acervo_publicador`, que recebe SELECT só nas tabelas efetivamente publicadas. plat_app não ganha nada
-- em `public` — é exatamente o que a cláusula "nenhuma tabela public tem GRANT direto a plat_app" quer.
--
-- SEGUNDA MEDIDA, sobre `security_barrier`: a proteção clássica de view definer é WITH (security_barrier =
-- true), que impede o qual do usuário de descer abaixo do qual da view. Medido nesta base: com barrier, o
-- operador `&&` de geometria (pg_proc.proleakproof = false, conferido) deixa de descer até o índice GiST e a
-- consulta de mapa vira varredura sequencial das 7,36 mi de linhas — cancelada depois de 2 min 10 s, contra
-- 3,0 ms sem barrier. Barrier e o portão de "≤ 100 ms" são incompatíveis nesta consulta.
-- O que substitui a barreira, e é mais forte aqui: o porteiro `plat.acervo_pode_ler('<camada>')` recebe um
-- ARGUMENTO CONSTANTE e não referencia nenhuma coluna, então o planejador o transforma em `One-Time Filter` —
-- avaliado UMA vez, ANTES de a varredura começar. Medido no plano: com o porteiro falso o nó do índice sai
-- como `(never executed)`, 0 linha, 0,046 ms. Não existe linha para vazar por qual malicioso porque nenhuma
-- linha chega a ser lida. Fica anotado como limite honesto: se um dia o porteiro passar a depender de coluna
-- (por exemplo assinatura por UF), ele deixa de ser One-Time Filter e esta análise tem de ser refeita.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- 1. papel dono das views publicadas. NOLOGIN: ninguém se conecta com ele; ele existe só para ser o dono da
-- view (é o privilégio dele que a view definer usa na tabela de base) e para que o raio de exposição seja
-- exatamente o conjunto de tabelas publicadas, nunca "tudo que o postgres enxerga".
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plat_acervo_publicador') THEN
    CREATE ROLE plat_acervo_publicador NOLOGIN;
  END IF;
END $$;

-- 2. schema das views. CREATE fica só com o postgres: plat_app lê e nada mais.
CREATE SCHEMA IF NOT EXISTS plat_acervo AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA plat_acervo FROM PUBLIC;
GRANT USAGE ON SCHEMA plat_acervo TO plat_app;
GRANT USAGE ON SCHEMA plat_acervo TO plat_acervo_publicador;
COMMENT ON SCHEMA plat_acervo IS
  'Views de publicação sem cópia do acervo da casa (item L6-01-b). Uma view por camada exposta, dona '
  'plat_acervo_publicador, lista branca de colunas de plat.acervo_camada, porteiro plat.acervo_pode_ler no '
  'WHERE. Criadas por scripts/acervo_publicar.py (roda como postgres), nunca por migração.';

-- 3. assinatura por inquilino: sem linha aqui, a view devolve zero linha e a API devolve 403.
CREATE TABLE IF NOT EXISTS plat.acervo_assinatura (
  tenant_id        int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  acervo_camada_id text NOT NULL REFERENCES plat.acervo_camada(acervo_camada_id) ON DELETE CASCADE,
  assinado_em      timestamptz NOT NULL DEFAULT now(),
  assinado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  PRIMARY KEY (tenant_id, acervo_camada_id)
);
CREATE INDEX IF NOT EXISTS ix_acervo_assinatura_camada ON plat.acervo_assinatura (acervo_camada_id);

ALTER TABLE plat.acervo_assinatura ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_acervo_assinatura_ler ON plat.acervo_assinatura;
CREATE POLICY p_acervo_assinatura_ler ON plat.acervo_assinatura FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_acervo_assinatura_inserir ON plat.acervo_assinatura;
CREATE POLICY p_acervo_assinatura_inserir ON plat.acervo_assinatura FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_acervo_assinatura_apagar ON plat.acervo_assinatura;
CREATE POLICY p_acervo_assinatura_apagar ON plat.acervo_assinatura FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual());
-- sem policy de UPDATE de propósito: assinatura se cria ou se cancela, não se edita.
GRANT SELECT, INSERT, DELETE ON plat.acervo_assinatura TO plat_app;
REVOKE UPDATE ON plat.acervo_assinatura FROM plat_app;

-- 4. porteiro. SECURITY DEFINER porque ele é chamado de dentro da view por plat_app, e plat_app não pode
-- depender de RLS aqui: a função faz o recorte por inquilino ELA MESMA, lendo o mesmo GUC que a RLS do resto
-- da plataforma usa (plat.tenant_id, posto por app/db.py a cada transação). search_path fixo (higiene de
-- SECURITY DEFINER: sem isto quem chama poderia trocar o significado de `plat.`).
CREATE OR REPLACE FUNCTION plat.acervo_pode_ler(camada text) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, pg_temp AS
$$
  SELECT EXISTS (
    SELECT 1 FROM plat.acervo_assinatura a
    WHERE a.acervo_camada_id = camada
      AND a.tenant_id = NULLIF(current_setting('plat.tenant_id', true), '')::int
  )
$$;
COMMENT ON FUNCTION plat.acervo_pode_ler(text) IS
  'Porteiro das views de plat_acervo (item L6-01-b): verdadeiro só quando o inquilino da sessão assina a '
  'camada. Recebe argumento constante e não olha coluna nenhuma — por isso vira One-Time Filter no plano e a '
  'tabela de base nem chega a ser varrida quando é falso.';
REVOKE ALL ON FUNCTION plat.acervo_pode_ler(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.acervo_pode_ler(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_pode_ler(text) TO plat_acervo_publicador;

-- 5. registro do que está publicado (uma linha por view). Escrito por scripts/acervo_publicar.py como
-- postgres; plat_app só lê — mesmo padrão de plat.acervo_camada (027) e plat.acervo_licenca (043).
CREATE TABLE IF NOT EXISTS plat.acervo_publicacao (
  acervo_camada_id text PRIMARY KEY REFERENCES plat.acervo_camada(acervo_camada_id) ON DELETE CASCADE,
  view_nome        text NOT NULL UNIQUE,          -- nome dentro de plat_acervo, derivado do id da camada
  schema_origem    text NOT NULL,
  tabela_origem    text NOT NULL,
  coluna_geom      text NOT NULL,
  srid             int  NOT NULL,
  colunas          text[] NOT NULL,               -- exatamente as colunas da view, na ordem
  security_invoker boolean NOT NULL,              -- sempre falso: ver a refutação no topo deste arquivo
  security_barrier boolean NOT NULL,              -- sempre falso: ver a segunda medida no topo
  publicado_em     timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT ON plat.acervo_publicacao TO plat_app;
REVOKE INSERT, UPDATE, DELETE ON plat.acervo_publicacao FROM plat_app;

-- 6. vocabulário de evento (plat.evento.tipo tem FK para plat.evento_tipo)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('acervo/assinar',  'POST /api/acervo/camadas/{id}/assinatura — inquilino passa a poder ler a camada'),
  ('acervo/cancelar', 'DELETE /api/acervo/camadas/{id}/assinatura — inquilino deixa de poder ler a camada')
ON CONFLICT (nome) DO NOTHING;
