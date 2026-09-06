# Manual do `plat`

Uma seção por tela ou operação, sempre com a captura real produzida pelo teste e2e do item (arquivo em
`tests/e2e/capturas/`, fora do git, regravado a cada `make e2e`). Este manual descreve o que existe no repositório no
fim do turno 2 do laço PLATAFORMA ENTERPRISE (setembro de 2026): saúde e instalação (turno 1), identidade e acesso
(item L0-02) e fila de trabalhos (item L0-05). O que o produto ainda não faz está em
`/home/dev/plataforma/laco/PAINEL.md` e na seção final de `ARQUITETURA.md`, não aqui.

Estado: análise / beta privado. A URL é interna, marcada `noindex`, e não deve ser linkada de lugar público.

Números citados vêm de `tests/medidas/L0-01-repo.json`, `tests/medidas/L0-02-tenant-auth.json` e
`tests/medidas/L0-05-jobs.json` (os dois últimos gerados às 17:28 UTC de 05/09/2026 sobre o commit `90d03c0`), com o
comando que os produziu. Nenhum número foi digitado de cabeça.

---

## 1. Acesso e saúde do serviço

### 1.1 URL interna

`https://plat.iagrointel.com`. HTTP redireciona para HTTPS (301). A página inicial (`/`) e as rotas de saúde são
públicas para quem conhece o endereço e não devolvem dado de inquilino. Toda outra tela exige sessão (seção 2).

Captura do e2e (`tests/e2e/capturas/L0-01-repo_inicio.png`, gerada por `tests/e2e/test_saude_pagina.py`): o nome
`plat`, o aviso "análise / beta privado", o painel `versão` (`VERSAO`, commit, ambiente, lidos de `/api/versao`) e o
painel `saúde` com o JSON de `/saude`. Sem sessão a página mostra o link "Entrar"; com sessão mostra a barra lateral
e os atalhos das telas (seção 2.4).

### 1.2 O que `/saude` devolve

`GET https://plat.iagrointel.com/saude` (também `HEAD`), sem autenticação. Resposta ao vivo em 05/09/2026:

```json
{
  "versao": "0.1.0",
  "git_sha": "abbb03d02920",
  "ambiente": "producao",
  "banco": "ok",
  "migracoes_aplicadas": 10,
  "migracoes_pendentes": 0,
  "ultima_migracao": "011_catalogo",
  "servicos": {"martin": "ausente", "titiler": "ausente", "garage": "ok", "worker": "ok"},
  "fila": {"pendentes": 5, "rodando": 1, "workers_vivos": 1, "ultimo_heartbeat": "2026-09-05T17:36:51Z"},
  "tempo_ms": 3.7,
  "em": "2026-09-05T17:36:58Z"
}
```

| campo | como ler |
|---|---|
| `versao` | conteúdo do arquivo `VERSAO`. Deve ser igual ao `versão` da tela e ao `CHANGELOG.md`. |
| `git_sha` | commit em execução. Compare com `git -C /home/dev/plataforma/enterprise rev-parse --short=12 HEAD`. Se diferir, alguém comitou sem reiniciar: `sudo systemctl restart plat-api`. |
| `banco` | `ok` = banco respondeu e todas as migrações de `db/migracoes/` estão aplicadas; `desatualizado` = há arquivo sem registro (rode `sudo bash install.sh plat.iagrointel.com 8150`); `erro` = banco não respondeu (`journalctl -u plat-api -o cat`). |
| `migracoes_*` | contagem em `plat.versao_migracao` contra os arquivos em disco. Pendentes tem de ser 0. |
| `servicos` | `martin` e `titiler` continuam `ausente` (serviços inexistentes, portas 8151 e 8152 reservadas); `garage` é o armazenamento de objetos já ativo na máquina; `worker` sonda `http://127.0.0.1:8153/saude` do `plat-worker`. Nenhum dos quatro muda o status HTTP. |
| `fila` | lido de `plat.fila_estado()`: jobs pendentes e rodando no banco inteiro, workers com heartbeat recente e o instante do último heartbeat. `workers_vivos = 0` significa que a unidade `plat-worker` está parada ou sem sinal há mais de 90 s. |
| `tempo_ms`, `em` | tempo da rota e instante da resposta (UTC). |

HTTP **200 só com `banco = ok`**; `desatualizado` e `erro` devolvem **503** com o mesmo JSON.

`GET /api/versao` devolve só `versao`, `git_sha`, `ambiente` e `em`, sem tocar o banco.

### 1.3 Conferência rápida pela linha de comando

```
curl -sS https://plat.iagrointel.com/saude | python3 -m json.tool     # 200, banco ok, fila.workers_vivos >= 1
curl -s http://127.0.0.1:8153/saude | python3 -m json.tool              # saúde do worker (só na própria máquina)
systemctl status plat-api plat-worker --no-pager | grep -E 'Active|Main'
journalctl -u plat-api -o cat -n 20 | jq .                            # linhas JSON
journalctl -u plat-worker -o cat -n 20 | jq .
```

---

## 2. Entrar

### 2.1 A tela `/entrar`

Captura `tests/e2e/capturas/L0-02-tenant-auth_login.png` (gerada por `tests/e2e/test_login.py`,
`test_login_com_senha_entra_e_mostra_barra`): cartão centrado com o nome `plat`, o aviso "análise / beta privado",
a linha "Entrar em: Inquilino de demonstração", os campos `usuário` e `senha` (com o botão `mostrar`), o botão
`Entrar` e o texto "Esqueceu a senha? Peça ao administrador do seu inquilino."

O inquilino vem da URL: `/entrar?inquilino=demo`. A tela chama `GET /api/login/provedores?inquilino=demo` e mostra o
nome do inquilino; inquilino inexistente aparece como erro. O último inquilino usado fica no `localStorage`
(`plat_inquilino`), e é ele que a plataforma usa quando uma tela protegida redireciona para `/entrar` sem parâmetro.
`?proximo=/caminho` leva o usuário de volta à tela que pediu a sessão; só caminhos relativos que começam por `/` e
não por `//` são aceitos.

Não há "esqueci a senha" automático: a redefinição é feita pelo administrador do inquilino na tela Usuários
(seção 4.3). Não há auto-cadastro. A área de provedores externos existe na tela, mas `provedores` vem vazio: login
por SAML, OpenID Connect ou LDAP é o item L0-08, fora deste turno.

### 2.2 Senha errada e bloqueio

Captura `tests/e2e/capturas/L0-02-tenant-auth_login_erro.png` (`test_senha_errada_mostra_mensagem_e_nao_entra`): a
mesma tela com a faixa vermelha "inquilino, usuário ou senha inválidos". A mensagem é a mesma para usuário
inexistente e para senha errada, e o tempo de resposta também: a API confere a senha contra um hash fixo quando o
usuário não existe. Medido pelo testador (`testador_tempo_constante_ms`): mediana de 121,7 ms para usuário
inexistente contra 123,2 ms para senha errada, 6 tentativas de cada, direto no uvicorn.

