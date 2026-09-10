# ADR 20260908T1700 — arquivos, entrada por LDAP e console da plataforma com controle (UX-11, UX-17, UX-18)

## Contexto

Três grupos de rotas de escrita ficaram sem controle em tela na cobertura da interface: `POST/DELETE
/api/arquivos` (objetos genéricos do inquilino, L0-11), `POST /api/login/ldap` (L0-08-d) e o console do superadmin
(`/api/plataforma/inquilinos`, ADR 0002 seção 10). Os três têm particularidades que uma tela genérica não cobre:
o envio de arquivo só aceita token de serviço (corpo cru, proteção contra CSRF), a rota LDAP é pública e depende
de o inquilino ter habilitado o provedor, e o console só existe para o inquilino `plataforma`.

## Decisão

1. **Arquivos** entram como seção de `/admin/organizacao`, ao lado da cota: uso × cota (`GET /api/arquivos`),
   varredura de órfãos, envio e apagar. O envio cunha um token `admin:inquilino` de um dia por `POST /api/tokens`,
   envia o arquivo cru com `Authorization: Bearer` e `credentials: 'omit'` (cookie e Authorization juntos dão
   400 `autenticacao_ambigua`) e REVOGA o token no `finally`, dando certo ou errado. O servidor não lista objetos:
   a tabela mostra os enviados na sessão, cada um com baixar e apagar. 413 (cota) e 415 (bytes não batem com o
   tipo declarado) viram texto nomeado; classe fora do padrão é recusada no navegador.
2. **LDAP na entrada**: `GET /api/login/provedores` passa a declarar `{tipo: "ldap"}` quando
   `plat.provedor_ldap_de(slug).habilitado` (nenhum segredo sai). A tela mostra um botão que alterna o modo:
   mesmos campos usuário/senha, outra rota (`POST /api/login/ldap`). 503 `ldap_indisponivel` e
   `ldap_sem_configuracao` viram "o diretório não respondeu; tente o login local"; 403 `login_ldap_desabilitado`
   desliga o modo; 403 `sem_grupo_mapeado` e 409 `login_em_uso_local` viram texto próprio. O login local nunca
   sai da tela.
3. **Plataforma** (`/plataforma`): entrada na barra lateral só para `usuario.superadmin` (`telasVisiveis` ganha a
   chave `superadmin`, que nunca se confunde com privilégio de inquilino). Lista com filtro, estado e ações
   suspender/reativar/apagar com confirmação (a linha `plataforma` não tem ações); criação com validação local do
   slug e do login, 409 e 422 de volta ao campo, e a senha temporária mostrada UMA vez com botão de copiar e a
   ligação para a entrada do inquilino novo. 404 da API (não é superadmin) vira "negado", nunca "inexistente".
4. `button.perigo:hover` inverte (fundo vermelho, texto da superfície): o texto vermelho sobre vermelho-fraco não
   chegava a 4,5:1 e o axe reprovava a linha sob o ponteiro.

## Consequências

- A cobertura da trilha de interface fica sem lacuna própria: sobram categorias, geocodificador e ingestão, que
  estão com outros líderes (UX-12, UX-14/15, UX-16).
- O e2e do superadmin cria a sessão direto no banco (`tests/jobs_sessao`) e liga o 2FA obrigatório pela API,
  guardando o segredo no arquivo de TOTP da trilha — o mesmo que `tests/api` lê.
- O pool da API na trilha (`PLAT_POOL_MAX=2`) estoura com os pedidos paralelos do hub `/admin` quando a suíte
  inteira roda: `psycopg2.pool.PoolError` vira 500. Isso é do dono do banco (fila em vez de erro, ou pool maior
  por padrão); fica registrado no repasse.
