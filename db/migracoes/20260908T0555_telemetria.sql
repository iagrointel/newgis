-- 20260908T0555_telemetria: telemetria OPCIONAL do appliance (item L7-11-c-telemetria-opcional; L7_CONCEITO C13
-- "telemetria opt-in, desligada por padrão, só agregados, texto do que sai mostrado antes de ligar").
--
-- plat.telemetria: UMA linha por instalação (id = 1), desligada por padrão. `chave` é a identidade do appliance
-- (gerada aqui, nunca digitada), `ultimo_relatorio` é o JSON exatamente como foi enviado da última vez.
-- plat.telemetria_appliance: o lado RECEPTOR (a instalação da casa): chaves de appliance conhecidas e o último
-- relatório recebido de cada uma; chave desconhecida é recusada pela rota, nunca gravada.
-- Tabelas de instalação (não de inquilino): sem tenant_id, sem RLS; escrita só por sessão de superadmin (rota).
-- Idempotente. Sem BEGIN/COMMIT.
CREATE TABLE IF NOT EXISTS plat.telemetria (
  id                 int PRIMARY KEY CHECK (id = 1),
  ligada             boolean NOT NULL DEFAULT false,
  chave              text NOT NULL,
  nome_instalacao    text,
  ligada_por         text,
  ligada_em          timestamptz,
  ultimo_envio_em    timestamptz,
  ultimo_envio_ok    boolean,
  ultimo_envio_msg   text,
  ultimo_relatorio   jsonb,
  atualizado_em      timestamptz NOT NULL DEFAULT now()
);
INSERT INTO plat.telemetria (id, ligada, chave) VALUES (1, false, encode(gen_random_bytes(24), 'hex'))
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS plat.telemetria_appliance (
  chave              text PRIMARY KEY,
  nome               text NOT NULL,
  registrado_em      timestamptz NOT NULL DEFAULT now(),
  ultimo_recebido_em timestamptz,
  ultimo_relatorio   jsonb,
  recebidos          int NOT NULL DEFAULT 0
);

GRANT SELECT, UPDATE ON plat.telemetria TO plat_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.telemetria_appliance TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('telemetria/ligar', 'telemetria do appliance ligada pelo superadmin (opt-in explícito)'),
  ('telemetria/desligar', 'telemetria do appliance desligada'),
  ('telemetria/enviar', 'relatório diário de telemetria enviado (ou tentativa registrada)'),
  ('telemetria/receber', 'relatório de telemetria recebido de um appliance com chave conhecida')
ON CONFLICT (nome) DO NOTHING;

-- contagens AGREGADAS da instalação inteira (nunca uma linha, nunca um nome): é só o que a telemetria manda.
-- SECURITY DEFINER porque plat_app vê só o próprio inquilino pela RLS; a função devolve números, não dados.
CREATE OR REPLACE FUNCTION plat.telemetria_contagens() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT jsonb_build_object(
    'inquilinos', (SELECT count(*) FROM plat.tenant WHERE ativo),
    'usuarios',   (SELECT count(*) FROM plat.usuario WHERE ativo),
    'itens',      (SELECT count(*) FROM plat.item WHERE apagado_em IS NULL),
    'camadas',    (SELECT count(*) FROM plat.item WHERE apagado_em IS NULL AND tipo = 'camada_vetorial'),
    'jobs_24h',   (SELECT count(*) FROM plat.job WHERE criado_em > now() - interval '24 hours'),
    'gb_arquivos', round(coalesce((SELECT sum(bytes) FROM plat.arquivo WHERE apagado_em IS NULL), 0) / 1073741824.0, 3)
  );
$$;
REVOKE ALL ON FUNCTION plat.telemetria_contagens() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.telemetria_contagens() TO plat_app;