Cinco falhas em 15 minutos bloqueiam o usuário por 15 minutos; a sexta tentativa, mesmo com a senha certa, devolve
`423 bloqueado` com o instante em que o bloqueio termina, e a tela mostra "usuário bloqueado até <hora>". Falhas de
código do segundo fator contam no mesmo contador. O desbloqueio vem pelo tempo ou pelo botão `Desbloquear` na tela
Usuários. Os limites (5 tentativas, 15 minutos) são o padrão da plataforma e podem ser mudados por inquilino em
`tenant.config.auth` (`bloqueio_tentativas` entre 3 e 10, `bloqueio_minutos` entre 5 e 60); a tela para alterar essa
configuração é o item L0-07-a, ainda não construído, e hoje a mudança se faz na criação do inquilino ou por SQL.

Além do bloqueio por usuário, o nginx limita `POST /api/login` e `POST /api/login/2fa` a 10 pedidos por minuto por
endereço IP, com rajada de 10; acima disso a resposta é `429` em HTML do nginx (não JSON). Medido pelo testador de
outro endereço IP (`testador_nginx_login_10rpm`): 25 pedidos em 15 s deram 401 até esgotar a rajada e 429 depois.
`GET /api/eu` e as demais rotas não têm esse limite.

### 2.3 Segundo fator no login

Quando o usuário tem o segundo fator ligado (seção 3.3), a senha certa não cria sessão: a resposta é
`{"ok": false, "exige_2fa": true, "desafio": ...}` e a tela troca o formulário de senha pelo de código sem
recarregar. O código vem do aplicativo autenticador (TOTP, 6 dígitos, janela de 30 s, tolerância de um passo para
cada lado). O botão "usar código de recuperação" alterna para um dos oito códigos gerados ao ligar o fator; cada
código de recuperação vale uma entrada. O desafio expira em 5 minutos (a tela mostra o contador); expirado,
`410 desafio_expirado`, e o usuário volta à senha. O mesmo código TOTP não entra duas vezes (proteção contra
repetição por `totp_ultimo_passo`).

### 2.4 Depois de entrar

O login cria o cookie `plat_sessao` (`HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800`) e redireciona para
`/` ou para `?proximo=`. A sessão vale 7 dias no máximo e expira depois de 12 horas sem uso (padrão; por inquilino
`sessao_max_dias` de 1 a 30 e `sessao_ociosa_horas` de 1 a 24). A página inicial passa a mostrar a barra lateral com
os itens Início, Minha conta, Usuários, Grupos, Tarefas, Papéis, Tokens e Log; cada item aparece só quando a sessão
tem o privilégio correspondente (`membros.ver`, `jobs.executar`, `papeis.gerir`, `tokens.gerar`, `org.log_ver`;
Grupos e Minha conta aparecem sempre). No rodapé da barra ficam o nome, o login e o perfil do usuário e o botão
`Sair` (`POST /api/logout`, `204`, cookie apagado; a saída é registrada no log de acesso com `resultado = logout`).

Se a conta tem pendência (senha temporária ou segundo fator exigido pelo inquilino), toda tela redireciona para
`/conta#senha` ou `/conta#2fa` até a pendência ser resolvida; a API responde `403 pendencia` fora das rotas de conta.

Latência medida (`latencia_login_ms`): mediana de 128,6 ms por `POST /api/login` no TestClient, 3 chamadas; o custo é
do hash pbkdf2 com 600.000 iterações. Pela URL pública, 3 chamadas individuais deram 142,9, 141,7 e 146,0 ms
(`testador_login_ms_3_nginx`). Página `/entrar` pronta em 54,3 ms no chromium do playwright (`pagina_pronta_ms_login`).

---

## 3. Minha conta (`/conta`)

Captura `tests/e2e/capturas/L0-02-tenant-auth_conta.png` (`tests/e2e/test_conta.py`,
`test_pendencia_de_senha_troca_e_sessoes`): cartões Dados, Senha, Segundo fator (desligado, botão `Ligar`), Sessões
(duas sessões listadas com data de criação, último uso, expiração, IP e navegador; a atual marcada `atual`, a outra
com o botão `Encerrar`; abaixo, `Encerrar as outras`), Convites (vazio) e Tokens de serviço (link para a tela Tokens).

### 3.1 Dados

`login` e `perfil` são só leitura (o perfil é o administrador quem muda, seção 4). `nome` e `e-mail` são editáveis
(`PUT /api/eu`); e-mail fora dos domínios permitidos pelo inquilino (`dominios_email`) é recusado com
`422 email_dominio`. O detalhe `privilégios` lista os privilégios da sessão.

### 3.2 Senha

Exige a senha atual e a nova (`PUT /api/eu/senha`). A regra aparece abaixo do campo e é conferida no servidor:
pelo menos 8 caracteres com letra e número (padrão da plataforma; o inquilino pode exigir maiúscula, minúscula,
símbolo e comprimento maior); no máximo 128; diferente do login; diferente das 5 últimas. A recusa nomeia a regra
(`detalhe.regra` em `minimo`, `composicao`, `maximo`, `igual_login`, `historico`). A troca encerra as outras sessões
do usuário e mantém a atual; a tela avisa "senha trocada; as outras sessões foram encerradas". Quando a senha é
temporária (criada ou redefinida pelo administrador), a tela abre com o aviso de pendência e só libera o resto
depois da troca.

### 3.3 Segundo fator

Captura `tests/e2e/capturas/L0-02-tenant-auth_2fa.png` (`tests/e2e/test_2fa.py`,
`test_ligar_entrar_com_codigo_e_desligar`): o cartão "Segundo fator" com a marca `ligado`, a frase "segundo fator
ligado: a entrada pede senha e código do aplicativo autenticador. 8 códigos de recuperação restantes", os oito
códigos de recuperação em caixas (formato `xxxx-xxxx-xx`), o botão `Copiar`, `Gerar novos códigos` e `Desligar`.

Fluxo: `Ligar` chama `POST /api/eu/2fa/iniciar` e mostra o QR (SVG gerado no servidor), o segredo em texto e o campo
do primeiro código; `POST /api/eu/2fa/confirmar {codigo}` liga o fator e devolve os oito códigos de recuperação, que
aparecem uma única vez. `Desligar` exige senha e código atual; se o inquilino exige segundo fator
(`exigir_2fa = true`), a resposta é `409 2fa_obrigatorio` e o fator não se desliga. `Gerar novos códigos` exige a
senha. O segredo fica cifrado no banco (AES-GCM com chave derivada de `PLAT_SECRET`, prefixo `enc:v1:`).

Na captura, as seções Sessões e Convites mostram a faixa "disponível depois de resolver a pendência da conta": o
usuário do teste acabou de ligar o fator num inquilino que o exige, e a tela libera essas seções depois. O testador
encontrou nessa mesma captura uma chave de tradução crua (`conta.apos_pendencia`), corrigida no commit `7c62831`;
a captura atual, regravada às 17:26 UTC, já mostra o texto traduzido.

### 3.4 Sessões e convites

`GET /api/eu/sessoes` lista as sessões do usuário (id exibido = 12 primeiros hexadecimais do hash, nunca o valor do
cookie). `Encerrar` apaga uma; `Encerrar as outras` apaga todas menos a atual (`DELETE /api/eu/sessoes?outras=1`).
Uma sessão encerrada recebe `401 sessao_expirada` na chamada seguinte. Convites de grupo pendentes aparecem no
cartão Convites com `Aceitar` e `Recusar` (seção 5).

Página pronta em 37,8 ms (`pagina_pronta_ms_conta`); a tela do teste de 2FA, em 9,7 ms (`pagina_pronta_ms_2fa`).

---

## 4. Usuários (`/admin/usuarios`)

