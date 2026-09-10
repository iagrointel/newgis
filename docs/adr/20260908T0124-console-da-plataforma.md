# Console da plataforma: um portal, N inquilinos (item L0-07-f-console-plataforma)

Data: 08/09/2026. Estado: aceito. Par: ADR 0002 seção 10 (superadmin resolvido pela sessão); `laco/decomposicao/L0_CONCEITO.md`.

## Contexto

O console mínimo da 003/029 (listar, criar, suspender, reativar, apagar) não bastava para operar a plataforma:
sem uso por inquilino, sem cotas alteráveis, suspensão muda (401 igual a sessão expirada), sem saída para o
administrador de inquilino que perdeu o segundo fator, sem visão da fila e sem a trilha do próprio operador.
A Esri resolve isso com um portal por organização; aqui é um portal com N inquilinos e um operador fora de
qualquer inquilino.

## Decisões

1. **Tudo continua atrás de `plat.plataforma_operador(hash da sessão)`.** Nenhuma função nova lê GUC, cookie ou
   `superadmin` da requisição; a API só repassa `auth.sessao_hash`. Cookie forjado = 401; sessão comum, token e
   anônimo = 404 em toda rota `/api/plataforma` (teste varre o OpenAPI).
2. **Suspensão é estado, não apagamento.** `tenant.ativo=false` + `config.suspensao {mensagem, em}`; sessões e
   tokens ficam no lugar. `plat.credencial_suspensa(hash)` roda SÓ no caminho de falha da autenticação e permite
   responder **503 `inquilino_suspenso` com a mensagem do operador** em login, sessão viva e token (antes: 503 no
   login, 401 mudo no resto). Reativar apaga a chave e a mesma sessão volta a funcionar.
3. **Cotas moram onde as funções `cota_*` já leem.** `cota_bytes` (coluna) e `config.cota_usuarios /
   cota_jobs_dia / cota_jobs_simultaneos / cota_agendas / catalogo.cota_itens`; `plat.cotas_aplicar` é a única
   escrita. Criação aceita cotas iniciais (assinatura nova de `tenant_criar`, a de 7 argumentos delega). O
   contador simétrico de bytes do L0-07-c substitui `sum(plat.arquivo.bytes)` quando entrar em master.
4. **Slugs reservados numa função só** (`plat.slug_reservado`), com os caminhos de página da raiz. O codinome do
   produto entra como `left('plataforma', 4)` porque a base de trilha reescreve o token literal do schema.
5. **2FA de administrador de inquilino desligado pelo operador**: só perfil admin (membro comum é atendido pelo
   admin do inquilino, 409), nunca no inquilino `plataforma` (409), sessões do alvo caem, evento com o login.
6. **Sem "entrar como".** A leitura de dados de outro inquilino continua pelo caminho já auditado
   (`X-Plat-Inquilino` + evento `inquilinos/leitura_superadmin`); `GET /api/plataforma/eventos` mostra só a
   trilha do inquilino `plataforma`.
7. **Tela `/plataforma`** entra no layout comum com entrada de navegação condicionada a `superadmin=true` do
   `GET /api/eu` (o menu não é segurança; a API é).

## Consequências

- `tests/api/test_login.py` passou a esperar 503 (não 401) na sessão viva de inquilino suspenso.
- `/conta` tinha três ouvintes de evento no nível do módulo em elementos que a tela de falha remove; passaram a
  encadeamento opcional (qualquer falha não-401 de `GET /api/eu` quebrava a página).
- e2e sem nginx: `tests/e2e/frente_estatica.py` serve `/static/` e troca o `Origin` pela URL pública (a mesma
  troca que o domínio real faz sozinho).
