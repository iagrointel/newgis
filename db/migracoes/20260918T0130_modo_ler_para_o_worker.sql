-- 20260918T0130_modo_ler_para_o_worker: `plat modo estado` precisa LER o modo pela mesma role que o
-- liga (item L7-33-modo-somente-leitura).
--
-- A migração 20260906T2109 deu EXECUTE em plat.modo_ligar/modo_desligar ao `plat_worker` e EXECUTE em
-- plat.modo_ler só ao `plat_app`. Ligar e desligar funcionam porque as duas são SECURITY DEFINER e
-- chamam modo_ler por dentro, já como dona. Mas a CLI de infraestrutura (`scripts/plat modo estado`)
-- existe justamente para o caso em que a API está fora do ar, e aí não há `plat_app` nem rota
-- `/api/modo` para consultar: sem este GRANT, `plat modo estado` morre com "permission denied for
-- function modo_ler" (medido em 18/09/2026 na trilha seg).
--
-- Ler o estado de uma bandeira de infraestrutura é leitura, não escrita: o GRANT abaixo não dá à role do
-- worker nenhum poder novo de mudar o modo, e plat.sistema/plat.sistema_trilha continuam sem GRANT
-- nenhum para ela. `plat_app` segue como antes. Idempotente; sem BEGIN/COMMIT (o aplicador abre a
-- transação).

GRANT EXECUTE ON FUNCTION plat.modo_ler(int) TO plat_worker;

-- Mesma razão para o histórico: quem liga e desliga o modo é a role do worker, pela CLI, e a única
-- forma de CONFERIR que a ação ficou registrada é ler plat.sistema_trilha. Sem leitura, a cláusula do
-- portão "`plat modo` com motivo obrigatório grava trilha" não tem como ser provada por quem executa o
-- comando (medido em 18/09/2026: "permission denied for table sistema_trilha").
--
-- É SELECT, e só. INSERT/UPDATE/DELETE continuam sem GRANT para todo mundo: as linhas entram apenas por
-- dentro de plat.modo_ligar/modo_desligar, que são SECURITY DEFINER — o histórico segue append-only e
-- ninguém o reescreve. A tabela guarda chave, ação, motivo e quem: infraestrutura, sem dado de
-- inquilino. plat_app continua sem acesso nenhum (o REVOKE de 20260906T2109 vale).
GRANT SELECT ON plat.sistema_trilha TO plat_worker;
