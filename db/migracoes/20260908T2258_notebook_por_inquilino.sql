-- 20260908T2258_notebook_por_inquilino (L2-16-b-jupyter-por-inquilino-isolado, linha L2).
--
-- Hipótese do item: um JupyterLab por inquilino em contêiner efêmero (rede interna sem saída,
-- RAM/CPU limitados, único segredo = token de serviço do usuário) dá análise com dado da
-- plataforma SEM abrir banco nem internet ao usuário do notebook; quem quiser dado, pede pela
-- API com o token que ele já tem.
--
-- O que vive no banco é só o ESTADO DE USO que o ceifador precisa (item L2-16-b): qual inquilino
-- tem notebook de pé, desde quando, última passagem pelo proxy e qual token o contêiner carrega
-- (para revogar ao encerrar). O contêiner em si NUNCA é estado de banco (é do docker CLI).
--
-- RLS: políticas só por inquilino, SEM plat.usuario_do_inquilino() — as linhas são escritas pela
-- própria aplicação em nome do inquilino (login técnico 'notebooks', usuario_id 0) quando o
-- contêiner sobe/é tocado; exigir usuário membro quebraria o upsert do proxy. A role worker lê e
-- apaga para o ceifador (job periódico notebooks.ceifar), que roda fora de pedido HTTP.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres (trilha reescreve plat./roles).

-- ------------------------------------------------------------------ tipos de item do notebook
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front,
                           abre_em, tem_dado_fisico, linha_dona) VALUES
  ('notebook', 'documento', 'Notebook',
   'caderno Jupyter (.ipynb) do inquilino; abre no JupyterLab isolado em /notebooks/<inquilino>',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["chave","sha256","bytes","content_type","nome_original"],
     "properties":{
       "chave":{"type":"string","maxLength":400},
       "sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
       "bytes":{"type":"integer","minimum":0},
       "content_type":{"type":"string","maxLength":120},
       "nome_original":{"type":"string","maxLength":250}}}'::jsonb,
   1, '', '', '{}', true, 'L2-16'),
  ('notebook_saida', 'documento', 'Saída de notebook',
   'HTML com a saída de uma execução agendada de notebook (job notebooks.executar)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["chave","sha256","bytes","content_type","nome_original","notebook_id"],
     "properties":{
       "chave":{"type":"string","maxLength":400},
       "sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
       "bytes":{"type":"integer","minimum":0},
       "content_type":{"type":"string","maxLength":120},
       "nome_original":{"type":"string","maxLength":250},
       "notebook_id":{"type":"string","format":"uuid"},
       "job_id":{"type":"string","format":"uuid"}}}'::jsonb,
   1, '', '', '{}', true, 'L2-16')
ON CONFLICT (nome) DO NOTHING;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('notebooks/executado', 'execução agendada de notebook gravou a saída HTML como item')
ON CONFLICT (nome) DO NOTHING;

-- ------------------------------------------------------------------ estado de uso do notebook
CREATE TABLE IF NOT EXISTS plat.notebook_uso (
  tenant_id     int PRIMARY KEY REFERENCES plat.tenant(id) ON DELETE CASCADE,
  slug          text NOT NULL CHECK (btrim(slug) <> '' AND length(slug) <= 60),
  levantado_em  timestamptz NOT NULL DEFAULT now(),   -- última subida do contêiner
  ultimo_uso    timestamptz NOT NULL DEFAULT now(),   -- última passagem pelo proxy (ociosidade)
  token_id      int REFERENCES plat.token_servico(id) ON DELETE SET NULL  -- revogado ao ceifar
);
ALTER TABLE plat.notebook_uso ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_notebook_uso_ler ON plat.notebook_uso;
CREATE POLICY p_notebook_uso_ler ON plat.notebook_uso FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_notebook_uso_inserir ON plat.notebook_uso;
CREATE POLICY p_notebook_uso_inserir ON plat.notebook_uso FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_notebook_uso_alterar ON plat.notebook_uso;
CREATE POLICY p_notebook_uso_alterar ON plat.notebook_uso FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_notebook_uso_apagar ON plat.notebook_uso;
CREATE POLICY p_notebook_uso_apagar ON plat.notebook_uso FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual());

-- ceifador (notebooks.ceifar roda como worker, fora de pedido HTTP): lê tudo e apaga o órfão
DROP POLICY IF EXISTS p_notebook_uso_worker_ler ON plat.notebook_uso;
CREATE POLICY p_notebook_uso_worker_ler ON plat.notebook_uso FOR SELECT TO plat_worker USING (true);
DROP POLICY IF EXISTS p_notebook_uso_worker_apagar ON plat.notebook_uso;
CREATE POLICY p_notebook_uso_worker_apagar ON plat.notebook_uso FOR DELETE TO plat_worker USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.notebook_uso TO plat_app;
GRANT SELECT, DELETE ON plat.notebook_uso TO plat_worker;
