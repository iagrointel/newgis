-- 001_fundacao: schema plat, role plat_app (sem senha: o install.sh faz ALTER ROLE), grants, privilégios
-- padrão, tabela de controle de migrações e funções de contexto (ADR 0001 seções 3.1, 3.3 e 5).
-- Idempotente. Aplicada como postgres pelo db/migrar.sh. Sem BEGIN/COMMIT: o aplicador abre a transação.

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plat_app') THEN
    CREATE ROLE plat_app LOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS plat AUTHORIZATION postgres;

CREATE TABLE IF NOT EXISTS plat.versao_migracao (
  nome         text PRIMARY KEY,
  sha256       text NOT NULL,
  aplicada_em  timestamptz NOT NULL DEFAULT now(),
  duracao_ms   int NOT NULL,
  aplicada_por text NOT NULL DEFAULT current_user
);

CREATE OR REPLACE FUNCTION plat.tenant_atual() RETURNS int LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('plat.tenant_id', true), '')::int $$;
CREATE OR REPLACE FUNCTION plat.usuario_atual() RETURNS int LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('plat.usuario_id', true), '')::int $$;

GRANT USAGE ON SCHEMA plat TO plat_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA plat TO plat_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA plat TO plat_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO plat_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT USAGE, SELECT ON SEQUENCES TO plat_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT EXECUTE ON FUNCTIONS TO plat_app;

-- a tabela de controle é só leitura para a aplicação: quem escreve é o aplicador, como postgres
REVOKE INSERT, UPDATE, DELETE ON plat.versao_migracao FROM plat_app;
