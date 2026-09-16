-- Conserto de regressão (achado 16/09/2026, tests/api/exportacao/test_exportacao.py::
-- test_camada_de_outro_usuario_do_mesmo_inquilino_exige_a_opcao_do_dono): o esquema v3 de camada_vetorial
-- (20260906T1551_exportacao_camada.sql e 20260907T0141_exportacao_camada.sql, item L0-04-h-exportar)
-- acrescenta a propriedade OPCIONAL `exportacao.permitir_outros` — sem ela, `PATCH /api/itens/{id}` com
-- `dados.exportacao` é recusado (422 "Additional properties are not allowed ('exportacao' was unexpected)")
-- e a opção do dono "permitir que outros exportem" (app/exportacao/rotas.py::_pode_exportar_o_item) nunca
-- pode ser ligada.
--
-- MEDIDO ao vivo: o esquema hoje está na v4 — `20260908T1225_versionamento_por_ramo.sql` usou jsonb_set
-- para acrescentar `versionamento` a partir de UM estado do esquema, e o guard por NÚMERO de versão
-- (`esquema_versao < 4` / `esquema_versao > EXCLUDED.esquema_versao`) trava qualquer volta da v3 depois
-- disso — mas o jsonb_set daquela migração partiu de um esquema que ainda não tinha `exportacao` (as duas
-- migrações nasceram em ramos paralelos que nunca se viram, mesma classe do achado de
-- 20260916T1100_recurso_partilhado_por_inquilino_regressao.sql, só que aqui o veículo é jsonb_set sobre um
-- CONTADOR de versão, não um CREATE OR REPLACE). Resultado: a v4 tem `versionamento` mas perdeu
-- `exportacao` — nenhum comentário anterior mentiu, os dois simplesmente nunca se somaram.
--
-- Conserto = o MESMO padrão aditivo de 20260908T1225 (jsonb_set, nunca reescreve o esquema inteiro), mas
-- com guarda por CONTEÚDO (a propriedade já existe?) em vez de por número de versão — a esta altura já
-- ficou claro que um contador de versão não basta quando duas migrações crescem o mesmo documento em
-- paralelo; só uma pergunta ao próprio dado responde de verdade.
UPDATE plat.tipo_item
   SET esquema = jsonb_set(
         esquema, '{properties,exportacao}',
         '{"type":"object","additionalProperties":false,
           "properties":{"permitir_outros":{"type":"boolean"}}}'::jsonb, true),
       esquema_versao = greatest(esquema_versao, 5)
 WHERE nome = 'camada_vetorial' AND NOT (esquema->'properties' ? 'exportacao');
