---
id: tokens
titulo: Tokens de serviço
titulo_en: Service tokens
titulo_es: Tokens de servicio
resumo: "tokens com escopo, restrição de rede e validade para integrações sem navegador"
resumo_en: "tokens with scope, network restriction and validity for integrations without a browser"
resumo_es: "tokens con alcance, restricción de red y validez para integraciones sin navegador"
classe: tela
pagina: admin/tokens.html
caminho: /admin/tokens
e2e: tests/e2e/test_tokens.py
captura: L0-02-tenant-auth_tokens.png
e2e_captura: capturar("tokens")
palavras: [tokens, api, escopo, restricao, validade, integracao, servico, admin]
palavras_en: [tokens, api, scope, restriction, validity, integration, service, admin]
palavras_es: [tokens, api, alcance, restriccion, validez, integracion, servicio, admin]
---

## Tokens de serviço

A tela Tokens cria e gerencia tokens de serviço: credenciais para um programa chamar a API sem
navegador. Exige o privilégio `tokens.gerar`.

### Criar e usar

1. Escolha Novo token.
2. Dê um nome, escolha os escopos (famílias de rotas que o token alcança), a restrição de rede
   (lista de faixas de IP) e a validade.
3. O valor do token é mostrado uma única vez. A chamada leva o cabeçalho `Authorization: Bearer
   <token>`.

### Renovar, revogar e conferir acessos

Cada token lista as últimas chamadas aceitas e recusadas. Renovar troca o valor mantendo a
configuração; revogar desliga na hora. A validade nunca é infinita: o campo de validade é
obrigatório.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_tokens.py`) contra a versão atual.
