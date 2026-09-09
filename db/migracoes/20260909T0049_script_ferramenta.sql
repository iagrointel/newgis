-- 20260909T0049_script_ferramenta (L2-16-c-script-vira-ferramenta, linha L2).
--
-- Hipótese do item: um script Python com cabeçalho declarativo (docstring YAML: nome, parâmetros
-- com o vocabulário GP da Esri, saídas) publica-se como FERRAMENTA do catálogo; a execução é um
-- job (`ferramentas.executar_script`) que roda o script no contêiner do inquilino (L2-16-b) e o
-- resultado vira item `ferramenta_resultado` (migração 20260908T1847) com a procedência apontando
-- a versão e o sha256 EXATOS do texto executado.
--
-- O que vive no banco: o TIPO de item do script (o próprio item do catálogo é o registro da
-- ferramenta — versões pela máquina item_versao do L5-05, compartilhamento pelo do L0-03) e os
-- dois tipos de evento. NENHUMA tabela nova: estado de execução é `plat.job` (log de execução) e
-- resultado é item `ferramenta_resultado`.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres (trilha reescreve plat./roles).

-- ------------------------------------------------------------------ tipo de item da ferramenta-script
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front,
                           abre_em, tem_dado_fisico, linha_dona) VALUES
  ('ferramenta_script', 'ferramenta', 'Ferramenta de script',
   'ferramenta definida por script Python com cabeçalho declarativo; executa como job no contêiner do inquilino',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["codigo","sha256","cabecalho","versao"],
     "properties":{
       "codigo":{"type":"string","minLength":1,"maxLength":200000},
       "sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
       "cabecalho":{"type":"object"},
       "versao":{"type":"integer","minimum":1}}}'::jsonb,
   1, '', '/static/js/catalogo/tipos/ferramenta_script.js', '{}', false, 'L2-16')
ON CONFLICT (nome) DO NOTHING;

-- ------------------------------------------------------------------ eventos de domínio
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('ferramentas/script-publicado', 'script publicado (ou republicado em versão nova) como ferramenta do catálogo'),
  ('ferramentas/script-execucao-pedida', 'execução de ferramenta-script pedida: job criado com a versão congelada'),
  ('ferramentas/script-executado', 'execução de ferramenta-script gravou o resultado como item de catálogo')
ON CONFLICT (nome) DO NOTHING;
