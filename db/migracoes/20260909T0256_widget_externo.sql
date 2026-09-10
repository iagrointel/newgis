-- 20260909T0256_widget_externo: item L5-36-widgets-personalizados-sdk. Registro de widget externo instalado
-- por inquilino (o "web/ext/<inquilino>/" da hipótese, na forma servível da plataforma: o código mora AQUI e
-- a rota GET /api/widgets/externos/{nome}/modulo.js o serve same-origin com a sessão; a origem fica na tabela,
-- e o sha256 conferido na instalação é reexigido pelo carregador do navegador). RLS por tenant_id como nas
-- outras tabelas do plat: um inquilino nunca lê, instala nem apaga widget de outro.
CREATE TABLE IF NOT EXISTS plat.widget_externo (
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  nome          text NOT NULL CHECK (nome ~ '^[a-z][a-z0-9-]{1,38}[a-z0-9]$'),
  versao        text NOT NULL CHECK (versao ~ '^\d+\.\d+\.\d+$'),
  api_widget    int NOT NULL,
  sandbox       boolean NOT NULL DEFAULT false,
  sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  manifesto     jsonb NOT NULL,
  modulo        text NOT NULL,
  i18n          jsonb,
  origem        text NOT NULL DEFAULT 'upload',
  instalado_por int REFERENCES plat.usuario(id),
  instalado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, nome)
);
ALTER TABLE plat.widget_externo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_widget_externo ON plat.widget_externo;
CREATE POLICY p_widget_externo ON plat.widget_externo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- tipos de evento da auditoria de widgets (a FK de plat.evento exige o tipo cadastrado)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('widgets/instalar',    'widget externo instalado ou atualizado pelo inquilino'),
  ('widgets/desinstalar', 'widget externo desinstalado pelo inquilino')
ON CONFLICT (nome) DO NOTHING;
