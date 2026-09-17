-- Ficha de metadado e licença da imagem (item L1-27): o tipo de item `raster` passa a admitir o objeto
-- `ficha` dentro de `dados`. O JSON Schema aqui é DELIBERADAMENTE permissivo (`type: object`): a lista
-- fechada de licenças e a validação campo a campo vivem numa única tabela, em `app/imagens/ficha.py`, e
-- repetir a lista aqui criaria uma segunda tabela que envelheceria em silêncio (cláusula do portão:
-- "lista de licenças lida do código (uma só tabela)"). O que esta migração garante é só que `ficha` deixa
-- de ser propriedade adicional recusada por `additionalProperties: false`.
-- Idempotente: só mexe se a propriedade ainda não existir.
UPDATE plat.tipo_item
   SET esquema = jsonb_set(esquema, '{properties,ficha}', '{"type":"object","title":"ficha de metadado e licença"}'::jsonb, true),
       esquema_versao = esquema_versao  -- `ficha` é propriedade OPCIONAL: nenhum documento gravado
       -- fica ilegível e não há cadeia `migrar_raster_v1_v2` a escrever, então a versão do esquema não sobe
       -- (subir sem migração registrada só faria `documento.migrar_para_leitura` andar em falso)
 WHERE nome = 'raster'
   AND NOT (esquema -> 'properties' ? 'ficha');

-- Eventos de domínio da ficha (item L1-27). `imagens/ficha_licenca_afrouxada` e
-- `imagens/ficha_licenca_recusada` são a trilha de auditoria da refutação do item: trocar uma licença que
-- NÃO autoriza redistribuição por uma que autoriza muda o que a plataforma passa a permitir com o arquivo
-- do cliente, então tanto a troca aprovada quanto a tentativa recusada ficam gravadas.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('imagens/ficha_gravar', 'ficha de metadado e licença da imagem gravada (licenca, licenca_anterior, projetado_no_stac)'),
  ('imagens/ficha_licenca_afrouxada', 'licença da imagem trocada de restrita para livre por quem tem org.configurar (de, para)'),
  ('imagens/ficha_licenca_recusada', 'tentativa recusada de trocar licença restrita por livre sem org.configurar (de, para, exigido)')
ON CONFLICT (nome) DO NOTHING;
