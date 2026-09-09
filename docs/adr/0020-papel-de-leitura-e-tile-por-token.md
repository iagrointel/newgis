# ADR 0020 — papel de leitura, contexto por token e função de tile por camada

Item `L2-04-a-leitor-rls-martin`. Estado: aceito, setembro de 2026.

## Contexto

O servidor de tiles vetoriais (Martin) fala com o PostGIS por conta própria: recebe `/{camada}/{z}/{x}/{y}`,
executa uma função SQL e devolve o MVT. Ele não sabe o que é inquilino, não lê a nossa sessão e não tem como
aplicar privilégio nenhum. Se conectasse com `plat_app`, um pedido de tile teria a mesma autoridade que a API
inteira. A RLS das tabelas de camada (`d_<slug>.c_<16 hex>`, ADR 0005) já filtra por inquilino; o que faltava
era um jeito de o inquilino chegar até o banco a partir de um pedido HTTP anônimo.

## Decisão

1. **Um papel só de leitura**, `plat_leitor` (`plat_t<trilha>_leitor` nos ambientes reescritos). Com LOGIN,
   sem BYPASSRLS, sem ser dona de nada, sem CREATE. Recebe `SELECT` nas tabelas de camada e `EXECUTE` nas
   funções de tile — nada mais. Senha em credential fora do repositório e linha própria no `pg_hba.conf`,
   escritas por `db/leitor_instalar.sh`, que o `install.sh` chama e que é idempotente (`mudancas: 0`).
2. **`plat.contexto_por_token(token, ip, origem, item, escopo, rota)`**, SECURITY DEFINER: valida o token de
   serviço (reusa `plat.auth_token`, ADR 0002 seção 8), confere revogação, expiração, escopo `camada:ler`
   (com ou sem uuid do item) e restrição de Referer/IP, grava uma linha em `plat.log_acesso` e põe o contexto
   na TRANSAÇÃO. Toda recusa é exceção nomeada: `token_ausente`, `token_invalido`, `token_revogado`,
   `token_expirado`, `escopo_insuficiente`, `ip_nao_permitido`, `referer_ausente`, `referer_nao_permitido`.
3. **Uma função de tile por camada**, `d_<slug>.t_<16 hex>(z, x, y, query_params json)`, criada por
   `plat.camada_tile_garantir` junto com a tabela e apagada por `plat.camada_tile_apagar` junto com ela. É
   SECURITY INVOKER de propósito — quem filtra as linhas é a RLS de quem chama. A primeira instrução é o
   `contexto_por_token`; o inquilino da camada fica gravado no corpo e um contexto de outro inquilino levanta
   `tile_de_outro_inquilino` em vez de devolver tile vazio.
4. **A política de RLS do papel de leitura não olha a GUC crua.** `plat.tenant_id` é parâmetro de
   configuração: qualquer papel conectado escreve nela. Para `plat_app` isso é indiferente (quem tem a senha
   da aplicação já tem tudo), mas o papel de leitura conecta de fora e é o MESMO para todos os inquilinos.
   Por isso a política dele é `tenant_id = (SELECT plat.tenant_leitor())`, e `plat.tenant_leitor()` só
   devolve o inquilino quando a GUC `plat.prova` bate com `sha256(segredo || inquilino || pid)`. O segredo
   vive em `plat.segredo_leitor`, sem SELECT para ninguém além de função SECURITY DEFINER, e a prova é
   emitida por `contexto_por_token` — isto é, só a quem apresentou um token válido daquele inquilino.

## Consequências

- Martin não precisa de código nosso: basta a fonte de função e o token na consulta.
- `SET plat.tenant_id` feito pelo próprio leitor não lê nada (medido: 0 linhas).
- Uma camada preparada pela 029 e nunca passada por `camada_tile_garantir` mantém a política antiga, que
  incluía `plat_leitor`. O retroativo da migração varre o CATÁLOGO (não o `pg_class`, porque o schema
  `d_<slug>` é compartilhado entre ambientes desta máquina) e a ingestão chama a função em toda carga nova.
- O log de uma recusa é escrito e depois desfeito com a transação abortada (o PostgreSQL não tem transação
  autônoma). O rastro da recusa fica no log do servidor e no log de acesso da API; o de plat.log_acesso vale
  para a chamada aceita, que é a que conta uso.
