-- reaplicavel
-- 20260915T2349_fk_autoria_ator_fora_do_inquilino (item F2-FKSTALE).
-- depende: 20260906T1847_fk_por_inquilino_classe.sql, 022_arquivos.sql, 016_catalogo_apagar_usuario.sql
--
-- MEDIDO na trilha uniao (pg_constraint contra plat_tuniao.usuario, zero órfãos hoje — a FK sempre
-- barrou a escrita, nunca deixou lixo): duas causas distintas por trás dos dois sintomas relatados
-- (tests/api/catalogo/test_lixeira.py e tests/api/catalogo/test_uso_bytes_simetrico.py apontando
-- "item_tenant_apagado_por_fkey" / "arquivo_tenant_criado_por_fkey").
--
-- CAUSA 1 — arquivo.criado_por é AUTORIA (rastro de quem gravou o metadado do objeto; não existe
-- "dono" de arquivo, só quem criou), mesma classe que 016_catalogo_apagar_usuario.sql já resolveu para
-- item.criado_por/apagado_por/modificado_por e compartilhamento_link.criado_por. `022_arquivos.sql`
-- (posterior a 016) nunca ganhou o mesmo tratamento — ficou REFERENCES plat.usuario(id) simples, sem
-- ON DELETE. A migração 20260906T1847 converteu para composta (tenant_id, criado_por) preservando o
-- ON DELETE de antes (nenhum) porque seu escopo era só a checagem tenant×tenant, não auditou a
-- política de autoria x posse. Efeito medido: `laco/trilha_ambiente.sh` passo "d. ambiente de teste"
-- apaga usuários de teste com `DELETE FROM $SCHEMA.usuario WHERE login LIKE 'zt%'` depois de já ter
-- expurgado o inquilino zt-* dono deles; um usuário zt* criado DENTRO de demo/demo2 (não sob seu
-- próprio inquilino zt-) que chegou a gravar um `plat.arquivo` trava esse DELETE com em_uso. Conserto:
-- ON DELETE SET NULL (criado_por), mesma sintaxe de lista de colunas do resto da classe (Postgres 15+;
-- sem a lista, a composta zeraria também tenant_id, que é NOT NULL — nota já registrada no ADR de
-- 20260906T1850).
--
-- CAUSA 2 — item.apagado_por/criado_por/modificado_por são AUTORIA, mas o ator pode legitimamente ser
-- de OUTRO inquilino: D20 (laco/decomposicao/L0_CONCEITO.md) — "superadmin fora de inquilino" — é
-- decisão travada ("custo de mudar: não se muda; é o que o produto vende"). `Auth.contexto_leitura()`
-- (app/auth/sessao.py) monta de propósito um Contexto com tenant_id do inquilino ALVO e usuario_id do
-- PRÓPRIO superadmin (de outro inquilino) quando a rota aceita X-Plat-Inquilino; `plat.item_lixeira()`
-- (011_catalogo.sql) grava apagado_por = plat.usuario_atual() nesse contexto. A trava
-- test_lixeira.py::test_protegido_admin_do_inquilino_nao_apaga_superadmin_apaga_com_evento espera
-- textualmente esse comportamento ("o ator é o superadmin... o id fica gravado, mas o login não
-- resolve dentro de demo"). A FK composta (tenant_id, apagado_por) exige que o ATOR pertença ao MESMO
-- inquilino do item — nunca vale para o superadmin cross-tenant, e nenhuma reseed está envolvida: o
-- 409 em_uso estoura na hora, dentro de uma única sessão de teste. `plat.evento` (011_catalogo.sql),
-- que já registra ator cross-tenant há mais tempo, nunca teve FK nenhuma em ator_id para exatamente
-- este motivo — não é caso novo, é precedente. O risco que 20260906T1847 fechou (oráculo de
-- existência: FK simples aceita/recusa um uuid ADIVINHADO por quem CONTROLA o valor gravado) não se
-- aplica aqui: autoria nunca vem de corpo de requisição, só de plat.usuario_atual() lido no contexto
-- do servidor — dono_id, item_id, link_id etc. continuam compostos porque esses SIM vêm de entrada do
-- chamador. Conserto: as 3 FKs de autoria de item voltam a ser simples (usuario(id), sem tenant_id),
-- mantendo ON DELETE SET NULL. Idempotente: DROP CONSTRAINT IF EXISTS + ADD.

ALTER TABLE plat.arquivo DROP CONSTRAINT IF EXISTS arquivo_tenant_criado_por_fkey;
ALTER TABLE plat.arquivo ADD CONSTRAINT arquivo_tenant_criado_por_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id) ON DELETE SET NULL (criado_por);

ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_apagado_por_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_apagado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_apagado_por_fkey
  FOREIGN KEY (apagado_por) REFERENCES plat.usuario (id) ON DELETE SET NULL;

ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_criado_por_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_criado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_criado_por_fkey
  FOREIGN KEY (criado_por) REFERENCES plat.usuario (id) ON DELETE SET NULL;

ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_tenant_modificado_por_fkey;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_modificado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_modificado_por_fkey
  FOREIGN KEY (modificado_por) REFERENCES plat.usuario (id) ON DELETE SET NULL;

-- item_tenant_dono_fkey (posse, NO ACTION) e item_tenant_pasta_fkey/item_tenant_dono_fkey de outras
-- colunas não são tocados aqui: dono_id é sempre do MESMO inquilino (o próprio gatilho tg_item_antes
-- já barra com 'usuario_de_outro_inquilino'), então a composta continua correta e necessária lá.