Exige o privilégio `membros.ver`; os botões de escrita aparecem com `membros.gerir` (nome, e-mail, ativo, senha,
segundo fator, desbloqueio) e `membros.papel` (perfil e papel).

Captura `tests/e2e/capturas/L0-02-tenant-auth_usuarios.png` (`tests/e2e/test_usuarios.py`,
`test_usuarios_criar_editar_lote_e_ultimo_admin`): título "Usuários (3)", filtros `perfil` e `estado`, busca por
login, nome ou e-mail (o teste filtrou por `e2e_u`), tabela com colunas login · nome · perfil · papel · 2FA · último
acesso · IP · estado e, por linha, os botões `Editar`, `Redefinir senha`, `Desabilitar` e `Apagar`; caixa de seleção
por linha para ação em lote; rodapé "recomendação: mantenha dois administradores ativos; o bloqueio por senha vale
para administradores".

### 4.1 Criar

`Novo usuário` abre o painel lateral com login (só `a-z`, `0-9`, `.`, `_`, `@`, `-`, minúsculas), nome, e-mail,
perfil (`admin`, `editor`, `visualizador`, `campo`) e papel personalizado opcional. A resposta traz a senha
temporária, mostrada uma única vez ("senha temporária de <login>; o usuário troca no primeiro acesso"). Só um
administrador cria outro administrador (`403 so_admin_cria_admin`). Login repetido no inquilino: `409 login_existente`.

### 4.2 Editar, desabilitar, apagar

`Editar` altera nome, e-mail, perfil, papel e estado. Regras que a API aplica e a tela mostra com a mensagem
recebida: o último administrador ativo não se desabilita, não se rebaixa nem se apaga (`409 ultimo_admin`); ninguém
desabilita a própria conta (`409 proprio_usuario`); só administrador altera administrador
(`403 so_admin_altera_admin`); quem possui grupos não é rebaixado nem apagado antes de transferir os grupos
(`409 possui_grupos`, com a lista dos grupos). Desabilitar apaga as sessões do usuário na hora; `Reabilitar` desfaz.
`Apagar` pede confirmação e não tem volta.

### 4.3 Redefinir senha, desligar segundo fator, desbloquear

`Redefinir senha` (`POST /api/usuarios/{id}/senha`) gera uma senha temporária de 12 caracteres, mostrada uma vez,
marca `trocar_senha` e apaga as sessões do usuário. `Desligar 2FA` (`POST .../2fa/desativar`) apaga segredo e
códigos e as sessões; se o inquilino exige o fator, o usuário entra com a pendência de configurá-lo de novo.
`Desbloquear` (`POST .../desbloquear`) zera o contador de falhas e o bloqueio.

### 4.4 Ação em lote

Selecionando até 100 linhas aparecem as ações `Mudar perfil`, `Desabilitar`, `Reabilitar` e papel
(`POST /api/usuarios/lote`). A resposta diz quantos foram alterados e lista os recusados com o motivo (por exemplo
o último administrador). Acima de 100: `422 lote_acima_de_100`.

Página pronta em 59,4 ms (`pagina_pronta_ms_usuarios`).

---

## 5. Grupos (`/admin/grupos`)

Qualquer usuário do inquilino vê a tela; criar grupo exige `grupos.criar`; `grupos.gerir_todos` (administrador)
alcança todos os grupos.

Captura `tests/e2e/capturas/L0-02-tenant-auth_grupos.png` (`tests/e2e/test_grupos.py`,
`test_grupo_criar_convidar_aceitar_sair_apagar`): abas "Meus grupos" e "Do inquilino", tabela com nome · resumo ·
membros · meu papel, e o painel lateral do grupo aberto na aba "Membros": o dono (`Administrador demo`, estado
`ativo`) e um convidado (estado `convidado`, botão `Remover`), a faixa verde "e2e_g_ef1e3b convidado" e, abaixo, o
formulário `Convidar` com busca de usuário e escolha do papel (`membro` ou `gerente`).

Um grupo tem nome, resumo, marcações, visibilidade, forma de entrada (`convite`, `pedido` ou `livre`), contribuição,
as marcas `atualização compartilhada` (só na criação), `administrativo` e `protegido`, e um dono. Papéis dentro do
grupo: dono, gerente e membro. O dono e os gerentes convidam (`POST /api/grupos/{id}/membros`) e aprovam pedidos; o
convidado aceita ou recusa na tela Minha conta; em grupo de entrada livre `Entrar` é imediato, em grupo por pedido
fica `pedido` até aprovação. O dono não sai do próprio grupo (`409 dono_nao_sai`): transfere antes. Membro não sai de
grupo administrativo; grupo protegido não se apaga (`409 grupo_protegido`). Cada usuário pode pertencer a até 512
grupos.

O compartilhamento de conteúdo por grupo é do item L0-03 (catálogo), em construção; neste turno a tela gere só a
composição dos grupos. Página pronta em 60,8 ms (`pagina_pronta_ms_grupos`).

---

## 6. Papéis e privilégios (`/admin/papeis`)

Exige `papeis.gerir`. Captura `tests/e2e/capturas/L0-02-tenant-auth_papeis.png` (`tests/e2e/test_papeis.py`,
`test_papel_criar_editar_apagar`): cartão "Perfis (teto de privilégios)" com os quatro perfis e a contagem de
privilégios (administrador 46, dos quais 20 administrativos; editor 26; visualizador 7; campo 11) e o botão `Ver`;
cartão "Papéis personalizados" com nome · descrição · perfil mínimo · privilégios · usuários e os botões `Editar` e
`Apagar`; faixa verde "papel Curador E2E c5ec1c criado".

Como funciona: o perfil do usuário define o teto de privilégios; o papel personalizado é um subconjunto do teto,
criado com nome, descrição e a lista de privilégios (vocabulário fechado de 46 nomes, consultável em
`GET /api/privilegios`). O servidor calcula o `perfil mínimo` do papel (um privilégio administrativo obriga perfil
`admin`); usuário com perfil abaixo do mínimo não recebe o papel (`422 papel_incompativel`). Quem cria um papel só
concede privilégios que a própria sessão tem (`403 privilegio_proprio_insuficiente`). Papel em uso não se apaga
(`409 papel_em_uso`). Toda rota da API pergunta por privilégio, nunca por perfil; a lista de privilégios da sessão
está em `GET /api/eu`.

Página pronta em 58,7 ms (`pagina_pronta_ms_papeis`).

---

## 7. Tokens de serviço (`/admin/tokens`)

Exige `tokens.gerar` (todo perfil tem); a caixa "todos do inquilino" aparece com `tokens.gerir_todos`.

Captura `tests/e2e/capturas/L0-02-tenant-auth_tokens.png` (`tests/e2e/test_tokens.py`,
`test_token_criar_usar_acessos_revogar`): título "Tokens de serviço (78)" com a caixa "todos do inquilino" marcada,
tabela com nome · dono · prefixo · escopos · expira em · último uso · IP · restrições · estado, e por linha os
botões `Acessos`, `Renovar` e `Revogar` (os dois últimos só em token válido). A lista longa da captura é resíduo das
suítes de teste do dia (`zt-tok`, `zt-cruzado`), quase todos já revogados; o rodapé diz "o token aparece uma única
vez, na criação e na renovação; revogação vale na hora".

### 7.1 Criar e usar

