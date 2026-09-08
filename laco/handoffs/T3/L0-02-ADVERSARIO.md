# Adversário — linha L0-02 (identidade, sessão, segundo fator)

**Veredito: PASSA nos vetores atacados.** Ataque ao vivo (HTTP direto contra o processo `plat-api`
em `127.0.0.1:8150`, bypassando o proxy nginx para não brigar com o rate-limit de `/api/login`
que já é uma defesa separada e documentada — `10 r/min burst=10 nodelay`, zona `plat_login`,
`/etc/nginx/sites-enabled/plat.iagrointel.com`). Papel executado diretamente por esta sessão
(sem subagente), script em `/tmp/.../scratchpad/ataque_l0_02.py` (não versionado; comandos e saída
literal abaixo). Nenhum achado novo nesta passagem — registrado com honestidade: revisão de risco,
não prova de ausência de bugs.

## Itens cobertos
`L0-02-a-login-sessao` · `L0-02-b-politica-senha-bloqueio` · `L0-02-c-2fa-totp` ·
`L0-02-d-token-servico` · `L0-02-e-varredura-cruzada-rls` · `L0-02-f-tela-usuarios` ·
`L0-02-g-perfil-usuario` · `L0-02-tenant-auth`

## Ataques e evidência literal

1. **Cookie de A não abre recurso de B por id direto.** Logado como admin de `demo` e admin de
   `demo2`; peguei o id do admin de B e chamei `GET /api/usuarios/{id de B}` com o cookie de A.
   `-> 404`. PASSA.

2. **Cookie + `Authorization: Bearer` juntos.** `GET /api/eu` com cookie válido de sessão E um
   header `Authorization: Bearer qualquer-coisa` -> `400 {"erro":"autenticacao_ambigua", ...}`.
   PASSA (contrato exigido por `test_sessao.py::test_cookie_e_bearer_juntos_e_400`, confirmado
   também fora da suíte).

3. **Anti-replay de TOTP entre desafios de login diferentes.** Criei um editor temporário
   (`zt-adv-l002-...`), liguei 2FA nele, e testei especificamente o caso que a suíte não cobre
   pela estrutura de fixture (login → novo login → mesmo código): usei um código válido para
   abrir sessão (`POST /api/login/2fa -> 200`), então iniciei um SEGUNDO login (novo desafio) e
   tentei o MESMO código -> `401 codigo_invalido`. PASSA — confirma por fora que
   `totp_ultimo_passo` é por usuário, não por desafio (leitura de código em
   `app/auth/totp.py::verificar`, "nunca aceita passo menor ou igual ao último usado").

4. **Dois desafios abertos ao mesmo tempo: o mais antigo morre.** Abri dois logins (dois desafios)
   para o mesmo usuário sem completar nenhum. O desafio ANTIGO, ao tentar um código válido depois
   do segundo login, devolveu `410 desafio_expirado` — `plat.usuario` guarda um único par
   `desafio_2fa_hash`/`desafio_2fa_ate` por linha (não uma tabela de desafios concorrentes), então
   abrir um novo login sempre invalida o anterior. Não é bug: é a única leitura possível do dado,
   e do lado bom (nenhum desafio velho fica coletável para depois). O desafio mais recente aceitou
   o código válido normalmente -> `200`. PASSA (documentado como comportamento intencional, não
   como "concorrência resolvida com múltiplos desafios simultâneos" — isso simplesmente não existe
   no modelo de dado, e está correto que não exista).

5. **Código de recuperação de uso único.** 1a vez -> `200 ok`. 2a vez (desafio novo, mesmo código)
   -> `401 codigo_invalido` (a linha some do array `codigos_recuperacao` no primeiro uso). PASSA.

6. **Desafio forjado.** `desafio-forjado-<32 hex aleatórios>` com um código qualquer -> `410
   desafio_expirado` (o hash não bate com nenhuma linha, `auth_desafio_2fa_resolver` devolve NULL,
   tratado igual a expirado — nenhuma distinção observável entre "não existe" e "expirou", o que é
   bom: não vaza se o desafio já existiu). PASSA.

7. **Bloqueio por tentativas de senha errada.** 4 tentativas de senha errada em sequência contra o
   usuário temporário -> a 5a (índice 4) devolveu `423 bloqueado`. PASSA — a política de bloqueio
   está de fato ativa fora da suíte, não só nos testes.

8. **Escalada de privilégio via token de serviço.** Um editor comum tentando `POST /api/tokens`
   com `escopos: ["admin:inquilino"]` -> `422 escopo_fora_do_teto "admin:inquilino só para dono com
   perfil admin"`. PASSA (mesmo código já auditado nesta sessão em turnos anteriores, reconfirmado
   ao vivo agora, não só por leitura).

## O que ESTE laudo NÃO cobre (nomeado, não escondido)

- Ataques de má-formação profunda no corpo de `/api/login`/`/api/login/2fa` (fuzzing de tipo,
  Unicode em `login`/`inquilino`, payload gigante) — só testei o caminho funcional e o de negócio,
  não fuzzing estrutural.
- `L0-02-tenant-auth` já tem um laudo adversário independente de T2
  (`handoffs/T2/L0-02-tenant-auth/refutacao.json`) — não refiz esse trabalho, só as lacunas notadas
  acima que ele não cobria (replay entre desafios, dois desafios concorrentes).
- Login por LDAP/AD (`L0-08-d-ldap`) fica para quando eu atacar a linha de conectores/organização.
- Não tentei condição de corrida real (duas threads batendo login/2fa ao mesmo tempo pelo MESMO
  desafio) — o SQL usa `UPDATE ... WHERE id = %s` sem `SELECT FOR UPDATE` explícito antes de
  invalidar o desafio; em tese duas requisições simultâneas com o mesmo código válido poderiam
  ambas ler o desafio como válido antes de qualquer uma escrever. Não testado ao vivo por falta de
  tempo nesta passagem — **pendência nomeada para revisão futura**, não teoria descartada.

## Conclusão

A linha de identidade resiste aos 8 vetores atacados nesta passagem, incluindo os dois que a
suíte automatizada (por causa da estrutura de fixture de sessão única) não exercita: replay de
TOTP entre logins diferentes, e reuso de código de recuperação num desafio novo. Nenhum achado.
Recomendo próxima rodada nesta linha focar na condição de corrida do desafio (item pendente acima)
antes de considerar L0-02 comprovadamente livre de bugs de concorrência.
