-- 20260910T2325_conexao_camada_descoberta: item L6-02-conectores-vivos. `app/conexao/descoberta.py` lê o
-- GetCapabilities/`/collections`/`f=json` de uma `plat.conexao` viva e devolve a lista de camadas (nome,
-- título, CRS, extensão); esta tabela GUARDA essa lista (portão: "descoberta automática ... e listar as
-- camadas com nome, título, CRS e extensão ... guardar a lista"), para a tela mostrar sem sondar o serviço
-- de novo a cada carregamento e para o proxy (`app/conexao/proxy.py`) validar que uma `layer=` pedida é uma
-- das camadas realmente descobertas.
--
-- Filha de `plat.conexao` (ON DELETE CASCADE — a lista não sobrevive à conexão apagada), com `tenant_id`
-- DENORMALIZADO na própria linha (mesmo padrão de `plat.conexao_saude_historico`, 036): a política de RLS
-- não depende de JOIN com a tabela pai, e some junto se o inquilino inteiro for apagado (009).
--
-- Escrita por quem já é dono-ou-editor da conexão (mesma regra de UPDATE/DELETE de `plat.conexao`, 030) —
-- diferente de `conexao_saude_historico`, que só a função SECURITY DEFINER grava (o job periódico de saúde
-- roda no inquilino técnico `plataforma` para QUALQUER inquilino; a descoberta de camada é sempre uma ação
-- do PRÓPRIO inquilino, disparada pela tela, nunca um periódico cruzando inquilino) — por isso aqui bastam
-- políticas normais de INSERT/UPDATE/DELETE para `plat_app`, sem função intermediária.
--
-- Numeração 20260910T2325 (a mais recente no branch é 20260910T2315_campo_capturado_em_texto.sql, de outra
-- trilha). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.conexao_camada (
  id             bigserial PRIMARY KEY,
  conexao_id     uuid NOT NULL REFERENCES plat.conexao(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  nome           text NOT NULL CHECK (btrim(nome) <> ''),
  titulo         text,
  crs            jsonb NOT NULL DEFAULT '[]'::jsonb,   -- lista de códigos/URNs de CRS que o serviço declarou
  extensao       jsonb,                                -- {"minx","miny","maxx","maxy","crs"} ou NULL (não declarado)
  descoberta_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_conexao_camada_conexao ON plat.conexao_camada (conexao_id);
CREATE INDEX IF NOT EXISTS ix_conexao_camada_tenant ON plat.conexao_camada (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_conexao_camada_nome ON plat.conexao_camada (conexao_id, nome);

ALTER TABLE plat.conexao_camada ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_conexao_camada_ler ON plat.conexao_camada;
CREATE POLICY p_conexao_camada_ler ON plat.conexao_camada FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());

-- escreve quem é dono da conexão-mãe ou tem conteudo.editar_tudo (mesma regra de UPDATE/DELETE de
-- plat.conexao na 030); INSERT/UPDATE/DELETE todos exigem a mesma checagem porque a rota de descoberta
-- SUBSTITUI a lista inteira (apaga as antigas da conexão e insere as novas, dentro da mesma transação).
DROP POLICY IF EXISTS p_conexao_camada_inserir ON plat.conexao_camada;
CREATE POLICY p_conexao_camada_inserir ON plat.conexao_camada FOR INSERT TO plat_app
  WITH CHECK (
    tenant_id = plat.tenant_atual()
    AND EXISTS (
      SELECT 1 FROM plat.conexao c WHERE c.id = conexao_id
        AND c.tenant_id = plat.tenant_atual()
        AND (c.dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo'))
    )
  );

DROP POLICY IF EXISTS p_conexao_camada_alterar ON plat.conexao_camada;
CREATE POLICY p_conexao_camada_alterar ON plat.conexao_camada FOR UPDATE TO plat_app
  USING (
    tenant_id = plat.tenant_atual()
    AND EXISTS (
      SELECT 1 FROM plat.conexao c WHERE c.id = conexao_id
        AND c.tenant_id = plat.tenant_atual()
        AND (c.dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo'))
    )
  )
  WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_conexao_camada_apagar ON plat.conexao_camada;
CREATE POLICY p_conexao_camada_apagar ON plat.conexao_camada FOR DELETE TO plat_app
  USING (
    tenant_id = plat.tenant_atual()
    AND EXISTS (
      SELECT 1 FROM plat.conexao c WHERE c.id = conexao_id
        AND c.tenant_id = plat.tenant_atual()
        AND (c.dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo'))
    )
  );

-- defeito real de hoje (achado ao construir este item): rota que chama registrar_evento com um nome de
-- evento não semeado em plat.evento_tipo dá 500 (violação de chave estrangeira) — nunca um 4xx legível.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('conexoes/descobrir', 'camadas descobertas (ou redescobertas) de uma conexão externa (protocolo, quantidade)')
ON CONFLICT (nome) DO NOTHING;