`Novo token` pede nome, escopos (caixas), validade em dias e restrições opcionais de origem (`referer`, até 20
entradas, `*.` casa só subdomínios) e de IP (até 20 redes ou endereços). O valor (`plat_` mais 43 caracteres) aparece
uma única vez. Validade padrão 90 dias, máximo 365 (`400 validade_acima_do_maximo` acima disso; o inquilino pode
baixar o máximo em `token_max_dias`). Até 20 tokens ativos por usuário.

Uso: `Authorization: Bearer <token>` nas rotas `/api/`. O parâmetro `?token=` não é aceito em `/api/` (responde 401 e
o valor é redigido do log); ele fica reservado às rotas `/svc/`, `/ogc/` e `/tiles/`, que ainda não existem. Um token
tem no máximo os privilégios do dono restritos aos escopos escolhidos: `catalogo:ler`, `camada:ler[:uuid]`,
`camada:editar[:uuid]`, `tiles:ler[:uuid]`, `jobs:executar`, `admin:inquilino` (este só para dono `admin`). Escopo
insuficiente devolve `403 escopo_insuficiente` com o exigido e o que o token tem. Um token não cria nem revoga
tokens, não troca senha, não mexe no segundo fator e não lista sessões (`403 so_sessao`). Dono desabilitado, com
pendência ou inquilino suspenso invalida o token na hora.

### 7.2 Renovar, revogar, acessos

`Renovar` cria um token novo com os mesmos escopos, restrições e validade e encurta o antigo para 24 horas
(os dois valem nesse intervalo). `Revogar` grava `revogado_em`; a chamada seguinte recebe `401 token_revogado` com
a data. Medido: 0,01 s entre o `DELETE` e o 401 no TestClient (`tempo_revogacao_s`), 0,02 s pela URL pública
(`testador_token_revogado_s`) e 6,2 ms no e2e (`tempo_revogacao_ms_e2e`). `Acessos` abre `GET /api/tokens/{id}/log`:
as linhas do log de acesso daquele token, com IP, rota, status e bytes. Custo da autenticação por token: 3,0 ms
(`latencia_auth_token_ms`, mediana de 50 `GET /api/eu` com Bearer menos a mediana de `GET /api/versao`).

Página pronta em 78,9 ms (`pagina_pronta_ms_tokens`).

---

## 8. Log de acesso (`/admin/log`)

Exige `org.log_ver`. Captura `tests/e2e/capturas/L0-02-tenant-auth_log.png` (`tests/e2e/test_log_acesso.py`,
`test_log_filtro_csv_e_eventos`): título "Log de acesso (9.947)", abas "Acessos" e "Eventos", filtros período (7 d),
usuário, token, "rota começa com" e status (2xx), botões `Filtrar` e `Exportar CSV`, tabela com quando · usuário ·
token · IP · método · rota · status · bytes · ms · resultado (na captura: `POST /api/login` com resultado `ok`,
`POST /api/logout` com `logout`, e as chamadas de leitura do próprio teste), paginação "1–50 de 9.947" e o rodapé
"retenção: 12 meses; exporte antes".

O que se grava: uma linha por requisição autenticada ou de autenticação (inclusive 401, 403 e 404), com inquilino,
usuário ou token, IP, método, rota (query com `token`, `senha`, `codigo` e `desafio` substituídos por
`<redigido>`), status, bytes do corpo enviado, tempo e navegador. Não geram linha: `/saude`, `/api/versao`, `/`,
`/api/docs`, `/api/openapi.json` e `/static/`. Custo por requisição medido: 0,66 ms (`custo_log_acesso_ms`,
mediana de 30 `GET /api/eu` com e sem a gravação).

Filtros de `GET /api/log`: `usuario_id`, `token_id`, `rota` (prefixo), `status` (código ou classe `4xx`), `desde` e
`ate` (padrão 7 dias, janela máxima 92 dias, `422` acima), `limite` até 1.000. `Exportar CSV` baixa
`formato=csv` com as mesmas colunas, até 100 mil linhas. A aba Eventos lista `GET /api/eventos`: os eventos de
domínio do inquilino (entrar, sair, criar usuário, mudar papel, convidar, criar token, revogar e os demais do
vocabulário de `plat.evento_tipo`) com ator, alvo, propriedades (nunca senha, token ou código), IP e `req_id`.
Retenção de 12 meses por partição mensal; o expurgo automático é registrado como periódico no item L0-05-d, ainda
não agendado (hoje a função `plat.log_expurgar` existe e o `install.sh` cria as partições de 4 meses).

Página pronta em 73,7 ms (`pagina_pronta_ms_log`).

---

## 9. Tarefas (`/tarefas`)

Exige o privilégio `jobs.executar`. Quem tem `jobs.gerir_todos` (administrador) vê todos os jobs do inquilino e o
filtro `quem`; os demais veem só os próprios. A seção Agendas aparece para `admin` e `editor`.

### 9.1 Lista

