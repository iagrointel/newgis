-- item L5-37-pacotes-modelos-entre-inquilinos: galeria de modelos. O PACOTE em si (zip com os documentos
-- JSON, os estilos e as dependências declaradas, sem dado) é montado e lido em Python
-- (app/catalogo/pacote.py) e nunca precisa de tabela: exportar é um GET que devolve bytes e importar é um
-- POST que cria itens pelo mesmo caminho do catálogo. O que precisa de tabela é a GALERIA: o pacote que
-- alguém guarda para reusar depois, no próprio inquilino ou, quando quem publica é superadmin, para toda a
-- plataforma. O conteúdo fica em bytea porque um pacote é pequeno (só JSON; teto em app/limites.py) e
-- porque a galeria tem de funcionar no appliance, onde pode não haver armazenamento de objetos.

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('pacotes/exportar', 'pacote de documentos exportado a partir de um item raiz'),
  ('pacotes/importar', 'pacote importado: documentos criados com ids novos e fontes mapeadas'),
  ('modelos/publicar', 'pacote publicado na galeria de modelos (escopo inquilino ou plataforma)'),
  ('modelos/apagar', 'modelo removido da galeria')
ON CONFLICT (nome) DO NOTHING;

CREATE TABLE IF NOT EXISTS plat.pacote_modelo (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- escopo 'plataforma' é o modelo que toda instalação enxerga; tenant_id continua sendo o de QUEM
    -- publicou (rastro), nunca o de quem lê. Ver a política abaixo: leitura por escopo, escrita por dono.
    escopo         text NOT NULL CHECK (escopo IN ('inquilino', 'plataforma')),
    tenant_id      integer NOT NULL REFERENCES plat.tenant(id),
    nome           text NOT NULL CHECK (length(nome) BETWEEN 1 AND 200),
    descricao      text NOT NULL DEFAULT '',
    tipo_raiz      text NOT NULL REFERENCES plat.tipo_item(nome),
    documentos     integer NOT NULL DEFAULT 0,
    fontes         integer NOT NULL DEFAULT 0,
    sha256         text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    bytes          integer NOT NULL CHECK (bytes > 0),
    conteudo       bytea NOT NULL,
    publicado_por  integer REFERENCES plat.usuario(id),
    criado_em      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pacote_modelo_escopo_idx ON plat.pacote_modelo(escopo, tenant_id);

ALTER TABLE plat.pacote_modelo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_pacote_modelo_ler ON plat.pacote_modelo;
CREATE POLICY p_pacote_modelo_ler ON plat.pacote_modelo FOR SELECT TO plat_app
  USING (escopo = 'plataforma' OR tenant_id = plat.tenant_atual());
-- escrever no escopo do próprio inquilino é do administrador do inquilino (o privilégio é conferido na rota,
-- como no resto do catálogo); publicar para TODA a plataforma exige superadmin de verdade, conferido aqui
-- pela mesma função que as demais políticas usam (plat.eh_superadmin, migração 011).
DROP POLICY IF EXISTS p_pacote_modelo_escrever ON plat.pacote_modelo;
CREATE POLICY p_pacote_modelo_escrever ON plat.pacote_modelo FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual()
              AND (escopo = 'inquilino' OR (escopo = 'plataforma' AND plat.eh_superadmin())));
DROP POLICY IF EXISTS p_pacote_modelo_apagar ON plat.pacote_modelo;
CREATE POLICY p_pacote_modelo_apagar ON plat.pacote_modelo FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual()
         AND (escopo = 'inquilino' OR (escopo = 'plataforma' AND plat.eh_superadmin())));

GRANT SELECT, INSERT, DELETE ON plat.pacote_modelo TO plat_app;
REVOKE UPDATE ON plat.pacote_modelo FROM plat_app;  -- modelo é imutável: republicar é publicar outro
