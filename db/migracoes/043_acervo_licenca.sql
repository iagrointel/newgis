-- 043_acervo_licenca: licença CURADA e testada por HTTP, por fonte do acervo (item L6-01-g-licenca-curada;
-- depende de L6-01-a-registro, migração 027, ENTREGUE).
--
-- Regra D17 (repetida em toda a linha L6): "dado público sem licença escrita" NÃO conta como licença — a URL
-- tem de MOSTRAR o termo de verdade. `acervo.fonte.licenca` já guarda um texto livre por fonte (medido
-- 05/09/2026: 68 das 376 fontes têm texto não vazio, mas só 15 nomeiam uma licença de verdade — o resto é
-- "dado público (licença não declarada na fonte)", que o próprio texto já confessa não valer). Esta migração
-- NÃO reaproveita esse texto livre como prova: cria uma tabela PRÓPRIA da plataforma, `plat.acervo_licenca`,
-- com vocabulário FECHADO e um REGISTRO da verificação HTTP em si (status, quando, e um recorte literal da
-- página como evidência) — cada linha só existe porque `scripts/acervo_licenca_sync.py` buscou a URL AGORA e
-- encontrou o termo, nunca porque alguém digitou um tipo de cabeça.
--
-- `acervo.*` continua só-leitura (regra repetida em 021/027/040/041): esta migração não toca lá. A tabela nova
-- é curada por SCRIPT (não por migração com INSERT fixo, ao contrário de 041_acervo_lgpd — aqui o próprio ATO
-- de escrever exige uma chamada de rede bem-sucedida no momento da escrita, então não faz sentido "gravar" um
-- resultado de rede dentro de uma migração, que roda uma vez e fica congelada). O padrão de privilégio é o
-- mesmo de `plat.acervo_camada` (027) e `plat.acervo_lgpd` (041): `plat_app` só LÊ; quem escreve é o script,
-- rodando como `postgres` (mesma identidade de `db/migrar.sh` e de `acervo_sync.py`).
--
-- Vocabulário fechado (hipótese do item, verbatim): CC0, CC-BY, CC-BY-SA, ODbL, dado-aberto-com-termo-do-orgao,
-- Copernicus, licenca-propria, nao-declarada. Sem acento no valor do CHECK (evita duas grafias da mesma coisa
-- por causa de encoding) — o rótulo acentuado para tela fica em app/acervo_licenca (mapa fixo, não é dado).
--
-- Numeração 043 (042 = perfil_usuario, tomado por outra trilha do mesmo turno, checado ao vivo agora).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.acervo_licenca (
  fonte_id       text PRIMARY KEY REFERENCES acervo.fonte(fonte_id),
  tipo           text NOT NULL CHECK (tipo IN (
                   'CC0', 'CC-BY', 'CC-BY-SA', 'ODbL', 'dado-aberto-com-termo-do-orgao',
                   'Copernicus', 'licenca-propria', 'nao-declarada'
                 )),
  url_licenca    text NOT NULL CHECK (btrim(url_licenca) <> ''),   -- página/endpoint testado, nunca vazio
  metodo         text NOT NULL CHECK (btrim(metodo) <> ''),        -- como foi lido: html_regex | ckan_package_show | dcat_data_json
  identificador_remoto text,                                        -- slug/título usado na fonte remota (dataset CKAN, título DCAT) — auditoria
  http_status    int  NOT NULL,
  evidencia      text NOT NULL CHECK (btrim(evidencia) <> ''),     -- recorte LITERAL da resposta HTTP, nunca escrito à mão
  confianca      text NOT NULL CHECK (btrim(confianca) <> ''),     -- correspondência exata / por nome do dataset / geral do portal — nunca omitido
  verificado_em  timestamptz NOT NULL,
  atualizado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_acervo_licenca_tipo ON plat.acervo_licenca(tipo);

COMMENT ON TABLE plat.acervo_licenca IS
  'Licença curada e testada por HTTP real (item L6-01-g-licenca-curada). Cada linha exige uma verificação de '
  'rede bem-sucedida no momento da escrita (scripts/acervo_licenca_sync.py, roda como postgres); plat_app só lê.';

GRANT SELECT ON plat.acervo_licenca TO plat_app;
REVOKE INSERT, UPDATE, DELETE ON plat.acervo_licenca FROM plat_app;