Captura `tests/e2e/capturas/L0-05-jobs_lista.png` (`tests/e2e/test_tarefas.py`,
`test_lista_progresso_ao_vivo_e_detalhe`): cabeçalho "Tarefas" com o resumo "0 na fila · 1 rodando · 358 concluídas
em 24 h · 28 falhas em 24 h"; cartão `filtros` (estado, tipo, quem, período, `limpar`); cartão `tarefas` com
"412 tarefas" e a marca `1 ao vivo`; tabela estado · tipo · quem · criado · duração · progresso · ações, com a
primeira linha `rodando prova.progresso admin hoje 17:27 00:12` e a barra "20 % · passo 6 de 30" e o botão
`cancelar`; linhas `cancelado` ("cancelado pelo usuário"), `concluído` ("100 %") e `falhou` com o motivo em vermelho
("devolvido 5 vezes sem terminar (worker sem sinal)", "memória excedida (limite 256 MB)", "falha definitiva de
prova"); paginação "1–50 de 412" e `exportar CSV da página`; cartão `agendas` vazio com `nova agenda`. O item
Tarefas da barra lateral mostra o número de jobs ativos.

A lista se atualiza sem recarregar: cada job pendente ou rodando visível tem uma assinatura SSE
(`GET /api/jobs/{id}/eventos`) que traz estado, progresso e mensagem conforme mudam; o resumo é relido a cada 10 s
e, quando o número de ativos muda, a primeira página é relida (uma linha nova criada pela API aparece em até 10 s
mais a carga; medido 10,3 s, `linha_nova_aparece_s`). Acima de 10 assinaturas por página, ou depois de dois erros
seguidos do `EventSource`, a tela cai para consulta a cada 3 s e avisa. Durante um job de 60 s o e2e observou dois
valores distintos de progresso na linha (`progresso_valores_distintos`). Página pronta em 142,9 ms
(`pagina_tarefas_pronta_ms`).

### 9.2 Detalhe, log, cancelar, repetir

Captura `tests/e2e/capturas/L0-05-jobs_detalhe.png`: o painel à direita com `prova.progresso · concluído`, "100 % ·
tentativa 1 de 3 · worker <nome do host> · criado 05/09/2026 17:27:38 · iniciado 17:27:38 · 01:00", a mensagem
"passo 30 de 30", o `id`, os botões `repetir` e `baixar log`, os blocos `parâmetros` (`{"chave": null, "passos": 30,
"duracao_s": 60}`), `resultado` (`{"passos": 30, "marcador": "<uuid>", "duracao_s": 60}`), `proveniência`
(recolhido) e `log 11 linhas` com filtro de nível e as linhas `INFO início: 30 passos em 60 s ...`, `passo 3 de 30`,
`passo 6 de 30`, `passo 9 de 30`.

O detalhe abre por clique na linha ou pela URL `/tarefas/<id>`; assina o SSE do job e anexa as linhas de log
conforme chegam (`Last-Event-ID` recupera as perdidas numa reconexão). `cancelar` pede confirmação e trava o botão
até o evento de estado: job pendente vira `cancelado` na hora; job rodando recebe o pedido e a tarefa o atende no
próximo passo. Medido: 0,426 s do pedido ao estado `cancelado` num `prova.progresso` rodando (`cancelamento_s`) e
0,24 s pela tela (`cancelamento_tela_s`); uma tarefa que ignora o pedido é encerrada pelo worker com SIGTERM aos
30 s e SIGKILL 10 s depois (medido 40,5 s, `cancelamento_forcado_s`). `repetir` cria um job novo com os mesmos
parâmetros e `proveniencia.repetido_de`; job em estado final não muda mais (`409`). `baixar log` salva até 2.000
linhas em texto. Quando o resultado traz `item_id`, o painel mostra o link para o item (o catálogo é o item L0-03).

Estados: `pendente`, `rodando`, `concluido`, `falhou`, `cancelado`. `tentativa` conta execuções que falharam por
exceção da tarefa (retentativa em 2, 4 e 8 s, até 3 por padrão); `reinicios` conta devoluções por reinício ou
silêncio do worker, que não consomem tentativa. O job de 5 minutos do portão foi medido pelo testador
(`tempo_job_5min_s` 300,4 s, 62 eventos de estado, intervalo máximo entre heartbeats 5,0 s, latência do heartbeat ao
cliente 0,065 s; primeiro evento pela URL pública em 0,022 s, `sse_primeiro_evento_publico_s`). Reinício do worker no
meio do job: o job volta a `pendente` com `reinicios = 1` e é retomado em 1,0 s (`reinicio_retomada_s`); depois de 5
devoluções sem terminar fica `falhou` ("devolvido 5 vezes sem terminar").

### 9.3 Tipos de tarefa disponíveis

`GET /api/jobs/tipos` lista o registro. Neste turno existem os tipos de diagnóstico `prova.progresso` (N passos com
progresso, log e marcador de fim), `prova.memoria` (aloca N MB para provar o limite), `prova.falha`,
`prova.ignora_cancelamento`, `prova.pesado` (só um por vez na máquina), `prova.tempo_esgotado`, e o periódico
`jobs.expurgo` (só administrador). Tipos de ingestão, geoprocessamento, imagem e exportação entram com as linhas que
os usam (L0-04, L1, L2, L3). Criar um job: `POST /api/jobs {"tipo", "parametros", "prioridade"?, "agendado_para"?}`;
parâmetros inválidos devolvem `422` com o detalhe por campo; perfil abaixo do mínimo do tipo `403`; cota diária do
inquilino esgotada `413` (padrão 1.000 por dia; os inquilinos de demonstração têm 100.000); mais de 200 pendentes
`429`.

### 9.4 Agendas

Captura `tests/e2e/capturas/L0-05-jobs_agendas.png` (`test_agendas_criar_pausar_retomar_apagar`): cartão `agendas`
com "1 agenda", tabela nome · tipo · cron · fuso · próxima · última e a linha `e2e 789c8ff0 · prova.progresso ·
0 3 * * * · America/Sao_Paulo · 06/09 06:00` com os botões `rodar agora`, `pausar`, `editar` e `apagar`.

`nova agenda` pede nome, tipo, parâmetros (JSON validado no navegador contra o esquema do tipo e no servidor),
expressão cron de 5 campos e fuso IANA. Regras: intervalo mínimo de 15 minutos entre ocorrências (`422`), até 50
agendas por inquilino (`413`), nome único (`409`). O relógio é o próprio worker, a cada 30 s: enfileira a ocorrência
vencida mais recente (não recupera atraso) e avança `proxima_em`. Cinco falhas seguidas pausam a agenda. `rodar agora`
cria um job imediatamente. A cota diária de jobs vale também para as agendas.

---

## 10. Administração da plataforma (superadmin e inquilinos)

Não há tela neste turno: o console do operador é o item L0-07-f. O que existe é a API.

- O operador da plataforma é um usuário do inquilino técnico `plataforma` com `superadmin = true`. Entra por
  `/entrar?inquilino=plataforma`, com senha e, obrigatoriamente, segundo fator (o inquilino `plataforma` nasce com
  `exigir_2fa = true` e não o desliga). O `install.sh` semeia `plataforma/admin` com senha em
  `tests/credenciais.txt` (modo 600) e reinicia o segundo fator dele a cada instalação.
- `GET /api/plataforma/inquilinos` lista os inquilinos (id, slug, nome, ativo, usuários, criação, último acesso);
  `POST /api/plataforma/inquilinos {slug, nome, config?, admin_login, admin_nome}` cria um inquilino com o
  administrador inicial e devolve a senha temporária uma única vez; `POST .../{id}/suspender` e `.../reativar`
  (inquilino suspenso responde `503 inquilino_suspenso` no login e invalida tokens); `DELETE .../{id}` apaga o
  inquilino inteiro (usuários, grupos, tokens, jobs, agendas, log), recusando `plataforma` (`409`). Para quem não é
  superadmin todas essas rotas respondem `404`, sem confirmar que existem.
- `config` do inquilino (`tenant.config.auth`): `senha_min`, `senha_maiuscula`, `senha_minuscula`, `senha_simbolo`,
  `senha_historico`, `senha_expira_dias`, `bloqueio_tentativas`, `bloqueio_minutos`, `sessao_ociosa_horas`,
  `sessao_max_dias`, `exigir_2fa`, `token_max_dias`, `token_padrao_dias`, `dominios_email`, `compartilhar_publico`;
  padrões e faixas em `app/limites.py`. Valor fora da faixa é cortado para a faixa na leitura, nunca para uma
  política mais fraca que o padrão. A tela para editar isso depois de criado é o L0-07-a. O testador provou a
  configuração criando um inquilino com `sessao_max_dias = 1`, `sessao_ociosa_horas = 1`, `token_max_dias = 2` e
  `bloqueio_tentativas = 3` e observando a sessão de 1 dia, a validade recusada acima de 2 dias e o bloqueio na
  terceira tentativa (`40_testes.md`, seção 2e).
- Leitura de um inquilino pelo superadmin sem entrar nele: cabeçalho `X-Plat-Inquilino: <slug>` em `GET /api/log` e
  `GET /api/usuarios`, em transação só de leitura, com o evento `inquilinos/leitura_superadmin` gravado no inquilino
  lido. Sessão que não é de superadmin recebe `403 so_superadmin`.
- Cotas de jobs por inquilino em `tenant.config`: `cota_jobs_simultaneos` (padrão 2), `cota_jobs_dia` (1.000),
  `cota_agendas` (50).

---

## 11. Instalação e atualização

### 11.1 Comando

```
cd /home/dev/plataforma/enterprise
sudo bash install.sh plat.iagrointel.com 8150
```

Idempotente: roda em máquina nova e roda de novo depois de cada `git pull`. É o único caminho de instalação e
atualização.

### 11.2 O que ele cria (passos a-j)

| passo | o quê |
|---|---|
| a-c | mostra a máquina; extensões `postgis` e `pgcrypto`; migrações de `db/migracoes/` por `db/migrar.sh` (sha256 por arquivo, uma transação por arquivo; arquivo aplicado que mudou = parada com código 3) |
| d | `.env` (modo 600) com senha da role `plat_app`, `PLAT_SECRET`, ambiente, URL pública, `PLAT_GIT_SHA`, `PLAT_WORKER_URL`, `PLAT_WORKER_PROCESSOS=1`, `PLAT_WORKER_MEMORIA_MB=1536` e `PLAT_DSN_WORKER` (role `plat_worker`); as senhas das duas roles são realinhadas ao `.env` a cada execução |
| e | linhas `host iagro_sat plat_app 127.0.0.1/32 scram-sha-256` e a equivalente de `plat_worker` no `pg_hba.conf`, uma vez cada, e `pg_reload_conf()` |
| e2 | pacotes apt de `deploy/pacotes_apt.txt` (item L7-14): confere com `dpkg -s` e só chama `apt-get install -y` no que faltar (idempotente); lista fechada de 7 — `python3-uvicorn`, `python3-psycopg2`, `python3-venv`, `python3-cryptography`, `gdal-bin`, `python3-gdal`, `python3-magic` |
| f | cria a venv (`--system-site-packages`) e instala `requirements.txt` com `PYTHONNOUSERSITE=1`; prova a importação da aplicação |
| g | `tests/credenciais.txt` (600) com `plataforma admin`, `demo admin` e `demo2 admin`; semeia os três administradores (senha por stdin; o de `plataforma` com `superadmin`, os outros sem), reinicia o segundo fator deles e apaga `tests/credenciais_totp.txt`; garante as partições de `log_acesso` e `evento` do mês e dos 3 seguintes; em `PLAT_AMBIENTE=dev` apaga resíduos `zt-*` das suítes; cota diária de jobs dos inquilinos de demonstração = 100.000 |
| h | unidade `plat-api`, espera `/saude` = 200 na porta local |
| h2 | diretório `var/jobs`, unidade `plat-worker`, espera `http://127.0.0.1:8153/saude` = 200 |
| i | bloco nginx de `deploy/nginx.conf` (noindex, HSTS e `Referrer-Policy` em toda `location`; `limit_req` em `/api/login` e `/api/login/2fa`) mais `/etc/nginx/conf.d/plat_limites.conf` (zona `plat_login`, 10 r/min); troca atômica com `nginx -t`; certbot na primeira vez |
| j | `curl -sI https://<dominio>/saude` até 15 vezes: exige 200, `noindex`, `max-age=31536000` e `fila.workers_vivos >= 1` |

### 11.3 Como conferir

```
make check                     # ruff + varredura de marcador + testes rápidos + e2e
make e2e-worker                # testes lentos da fila (job de 5 min, reinício e kill -9 por systemctl; exige sudo -n)
make vendor                    # sha256 de web/vendor contra VERSOES.txt (5 arquivos: MapLibre, Swagger UI, DOMPurify)
sudo -u postgres psql -d iagro_sat -Atc "select nome, left(sha256,12), aplicada_em from plat.versao_migracao order by 1"
systemctl show plat-api plat-worker -p NRestarts -p MemoryCurrent
```

O adversário do L0-02 reinstalou do zero (`DROP SCHEMA plat CASCADE; DROP SCHEMA plat_trabalho CASCADE; DROP OWNED BY
plat_app; DROP OWNED BY plat_worker; DROP ROLE plat_app; DROP ROLE plat_worker` e `install.sh`) entre 17:14:17 e
17:15:20 UTC de 05/09/2026: o `install.sh` imprimiu "instalado em 50 s", o serviço ficou indisponível cerca de 63 s,
e a instalação nova resistiu à varredura cruzada (`laco/handoffs/T2/L0-02-tenant-auth/refutacao.json`). Memória do
`plat-api` medida pelo testador: 122.781.696 bytes no cgroup, mestre mais 2 workers (`testador_plat_api_memoria_bytes`);
RSS do processo pai do worker: 40.556 kB (`rss_worker_kb`).

### 11.4 Atualizar

```
cd /home/dev/plataforma/enterprise && git pull && sudo bash install.sh plat.iagrointel.com 8150
```

Reinicia `plat-api` e `plat-worker`. Ao reiniciar o worker, os jobs em execução voltam a `pendente` com
`reinicios + 1` e são retomados do zero pelo worker novo (toda tarefa tem de poder recomeçar; o efeito parcial fica
em área de trabalho e só entra no fim).

### 11.5 Assinatura de pacote (item L7-16, ADR 0007 seção 2-3)

Todo pacote de atualização (tar/zip de release) é assinado com Ed25519 antes de sair para um appliance sem
internet; a verificação roda offline, sem depender de rede nem de um serviço externo (`cosign` keyless exigiria as
duas).

```
# quem corta o release (nunca no appliance do cliente)
bash scripts/assinar_pacote.sh plat-1.2.0.tar
# gera deploy/chaves_publicas_release.txt na 1ª vez — commitar essa linha ANTES de distribuir o pacote assinado
git add deploy/chaves_publicas_release.txt && git commit -m "chave de release k…"

# no appliance, antes de aplicar a atualização
bash scripts/verificar_pacote.sh plat-1.2.0.tar   # lê plat-1.2.0.tar.sig ao lado
```

`verificar_pacote.sh` sai com código 2 (`.sig` ausente ou malformado), 3 (chave que assinou não está em
`deploy/chaves_publicas_release.txt` desta versão — rotação pendente) ou 4 (assinatura não confere: o arquivo foi
alterado); só sai 0 quando o pacote é exatamente o que foi assinado por uma chave que esta versão já conhece. A
chave privada nunca fica no repositório (fica em `/etc/plat/chaves/…` como root, ou `$HOME/.config/plat/chaves/…`
como usuário comum); rotação de chave sempre distribui a pública nova numa versão assinada com a antiga, antes de
assinar qualquer pacote com a nova (`tests/unit/test_assinatura_pacote.py` prova as duas pontas — cedo recusa,
tarde aceita). Detalhe completo: ADR 0007.

### 11.6 Worker também em contêiner (item L0-05-e, opcional, ADR 0010)

```
sudo bash install.sh plat.iagrointel.com 8150 --worker-container
```

Builda `deploy/Dockerfile.worker` e sobe `deploy/docker-compose.worker.yml` como um SEGUNDO executor da fila,
ao lado da unidade systemd `plat-worker` (nunca no lugar dela — a instalação sem a flag continua exatamente
como antes). Exige `docker` e o plugin `docker compose` (v2) já instalados; o script confere e para com
mensagem clara se faltar. Saúde do executor em contêiner: `curl http://127.0.0.1:8155/saude`. Quando usar um
ou outro (tabela de decisão) e o bug que só aparece dentro de contêiner (worker como PID 1): `ARQUITETURA.md`
seção 5.8 e o ADR.

---

## 12. Limites conhecidos neste turno

- Não há tela de configuração do inquilino (política de senha, sessão, token, exigir segundo fator): item L0-07-a.
  Não há console do superadmin: L0-07-f. Não há login externo (SAML, OIDC, LDAP): L0-08. Não há e-mail (convite,
  senha temporária por e-mail): L0-07-d. Não há relatório de uso: L0-07-e.
- Apagar usuário com transferência de conteúdo depende do catálogo (L0-03-j); hoje apagar exige que o usuário não
  possua grupos.
- O segundo fator é TOTP por aplicativo; não há isenção individual quando o inquilino o exige.
- `Referrer-Policy` passou a ser repetido em toda `location` no commit `abbb03d`; chega ao navegador depois da
  próxima execução do `install.sh`. Não há `Content-Security-Policy` (item L7-03).
- A fila roda com um processo por padrão (`PLAT_WORKER_PROCESSOS=1`): a execução é serial e sem justiça entre
  inquilinos; a cota `cota_jobs_simultaneos` só faz efeito com mais de um processo. O testador observou 4 jobs
  curtos de um inquilino esperando 14 minutos atrás de dois jobs de 5 minutos de outro.
- Identidade do worker: até o commit `abbb03d` o nome era o do host e um segundo worker com o mesmo nome (por
  exemplo `make worker` na mesma máquina) devolvia, ao nascer, os jobs do worker da unidade, que eram reexecutados do
  zero; o testador flagrou o caso e o portão do item L0-05 ganhou a cláusula "identidade do worker única por
  processo". O commit `9be9c6a` (migrações 012 e 013) corrige: identidade `<nome-base>:<pid>` e ceifa só por
  heartbeat vencido do job e do worker dono; consequência a conhecer: depois de um `kill -9` no processo pai, o job
  fica `rodando` até a ceifa o recolher, em até cerca de 90 s (um `systemctl restart` limpo continua devolvendo na
  hora). A correção ainda não tem veredito do testador nem do adversário.
- Um job devolvido 5 vezes termina `falhou` com `tentativa = 0` na tela (a devolução desfaz o incremento de
  `job_pegar`); o texto "tentativa 0 de 3" num job que rodou 5 vezes confunde e fica registrado para o gerente.
- O cabeçalho `Cache-Control` do SSE sai duplicado pela URL pública (`no-store, no-store, must-revalidate`): o nginx
  acrescenta o seu ao da API; inofensivo.
- A tela Tarefas com 1.000 jobs semeados não teve a primeira pintura medida pela suíte: a semeadura por SQL do
  teste foi barrada pelo gatilho da migração 006 (o teste inseria jobs já `concluido` como `plat_app`); é defeito do
  teste, não do produto, e a medida não está em `tests/medidas/L0-05-jobs.json`.
- Limites e demais números de referência: `app/limites.py` (identidade e catálogo) e a seção 11 do ADR 0003 (fila).


---

## 13. Mapa (`/mapa`, item L2-01-a-basemap-local-pmtiles)

Primeira tela de mapa do produto: MapLibre GL JS 4.7.1 (vendorizado, já presente no repositório desde o turno 2)
mais o protocolo `pmtiles-4.5.0.js` (novo, BSD-3-Clause), lendo um PMTiles estático servido pelo próprio nginx do
appliance por Range HTTP — sem Martin, sem serviço de tiles dinâmico, sem chave de terceiro. É a fatia mínima do
item `L2-01-mapa-web` (visualizador completo: camadas do catálogo, legenda, popup, busca, impressão), que fica
para os itens seguintes da linha.

### 13.1 Mapa-base

`web/dados/basemap/guarulhos.pmtiles` (18,4 MiB): recorte de OpenStreetMap (ODbL 1.0) da área de Guarulhos-SP,
extraído com `ogr2ogr` (streaming, baixo consumo de memória) de um `.pbf` regional já presente na máquina e
ladrilhado com `tippecanoe` em 4 camadas (estradas, edificações, cobertura do solo, lugares). Proveniência
completa, com sha256 e comando de reprodução, em `web/dados/basemap/PROVENIENCIA.md`. Nginx serve o arquivo em
`/static/dados/basemap/guarulhos.pmtiles` com suporte a Range (206) e `gzip off` (obrigatório: gzip on-the-fly
quebra Range); a resposta a `Range: bytes=0-99` foi medida devolvendo `206 Partial Content` com
`Content-Range: bytes 0-99/19272343`.

### 13.2 Tela

Tela cheia (sem a barra de ferramentas larga das outras telas): mapa MapLibre ocupando toda a área principal,
barra lateral padrão do produto à esquerda. Controles: navegação (zoom/pan por arrastar/roda do mouse + botões
`+`/`−`/bússola do `NavigationControl`), escala (`ScaleControl`, canto inferior esquerdo), atribuição ODbL
(`AttributionControl`, canto inferior direito, sempre visível — licença do dado é obrigação, não opção), painel
de coordenadas do cursor (latitude, longitude e zoom, atualiza a cada `mousemove` e a cada mudança de zoom) e
seletor de camada base (uma opção hoje, `OSM aberto — recorte Guarulhos (ODbL 1.0)`; o mecanismo é uma lista
(`BASES` em `web/js/mapa/mapa.js`) já pronta para receber a próxima base sem mudar a fiação). Estilo cartográfico
próprio (não é o estilo de nenhum provedor externo): fundo escuro, água e cobertura do solo diferenciadas, vias
coloridas por classe (via principal em âmbar, o acento do produto), edificações visíveis a partir do zoom 12 —
cores copiadas à mão da paleta escura de `web/estilo/tokens.css` (documentado em `web/js/mapa/estilo.js`, já que
o MapLibre lê JSON puro e não `var()` de CSS). Rótulos de nome de rua/bairro ficam para
`L2-02-e-simbolos-sprites-glifos` (exige servidor de glifos); a camada `lugares` está no tileset mas não é
desenhada como texto nesta fatia.

### 13.3 Prova (e2e)

`tests/e2e/test_mapa.py`: (1) o nginx devolve 206/Content-Range para o PMTiles, sem `content-encoding: gzip`;
(2) o canvas WebGL do MapLibre realmente desenha — `readPixels` sobre o canvas conta mais de 50 pixels com cor
diferente da do canto (0,0), afastando a hipótese de tela em branco; (3) os controles de navegação, escala,
coordenadas e camada base existem e reagem (clicar no `+` do zoom muda a leitura do painel de coordenadas);
(4) 0 erro de console, 0 resposta HTTP ≥ 400 não esperada. Captura em
`tests/e2e/capturas/L2-01-a-basemap-local-pmtiles_mapa.png`.

### 13.4 Limites desta fatia

Sem camadas do catálogo do inquilino (isso é o resto do `L2-01-mapa-web`: Martin/vetor por RLS, raster por
tiles, legenda, popup, busca de endereço/coordenada, impressão). Sem rótulo de texto (glifos, L2-02-e). Sem
segunda base (a lista está pronta; falta a segunda entrada). Mapa-base cobre só a área de teste de Guarulhos-SP,
não o território nacional — isso é o D27 do dono (`L2_CONCEITO.md`), travado por disco (98 % em `/`), não por
esta fatia.

## 14. Rota, matriz e isócrona (item L2-11-c-rota-matriz-isocrona — PARCIAL)

Três rotas de API sobre um serviço OSRM isolado de teste, sem tela própria ainda (a UI no mapa — clicar dois
pontos, ver instruções, desenhar a isócrona — fica para o `L2-05-f-rede-isocrona-rota-ferramentas`).

### 14.1 `POST /api/rota`

Corpo `{"origem": [lon, lat], "destino": [lon, lat], "perfil": "carro"}`. Devolve distância (m), duração (s),
geometria (GeoJSON `LineString`), lista de instruções resumidas em português (`app/rede/instrucoes.py`, uma
frase por passo do OSRM: "Vire à direita em Rua X, siga por 350 m") e a ficha de proveniência do grafo. Só o
perfil `carro` existe nesta instância de teste (`carro`.lua é o único grafo carregado); pedir `pe` ou
`bicicleta` devolve 422 nomeando os perfis disponíveis.

### 14.2 `POST /api/matriz`

Corpo `{"origens": [[lon,lat], ...], "destinos": [[lon,lat], ...], "perfil": "carro"}`. Devolve as matrizes de
duração e distância (N×M). Teto de N×M configurável por `PLAT_ROTA_MATRIZ_MAX` (padrão 625, bate com
`--max-table-size` do contêiner de teste); pedido maior devolve 422 `matriz_grande_demais` com o teto.

### 14.3 `POST /api/isocrona`

Corpo `{"ponto": [lon, lat], "minutos": N, "perfil": "carro"}`. O OSRM não tem serviço de isócrona nativo (doc
testada — só route/table/nearest/match/trip/tile); o cálculo é uma grade de pontos ao redor do centro (raio
inicial estimado, dobrado uma vez se a borda da grade ainda estiver alcançável), o tempo de cada ponto pedido
de uma vez ao `/table` do OSRM, e o polígono é o casco côncavo (`shapely.concave_hull`) sobre os pontos dentro
do orçamento de tempo. Resposta traz o polígono (GeoJSON), a resolução e o raio da grade usados, e quantos
pontos foram amostrados/alcançados — para quem quiser auditar o cálculo sem recomputar.

### 14.4 O serviço por trás: `plat-osrm-guarulhos`

OSRM isolado, só para este item, recorte de Guarulhos-SP ≤ 50 MB (`osrm/guarulhos.osm.pbf`, 1,6 MiB — mesma
área do mapa-base do item 13), em **127.0.0.1:5010** (unidade systemd `plat-osrm-guarulhos`, instalada pelo
`install.sh`). Proveniência completa (fonte, sha256, método de extração, o que ficou de fora) em
`osrm/PROVENIENCIA.md`. **Nunca** é o mesmo processo dos outros 4 contêineres OSRM já ativos nesta máquina
para outras frentes (portas 5000-5003) — nenhum foi tocado.

### 14.5 Limites desta fatia (o que falta para o item completo do backlog)

pgRouting não foi instalado (a hipótese do item pede `postgresql-16-pgrouting` para rede própria do
inquilino — L4); sem `/mais-proximo` nem `/ajuste-de-trajeto` (map matching); sem perfil de pé/bicicleta
(precisaria de um segundo grafo); sem NAServer Esri-compatível (`solve`/`solveServiceArea`/
`solveClosestFacility`/OD cost matrix síncronos); teste só até matriz 5×5 (o portão do item pede 1.000×1.000
medido e um teste de 5.000×5.000 pelo adversário); isócrona testada só a 10 min contra a própria API de rota
(o portão completo pede 200 pontos amostrados nas faixas de 15/30/45 min). Ver
`laco/handoffs/T3/L2-11-c-rota.md` para o estado exato e o que a próxima trilha retoma.

## 15. LDAP/Active Directory (item L0-08-d-ldap) — API pronta, sem tela ainda

Login federado por LDAP/Active Directory, por inquilino. Ainda sem botão na tela de entrada nem formulário de
configuração em `/admin` (isso é o `L0-08-f`, item de frontend à parte); hoje é consumido por API — um
integrador (ou a equipe, via `curl`/Postman) configura e testa direto pelas rotas abaixo.

### 15.1 Configurar o provedor (administrador do inquilino, privilégio `org.integracoes`)

```
PUT /api/org/ldap
{
  "habilitado": true,
  "url": "ldap://ad.empresa.org:389",      // ou "ldaps://..."; omitido usa o padrão do ambiente
  "base_dn": "dc=empresa,dc=org",
  "start_tls": true,                        // StartTLS sobre "ldap://"; ignorado com "ldaps://"
  "bind_dn": "cn=servico-plat,ou=svc,dc=empresa,dc=org",   // null = busca anônima
  "bind_senha": "...",                      // só na escrita; nunca devolvido (GET traz "tem_bind_senha": true)
  "filtro_usuario": "(sAMAccountName={login})",   // Active Directory; OpenLDAP costuma ser "(uid={login})"
  "atributo_grupos": "memberOf",
  "perfil_padrao": null,                    // perfil de quem não bate em nenhum grupo mapeado (ou null = recusa)
  "mapa_grupo_perfil": {
    "CN=Administradores TI,OU=Grupos,DC=empresa,DC=org": "admin",
    "CN=Editores GIS,OU=Grupos,DC=empresa,DC=org": "editor"
  }
}
```

`GET /api/org/ldap` devolve a mesma forma sem a senha (`tem_bind_senha` no lugar). A chave do
`mapa_grupo_perfil` aceita o DN inteiro do grupo (como o diretório devolve em `memberOf`) OU só o valor do
primeiro RDN (o "nome" do grupo) — útil quando o administrador não quer copiar o DN inteiro.

### 15.2 Entrar

```
POST /api/login/ldap
{"inquilino": "empresa", "login": "maria.silva", "senha": "..."}
```

Mesmo formato de resposta do login local (`{"ok": true, "usuario": {...}}` + cookie `plat_sessao`). Se a
senha estiver errada, `401 credenciais_invalidas` (a mesma mensagem genérica do login local — nunca revela se
o problema foi login inexistente, senha errada ou 0/2+ resultados na busca). Se o diretório estiver fora do
ar, `503 ldap_indisponivel` — **o login local continua funcionando normalmente** (é outra rota, outro
caminho; nunca compartilha estado). Se o usuário existir no diretório mas nenhum grupo dele estiver mapeado
(e não houver `perfil_padrao`), `403 sem_grupo_mapeado`. Se já existir uma conta LOCAL com o mesmo login,
`409 login_em_uso_local` — o LDAP nunca assume uma conta local homônima.

No primeiro login bem-sucedido, o usuário é criado automaticamente (`origem: "ldap"`, sem senha local) com o
perfil calculado dos grupos; logins seguintes atualizam nome/e-mail/perfil se mudaram no diretório.

### 15.3 Importar um grupo em massa

```
POST /api/org/ldap/importar
{"grupo_dn": "CN=Editores GIS,OU=Grupos,DC=empresa,DC=org", "atributo_membro": "memberOf",
 "atributo_login": "sAMAccountName", "perfil": "editor"}
```

Cria um usuário local **desabilitado** (`ativo: false`) para cada membro do grupo que ainda não existe;
usuários já provisionados (por login anterior ou importação anterior) só são contados, não recriados. A conta
importada ativa sozinha no primeiro login bem-sucedido pela rota 15.2 — não é preciso reabilitar à mão.

### 15.4 Limites desta fatia

Sem StartTLS testado contra um diretório real (só contra o de teste, sem certificado); sem tela de
configuração nem botão de entrada (frontend, L0-08-f); contador de força bruta do bind é em memória de
processo (não compartilhado entre os `--workers 2`, não sobrevive a reinício — nomeado, não escondido). Ver
`docs/adr/0008-ldap-ad.md` e `laco/handoffs/T3/L0-08-d-ldap.md`.
