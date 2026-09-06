-- 041_acervo_lgpd: classificação de risco de dado pessoal por FONTE do acervo (item L6-01-f-lgpd).
--
-- Conferido antes de escrever: `acervo.fonte` (`\d acervo.fonte`, 06/09/2026) NÃO tem nenhum campo de
-- classificação (nem "identidade_resolvente" nem equivalente) — a coluna `cliente_ve` mais próxima é sobre
-- visibilidade comercial, não sobre risco de dado pessoal. E `acervo.*` é escrito só pelos scripts da casa
-- (registro.py/contagem2.py/frescor.py — regra repetida em três lugares no ADR 0012); a plataforma NUNCA grava
-- lá. Por isso a classificação vive numa tabela PRÓPRIA da plataforma (`plat.acervo_lgpd`), curada à mão,
-- nunca calculada — o próprio pedido do item ("nunca automática").
--
-- CURADORIA (evidência, não suposição): as cinco fontes citadas na hipótese do item como candidatas a bloqueio
-- permanente (SICOR identidade, CAFIR, TSE eleitorado/candidaturas — CNPJ de sócio e SNGPC não têm fonte_id
-- correspondente nesta base) JÁ existem em acervo.fonte mas SEM licença escrita:
--   bcb-sicor-identidade-mutuarios-propriedades-cooperados, rfb-cafir-cadastro-de-imoveis-rurais-itr,
--   tse-candidaturas-e-bens-declarados, tse-resultados-eleitorado-e-locais-de-votacao
-- — a regra D17 (licenca IS NOT NULL) já as tira da ficha e do POST /adicionar (testado em
-- test_fonte_sem_licenca_nunca_aparece / test_adicionar_fonte_sem_licenca_404); não precisam de linha aqui.
--
-- Das 68 fontes COM licença (as únicas que passam pelo POST /adicionar), foi rodada uma varredura de
-- information_schema.columns em todas as 219 tabelas canônicas ligadas a elas (acervo.objeto, canonico=true)
-- contra um padrão amplo (cpf|cnpj|nome|name|email|telefone|celular|endereco|address|rg|titular|proprietar|
-- possuidor|responsavel|contribuinte|...): 114 colunas bateram. Cada uma foi lida à mão (não só o NOME da
-- coluna — o item pede exatamente o cuidado que falta nisso): a esmagadora maioria é nome de LUGAR
-- (zona_nome, nome_municipio, nome_uc, terrai_nome, se_dist_nome, macro_nome...), nome de ARQUIVO
-- (leilao_documento.nome_original), CNPJ de FUNDO/PESSOA JURÍDICA (b3.estoque_fii.fii_cnpj — fundo
-- imobiliário, não pessoa física) ou endereço de IMÓVEL já público por natureza (leilão/edital — o próprio
-- produto é mostrar isso). Um caso quase enganou a varredura: `cbre.cad_gu_face_pgv` (cadastro fiscal de
-- Guarulhos) tem colunas `telefone`/`telefone_p`/`id_responsavel`, mas são FLAGS de infraestrutura de rua
-- (a rua tem rede telefônica? — ao lado de `agua`/`luz`/`esgoto`/`iluminacao`/`hidrante`, mesma tabela),
-- não telefone de pessoa (medido: id_responsavel preenchido em 1 de 25.436 linhas — não é um cadastro de
-- contato). NÃO marcada.
--
-- O ÚNICO achado real: `onr` (ONR — matrículas). A tabela ingerida (cbre.onr_matricula) não guarda nome do
-- titular, mas guarda `url_mat`, link direto para o visualizador de matrícula do cartório
-- (registradores.onr.org.br/ridigital.org.br) — o documento do OUTRO LADO do link é uma matrícula de imóvel
-- de verdade, com o nome do proprietário. Referenciar `onr` (protocolo 'acervo', modo 'referenciada') dá a
-- quem adiciona um caminho de um clique até dado de pessoa identificada; por isso entra marcada.
--
-- Esta curadoria cobre só o que o item pediu (gate no POST /adicionar); NÃO é o portão inteiro do backlog
-- (varredura de TODA view exposta, regex sobre amostra de conteúdo) — isso fica registrado como pendência no
-- handoff, não prometido como feito aqui.
--
-- Numeração 041 (040 = acervo_endpoint, mesmo turno; 034-039 tomados por outras trilhas, checado ao vivo). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- vocabulário de evento (ADR 0002 seção 9.4, plat.evento.tipo tem FK para plat.evento_tipo — sem esta linha o
-- INSERT de app/acervo/rotas.py::adicionar cairia em violação de FK na primeira fonte marcada risco_pii).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('acervo/adicionar_recusado_pii', 'POST /api/acervo/{fonte_id}/adicionar recusado por falta de confirma_risco_pii')
ON CONFLICT (nome) DO NOTHING;

CREATE TABLE IF NOT EXISTS plat.acervo_lgpd (
  fonte_id      text PRIMARY KEY REFERENCES acervo.fonte(fonte_id),
  risco_pii     boolean NOT NULL,
  motivo        text NOT NULL CHECK (btrim(motivo) <> ''),   -- nunca marcado (nem limpo) sem razão escrita
  decidido_por  text NOT NULL CHECK (btrim(decidido_por) <> ''),
  decidido_em   timestamptz NOT NULL DEFAULT now(),
  revisar_em    date                                          -- opcional: quando a curadoria pede nova olhada
);

-- só leitura para a aplicação: esta tabela é curada à mão (INSERT/UPDATE literal em migração ou por quem tem
-- acesso direto ao banco), nunca pela API — mesmo padrão de plat.acervo_camada (migração 027).
GRANT SELECT ON plat.acervo_lgpd TO plat_app;
REVOKE INSERT, UPDATE, DELETE ON plat.acervo_lgpd FROM plat_app;

INSERT INTO plat.acervo_lgpd (fonte_id, risco_pii, motivo, decidido_por, decidido_em) VALUES
  ('onr', true,
   'onr_matricula.url_mat aponta para o visualizador do cartório (registradores.onr.org.br/ridigital.org.br); '
   || 'o documento de matrícula do outro lado do link traz o nome do titular do imóvel — dado de pessoa '
   || 'identificada, mesmo a tabela ingerida não guardando o nome. Revisão de 219 tabelas canônicas das 68 '
   || 'fontes licenciadas (item L6-01-f, 06/09/2026); nenhuma outra fonte licenciada mostrou coluna de '
   || 'identidade de pessoa física em conteúdo real (cad_gu_face_pgv.telefone* são flag de infraestrutura de '
   || 'rua, não contato pessoal — medido 1/25.436 linhas com id_responsavel preenchido).',
   'arquiteto+backend T3 (item L6-01-f-lgpd)', now())
ON CONFLICT (fonte_id) DO UPDATE SET
  risco_pii    = EXCLUDED.risco_pii,
  motivo       = EXCLUDED.motivo,
  decidido_por = EXCLUDED.decidido_por,
  decidido_em  = EXCLUDED.decidido_em;
