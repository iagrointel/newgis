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

### 3.1a Perfil próprio: foto, idioma, unidades, formato de data, visibilidade (item L0-02-g-perfil-usuario)

Captura `tests/e2e/capturas/L0-02-tenant-auth_perfil.png` (`tests/e2e/test_conta.py`,
`test_perfil_nome_unidades_foto_na_barra_e_email_fora_do_dominio`): o cartão Dados ganha uma foto redonda (ou o
aviso "sem foto"), os botões `Enviar foto`/`Remover foto`, e quatro campos novos no mesmo formulário — Idioma
(pt-BR/en/es), Unidades (métrico/imperial), Formato de data (dd/mm/aaaa, mm/dd/aaaa, aaaa-mm-dd) e Visibilidade do
perfil (visível a quem está no inquilino / privado) — tudo pelo mesmo `PUT /api/eu` que já grava nome e e-mail
(campos novos na mesma whitelist do servidor; `login`, `perfil`, `papel_id` e `ativo` continuam fora dela — o
próprio usuário nunca escala o próprio acesso nem troca o login por aqui).

A foto é `POST /api/eu/foto` (JSON `{conteudo: base64}`, mesmo truque de base64 sob cookie que o logotipo da
organização já usa) e `DELETE /api/eu/foto`: o servidor decodifica, REDESENHA com o Pillow num recorte central
200×200 (nunca os bytes originais do cliente) e recusa com `415 formato_nao_aceito` qualquer coisa que não seja
PNG/JPEG/GIF/WEBP de verdade — inclusive um SVG com `<script>`, que o Pillow nunca chega a abrir. Acima de 1 MiB é
`413 foto_grande`. A foto aparece também na barra lateral (`#pessoa-foto`), ao lado do nome, sem recarregar a
página. `idioma_preferido` grava a preferência mas a tradução da tela ainda não a segue (isso é o item
`L7-10-a-i18n-pt-en-es`, pendente); os outros três campos (unidades, formato de data, visibilidade do perfil) só
persistem — nenhuma tela ainda lê `unidades`/`formato_data` para reformatar número/data, e não existe hoje uma
tela de "perfil de outro usuário" que leia `visibilidade_perfil`; a landing desses dois é o próximo consumidor.

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
administrador cria outro administrador (`403 so_admin_cria_admin`); criar com perfil diferente de
`visualizador`, ou atribuir papel personalizado, exige `membros.papel` além de `membros.gerir` (`403
sem_privilegio`) — sem essa checagem um admin deliberadamente restrito a `membros.gerir` conseguia fabricar um
admin pleno pela criação, mesmo sem poder editar perfil de ninguém (achado do adversário, T3). Login repetido
no inquilino: `409 login_existente`.

### 4.2 Editar, desabilitar, apagar

`Editar` altera nome, e-mail, perfil, papel e estado. Regras que a API aplica e a tela mostra com a mensagem
recebida: o último administrador ativo não se desabilita, não se rebaixa nem se apaga (`409 ultimo_admin`); ninguém
desabilita a própria conta (`409 proprio_usuario`); só administrador altera administrador
(`403 so_admin_altera_admin`); quem possui grupos não é rebaixado nem apagado antes de transferir os grupos
(`409 possui_grupos`, com a lista dos grupos); quem possui itens do catálogo (mapas, camadas, pastas) não é apagado
antes de transferi-los ou apagá-los (`409 possui_itens`, com a lista dos títulos — `plat.item.dono_id` é chave
estrangeira sem `ON DELETE`, então sem esta checagem o banco recusaria com um erro genérico em vez de nomear o que
falta resolver; a transferência em massa é o item L0-03-j, `POST /api/itens/transferir`). Desabilitar apaga as
sessões do usuário na hora (medido em `desabilitar_para_401_ms`, bem abaixo de 1 s); `Reabilitar` desfaz. `Apagar`
pede confirmação e não tem volta.

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
privilégios (administrador 47, dos quais 20 administrativos; editor 27; visualizador 8; campo 12) e o botão `Ver`;
cartão "Papéis personalizados" com nome · descrição · perfil mínimo · privilégios · usuários e os botões `Editar` e
`Apagar`; faixa verde "papel Curador E2E c5ec1c criado".

Como funciona: o perfil do usuário define o teto de privilégios; o papel personalizado é um subconjunto do teto,
criado com nome, descrição e a lista de privilégios (vocabulário fechado de 47 nomes, gerado do banco em
`docs/PRIVILEGIOS.md`, consultável também em `GET /api/privilegios`). O servidor calcula o `perfil mínimo` do papel
(um privilégio administrativo obriga perfil `admin`); usuário com perfil abaixo do mínimo não recebe o papel
(`422 papel_incompativel`). Quem cria um papel só concede privilégios que a própria sessão tem (`403
privilegio_proprio_insuficiente`). Papel em uso não se apaga (`409 papel_em_uso`). Rebaixar o perfil de um usuário
que ainda possui grupos ou itens do catálogo é recusado (`409 possui_grupos`/`409 possui_itens` — item
L0-07-b-papeis-privilegios, T3: a checagem de conteúdo não existia até este turno). Toda rota da API pergunta por
privilégio, nunca por perfil; a lista de privilégios da sessão está em `GET /api/eu`;
`tests/api/test_privilegios_matriz.py` chama toda rota do OpenAPI vivo com um usuário sem o privilégio declarado e
exige 403 em todas. Paridade linha a linha contra a lista de privilégios da Esri (43 gerais + 33 administrativos):
`docs/PARIDADE.md` seção "Privilégios e papéis personalizados" (35 feito · 11 parcial · 30 fora de 76).

Cenário provado ponta a ponta (`tests/e2e/test_papeis.py::test_papel_curador_categoriza_mas_nao_publica`, captura
`L0-02-tenant-auth_papel_curador.png`): papel "Curador" com `conteudo.criar` + `conteudo.categorias` (este último
administrativo, então o papel só cabe em perfil `admin`) atribuído a um usuário novo — ele reescreve a árvore de
categorias do inquilino e cria conteúdo comum, mas uma tentativa de criar/publicar camada vetorial nega com `403
sem_privilegio` (`exigido: conteudo.publicar_camada`, que o papel não deu).

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
- Limite de taxa em três camadas (item L7-03-b-rate-limit-abuso; `ARQUITETURA.md §18`, `docs/SEGURANCA.md §9`)
  entrou nesta passagem, mas a cláusula "ladrilho acima do limite do plano" fica parcial: a rota real de
  ladrilho (`L1-02-tiles-token`) ainda não está mesclada nesta base — a zona de borda já protege `/tiles/` e o
  mecanismo já suporta o escopo, falta só a fiação quando aquele ramo entrar.


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

## 16. Metadado ISO e catálogo externo (item L0-09-metadado-catalogo)

### 16.1 Exportar o metadado ISO 19139 de um item

```
GET /api/itens/{id}/metadado.xml
```

Devolve `gmd:MD_Metadata` (ISO 19139/GMD — o mesmo perfil que o Perfil MGB 2.0/INDE consome), montado a partir
do próprio item (título, resumo/descrição, palavras-chave, créditos, termos de uso, extensão geográfica, dono
como `pointOfContact`) e do bloco `dados.procedencia` quando existir (vira `dataQualityInfo`/`lineage`). O
servidor valida o XML contra o XSD oficial ANTES de responder — se algum dia isso falhar é erro de build do
gerador (`500 metadado_invalido`), nunca do pedido. Aceita sessão OU token de serviço com escopo `catalogo:ler`
(`POST /api/tokens {"escopos": ["catalogo:ler"]}`, seção 7); nunca anônimo. Item de outro inquilino: `404`,
igual a qualquer outra rota do catálogo (a RLS de `plat.item` decide, não um filtro escrito na rota).

O XSD fica cacheado OFFLINE em `docs/xsd/cache/` (baixado uma vez por `venv/bin/python
docs/xsd/baixar_iso19139.py`, comitado no repositório e refeito pelo `install.sh`); a rota nunca depende de
rede para validar.

### 16.2 Catálogo externo por protocolo padrão: OGC API Records

```
GET /ogc/records                                          # pouso
GET /ogc/records/conformance
GET /ogc/records/collections                              # 1 coleção: "catalogo"
GET /ogc/records/collections/catalogo/items?q=...&bbox=...&tipo=...&tags=...&limit=...
GET /ogc/records/collections/catalogo/items/{id}
```

Descoberta do catálogo por um cliente OGC padrão (OGC API — Records, Parte 1: Core, 20-004r1), sempre
autenticada (mesmo escopo `catalogo:ler` da seção 16.1) — nunca aberta, mesmo a página de pouso. Cada registro
(GeoJSON) traz `links` para o item na API própria e para o metadado ISO da seção 16.1. Os mesmos filtros
simples da lista de itens (`GET /api/itens`) valem aqui: `q` (busca), `bbox`, `tipo`, `tags`; a paginação usa
`limit`/`offset` e o link `rel=next` com `cursor` para a página seguinte. Isolamento por inquilino: o registro
de um item nunca aparece para o token/sessão de outro inquilino (mesma RLS da seção 16.1, provada em
`tests/api/catalogo/test_metadado_ogc.py`).

CSW (Catalog Service for the Web) fica de fora desta passagem — decisão registrada em
`app/catalogo/rotas_ogc.py` e em `docs/PARIDADE.md`: RAM desta máquina no limite, nenhuma biblioteca CSW
instalada, e o protocolo é legado frente ao OGC API Records. Ver `laco/handoffs/T3/L0-09-metadado.md`.

## 17. Documento de construtor (item L5-05-documento-versoes)

Base que qualquer construtor do L5 (app, painel, e depois formulário, fluxo) usa para gravar um grafo: o
documento vive dentro de `dados` do item, no envelope `{tipo, esquema_versao, corpo}`; `corpo.nos` é a lista de
nós, cada um com `id` **ULID** (26 caracteres, nunca reaproveitado, nunca derivado de posição) e `tipo`;
`corpo.ligacoes` referencia nós por `id` (`origem`/`alvo`). Reaproveita por inteiro o mecanismo de versão do
catálogo (seção anterior a esta, item L0-03): salvar cria versão nova e imutável; publicar aponta
`versao_publicada`; a versão anterior continua legível.

```
GET  /api/esquemas                          # tipos com JSON Schema publicado (nome, família, esquema_versao)
GET  /api/esquemas/{tipo}?versao=N          # esquema (N ausente = versão vigente; versões antigas em docs/esquemas/)
GET  /api/itens/{id}/integridade            # recomputa o sha256 de cada versão a partir do corpo GRAVADO e
                                             # compara com o sha256 da linha — corrupção direta no banco aparece aqui
```

Hoje `app` e `painel` têm esquema de grafo publicado (`docs/esquemas/app-v2.json`, `painel-v2.json`; as
versões v1, triviais, ficam arquivadas para registro). `POST/PUT /api/itens` com um desses tipos recusa
(`422 grafo_invalido`) dois nós com o mesmo id ou uma ligação apontando para um id que não está em `corpo.nos`
— regra que o JSON Schema sozinho não expressa (precisa olhar a lista inteira), em `app/catalogo/
documento.py::validar_grafo`. Documento gravado com `esquema_versao` antiga (os itens semeados em demo/demo2
antes desta migração, `corpo:{}`) chega **já migrado** em toda leitura (`GET /api/itens/{id}`), nunca gravado
de volta — o evento `itens/esquema_migrado` fica no log.

`GET /api/itens/{id}/versoes/{n}` traz, para todo tipo cujo `dados` tenha um `corpo` objeto, um campo extra
`sha256_canonico`: hash de `dados.corpo` numa forma canônica (chaves ordenadas, sem espaço) que qualquer
`sha256sum` externo reproduz — diferente do `sha256` da versão inteira (que é do jsonb do Postgres, estável
dentro dele mas não reproduzível fora sem reimplementar a serialização do banco). Ver `app/catalogo/
documento.py` para o comando exato de reprodução. Detalhe técnico e decisões em `docs/adr/0011-documento-
de-construtor.md`.

## 18. Registro de camadas do acervo e modelo de conexão externa (itens L6-01-a-registro e
L6-02-a-modelo-conexao-e-seguranca) — API pronta, sem tela ainda

Dois modelos de fundo da linha L6 (conectores e acervo). Nenhum dos dois tem tela própria ainda (frontend é
item futuro: L6-01-c para o acervo, L6-02-b em diante para os conectores concretos); hoje são consumidos por
API. Ver `docs/adr/0012-registro-do-acervo-e-conexao-externa.md` para as decisões e o que ficou de fora.

### 18.1 Registro de camadas do acervo (`plat.acervo_camada`)

Diferença do que já existe (seção "Acervo da casa", item L6-01-a-procedencia-acervo, `GET /api/acervo`): aquilo
é a ficha da FONTE (376 linhas de metadado — licença, frescor, sha256); isto é o registro de CAMADA — uma
linha por TABELA canônica com geometria no servidor principal, candidata a virar camada só-leitura no mapa do
inquilino (a view com RLS por assinatura é o próximo item, L6-01-b, ainda não construído — por isso ainda não
há rota HTTP para `acervo_camada`, só a tabela e o script que a povoa).

`sudo -u postgres python3 scripts/acervo_sync.py` (idempotente; ~275-290 s para o universo inteiro nesta
máquina, medido 06/09/2026 com ~462 candidatas) preenche `plat.acervo_camada`: schema/tabela, coluna e SRID
da geometria, lista branca de colunas (nega por nome — `cpf`, `nome`, `email`, `telefone`... — rede mínima até
o item L6-01-f existir e checar por conteúdo), `COUNT(*)` exato com timeout de 25 s (nunca a estimativa de
`reltuples`), e o estado: `exposta` (tem licença escrita e contagem concluída), `pendente_de_licenca`
(licença ainda não registrada em `acervo.fonte`, regra D17) ou `bloqueada` (contagem não concluiu a tempo, ou
é tabela fantasma — estimativa positiva com contagem exata zero). Rodar de novo processa primeiro o que há
mais tempo não sincroniza, então uma rodada que não dá tempo de cobrir tudo (a máquina pode estar ocupada com
outro job pesado da casa) avança em tabelas diferentes na próxima vez, em vez de sempre travar nas mesmas.

### 18.2 Conexão externa (`plat.conexao`) e defesa de SSRF

```
POST   /api/conexoes                 {"tipo": "ogc_api", "nome": "...", "url": "https://...", "modo": "referenciada",
                                       "config": {}, "credencial": "..."}   # credencial nunca volta em nenhuma resposta
GET    /api/conexoes                 # lista do inquilino (RLS)
GET    /api/conexoes/{id}
PATCH  /api/conexoes/{id}
DELETE /api/conexoes/{id}
POST   /api/conexoes/{id}/testar     # teste de saúde: GET seguro contra a URL gravada, timeout curto
```

`tipo` é um vocabulário fechado (`wms`, `wmts`, `wfs`, `ogc_api`, `esri_rest`, `stac`, `geoparquet`,
`pmtiles`, `postgres_fdw`, `s3`, `http`) — esta trilha entrega só o MODELO e a segurança; cada conector
concreto (que sabe LER o serviço de verdade — listar camadas WMS, paginar um OGC API Features, etc.) é item
futuro. `credencial` é cifrada (AES-GCM) antes de gravar e nunca decifrada de volta para a API — só o teste
de saúde a usa, em memória, para autenticar o pedido.

Toda URL passa pela defesa de SSRF (`app/conexao/seguranca.py`) ANTES de gravar (criar ou editar) e de novo
a cada teste de saúde: recusa esquema fora de `http`/`https`, host ausente, usuário/senha na URL, e qualquer
IP resolvido que seja privado, loopback, link-local (inclui o metadado de nuvem, `169.254.169.254`), CGNAT
ou reservado. A conexão real nunca resolve o host de novo depois de validado (fixada no IP já conferido), e
todo redirecionamento é revalidado do zero, salto a salto — um serviço público que redireciona para um IP
interno é aceito no primeiro salto e recusado no segundo, nunca no primeiro.

### 18.2a Fonte de dado registrada: conector `postgres_fdw` (item L0-04-i-fonte-registrada)

O primeiro conector concreto de `plat.conexao` — "Data store item" da Esri Enterprise 11.4 / "store" do
GeoServer, restrito a PostgreSQL/PostGIS externo (`docs/adr/20260907T0148-fonte-registrada-postgres-fdw.md`).

```
GET  /api/conexoes/{id}/tabelas            ?schema_remoto=public   # tabelas do banco do cliente (pg_catalog)
POST /api/conexoes/{id}/publicar-em-massa  {"tabelas": ["t1","t2"], "schema_remoto": "public"}
GET  /api/conexoes/{id}/camadas            # camadas já publicadas desta conexão + estado_fonte ao vivo
```

`url` de uma conexão `postgres_fdw` é `postgres://host:porta/banco` (nunca `http(s)`); `config.usuario` é o
usuário remoto (não secreto), `credencial` é a senha (cifrada, mesmo mecanismo do resto de `plat.conexao`).
A defesa de alvo (`app/conexao/pgfdw.py::validar_alvo`) é DIFERENTE da defesa de SSRF HTTP acima: um Postgres
de cliente pode estar numa rede privada/VPN de propósito, então só metadado de nuvem/multicast/não-
especificado são recusados por categoria de IP; o banco `iagro_sat` é recusado em qualquer host (lista
explícita) e o `(host,porta,banco)` do `PLAT_DSN` desta instalação é recusado por IP.

Cada tabela publicada vira uma `FOREIGN TABLE` + `VIEW` num schema `d_<slug>` do inquilino (função SECURITY
DEFINER `plat.conexao_fdw_publicar`, já que `plat_app` não tem `CREATE` nem `USAGE` na extensão
`postgres_fdw`) e um item de catálogo `camada_vetorial` com `dados.fonte = "referenciada"` — nenhum dado é
copiado. Conexão fora do ar devolve `503 fonte_indisponivel` com mensagem em qualquer rota que precise falar
com o Postgres do cliente; a camada e a conexão continuam no catálogo, e `GET .../camadas` mostra
`estado_fonte: "fonte_indisponivel"` calculado da última saúde registrada.

### 18.3 Limites desta fatia

Sem tela em nenhum dos dois; `acervo_camada` ainda não tem rota HTTP própria (só a tabela); lista branca de
coluna do acervo é por nome, não por conteúdo (L6-01-f); os demais 14 conectores concretos (o que de fato
busca e traduz WMS/WFS/STAC/... para camada do mapa) são itens futuros, L6-02-b em diante — só `postgres_fdw`
foi construído (item L0-04-i). `DELETE /api/conexoes/{id}` ainda não limpa `SERVER`/`USER MAPPING` do
`postgres_fdw` associados (pendência no handoff do item); risco conhecido de senha em texto claro na DDL do
`postgres_fdw` (limitação do próprio `postgres_fdw`, não deste código — ver ADR).
### 18.3 Publicar uma camada do acervo e assinar (item L6-01-b-view-so-leitura)

### 18.3 Publicar uma camada do acervo e assinar (item L6-01-b-view-so-leitura)

### 18.3 Publicar uma camada do acervo e assinar (item L6-01-b-view-so-leitura)

Publicar é criar a VIEW; assinar é ganhar o direito de lê-la. São dois passos com donos diferentes.

1. **A casa publica** (uma vez por camada, como `postgres`):

       sudo -u postgres python3 scripts/acervo_publicar.py --schema plat --banco iagro_sat

   Cria uma view em `plat_acervo` para cada camada `estado = 'exposta'` do registro, com só as colunas da
   lista branca. É idempotente e derruba a view de quem saiu de `exposta`. Nada é copiado: a view lê a tabela
   original e usa o índice espacial dela.

2. **O inquilino assina** (precisa do privilégio `conteudo.registrar_fonte`):

       GET    /api/acervo/camadas                                  o que está publicado; `assinada` é do seu
       POST   /api/acervo/camadas/<view>/assinatura                passa a poder ler
       DELETE /api/acervo/camadas/<view>/assinatura                deixa de poder ler

3. **Lê**:

       GET /api/acervo/camadas/<view>/feicoes?bbox=oeste,sul,leste,norte&limite=500     GeoJSON
       GET /api/acervo/camadas/<view>/tiles/{z}/{x}/{y}.mvt                             tile vetorial

   Sem assinatura, as duas devolvem 403 `sem_assinatura` — e a view por baixo devolve zero linha, mesmo para
   quem chegasse ao SQL por fora. Só leitura: qualquer verbo de escrita nestes caminhos é 405, e a view não
   tem `GRANT` de escrita para o papel da aplicação, então o próprio banco recusa.

### 18.4 Limites desta fatia

Sem tela em nenhum dos dois; lista branca de coluna do acervo é por nome, não por conteúdo (L6-01-f); os 15
conectores concretos (o que de fato busca e traduz WMS/WFS/STAC/... para camada do mapa) são itens futuros,
L6-02-b em diante. Da publicação: `plat-martin` não existe nesta máquina (o SQL de tile é servido pela própria
API), FeatureServer e OGC API de feição não existem (L2-04) e o visualizador ainda não recebe camada do
catálogo (L2-01), então "adicionar ao mapa" é por API, não por tela.

### 18.5 Camada do acervo como fator do motor multicritério (item L6-04-acervo-no-motor)

Um fator do modelo AMC (`docs/esquemas/amc_modelo.v1.json`, seção 20) com `camada.tipo = "acervo"` e
`camada.id = "<acervo_camada_id>"` roda de verdade: `POST /api/amc/execucoes` recusa (422 `sem_assinatura`) se
o inquilino não assinar a camada (mesmo porteiro do 18.3) e, quando aceita, enfileira sozinho o job
`amc.executar`. O job lê a view de `plat_acervo` (nunca copia a tabela), extrai o valor bruto com
`app.amc.vetorial` (só extratores de vetor: `poligono_fracao_area`, `poligono_area`, `poligono_contagem`,
`poligono_atributo_ponderado`, `linha_comprimento`, `linha_distancia_mais_proxima`, `ponto_contagem_raio`,
`ponto_densidade_kernel`, `ponto_distancia_mais_proximo`, `ponto_atributo_mais_proximo`), aplica a transformação
do fator — os 16 tipos de `app.amc.transformacoes` (item L3-01-d, seção 22) — e combina por soma ponderada
normalizada. `GET /api/amc/execucoes/{id}` mostra, por camada, `fonte_id`, `sha256` e `contagem` (de
`acervo.linhas_exatas`). Revogar a assinatura DEPOIS de a execução concluir não apaga o resultado (a execução
concluída é imutável); revogar DURANTE um job em andamento derruba o job com mensagem — a checagem da
assinatura acontece de novo, uma vez antes de cada fator e uma vez depois do último, e nenhuma linha de
resultado é gravada se qualquer uma delas falhar. Fora do escopo: fator do tipo `item` (catálogo do
inquilino) não é extraído por este job; raster do acervo e combinador diferente do padrão ficam para outro
item. Ver ADR `20260907T1319`.
`linear` do fator e combina por soma ponderada normalizada. `GET /api/amc/execucoes/{id}` mostra, por camada,
`fonte_id`, `sha256` e `contagem` (de `acervo.linhas_exatas`). Revogar a assinatura DEPOIS de a execução
concluir não apaga o resultado (a execução concluída é imutável); revogar DURANTE um job em andamento derruba
o job com mensagem — a checagem da assinatura acontece de novo, uma vez antes de cada fator e uma vez depois
do último, e nenhuma linha de resultado é gravada se qualquer uma delas falhar. Fora do escopo: fator do tipo
`item` (catálogo do inquilino) não é extraído por este job; raster do acervo, transformação além de `linear` e
combinador diferente do padrão ficam para o item L3-01-d/e. Ver ADR `20260907T1319`.

## 19. Ficha do acervo completa e gate de LGPD (itens L6-01-d-ficha-fonte e L6-01-f-lgpd)

### 19.1 Ficha de procedência (`GET /api/acervo/{fonte_id}`)

Os 10 campos de procedência da hipótese do item (url, licença, frescor, data do dado, script gerador, sha256,
método, confiança, limites, próxima verificação) já estavam expostos desde o item anterior
(L6-01-a-procedencia-acervo, migração 021) — conferido por leitura antes de somar código. `limites` já É "o
que este dado não sustenta" em conteúdo real (ex.: "só fluxo, sem estoque RAIS", "0 vendidos lidos; só o
tempo resolve"); não foi duplicado sob outro nome. O que faltava e foi somado nesta passagem:

- **`endpoints`** (lista) + **`endpoints_total`** + **`endpoints_confirmados_vivos`**: `plat.acervo_endpoint`
  (migração 040), view sobre `acervo.endpoint` com a mesma regra D17 (só fonte com licença escrita). "Vivo"
  replica a definição que a própria casa já usa: `confirmado = true AND http = '200'`. O total é contado à
  parte da lista (que trunca em 200 itens) — nunca "total" mentindo por causa do truncamento da lista.
- **`completude_texto`**: "4,5/10" por extenso a partir de `procedencia_pontuacao`; `None` (nunca "0/10")
  quando a view não tem base de cálculo — campo ausente é responsabilidade de quem EXIBE ("não registrado"),
  a API nunca fabrica um número.
- **`risco_pii` / `risco_pii_motivo`**: ver 19.2.

Verificado campo a campo contra `acervo.fonte`/`acervo.endpoint` para 20 fontes licenciadas
(`tests/api/test_acervo.py::test_ficha_confere_20_fontes_campo_a_campo_incluindo_endpoints_e_completude`) e
que um campo ausente (`sha256 IS NULL` em 33 das 68 fontes licenciadas) chega como `None`, nunca fabricado
(`test_campo_ausente_na_ficha_nunca_e_fabricado`). **Sem tela própria ainda** (a lista/ficha só existe como
API — item L6-01-c, não construído nesta passagem); o portão completo do item (e2e no navegador) fica
pendente até essa trilha de frontend.

### 19.2 Gate de LGPD no "adicionar" (`plat.acervo_lgpd`, migração 041)

`acervo.fonte` não tem nenhum campo de classificação de risco de dado pessoal (conferido por `\d acervo.fonte`
antes de escrever qualquer coisa — a coluna mais próxima, `cliente_ve`, é sobre visibilidade comercial, não
LGPD). Como `acervo.*` só é escrito pelos scripts da casa (nunca pela plataforma — regra repetida três vezes
no ADR 0012), a classificação vive numa tabela própria da plataforma: `plat.acervo_lgpd` (`fonte_id`,
`risco_pii`, `motivo` NOT NULL, `decidido_por`, `decidido_em`), curada à mão — sem GRANT de escrita para
`plat_app`, só `INSERT`/`UPDATE` literal em migração ou acesso direto ao banco. Nunca calculada.

Curadoria (evidência, não suposição): das 68 fontes licenciadas, uma varredura de
`information_schema.columns` nas 219 tabelas canônicas ligadas a elas (contra um padrão amplo de nome de
coluna — cpf/cnpj/nome/email/telefone/endereço/titular/...) achou 114 colunas suspeitas; lidas uma a uma, a
esmagadora maioria é nome de LUGAR (`zona_nome`, `nome_municipio`), CNPJ de FUNDO (não de pessoa física) ou
endereço de IMÓVEL já público por natureza (leilão/edital). Um caso quase enganou: `<frente>.cad_gu_face_pgv`
tem `telefone`/`telefone_p`, mas são FLAGS de infraestrutura de rua (a rua tem rede telefônica?), não contato
de pessoa. O único achado real: **`onr`** (ONR/matrículas) — a tabela ingerida não guarda nome do titular,
mas `url_mat` aponta para o visualizador de matrícula do cartório, que guarda. Marcada `risco_pii = true`.

`POST /api/acervo/{fonte_id}/adicionar` consulta `plat.acervo_lgpd` (LEFT JOIN, `coalesce(risco_pii,
false)`); fonte marcada e sem `{"confirma_risco_pii": true}` no corpo recusa com **409
`confirmacao_pii_exigida`** ANTES de tocar `plat.item` — e a recusa fica registrada como evento
(`acervo/adicionar_recusado_pii`) em transação PRÓPRIA (mesmo padrão de `_falhou()` em
`app/auth/rotas_login.py`: registrar dentro do bloco que vai levantar a exceção faria `db.db` dar rollback e
apagar o próprio evento da auditoria). Confirmando, o item criado grava `parametros.confirma_risco_pii: true`
(a chave nem aparece quando a fonte nunca precisou de confirmação — nunca `false` fingindo confirmação que
não foi pedida).

**Isto NÃO é o portão inteiro do backlog** (`estado.json`, item L6-01-f-lgpd): falta a classificação POR
COLUNA (lista negra + regex de conteúdo sobre amostra) em TODA view exposta, incluindo `plat.acervo_camada`
(L6-01-a-registro) — hoje só `colunas_expostas`/`colunas_bloqueadas` por nome, comentado como provisório
naquele item. O que foi entregue é o gate no fluxo de "adicionar fonte" descrito no pedido desta passagem;
o resto fica registrado como pendência, não prometido como feito.

## 20. Geocodificador (item L2-11-b-geocodificador-brasil)

Geocodificador PRÓPRIO em PostgreSQL/PostGIS — sem Nominatim nem Pelias instalados (exigiriam o OSM inteiro
do Brasil em disco; decisão D28). Base: CNEFE 2022 do IBGE (endereço com coordenada por face de quadra),
instalado por UF. Nesta demo: **Roraima** (o menor arquivo de UF do CNEFE, medido por `HEAD` antes de
escolher), 260.515 pontos em 15 municípios.

### 20.1 API própria

- `POST /api/geocodificar` — corpo `{"endereco": "Rua X, 123, Bairro, Município - UF"}` (linha única) OU
  campos separados (`logradouro`, `numero`, `bairro`, `municipio`, `uf`, `cep`) — os dois se misturam, o que
  faltar num é completado pelo outro. Devolve até `max_locations` candidatos ordenados por `score` (0-100),
  cada um com `tipo_acerto`: `numero_exato` (ponto do CNEFE com o mesmo número) → `interpolado_na_face`
  (interpolação linear entre dois pontos conhecidos da MESMA face de quadra) → `aproximado_no_logradouro` →
  `aproximado_no_bairro` → `aproximado_no_cep` → `aproximado_no_municipio`. CEP e município/UF que não
  correspondem ao mesmo lugar no CNEFE carregado recusam com `422 cep_municipio_inconsistente`/
  `cep_uf_inconsistente` (nomeando o lugar correto do CEP), ANTES de qualquer busca por logradouro. Nome
  repetido em municípios diferentes (ex.: `Rua A`, que se repete em 8 dos 15 municípios de Roraima) devolve
  vários candidatos, um por município — nunca escolhe um arbitrariamente.
- `POST /api/reverso` — corpo `{"lon": ..., "lat": ..., "raio_m": 2000}`. Vizinho mais próximo por índice
  GiST (`geom <->`, KNN); devolve o endereço, a distância em metros e `fora_do_raio` quando a distância passa
  do raio pedido (o vizinho mais próximo sempre volta, mesmo fora do raio — quem decide descartar é o
  chamador).
- `GET /api/sugerir?q=...` — autocomplete por prefixo sobre índice GIN trigram (medido: p95 33,1 ms com 260
  mil linhas instaladas).

Todas exigem sessão de usuário ou token de serviço com o escopo `geocodificar:usar` (novo).

### 20.2 GeocodeServer compatível Esri

`GET /rest/services/Geocodificador/GeocodeServer` (descritor, sem autenticação — só metadado) e
`findAddressCandidates` / `reverseGeocode` / `suggest` / `geocodeAddresses` sob o mesmo prefixo, com os
mesmos parâmetros que o ArcGIS Enterprise usa (`SingleLine`, `address`/`city`/`region`/`postal`,
`maxLocations`, `location=lon,lat`, `text`, `addresses.records[].attributes`). **Autenticação por
`?token=<token de serviço>` na querystring** (o protocolo real do locator publicado pela Esri, diferente da
regra geral de `/api/`, que só aceita `Authorization: Bearer` — ver seção sobre tokens) além do cabeçalho
normal. `Addr_type` da resposta é uma tradução aproximada da hierarquia de recuo para o vocabulário Esri
(`PointAddress`, `StreetAddress`, `StreetName`, `Locality`, `PostalExt`) — não é 1:1 com o locator real.
Tabela de paridade completa (feito/parcial/fora) em `docs/PARIDADE.md`, seção "Geocodificador".

**QGIS como locator real fica como PENDÊNCIA, não como feito**: esta máquina não tem QGIS instalado nem
ambiente gráfico (mesma limitação do Chrome headless já registrada neste documento). O protocolo foi
verificado por chamada HTTP direta simulando exatamente o que o QGIS/ArcGIS Pro mandariam — prova o
protocolo, não a integração do produto.

### 20.3 Instalação por UF

`venv/bin/python3 scripts/geocodificador_instalar_uf.py --uf <SIGLA>` mede o tamanho do arquivo por `HEAD`
antes de baixar (teto padrão 200 MB comprimidos, D28; `--forcar` ignora), baixa em streaming com sha256
acumulado, lê o zip membro a membro (nunca extrai por inteiro em disco) e carrega por `COPY` em lotes de 20
mil linhas. Reinstalar a mesma UF apaga e recarrega (idempotente). Proveniência em `plat.geo_instalacao`
(tamanho do zip/CSV, linhas, municípios, duração, sha256) — Roraima: 4,52 MB comprimidos, 42,05 MB de CSV,
260.515 linhas, 15 municípios, **10,4 s**, tabela final **126 MB com índices**.

### 20.4 Limites desta fatia

Sem São Paulo carregado (é o MAIOR arquivo de UF do CNEFE — fora do teto de disco D28); a ambiguidade
multi-município foi provada com `Rua A` em Roraima, registrado explicitamente como substituto, nunca
disfarçado de SP real. Sem `outSR`/`searchExtent`/boost por proximidade/`category`/`langCode`/paginação
`search-start-num`. `magicKey` do `suggest` é devolvido mas ainda não é aceito de volta no
`findAddressCandidates` (o item-irmão `L2-11-a-geocodificacao-csv`, lote de planilha do usuário, também não
foi construído nesta passagem — reusa o mesmo motor). Ver `laco/handoffs/T3/L2-11-b-geocodificador-brasil.md`
e ADR 0013 para o estado exato.

## 21. SMTP, convite de membro e redefinição de senha (item L0-07-d-smtp-convites)

### 21.1 SMTP (`/admin/organizacao`, seção "E-mail (SMTP)")

`GET/PUT /api/org/smtp` (privilégio `org.integracoes`) grava host, porta, STARTTLS, usuário, senha (cifrada,
nunca devolvida — só `senha_configurada: bool`), remetente e rótulo em `tenant.config->'smtp'`. Sem SMTP
próprio, o inquilino usa o da instalação (`PLAT_SMTP_*` do `.env`); sem nenhum dos dois, os fluxos abaixo
caem no caminho manual já existente (senha temporária mostrada uma vez ao admin). Deixar `host` em branco no
PUT remove o override do inquilino. `POST /api/org/smtp/testar` envia um e-mail de teste SÍNCRONO (não pela
fila) para o próprio e-mail do admin (ou outro informado) e devolve o erro em texto simples na mesma
resposta quando falha — nunca um traceback, nunca a senha.

### 21.2 Convite de membro (`/admin/usuarios`, seção "Convidar por e-mail")

Um admin com `membros.gerir` convida por e-mail (perfil diferente de visualizador ou com papel exige
`membros.papel`, mesmo teto de `POST /api/usuarios`). Com SMTP configurado, o convite sai por e-mail (job
`correio.enviar` da fila do L0-05); sem SMTP, a resposta devolve `link_manual` para o admin repassar. O link
(`/aceitar-convite?token=...`) carrega só o token — nunca o e-mail nem o perfil, que o servidor sempre lê do
convite. O convidado escolhe login, nome e senha; a conta nasce com o perfil/papel do convite. Token de uso
único, válido por 7 dias; usar de novo ou usar depois de expirado devolve `410`. Reenviar um convite para o
mesmo e-mail cancela o anterior (nunca acumula links vivos).

### 21.3 Redefinição de senha por e-mail (`/redefinir-senha`, pública)

`POST /api/senha/redefinir/solicitar {inquilino, email}` sempre responde `202 {"ok": true}` — existindo ou
não a conta, exceto quando o limite de taxa por (inquilino, e-mail) estoura (`429`, no máximo 5 pedidos a
cada 15 minutos). Com SMTP configurado e a conta existindo, chega um e-mail com um link de 1 hora,
uso único; `POST /api/senha/redefinir/aplicar {token, senha}` troca a senha pela MESMA regra de política e
histórico que `/conta` já usa, encerra as sessões do usuário e registra o evento. Sem SMTP, o pedido fica
registrado (conta para o limite de taxa) mas não chega e-mail nenhum — o usuário pede ao admin.

### 21.4 O que ficou de fora

Avisos de expiração de token (90/30/7/1 dia) e notificação de grupo por e-mail não foram construídos neste
turno (fora do portão literal do item; ver ADR 0017 seção D5) — o job `correio.enviar` já está pronto para
os dois, falta só o gatilho periódico.

## 22. Construtor de camada por esquema (`/construtor-camada`, item L5-31-construtor-de-camada-esquema)

Cria uma camada VAZIA a partir de uma lista de campos, sem precisar de arquivo nenhum. Passo 1: título,
tipo de geometria e SRID. Passo 2: uma paleta de 8 tipos de campo (texto, inteiro, inteiro longo, decimal,
verdadeiro/falso, data, hora, data e hora) — arraste um até a lista de campos abaixo, ou clique nele (as
duas formas fazem a mesma coisa; quem não usa mouse usa o clique). Cada linha de campo tem nome, alias
(rótulo de tela), tamanho (só para texto), valor padrão, domínio (lista `código:rótulo, código:rótulo`,
separada por vírgula) e as caixas "obrigatório"/"índice". "criar camada" grava a tabela de verdade no
PostgreSQL (com a mesma segurança — RLS, colunas de auditoria — de uma camada importada) e mostra de volta
os campos no formato que um FeatureServer usa (`fields`), já com o alias e o domínio certos.

### 22.1 Alterar o esquema de uma camada existente

`POST /api/camadas/{id}/esquema/plano` mostra o que ACONTECERIA com uma lista de mudanças, sem tocar o
banco: cada mudança vem com `aplicavel` (sim/não) e, quando não, o motivo exato. `PUT /api/camadas/{id}/esquema`
aplica só as que passaram no plano. Mudanças possíveis: `adicionar_campo` (sempre aplica), `renomear_alias`
(sempre aplica — é só um rótulo, não mexe na coluna real), `mudar_tamanho` (aumentar sempre aplica; diminuir
só se ninguém tiver gravado um valor maior que o novo tamanho) e `mudar_tipo` (alargar — inteiro→inteiro
longo→decimal, ou qualquer coisa→texto — sempre aplica; o resto só se a camada estiver VAZIA, porque poderia
perder dado. Ex.: texto→inteiro com uma camada que já tem "AB-12" gravado é recusado com a mensagem exata).

### 22.2 O que ficou de fora

O formulário padrão (L5-03) e o popup padrão (L5-26) que a hipótese do item cita não foram montados nesta
passagem — dependem desses dois itens existirem nesta árvore; o contrato que eles vão consumir
(`GET /api/camadas/{id}/campos`, formato `fields`) já está pronto e testado. Modelos de camada por setor
(agro, energia, ...) também ficaram de fora — não fazem parte do portão literal deste item.
## 22. Edição de feições no mapa (`/mapa`, painel "Edição", item L2-03-edicao)

Aparece na tela `/mapa` (seção 13) sempre que houver ao menos uma camada com edição habilitada
(`dados.edicao.habilitada`) — o seletor "camada a editar" lista só essas.

- **Criar**: botões Ponto/Linha/Polígono; ponto entra com um clique, linha/polígono acumulam cliques
  até "Concluir". Um formulário abre com os campos da camada, domínio (lista fechada vira `<select>`,
  faixa numérica é conferida) e obrigatório marcados — a mesma regra que `app/edicao/servico.py`
  aplica no servidor (a tela nunca é a única barreira: mandar um valor fora do domínio direto na API
  também volta `422`).
- **Selecionar/mover/editar vértice**: botão "Selecionar" e clique numa feição desenhada; a geometria
  de trabalho é sempre lida de `GET /api/camadas/{id}/feicoes/{globalid}` (exata), nunca a versão
  recortada por tile. Vértices aparecem como círculos arrastáveis — soltar salva na hora.
- **Apagar**: com uma feição selecionada, botão "Apagar".
- **Aderência**: caixa "aderir a vértice próximo" (ligada por padrão); ao desenhar ou arrastar, um
  vértice a até 12 px de outra feição desenhada salta para a coordenada exata dela.
- **Edição em lote**: selecionar mais de uma feição (shift+clique) muda um atributo e clicar "Aplicar
  às selecionadas" grava o mesmo valor em todas, num único lote.
- **Dividir/Unir**: "Dividir" pede um clique no meio de uma linha selecionada (LineString de uma parte
  só nesta passagem — polígono e linha de mais de uma parte ficam fora, ver ADR); "Unir" combina duas
  ou mais feições selecionadas (qualquer geometria) numa só.
- **Desfazer**: o histórico de cada feição (abaixo do formulário, ao selecionar UMA) lista toda escrita
  — inclusive as que não passaram pela tela — com botão "restaurar" por entrada; restaurar uma feição
  apagada a recria com o MESMO identificador.
- **Anexos**: por feição, envia (limite de tamanho e de tipo aplicados no servidor, contra o conteúdo
  de verdade, não só o `Content-Type` declarado), lista e apaga.
- **Edição concorrente**: duas sessões na mesma feição — quem salva por último recebe o aviso "outra
  sessão alterou esta feição" (nunca sobrescreve calado; versão otimista do L2-03-a).

### 22.1 O que ficou de fora

Dividir polígono por linha de corte; união com política de mesclagem de atributo além de "usa os da
primeira feição ou o que o chamador mandar"; desfazer/refazer por atalho de teclado (o mecanismo hoje
é o histórico por feição, não uma pilha global de ações). Ver
`docs/adr/20260907T1123-historico-restauracao-anexos-feicao.md`.
## 22. Modelo de estilo (item L2-02-a-modelo-estilo)

O documento de um item do tipo `estilo` tem duas partes: `plat_construtor` (o que o editor grava — tipo de
classificação entre `unico`, `categoria`, `classes`, `proporcional`, `calor`, `agrupamento`, `raster`, o
campo classificador, as cores, os rótulos, a faixa de escala e a transparência) e `maplibre` (as camadas da
MapLibre Style Spec v8 que o navegador desenha). Só `plat_construtor` é editável de fato: `maplibre` é sempre
recalculado pelo servidor a partir dele no momento de gravar (`POST`/`PUT /api/itens`), então salvar duas
vezes o mesmo construtor produz sempre o mesmo estilo — reabrir um estilo salvo e salvar de novo nunca muda o
desenho por acidente.

Um estilo inválido nunca chega a ficar salvo: campo de classificação que não existe na lista declarada,
faixa de classe com o mínimo maior que o máximo, valor de categoria repetido, mais de 200 camadas, ou uma
camada que não é uma MapLibre Style Spec válida — tudo isso volta como erro `422` no momento de salvar, com
o campo exatamente apontado, nunca como um mapa que desenha errado depois de aberto.

### 22.1 Como um estilo se referencia num mapa

A entrada de camada de um documento de mapa (item L2-01-a-documento-mapa) referencia um estilo por
`{ref: <uuid do item estilo>}` (reutilizável entre vários mapas) ou `{embutido: <o mesmo formato>}` (só
daquele mapa). Apagar um item `estilo` referenciado por algum mapa é recusado (`409`, com a lista de mapas
que dependem dele — mesmo mecanismo de dependência do L0-03-i).

### 22.2 Estilo padrão e exportação

Toda camada nova recebe um estilo padrão determinístico por tipo de geometria: a cor sai de um hash da
identidade do item, então a mesma camada tem sempre a mesma cor padrão, em qualquer instalação. Um estilo
`unico`/`categoria`/`classes` pode ser exportado como SLD 1.0 (para QGIS ou para o WMS do L2-04-i); os demais
tipos (`proporcional`, `calor`, `agrupamento`, `raster`) não têm equivalente em SLD e a exportação recusa,
dizendo por quê.

### 22.3 O que ficou de fora

A conversão para/do renderer da Esri (item L2-04-b) e o WMS que consome o SLD (L2-02-e/L2-04-i) são itens
seguintes. O editor visual do construtor (tela) não foi construído aqui — este item é o formato e a
validação do documento, não a interface.
## 22. Ladrilho raster por token (item L1-02-tiles-token)

Publica uma imagem já ingerida (L1-01) como camada de mapa para qualquer cliente — QGIS, ArcGIS,
navegador, mapa de terceiro — sem login e sem plugin. O que dá acesso é um **token de serviço** com
escopo `tiles:ler`, criado em `/admin/tokens`, e ele vai **no caminho da URL**.

### 22.1 As URLs

Com `<tok>` = o token e `<item>` = o identificador da imagem no catálogo:

| para quê | endereço |
|---|---|
| XYZ (a camada "XYZ Tiles" do QGIS, `L.tileLayer` do Leaflet, `raster` do MapLibre) | `https://<dominio>/svc/<tok>/raster/<item>/{z}/{x}/{y}.png` |
| TileJSON (o mapa lê extensão e zoom sozinho) | `https://<dominio>/svc/<tok>/raster/<item>/tilejson.json` |
| WMTS (o que o QGIS e o ArcGIS pedem em "Add WMTS layer") | `https://<dominio>/svc/<tok>/raster/<item>/wmts/1.0.0/WMTSCapabilities.xml` |
| WMTS por KVP | `https://<dominio>/svc/<tok>/raster/<item>/wmts?SERVICE=WMTS&REQUEST=GetCapabilities` |
| extensão, bandas, tipo do dado, lista de colormaps | `https://<dominio>/svc/<tok>/raster/<item>/info.json` |
| mosaico de uma coleção (cena mais recente por cima) | `https://<dominio>/svc/<tok>/mosaico/<colecao>/{z}/{x}/{y}.png` |

Formatos: `.png` (padrão), `.jpg`, `.webp`.

### 22.2 Como pintar (os parâmetros)

| parâmetro | o que faz | exemplo |
|---|---|---|
| `bandas` | ordem das bandas na saída | `bandas=3,2,1` |
| `expressao` | conta sobre as bandas, avaliada por pixel | `expressao=(b4-b3)/(b4%2Bb3)` (NDVI) |
| `faixa` | valores que viram 0 e 255, por banda | `faixa=-1,1` |
| `colormap` | paleta (211 disponíveis; a lista está em `info.json`) | `colormap=viridis` |
| `asset` | `visual` (8 bits, mais barato) ou `cientifico` (bandas originais) | `asset=cientifico` |

O `+` da expressão precisa ir codificado como `%2B` na URL — em `+` cru o servidor lê espaço.
Sem `bandas` e sem `expressao`, uma imagem de mais de três bandas sai com as três primeiras.
Com `expressao`, o padrão passa a ser o asset `cientifico`.

Os mesmos parâmetros valem no `tilejson.json` e no WMTS: o documento devolvido já traz a pintura
embutida no endereço dos ladrilhos, então a camada salva no QGIS reabre igual.

### 22.3 Quem pode ler, e por quanto tempo

- o token precisa do escopo `tiles:ler` (ou `tiles:ler:<uuid do item>`, para liberar uma imagem só);
- em `/admin/tokens` dá para restringir por **Referer/Origin** (o mapa só funciona no site declarado) e
  por **faixa de IP**;
- **revogar o token tira o serviço do ar em poucos segundos** — medido de 2,86 s a 2,90 s, inclusive
  para ladrilhos que já estavam no cache;
- toda recusa responde **403**, com o motivo em `erro` (`token_revogado`, `escopo_insuficiente`,
  `referer_nao_permitido`, `ip_nao_permitido`, `item_indisponivel`).

Ladrilho fora da área da imagem responde **204 sem corpo** — o mapa continua navegável.

### 22.4 Quanto foi usado

`GET /api/tiles/leituras?dias=30` devolve, por token, quantos ladrilhos foram servidos, quantos bytes,
quantos erros e quantas imagens diferentes. É o que a cobrança por uso vai ler. O token em si nunca é
guardado — só o identificador dele e o prefixo visível.

### 22.5 O que ainda não faz

- o mosaico serve a cena mais recente que cobre o ladrilho; não há escolha por pixel (nuvem) nem linha
  de costura — isso é o L1-07/L1-08;
- não há WMS 1.3.0 (L1-02-g), nem OGC API Tiles/Maps (L1-02-i), nem ponto/estatística/histograma
  (L1-02-h), nem predefinição de renderização gravada (L1-02-f): por enquanto a pintura vive na URL;
- a única grade é a WebMercatorQuad (a do Google/OSM/AGOL).
## 22. Exportação de camada para outros formatos (item L0-04-h-exportar)

### 22.1 Botão Exportar (painel do item, camada vetorial hospedada)

O painel de uma camada vetorial hospedada (não referenciada) mostra o botão **Exportar** quando o usuário
tem o privilégio `conteudo.exportar` (perfis editor e admin por padrão). O diálogo pede: formato (11
opções), nome do arquivo, campos a exportar, filtro `where` opcional, sistema de coordenadas de saída
(EPSG; em branco mantém o da camada), codificação de texto e, para CSV, separador de coluna, separador
decimal e o nome das colunas de longitude/latitude. O dono do item vê também a caixa "permitir que outros
exportem esta camada" (nasce desligada — como o "Allow others to export to different formats" da Esri).
Depois de mandar exportar, o diálogo consulta o estado a cada segundo sem travar a tela; quando o arquivo
fica pronto, mostra o link de download com a validade (7 dias). Erro do servidor (filtro inválido, limite
de exportações em curso, EPSG inexistente, item de outro dono) aparece com a mensagem que o servidor
mandou.

### 22.2 Formatos e o que cada um NÃO guarda

`gpkg · geojson · geojsonseq · shapefile (zip) · csv · xlsx · kml · kmz · fgb (FlatGeobuf) · gml · dxf ·
filegdb (File Geodatabase em zip) · mvt (zip) · pmtiles · geoparquet`, mais o `pacote` de mapa (§22.7).
`gpkg · geojson · shapefile (zip) · csv · xlsx · kml · kmz · fgb (FlatGeobuf) · gml · dxf · geoparquet`.
DXF não guarda atributo (o driver recusa criar campo); CSV e XLSX não guardam geometria (o CSV ganha
colunas de X/Y, ou WKT quando pedido) — limites do FORMATO, declarados em `GET /api/exportacoes/formatos`
e mostrados no diálogo antes de escolher. GeoParquet sai por um processo próprio (`app.exportacao.parquet_cli`,
via DuckDB) porque o `ogr2ogr` desta instalação não tem driver Parquet e o DuckDB não sobrevive a um fork.

### 22.3 Isolamento entre inquilinos

A exportação nunca traz linha de outro inquilino, mesmo que o pedido seja forjado diretamente no banco: o
`ogr2ogr` abre conexão própria (fora do pool da aplicação) com o inquilino na PRÓPRIA string de conexão
(`-c plat.tenant_id=N`), e é a política de RLS da tabela da camada que faz o corte — não um `WHERE` escrito
pela aplicação. `tests/api/exportacao/test_exportacao_cruzado.py` prova isso em quatro níveis: API (404 no
item alheio), job com pedido forjado no banco (falha dizendo que a camada não existe), `ogr2ogr` chamado
com o contexto do outro inquilino e sem contexto nenhum (0 feições nos dois casos) e o conteúdo do arquivo
final (nenhuma linha do outro inquilino).

### 22.4 Arquivo grande nunca vai inteiro à memória

O envio ao armazenamento de objetos (`objetos.guardar_arquivo`) lê o arquivo do disco em blocos de 8 MiB:
até um bloco, um `PUT` só; acima disso, multipart real (uma parte por vez). O download
(`GET /api/exportacoes/{id}/baixar`, via `objetos.ler_stream`) entrega em blocos de 1 MiB. Medido com
`tracemalloc`: um arquivo de 40 MiB sobe em 5 partes de 8 MiB com pico de memória abaixo de 3 partes.

### 22.5 Limites

3 exportações em curso por usuário (a 4ª e a 5ª recebem `429`); guarda de disco (`shutil.disk_usage`) antes
do primeiro byte, com estimativa de tamanho×3 + 2 GiB de folga (disco desta máquina a 98 %); arquivo gerado
some depois de 7 dias (periódico `exportacao.expirar`, de hora em hora).

### 22.6 O que ficou de fora

Exportação de camada REFERENCIADA (recusada com 422 `camada_nao_hospedada`, nunca silenciosa).

## 23. Exportar a partir do mapa (item L2-01-l)

### 23.1 O bloco Exportar da tela do mapa

O painel do mapa tem o bloco **Exportar** com a camada ligada, o formato, o EPSG de saída e a caixa "só as
feições da vista atual" (que manda a extensão da tela como recorte). O botão cria a exportação, a tela
acompanha o estado e mostra o link com a validade que o servidor informa (7 dias). Ao lado, dois botões
baixam o ESTILO da camada: MapLibre (JSON) e SLD 1.0.0 — os dois gerados da mesma lista de classes que
gera a legenda, então o mapa da tela, a legenda impressa e o arquivo entregue nunca discordam de cor.

### 23.2 O que se exporta: a camada, o filtro ou a seleção

`POST /api/exportacoes` aceita como `item_id` uma `camada_vetorial`, uma `vista_de_camada` ou uma
`selecao` salva, e ainda `ids` (a lista de fid da seleção do mapa) e `filtro` (CQL2-JSON, o mesmo objeto
de `POST /api/mapa/camadas/{id}/filtrar`). Numa vista, o filtro dela vale sempre e os `campos_ocultos`
ficam de fora: pedir um campo escondido é `422 campo_oculto`, e filtrar por ele é `422 campo_nao_permitido`
(esconder um campo que ainda serve de filtro não esconde nada — a contagem entregaria o valor).

### 23.3 CRS: o que o formato deixa

Formato de CRS livre (GeoPackage, shapefile, FlatGeobuf, GML, File Geodatabase) grava o EPSG pedido.
Formato de CRS preso pela especificação (GeoJSON, GeoJSON Sequence, KML, KMZ = 4326; MVT e PMTiles = 3857)
grava sempre o dele, e pedir outro é `422 crs_fixo_do_formato` — a alternativa seria um arquivo com
coordenada projetada sob rótulo de WGS 84. CSV, XLSX e DXF não guardam CRS nenhum: a reprojeção vale para
os números, e quem diz em que CRS eles estão é o relatório da exportação.

### 23.4 Perda declarada e teto do formato

A resposta do pedido traz `perda_declarada`: DXF não leva atributo, CSV/XLSX não levam geometria, o
shapefile trunca nome de campo em 10 caracteres, MVT/PMTiles recortam a geometria por tile (a contagem do
arquivo não é a do banco). O XLSX tem teto de 1.048.576 linhas do próprio Excel: acima disso o pedido é
recusado com `422 formato_limite_de_linhas` e o número de feições, ANTES de existir job — um arquivo
truncado em silêncio seria pior que a recusa.

### 23.5 Copiar uma feição

Na janela de atributos, dois botões copiam a feição como GeoJSON ou como WKT
(`GET /api/mapa/camadas/{id}/feicoes/{fid}?formato=geojson|wkt`, sempre em EPSG:4326). O texto vem da
TABELA, não do tile: a geometria do tile chega recortada na borda e generalizada pelo zoom.

### 23.6 Imagem do mapa

O botão PNG desenha, sobre a imagem, a legenda das camadas ligadas e a atribuição das fontes, além da
escala, da barra e do norte que já existiam. A caixa "2x" monta um mapa temporário fora da tela com o
dobro de largura e altura e um nível de zoom a mais, e lê ELE — o dobro de detalhe de verdade, não uma
ampliação do que estava na tela.

### 23.7 Pacote de mapa (levar para outra instalação)

`POST /api/exportacoes` com `formato: "pacote"` e um item do tipo `mapa` gera um zip com `MANIFESTO.json`,
`dados.gpkg` (uma tabela por camada CITADA pelo mapa, e só) e `estilos/<camada>.json` + `.sld`. É o mesmo
job e o mesmo link de 7 dias da exportação de camada. `POST /api/mapa/pacotes/importar` (corpo
`application/zip`) recria o mapa no inquilino de destino: cada camada vira tabela nova, com a simbologia
que veio, e o corpo do documento é reescrito para apontar para os identificadores novos. Camada citada que
já não existe entra no relatório como ausente — um pacote menor e verdadeiro em vez de tabela vazia.
## 24. Regras de atributo por camada (item L2-10-d-regras-de-atributo)

Uma camada hospedada pode ter regras avaliadas no servidor, na mesma porta de escrita da seção de edição:

```
GET  /api/camadas/{id}/regras            # regras, campos virtuais, última validação, ordem de avaliação
PUT  /api/camadas/{id}/regras            {"regras": [...], "campos_virtuais": [...]}   # compila antes de gravar
POST /api/camadas/{id}/validar           # job camadas.validar -> {"job_id", "estado"}
GET  /api/camadas/{id}/feicoes?limite=&fid=   # feições com os campos virtuais avaliados
GET  /api/camadas/{id}/erros             # erros da última validação
```

Uma regra é `{"id", "tipo", "expressao", ...}` na linguagem de expressão (`docs/EXPRESSAO.md`; campo = `$nome`):
- `calculo`: `campo` alvo recebe o valor da expressão ao inserir e ao atualizar; `gatilhos` (lista de campos,
  `geom` inclusive) limitam a atualização aos pedidos que mudam um deles; `ordem` define a sequência e o valor
  calculado por uma regra dispara as seguintes; `eventos` restringe a `inserir`/`atualizar`.
- `restricao`: expressão booleana; falso ou nulo recusa a edição com HTTP 422, `erro` = `codigo` da regra e
  `mensagem` configurada (no modo `parcial`, só aquela feição falha).
- `validacao`: nunca roda na edição; `POST .../validar` percorre a camada inteira em lotes e grava cada falha
  (feição, regra, código, mensagem, instante, geometria) na tabela `e_<hex16>` ao lado da camada, e cria o item
  "Erros de validação — <camada>" (camada só-leitura) no catálogo.
- `habilitada: false` desliga sem apagar; `excluir_em_massa: true` pula a regra quando o lote de edição vem com
  `"em_massa": true` (importação em massa).
- `campos_virtuais`: `{"nome", "expressao"}` só leitura, avaliados na leitura e disponíveis nas expressões das
  regras; nunca gravados nem aceitos como atributo.
Erros de configuração (422, antes de gravar): `regra_expressao_invalida`, `regra_campo_inexistente`,
`regra_invalida` e `regra_ciclo` (regra que calcula um campo que está nos próprios gatilhos, ou cadeia fechada
entre regras; o `detalhe.ciclo` traz o caminho). A regra vale por qualquer caminho de escrita porque todos passam
por `POST /api/camadas/{id}/edicoes`.

## 25. Linguagem de expressão no navegador (item L5-11-expressoes-no-navegador)

A mesma linguagem de expressão da seção 24 roda também no NAVEGADOR, com semântica idêntica: um
analisador escrito à mão em `web/js/expressao/avaliador.js` e outro em `app/expressao/avaliador_py.py`,
os dois sobre os mesmos vetores de teste (`tests/expressoes/vetores.json` e
`tests/expressoes/vetores_perfis.json`), comparados valor a valor pela suíte. A gramática completa,
os tipos, a propagação de nulo e a AST em JSON estão em `docs/EXPRESSAO.md`; esta seção é o resumo
de uso, com um exemplo por função.

Como se escreve: `$nome` é um atributo da feição, `$feicao` é a feição inteira
(`{"atributos": ..., "geometria": ...}`) e `$geometria` é a geometria dela, em GeoJSON
(`{"type": "Point"|"LineString"|"Polygon", "coordinates": ...}`, grau decimal WGS-84, longitude
antes da latitude). Atributo cujo nome tem espaço, acento ou hífen não vira `$nome`: alcança-se por
`Atributo($feicao, 'nome do lote')`. Exemplo de popup:
`Concatenar($nome, ' - ', TextoNumero($area_ha, 1), ' ha')`.

O que a expressão NÃO alcança: rede, disco, banco, outra feição e outro inquilino. O contexto é
montado por `contexto_da_feicao` (`app/expressao/perfis.py` e `web/js/expressao/perfis.js`) só a
partir da feição recebida, e `$campo` fora dessa lista devolve o erro `campo_nao_permitido`.
Expressão que não termina é cortada pelo orçamento de tempo do perfil (50 ms no navegador, 500 ms
no servidor) ou pelo orçamento de 100.000 passos, sempre com erro nomeado (`tempo_excedido`,
`limite_passos`), nunca com a aba travada.

Medidas de área, comprimento e distância usam a ESFERA de raio autálico 6.371.008,8 m, sem
elipsoide e sem projeção — o erro do modelo chega a 0,5 %, então servem para ordem de grandeza e
comparação, não para medição legal de área. O resultado é arredondado a 6 casas decimais para o
servidor e o navegador devolverem exatamente o mesmo número.

<!-- inicio: catalogo de expressao gerado por docs/gerar_manual_expressao.py -->

### Perfis (onde a expressão é usada)

| perfil | tipo de valor que tem de devolver | orçamento de tempo | para que serve |
|---|---|---|---|
| `popup` | texto · numero · booleano · nulo | 50 ms | linha de conteúdo da janela de feição, avaliada no navegador a cada clique |
| `rotulo` | texto · numero · nulo | 50 ms | texto desenhado sobre a feição no mapa, avaliado no navegador a cada quadro |
| `calculo_formulario` | texto · numero · booleano · nulo | 500 ms | valor calculado de um campo do formulário de edição, conferido também no servidor |
| `visibilidade` | booleano · nulo | 50 ms | mostra ou esconde um campo/elemento; nulo é 'não sei' e o chamador trata como escondido |
| `restricao` | booleano · nulo | 500 ms | verdadeiro = a feição pode ser gravada; falso ou nulo = a gravação é recusada |
| `indicador_painel` | numero · nulo | 500 ms | número exibido num indicador de painel |
| `titulo_dinamico` | texto · numero · nulo | 50 ms | título de janela, aba ou painel montado a partir da feição |

### Catálogo de funções (49), uma linha e um exemplo por função

| função | argumentos | o que faz | exemplo |
|---|---|---|---|
| `Maiuscula` | 1 | converte texto para maiúsculas | `Maiuscula('sítio') → 'SÍTIO'` |
| `Minuscula` | 1 | converte texto para minúsculas | `Minuscula('SÍTIO') → 'sítio'` |
| `Concatenar` | 1 ou mais | junta 2+ textos (nulo vira texto vazio) | `Concatenar('a','b','c') → 'abc'` |
| `Texto` | 1 | converte número/booleano/nulo para texto | `Texto(3.5) → '3.5'` |
| `Arredondar` | 1-2 | arredonda para N casas (padrão 0), meio-para-longe-de-zero | `Arredondar(2.345, 2) → 2.35` |
| `Absoluto` | 1 | valor absoluto | `Absoluto(-4) → 4` |
| `Minimo` | 1 ou mais | menor valor entre 1+ números | `Minimo(4, 1, 9) → 1` |
| `Maximo` | 1 ou mais | maior valor entre 1+ números | `Maximo(4, 1, 9) → 9` |
| `Numero` | 1 | converte texto/booleano para número (nulo se não for número válido) | `Numero('42') → 42` |
| `Potencia` | 2 | base elevada ao expoente | `Potencia(2, 10) → 1024` |
| `AgoraUTC` | 0 | instante atual, milissegundos UTC desde a época Unix | `AgoraUTC() → 1798000000000` |
| `Ano` | 1 | ano civil UTC de uma data | `Ano(1798761600000) → 2026` |
| `Mes` | 1 | mês civil UTC de uma data (1-12) | `Mes(1798761600000) → 12` |
| `Dia` | 1 | dia do mês civil UTC de uma data (1-31) | `Dia(1798761600000) → 31` |
| `DiferencaDias` | 2 | dias corridos completos entre duas datas (data2 − data1) | `DiferencaDias(a, b) → 30` |
| `SeNulo` | 2 | se o 1º argumento é nulo, avalia e devolve o 2º (curto-circuito) | `SeNulo($x, 0) → 0` |
| `EhNulo` | 1 | verdadeiro se o argumento é nulo | `EhNulo($x) → falso` |
| `Se` | 3 | condição booleana decide qual ramo é avaliado (curto-circuito) | `Se($a > 0, 'pos', 'neg')` |
| `Trim` | 1 | remove espaços ASCII das pontas | `Trim(' a ') → 'a'` |
| `Left` | 2 | primeiros N pontos de código | `Left('a🌍b', 2) → 'a🌍'` |
| `Right` | 2 | últimos N pontos de código (0 devolve vazio) | `Right('abc', 1) → 'c'` |
| `Mid` | 2-3 | trecho a partir de um índice; sem quantidade vai até o fim | `Mid('abcd', 1, 2) → 'bc'` |
| `Find` | 2-3 | índice da 1ª ocorrência a partir de um início; −1 se ausente | `Find('b', 'abc') → 1` |
| `Split` | 2 | divide por separador literal (vazio divide em pontos de código) | `Split('a,b', ',')` |
| `Replace` | 3 | troca todas as ocorrências literais | `Replace('aba', 'a', 'x') → 'xbx'` |
| `Floor` | 1 | maior inteiro ≤ número | `Floor(-1.5) → -2` |
| `Ceil` | 1 | menor inteiro ≥ número | `Ceil(-1.5) → -1` |
| `Sqrt` | 1 | raiz quadrada (negativo é numero_invalido) | `Sqrt(9) → 3` |
| `Weekday` | 1 | dia da semana UTC, domingo 0 … sábado 6 | `Weekday(0) → 4` |
| `Decode` | 4 ou mais | pares caso/resultado e padrão; só o resultado escolhido é avaliado | `Decode(1, 1, 'a', 'z')` |
| `Lista` | 0 ou mais | lista nova com os argumentos (preserva nulos) | `Lista(1, nulo)` |
| `Contagem` | 1 | tamanho de lista, texto (pontos de código) ou dicionário | `Contagem(Lista(1, 2)) → 2` |
| `Primeiro` | 1 | primeiro elemento (nulo se vazia) | `Primeiro(Lista(4, 5)) → 4` |
| `Ultimo` | 1 | último elemento (nulo se vazia) | `Ultimo(Lista(4, 5)) → 5` |
| `Obter` | 2-3 | lista por índice ou dicionário por chave própria; ausente → padrão/nulo | `Obter(Lista(4), 0) → 4` |
| `Contem` | 2 | presença por igualdade estrutural estrita | `Contem(Lista(1), verdadeiro) → falso` |
| `Soma` | 1 | soma de números (vazia → 0; membro nulo → nulo) | `Soma(Lista(1, 2)) → 3` |
| `Media` | 1 | média de números (vazia ou membro nulo → nulo) | `Media(Lista(1, 2)) → 1.5` |
| `Reverter` | 1 | cópia em ordem inversa | `Reverter(Lista(1, 2))` |
| `Unicos` | 1 | sem repetições, preservando a 1ª ocorrência | `Unicos(Lista(1, 1))` |
| `Juntar` | 1-2 | texto dos escalares com separador (nulo vira vazio) | `Juntar(Lista(1, 2), '/') → '1/2'` |
| `TextoNumero` | 1-2 | número em pt-BR: milhar '.', decimal ',', N casas (padrão 2) | `TextoNumero(1234.5) → '1.234,50'` |
| `TextoData` | 1-2 | data UTC em pt-BR: 'data' (padrão), 'data_hora', 'data_hora_segundos', 'extenso' | `TextoData(0) → '01/01/1970'` |
| `Atributo` | 2-3 | atributo da feição por nome; ausente devolve o padrão (ou nulo) | `Atributo($feicao, 'uso')` |
| `Geometria` | 1 | geometria da feição (nulo se a feição não tiver) | `Geometria($feicao)` |
| `Area` | 1 | área do polígono em metros quadrados | `Area($area) → 12363718145.180046` |
| `Comprimento` | 1 | comprimento da linha em metros | `Comprimento($linha) → 111195.080234` |
| `Distancia` | 2 | distância entre dois pontos em metros | `Distancia($a, $b) → 111195.080234` |
| `Dentro` | 2 | verdadeiro se o ponto está dentro do polígono | `Dentro($p, $area) → verdadeiro` |
<!-- fim: catalogo de expressao gerado por docs/gerar_manual_expressao.py -->

---

## 23. Réplicas para trabalho desconectado (item L2-13-b-replicas-sincronizacao)

Uma réplica é um recorte declarado de camadas empacotado num GeoPackage, para editar sem rede e devolver
depois. É a base da PWA de campo (L2-07-c) e o formato que o QField lê.

### Criar

```
POST /api/replicas
{"nome": "campanha de campo", "dispositivo": "tablet-3", "politica_conflito": "servidor_vence",
 "anexos": false,
 "extensao": {"type": "Polygon", "coordinates": [[[...]]]},
 "camadas": [{"camada_id": "<uuid>", "nome_gpkg": "pontos", "filtro": "grupo = 'norte'"}]}
```

Responde 202 com a réplica em `criando` e o `job_id` do trabalho que monta o pacote (tipo `replicas.criar`).
O `filtro` é escrito na mesma linguagem `where` do FeatureServer e vale só para os campos daquela camada;
filtro inválido reprova a criação com 422, não vira job que falha depois. A `extensao` é um Polygon em
EPSG:4326 e recorta todas as camadas. Sem `nome_gpkg` o nome da tabela no pacote é derivado do título do
item. Tetos: 20 camadas por réplica, 100 mil feições por camada, 20 réplicas vivas por usuário.

Quando o job termina, `GET /api/replicas/{id}` mostra `estado: "pronta"` e `GET /api/replicas/{id}/pacote`
baixa o arquivo (`application/geopackage+sqlite3`, com o sha256 no cabeçalho `x-plat-sha256`).

### O que vem dentro do pacote

Uma tabela por camada, mais quatro tabelas de serviço: `plat_sync` (camada, fid, globalid e versão de cada
feição — é o que o aparelho compara para saber o que ele mudou), `plat_replica` (geração do servidor,
filtro, política e validade por camada), `plat_dominio` (os valores de domínio dos campos, para montar lista
fechada) e, quando a réplica foi pedida com anexos, `plat_anexo` com o METADADO dos anexos. O conteúdo
binário do anexo não vai no pacote: é baixado por
`GET /api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}` quando houver rede.

### Sincronizar

```
POST /api/replicas/{id}/sincronizar
{"idempotencia": "<chave do lote, gerada pelo cliente>",
 "camadas": [{"camada_id": "<uuid>",
              "adicionar": [{"atributos": {...}, "geometria": {...}}],
              "atualizar": [{"id": "<globalid>", "versao": 3, "atributos": {...}}],
              "apagar":    [{"id": "<globalid>", "versao": 3}]}]}
```

A resposta traz `subidas` (quantas foram aplicadas), `conflitos` e `baixadas` (o que o servidor mudou desde
a geração que o aparelho tinha). Regras que valem saber:

- **A mesma chave de idempotência repete a resposta e aplica zero.** Se a rede caiu depois de o servidor
  aplicar e antes de o aparelho ler a resposta, repita o lote com a MESMA chave: a resposta volta igual, com
  `repetida: true`, e nada é duplicado. Chave nova = lote novo.
- **Conflito é sempre relatado, mesmo quando resolvido.** Cada entrada de `conflitos` diz a versão que o
  cliente leu, a que o servidor tem, a resolução (`servidor`, `cliente` ou `pendente`) e a feição atual do
  servidor. Com `servidor_vence` a edição do cliente é descartada; com `cliente_vence` ela é reaplicada
  sobre a versão atual do servidor (e o histórico guarda o que foi sobrescrito); com `pergunta` nada é
  aplicado e a decisão fica com quem opera.
- **O que o cliente acabou de subir não volta na descida.**
- **Feição que saiu do recorte desce como `apagar`.** Da janela desta réplica ela deixou de existir; não é
  uma exclusão no servidor.
- **A geração só avança quando algo é aplicado**, e avança de um em um.
- Sincronizar uma camada que não está no recorte declarado da réplica é 404 `camada_fora_da_replica`, mesmo
  que a camada exista e o usuário possa editá-la por outra porta.

### Validade

A réplica vale 30 dias; o rastreio de mudanças é retido por 45. Passada a validade, sincronizar devolve 409
`replica_expirada` e o caminho é criar réplica nova — uma sincronização com rastreio incompleto devolveria
menos mudanças do que o real sem avisar ninguém, e é isso que a validade menor evita.

### Privilégio

`campo.coletar` em todas as rotas (o perfil `campo` já o tem); sincronizar exige também `feicoes.editar` ou
`feicoes.editar_total`, porque escreve feição. Token de serviço: escopo `camada:ler` para ler, `camada:editar`
para sincronizar. Só o dono da réplica (ou quem tem `conteudo.editar_tudo`) mexe nela.

### QField

O GeoPackage gerado é o formato que o QField lê. A sincronização própria do QFieldCloud auto-hospedado fica
registrada como alternativa (decisão pendente do dono): as duas convivem, porque o pacote é o mesmo arquivo.
A abertura no aparelho ainda não foi testada por esta equipe — o que está provado por máquina é a forma que
o QField exige (driver GPKG, CRS declarado, tabelas de serviço registradas em `gpkg_contents`).
## 22. Relacionamentos entre camadas (item L2-10-b-relacionamentos)

### 22.1 Criar uma classe de relacionamento (`POST /api/relacionamentos`)

`origem_item_id`, `destino_item_id`, `cardinalidade` (`1:1`, `1:N` ou `N:M`), `chave_origem`/`chave_destino`
(um nome de campo da camada ou `globalid`, nunca o `fid` físico — é o que faz o relacionamento sobreviver a
apagar e recriar a linha com o mesmo `globalid`), `composto` (só vale em `1:1`/`1:N`: apagar a origem apaga
os destinos), `nome_direto`/`nome_inverso` (como cada lado enxerga a classe) e, opcionalmente,
`cardinalidade_min`/`cardinalidade_max`/`limite_relacionados`. `1:N`/`1:1` grava uma FK real na tabela de
destino (`ON DELETE CASCADE` quando composto, `SET NULL`/`RESTRICT` quando simples); `N:M` não tem FK física
— a integridade é por gatilho sobre uma tabela de junção. `DELETE /api/relacionamentos/{id}` desfaz a FK ou
o gatilho antes de apagar a classe.

### 22.2 Ligar e desligar pares N:M

`POST /api/relacionamentos/{id}/ligar` e `.../desligar {origem_valor, destino_valor}` — os valores são a
CHAVE declarada na classe (não o `fid`). Ligar um par com um valor que não existe em nenhum dos dois lados
devolve `404 relacionamento_valor_inexistente` nomeando o lado; estourar `cardinalidade_max` devolve `422`.

### 22.3 Consultar os relacionados (`GET /api/camadas/{id}/relacionados/{rel}?fids=...`)

`rel` é o nome direto (visto da origem) ou inverso (visto do destino) da classe. `fids` é uma lista de fids
separada por vírgula; a resposta agrupa por fid. `limite`/`deslocamento` paginam, mas o `limite_relacionados`
declarado na classe sempre vence um `limite` maior pedido pela consulta (teto duro por classe).
`GET /rest/services/{id}/FeatureServer/0/queryRelatedRecords?relationshipId=...&objectIds=...` devolve o
mesmo dado no formato Esri (paridade testada: mesmos fids nos dois formatos).

### 22.4 Popup de relacionados na tela (`/camadas/{id}/dominios`)

A tabela de feições (mesma tela do item L2-10-a) ganha uma coluna "Relacionados" quando a camada tem
alguma classe: o botão abre um popup (`GET /api/camadas/{id}/relacionamentos` traz as classes que a camada
enxerga, dos dois sentidos) listando os registros ligados a cada fid, com um link por registro para
`/camadas/{alvo}/dominios?fid=N`. A página de destino lê `?fid=` da URL e destaca a linha correspondente
(classe `.destaque`) se ela estiver na primeira leva carregada.

### 22.5 O que ficou de fora

Criar, ligar ou desligar um registro relacionado a partir do próprio popup (hoje é só leitura e navegação;
a API de ligar/desligar já existe, falta o botão na tela); relacionamento sobrevivendo a
importação/exportação de File Geodatabase (a ingestão vetorial desta versão não cobre FGDB); medição de
paginação com 100 mil relacionados numa única origem (o mecanismo — `limite_relacionados` vencendo um
`limite` maior — foi medido com N=25; ver ADR 20260907T1436).
## 22. Chamados de suporte (item L7-13-a-chamados)

### 22.1 Reportar um problema (qualquer tela)

O botão "Reportar problema" fica no fim da barra lateral de TODA tela com layout. O formulário já vem com
a captura da tela marcada (em telas com mapa, o quadro real do canvas no momento do envio; em telas sem
mapa, o chamado vai sem captura) e monta o contexto automático: tela atual, versão do produto, navegador,
idioma, os req_id das últimas 20 requisições feitas pela tela e a estrutura dos títulos e botões visíveis.
O contexto NUNCA leva valor de campo de formulário, para não anexar dado de inquilino ao chamado. Severidade
(baixa, média, alta, crítica) define o prazo declarado da primeira resposta: 4 h crítica, 8 h alta, 24 h
média, 72 h baixa.

### 22.2 Acompanhar (`/chamados`)

A lista mostra cada chamado com o tempo de primeira resposta MEDIDO ao lado do prazo declarado e a etiqueta
"dentro do prazo"/"fora do prazo". Quando o suporte responde, um banner no topo da barra lateral avisa
("o suporte respondeu o chamado nº N."); abrir o chamado zera o banner. No detalhe: conversa com o suporte
(comentar), anexo de arquivo (imagens, zip e os formatos de dado aceitos no upload; executável é recusado),
contexto automático em texto e botão "Fechar chamado" (idempotente; chamado fechado não recebe comentário).

### 22.3 Painel do operador (`/admin/chamados`, só superadmin)

Fila de chamados de todos os inquilinos com filtro por estado, leitura do contexto completo (inclui o
inquilino), download dos anexos pela própria rota da API, resposta (registra o tempo de primeira resposta e
enfileira o e-mail ao cliente no idioma da conta dele) e mudança de estado: aberto → em análise /
aguardando cliente / resolvido; resolvido → fechado (encerra) ou de volta para em análise (reabre). Quem
não é superadmin recebe 404 nas rotas do painel e vê "sem permissão" na tela.

### 22.4 Notificação por e-mail

O e-mail de resposta/resolução sai pelo SMTP da instalação (job da fila, worker real) só no sentido
suporte → cliente, no idioma preferido da conta do cliente; o assunto nunca leva texto do cliente, só o
número do chamado. A volta do cliente é pelo próprio produto (comentário no chamado) — o banner cobre
quem não tem e-mail na conta.
Exportação de VISTA de camada (o tipo `vista_de_camada` existe no catálogo, mas o item `L0-04-j` que o
implementa ainda não foi entregue — quando for, o filtro da vista entra como mais um `where` neste mesmo
motor) e exportação de camada REFERENCIADA (recusada com 422 `camada_nao_hospedada`, nunca silenciosa).
## 22. Camada de WFS e de OGC API - Features (item L6-02-c-wfs-ogcapi)

Uma conexão do tipo `wfs` (WFS 2.0) ou `ogc_api` (OGC API - Features), já registrada como na seção 18, passa a
servir camadas de dois jeitos.

### 22.1 Ver o que o serviço publica

```
GET /api/conexoes/{id}/colecoes
GET /api/conexoes/{id}/colecoes/{colecao}/campos
```

A primeira lista as coleções (`wfs:FeatureTypeList` do GetCapabilities, ou `GET /collections`), com o CRS que o
serviço DECLARA (`crs_nativo` verbatim e `srid_nativo` em número quando dá para extrair) e a extensão em
WGS 84. A segunda lista os atributos e o tipo declarado de cada um: `DescribeFeatureType` no WFS,
`/queryables` no OGC API. Quando o serviço não declara nada — `/queryables` é opcional no padrão — o tipo vem
de uma amostra de uma feição e `origem_do_tipo` responde `amostra`. Inferido nunca aparece como declarado.

### 22.2 Modo referenciado (ao vivo)

```
GET /api/conexoes/{id}/colecoes/{colecao}/feicoes?limite=500&bbox=-47.9,-15.8,-47.8,-15.7&datahora=2026-01-01/2026-06-30
```

Devolve GeoJSON com `numberReturned` (o que veio agora) ao lado de `numberMatched` (o total que o serviço
declara). Sem os dois não dá para saber se a resposta é a coleção inteira ou um pedaço. `bbox` é
`minx,miny,maxx,maxy` em graus; `datahora` é o `datetime` do OGC API (instante ou intervalo). O teto por
chamada é `CONEXAO_VETOR_PREVIA_MAX` (mil feições).

A resposta fica em cache por 30 segundos dentro do processo de API, e `do_cache` diz se veio de lá. Duas
consequências, escritas aqui porque ninguém deve descobri-las sozinho: dois processos de API podem devolver
respostas de instantes diferentes dentro dessa janela; e editar a URL da conexão (ou apagá-la) esquece na hora
o que ela tinha cacheado, para que a resposta da URL antiga nunca seja servida depois da mudança.

Um WFS que não anuncia nenhum `outputFormat` JSON responde 422 `formato_json_indisponivel` neste modo. Ele é
atendido no modo copiado, que converte o GML localmente.

### 22.3 Modo copiado (traz para o PostGIS)

Não há rota própria: é a tarefa `conexao.copiar_vetor`, criada como qualquer outra tarefa pesada.

```
POST /api/jobs
{"tipo": "conexao.copiar_vetor",
 "parametros": {"conexao_id": "<uuid>", "colecao": "ns:pontos",
                "limite_feicoes": 100000, "tam_pagina": 1000,
                "bbox": [-48.0, -16.0, -47.0, -15.0], "datahora": "2026-01-01/2026-06-30"}}
```

Ao terminar existe uma tabela em `d_<slug>` e um item `camada_vetorial` no catálogo, com as mesmas colunas
obrigatórias, RLS e índices da camada que veio de arquivo. O resultado do job traz `feicoes` (o que foi
copiado), `declaradas_pelo_servico` (o `numberMatched`), `paginas`, `segundos_download`, `segundos_carga`,
`srid_nativo`, `srid_entregue`, `srid_gravado` (sempre 4326) e `avisos`.

Três coisas a saber antes de usar:

1. **O limite é seu.** `limite_feicoes` (padrão 100 mil, teto 2 milhões) é onde a cópia para, mesmo que o
   serviço declare mais. Quando ela para por limite, `limite_atingido` fica verdadeiro e o aviso vai para
   `dados.procedencia.limites` do item — a camada é um pedaço, e a ficha diz isso.
2. **Serviço que ignora a paginação não trava o worker.** Se o serviço devolve mais feições do que as pedidas,
   ou repete a mesma página, a cópia encerra na página seguinte com o aviso nomeado.
3. **O tipo da coluna é o que o serviço declarou.** Um `xsd:int` vira `integer`, um `xsd:date` vira `date`.
   Quando o dado não converte para o tipo declarado, a coluna fica como o GDAL a deixou e o aviso entra na
   procedência: nenhuma linha é descartada para fazer o tipo bater.

### 22.4 O que ainda não existe aqui

WFS 1.0/1.1 (só 2.0.0), filtro CQL2 ou `Filter` OGC (item L6-02-n), agendamento da reexecução da cópia (item
L6-02-k), desenho da camada referenciada no mapa (item L6-02-b), escrita de volta (WFS-T) e negociação de CRS
da Parte 2 do OGC API — `/items` é sempre lido em CRS84.

### 22.6 CDN (item L7-26-cdn-tiles): o endereço que fica para sempre

O `tilejson.json` já entrega um endereço com a **versão embutida** — `/svc/<tok>/raster/<item>@<sha
curto>/{z}/{x}/{y}.png` — que responde `Cache-Control: public, max-age=31536000, immutable`. Isso
significa: uma CDN na frente desse endereço (hostname `tiles-<x>`, separado do domínio da aplicação)
pode guardar o ladrilho **para sempre**, porque o conteúdo daquele endereço específico nunca muda —
se a imagem for reingerida, o sha256 muda e o endereço muda junto. O endereço SEM versão (o de sempre,
22.1) continua com cache curto (5 min), porque sem o sha256 no caminho o conteúdo por trás dele pode
mudar sem avisar. Detalhe completo, achados de bancada e o que falta configurar na conta Cloudflare
real: `docs/CDN.md`.
## 23. SDK JavaScript e exemplos no navegador (item L7-08-c-sdk-js)

O SDK JavaScript é um único módulo ES servido pela instalação em `/static/sdk/plat.js` (publicado também em
`sdk/js/plat.js`), sem dependência e sem CDN. Uso mínimo numa página da própria instalação:

```html
<script type="module">
  import { Plataforma } from '/static/sdk/plat.js';
  const p = new Plataforma(location.origin, 'plat_...');        // token de serviço (Minha conta -> Tokens)
  const pagina = await p.itens.listar({ tipo: 'camada_vetorial', limite: 20 });
  const mapa = new maplibregl.Map({ container: 'mapa', transformRequest: p.maplibre.transformRequest,
                                    style: p.maplibre.estilo(null, { basemapUrl: '/static/dados/basemap/guarulhos.pmtiles' }) });
  mapa.on('load', async () => {
    const item = await p.itens.obter(pagina.itens[0].id);
    mapa.addSource('item', p.maplibre.fonte(item));          // extensão do item, PMTiles ou catálogo
    mapa.addLayer(p.maplibre.camada(item, { id: 'item' }));
    p.maplibre.enquadrar(mapa, item);
  });
</script>
```

Regras que o SDK aplica sozinho: Bearer nunca junto com o cookie de sessão (a API recusa os dois com 400
`autenticacao_ambigua`); retentativa só em 429/502/503/504 e erro de rede; erro sempre como `ErroPlataforma`
(`status`, `tipo`, `titulo`, `detalhe`, `instancia` = `req_id`); `.tokens` só com sessão (a da página ou a de
`Plataforma.entrar()`). Os 10 exemplos ficam em `/static/sdk/exemplos/01_login.html` … `10_catalogo_no_mapa.html`,
cada um com formulário (inquilino, login, senha) e CSP estrita na própria página; a tabela está em
`sdk/js/README.md`. O que não existe: feições por camada e tiles dinâmicos (L2-04) e CORS (a API é same-origin;
de outra origem use Node ou o SDK Python).
## 23. Geocodificar uma planilha de endereços (item L2-11-a-geocodificacao-csv)

Uma planilha de endereços (CSV, TXT ou XLSX) vira camada de pontos do inquilino em quatro passos: enviar o
arquivo, confirmar de qual coluna sai cada campo do endereço, esperar o job e revisar o que ficou pendente.
O motor é o do capítulo 20 — mesmo CNEFE 2022, mesma hierarquia de recuo, mesmo tipo de acerto.

### 23.1 Passo a passo

1. **Enviar o arquivo** — `/uploads` (capítulo do upload retomável) ou `POST /api/arquivos`, e registrar o
   item `arquivo` com `POST /api/itens`.
2. **Ver as colunas** — `POST /api/geocodificacoes/colunas` com `{"arquivo_id": "..."}`. Devolve os nomes de
   coluna do arquivo e um `mapeamento_proposto` por nome de cabeçalho (Logradouro, Nº, Cidade, UF, CEP,
   "endereço completo"...). A proposta é palpite; quem decide é quem confirma.
3. **Criar o lote** — `POST /api/geocodificacoes` com `{"arquivo_id", "titulo", "mapeamento"}`. O mapeamento
   é `{campo: nome da coluna}` e os campos aceitos são `endereco`, `logradouro`, `numero`, `bairro`,
   `municipio`, `uf`, `cep`. Mapear só `numero` e `uf` é recusado com 422: nenhum dos dois localiza nada.
   Responde 202 com `geocodificacao_id` e `job_id`.
4. **Acompanhar** — `GET /api/geocodificacoes/{id}` traz estado, contagens (`resolvidas`, `pendentes`,
   `malformadas`, `manuais`), o `resumo` com a contagem por tipo de acerto e o tempo medido, e a ficha da
   base de endereços usada. `GET /api/geocodificacoes/{id}/linhas?estado=pendente` lista as linhas.
5. **Revisar** — tela `/geocodificacoes/{id}`: lista à esquerda, mapa à direita. Clicar numa linha põe um
   marcador arrastável; soltar o marcador grava a coordenada com `origem: manual`
   (`PUT /api/geocodificacoes/{id}/linhas/{n}`). O botão "refazer só as pendentes" chama
   `POST /api/geocodificacoes/{id}/regeocodificar`, que reprocessa apenas o que não está resolvido e nunca
   toca no que foi arrastado à mão.

### 23.2 O que a camada publicada carrega

Além dos campos do endereço lidos do arquivo, cada ponto tem `geo_score` (0-100), `geo_tipo_acerto` (o mesmo
vocabulário do capítulo 20), `geo_origem` (`automatica` ou `manual`), `geo_municipio_cod` e `geo_avisos`.
A `dados.procedencia` do item traz o sha256 do arquivo de origem, o método, o comando de reexecução e, em
`base_enderecos`, a versão da base: quais UFs do CNEFE estão instaladas, quantos endereços cada uma tem, o
sha256 do zip do IBGE e a data da instalação.

Ponto com `geo_tipo_acerto = aproximado_no_municipio` está no CENTRO DO MUNICÍPIO, não no endereço. Ele é
publicado assim de propósito, marcado e com aviso, e a tela mostra um alerta com a contagem — o que não pode
existir é um ponto no centróide sem esse rótulo.

### 23.3 Três estados de linha

- **resolvida** — o motor achou um lugar; tem coordenada, pontuação e tipo de acerto.
- **pendente** — problema de COBERTURA: a UF não está instalada, o logradouro não casou, ou o CEP contradiz o
  município informado. Melhora instalando UF e mandando refazer.
- **malformada** — problema do ARQUIVO: a linha tem menos colunas do que o cabeçalho, está em branco, ou não
  sobrou nenhum campo de endereço. Não melhora com base melhor; a planilha é que precisa de conserto. O
  motivo vem escrito em português na própria linha.

Linha ruim não derruba o lote: o job conclui e publica a camada com o que deu certo.

### 23.4 Limites desta fatia

- **Só as UFs instaladas existem.** Nesta máquina, Roraima. Endereço de outra UF vira linha pendente.
- **Tetos**: 32 MiB de arquivo e 200 mil linhas de dado (`docs/LIMITES.md`). Acima disso a criação do lote
  responde 413 (tamanho) ou o job para com o motivo (linhas), mantendo o que já gravou.
- **A entrada é um arquivo, não uma tabela já importada.** Geocodificar uma tabela que já está no catálogo
  depende do item `L0-04-d`; a rota é a mesma quando ele fechar.
- **O mapa-base local cobre Guarulhos-SP** (item L2-01-a). Fora dali a tela desenha os pontos sobre o fundo,
  sem imagem de referência, e escreve isso na barra de instrução. O arrasto grava a coordenada certa
  igualmente.
- **Sem geocodificação reversa em lote** (coluna de coordenada -> endereço): o motor tem `POST /api/reverso`,
  o lote não o usa.
- **CSV latin-1 muito curto** pode ser lido com acento errado (a codificação é adivinhada). O endereço ainda
  casa, porque a comparação no banco dobra acento com `unaccent`.
## 22. Vídeos por tarefa (item L7-04-d-videos-por-tarefa)

O comando `make videos` grava a sessão real de cada tarefa com o mesmo navegador dos testes e2e
(playwright, 1280×800), monta o vídeo com o ffmpeg e publica em `/videos` (página com sessão de
usuário, `noindex`). Cada vídeo tem até 3 minutos, narração sintética em português (voz livre piper,
sem voz clonada, sem rosto) e legenda em português, inglês e espanhol (WebVTT). A legenda de um passo
só é escrita depois de a ação do passo acontecer de verdade: passo que não existe na versão instalada
derruba a geração. Os arquivos ficam em `web/videos/` (fora do git, regenerados quando a versão menor
muda); o registro citável fica em `tests/medidas/L7-04-d-videos-por-tarefa.json`.

| arquivo em /videos | tarefa | seção do manual |
|---|---|---|
| saude.mp4 | saúde do serviço | 1 |
| entrar.mp4 | entrar | 2 |
| conta.mp4 | minha conta | 3 |
| usuarios.mp4 | usuários | 4 |
| grupos.mp4 | grupos | 5 |
| papeis.mp4 | papéis e privilégios | 6 |
| tokens.mp4 | tokens de serviço | 7 |
| log.mp4 | log de acesso | 8 |
| tarefas.mp4 | tarefas | 9 |
| mapa.mp4 | mapa | 13 |
| conexoes.mp4 | conexões externas | 18 |

O gerador (`scripts/videos/gerar.py --validar`) confere que a seção declarada por cada tarefa existe
em MANUAL.md antes de gerar e que cada mp4 tem fluxo de vídeo e de áudio dentro do limite de duração.
O que o vídeo não mostra: nada de dado de inquilino além do de demonstração, e nenhum passo que não
esteja nesta versão do produto.
## 22. Métricas Prometheus e exporters de infraestrutura (item L7-06-a-metricas-exporters)

`GET /metrics` na API (`:8150`) e no worker (`:8153`) — não exige sessão nem token, as duas portas só
escutam em `127.0.0.1`. Ver `docs/OBSERVABILIDADE.md` para a lista completa de famílias, rótulos e o
contrato de cardinalidade (rótulo por inquilino é sempre `tenant`/`tenant_id` numérico, nunca o slug do
schema `d_<slug>` nem token). Resumo:

- `plat_http_requests_total`/`plat_http_request_duracao_segundos` — toda requisição da API, rotulada
  pelo PADRÃO da rota (nunca o id do recurso).
- `plat_jobs_processados_total` (worker), `plat_jobs_fila`/`plat_jobs_workers_vivos` (API, agregado
  entre inquilinos) — a mesma fonte que já alimentava `/saude`.
- `plat_tiles_requisicoes_total` — família pronta, ainda sem chamador em `master` (a autorização de COG
  do item L1-01-d não estava mesclada na data desta entrega; docs/OBSERVABILIDADE.md §5).
- Martin (nativo, `:8151/_/metrics`), node-exporter (`:9100`, já existia), Garage (`:3903/metrics`, já
  existia), `postgres_exporter` (`:9187`, role dedicada `plat_metrica_pg`) e `nginx_exporter`
  (`:9113`, `stub_status` interno em `:8096`) — todos acrescentados ao Prometheus da casa
  (`/opt/monitoring/`, fora deste repositório) por *scrape job* novo, nunca substituindo o que já
  existia.
- `X-Req-Id` chega ao Martin: `location /tiles/` nova (`deploy/nginx.conf`) gera/repassa `$request_id` e
  grava a mesma string no log dedicado `/var/log/nginx/plat_tiles_access.log`. TiTiler não existe hoje
  no `plat` (porta 8152 reservada, sem serviço) — cláusula parcial, mecanismo pronto para quando nascer.

### 22.1 O que ficou de fora

`plat_tiles_requisicoes_total` sem tráfego real (§ acima); painéis Grafana, alertas e a tela
`plat logs --req-id` são os itens seguintes da mesma linha (`L7-06-b/c/d`), fora do portão literal
deste. `Garage :3903/metrics` continua sem exigir `metrics_token` — decisão do dono pendente (a porta
já não é alcançável de fora de `127.0.0.1`, então o risco imediato é baixo).
- não há WMS 1.3.0 (L1-02-g), nem OGC API Tiles/Maps (L1-02-i), nem ponto/estatística por local
  específico, nem predefinição de renderização gravada por conta própria do serviço (L1-02-f): a
  pintura ainda vive nos parâmetros da URL. Estatística/histograma **por banda ou por expressão** da
  cena inteira agora existe (`estatisticas.json`, item L2-02-f — ver seção 23), decimada pelo rio-tiler;
- a única grade é a WebMercatorQuad (a do Google/OSM/AGOL).

## 23. Editor de estilo raster (item L2-02-f-estilo-raster)

O tipo `raster` do construtor de estilo (seção 22) ganha o vocabulário para editar imagem de verdade,
sempre sobre o serviço de ladrilho da seção 22: `plat_construtor.parametros_raster` guarda `bandas`
(composição de 1 a 4 índices — 3 para RGB, 1 para banda única com rampa), `rescale` (faixa aplicada,
`min` estritamente menor que `max`), `colormap_name` (rampa nomeada, mesmas 211 disponíveis em
`info.json`; inverter é usar o nome com sufixo `_r`), `expression` (NDVI, NDWI ou qualquer conta livre
sobre as bandas, na MESMA gramática restrita que o serviço de ladrilho aceita), `esticamento.metodo`
(`minmax`, `percentil_2_98`, `desvio_padrao` ou `nenhum` — documenta como o `rescale` foi calculado, para
reabrir a mesma escolha) e `resampling`/`nodata` (aceitos no documento; o serviço de ladrilho ainda não
lê nenhum dos dois da URL, então ficam registrados para quando existir o parâmetro — nunca fingidos como
aplicados).

### 23.1 De onde vêm os números do esticamento

`GET /svc/<token>/raster/<item>/estatisticas.json` (bandas ou expressão, os mesmos nomes da seção 22.2)
devolve mínimo, máximo, média, desvio-padrão e percentis 2 e 98 por decimação — nunca lendo a cena
inteira. O editor chama esta rota, escolhe `rescale` pelo método pedido e grava o número; a legenda
contínua nunca recalcula por conta própria, só repete o que essa rota mediu. Round-trip: salvar e reabrir
o mesmo estilo devolve `parametros_raster` byte a byte igual.

### 23.2 O que a URL de ladrilho aceita

`plat_construtor` compila para os quatro parâmetros que o serviço de ladrilho de fato lê (`bandas`,
`faixa`, `colormap`, `expressao`) e nada além disso — nenhum outro campo do construtor (esticamento,
`nodata`, `resampling`) vaza para a URL. `expression` passa pela mesma validação de gramática do serviço
de ladrilho antes de ser aceita no documento, então o editor nunca grava algo que o ladrilho recusaria;
divisão por zero literal (ex. `b4/0`) é recusada na hora de salvar, não só na hora de desenhar.

### 23.3 O que ficou de fora

Classes discretas custom na rampa (o serviço só aceita rampa nomeada, não uma tabela de cor arbitrária) e
funções raster encadeadas do Image Server (stretch → convolução → colormap em sequência, com histórico de
passos) — o serviço aplica um esticamento e uma rampa por vez. Paridade contra "Style Imagery" do Map
Viewer, cláusula por cláusula, em `docs/PARIDADE.md`.

## 27. Acervo de arquivo da casa no catálogo (item L6-01-i-raster-e-arquivos)

Além das fontes (seção do acervo) e das tabelas com geometria, o acervo da casa tem ARQUIVOS registrados com
sha256. Eles aparecem em:

```
GET  /api/acervo/arquivos?tipo=raster|vetor&fonte_id=&q=&so_no_disco=&limite=&deslocamento=
POST /api/acervo/arquivos/expor    {"caminhos": ["backtest/3876/dem.tif", ...], "titulo": "opcional"}
```

A lista traz caminho, tipo, extensão, bytes, sha256, feições, SRID, a ficha da fonte (nome, órgão, domínio,
licença), `publicavel` (há licença escrita?), `exposto` (já está no catálogo deste inquilino?) e `no_disco` (o
arquivo do registro existe nesta instalação). A exposição enfileira um job por caminho; o job **confere o
sha256 do arquivo antes de escrever qualquer coisa** e recusa com `hash_divergente` se o arquivo mudou.

- **raster** (`.tif`, `.tiff`, `.vrt`): vira item `raster` com item STAC apontando para o arquivo onde ele está
  (`acervo://<caminho>`), sem cópia; serve ladrilho por token como qualquer raster (seção do ladrilho).
- **vetor** (`.geojson`, `.gpkg`, `.shp`, `.parquet`, ...): é ingerido uma vez para PostGIS e vira
  `camada_vetorial` hospedada.

Recusas nomeadas: `caminho_inexistente`, `arquivo_ausente`, `arquivo_grande_demais` (acima de 2 GB),
`lote_grande_demais` (soma acima de 3 GB), `ja_exposto`, `hash_divergente`, `acervo_sem_raiz`. A raiz dos
arquivos é `PLAT_ACERVO_ARQUIVOS_RAIZ` no `.env`; sem ela a lista vem vazia e a exposição responde 409.
Item de fonte **sem licença escrita** nasce privado e marcado `uso_restrito` no campo `dados`.
## 25. Edição concorrente no construtor (item L5-13-edicao-concorrente)

Várias pessoas podem ter o mesmo documento (`app`, `painel`) aberto. O construtor mostra, no alto, quem mais
está no documento e em que nó; um nó que outra aba está editando aparece com contorno tracejado e, ao selecioná-lo,
um aviso diz quem está lá. Nada trava: o aviso só evita que duas pessoas mexam no mesmo nó sem saber.

Ao gravar, a tela manda `base_versao` (a versão que ela leu). Se alguém gravou antes:
- nós DIFERENTES: o servidor mescla por nó e grava; a tela absorve o resultado e o estado diz
  "gravado (versão N; mesclado com a versão M de outra sessão)";
- o MESMO nó: HTTP 409 com o documento atual; o painel mostra a diferença com o nó em conflito marcado e oferece
  "gravar a minha nos nós em conflito (e mesclar o resto)" ou "descartar a minha e recarregar".

Pela API:

```
PATCH /api/itens/{id}   {"dados": {...}, "base_versao": 7}
  200 -> item (com "mesclagem": {"do_cliente": [...], "do_servidor": [...], "versao_servidor": 8}) quando mesclou
  409 -> {"erro": "versao_conflito", "detalhe": {"versao_atual": 8, "base_versao": 7, "conflitos": ["<id do nó>"],
          "do_cliente": [...], "do_servidor": [...], "dados": {...documento atual...}}}
POST /api/itens/{id}/presenca            {"sessao": "<id da aba>", "no": "<id do nó ou null>", "sair": false}
GET  /api/itens/{id}/presenca            -> {"itens": [{"login", "nome", "sessao", "no", "em", "usuario_id"}], "expira_s": 12}
GET  /api/itens/{id}/presenca/eventos    -> SSE, evento `presenca` com a lista a cada mudança
```

`versao_atual` (regra estrita: qualquer diferença = 409) continua aceito. Item sem grafo com `base_versao`
diferente recebe o 409 com o documento atual, sem mesclagem. A presença expira em 12 s sem batimento (a tela bate a
cada 5 s) e some ao fechar a aba.
---

## 22. Portal da API (`/portal`, item L7-08-d-portal-api-chaves)

Página pública da instalação (sem sessão) que mostra a API inteira: o que existe, com que escopo de chave,
e um botão para executar a requisição na hora. Serve para quem vai programar contra a plataforma. A
referência crua do esquema continua em `/api/docs` (Swagger UI); o portal é a leitura de trabalho.

Nada vem de fora: folha, módulo e fonte saem de `/static/`, e a resposta de `/portal` traz uma Política de
Segurança de Conteúdo (`Content-Security-Policy`) com `default-src 'none'` mais `script-src 'self'`,
`style-src 'self'`, `font-src 'self'`, `connect-src 'self'` e `frame-ancestors 'none'`. Medido no e2e com
o navegador interceptando toda requisição: **0 recurso externo** (`recursos_externos_carregados_pelo_portal`).

### 22.1 Como usar

À esquerda: o campo **chave de API**, o filtro de rota e o índice. O índice vem de `/api/openapi.json` e
mostra, por rota, o verbo, o caminho e o escopo que a chave precisa ter. A chave colada fica na memória da
aba e não é gravada em lugar nenhum — recarregar a página a apaga.

Ao clicar numa rota abre a ficha: escopo exigido, credencial aceita, privilégio que o dono da chave
precisa ter, parâmetros, o bloco **Experimentar** e o `curl` equivalente. `Experimentar` faz a requisição
de verdade contra esta instalação e mostra o código HTTP, o tipo de conteúdo, o tempo e o corpo.

Rota marcada `publico` responde sem chave. Rota marcada `sessao` só aceita cookie de navegador e devolve
`403 so_sessao` a qualquer chave. Rota marcada `superadmin` responde `404` a quem não é operador da
plataforma (não confirma que a rota existe).

### 22.2 Escopo de cada rota no esquema

Toda operação de `/api/openapi.json` traz `x-plat-escopo`. O valor é derivado da dependência de
autenticação da própria rota, não escrito à mão (ADR 0018, decisão 2), então não tem como divergir do que
o servidor confere. Vocabulário: `publico`, `sessao`, `superadmin`, `token:qualquer` ou um escopo de
chave. Medido: **197 rotas no esquema, 197 com `x-plat-escopo`, 0 sem**.

Varredura de regressão (`tests/api/test_portal_chaves.py`): uma chave de perfil `leitura` é usada em toda
rota que exige outro escopo — **0 resposta 200 indevida**. A mesma varredura sem credencial nenhuma
também não devolve 200 em rota não-pública.

### 22.3 Perfis de chave

Na criação da chave (`/admin/tokens` ou `POST /api/tokens`), quatro conjuntos nomeados poupam escolher
escopo a escopo. São apelidos, não escopos novos:

| perfil | escopos | para quê |
|---|---|---|
| `leitura` | `catalogo:ler` `camada:ler` `tiles:ler` | ler catálogo, feições e tiles; nenhuma escrita |
| `edicao` | os de leitura mais `camada:editar` `jobs:executar` | editar feições e executar jobs |
| `tiles` | `tiles:ler` | chave de aplicação de mapa |
| `admin` | `admin:inquilino` | tudo pela API, exceto gerir chave, senha, 2FA e sessão |

### 22.4 Prazo, contagem e revogação da chave

Toda chave tem prazo: padrão 90 dias, máximo 365 (`400 validade_acima_do_maximo` acima disso). Desde a
migração `20260906T1617_chaves_api.sql` isso é garantido pelo **banco**, não só pela rota: `expira_em` é
`NOT NULL` com `CHECK (expira_em <= criado_em + 366 dias)`, e `plat.auth_token` já não tem o ramo que
aceitava prazo nulo. Chave eterna é impossível por qualquer caminho, inclusive por SQL direto.

`GET /api/tokens` e `GET /api/tokens/{id}` trazem `usos` (quantas requisições a chave já autenticou) além
de `ultimo_uso` e `ultimo_ip`. O contador é incrementado na mesma atualização que grava o último uso.

Revogar (`DELETE /api/tokens/{id}`) vale na requisição seguinte. Medido de ponta a ponta pelo botão
`Experimentar` do portal: **abaixo de 5 s** (`segundos_revogar_ate_negar_no_portal`). A resposta é
`401 token_revogado`, não 403 — credencial que deixou de existir é problema de autenticação (ADR 0018,
seção "divergência assumida").

### 22.5 Formato de erro (RFC 9457)

Toda resposta de erro é `application/problem+json` com `type` (`urn:plat:erro:<codigo>`), `title`,
`status`, `detail` e `instance`, mais os campos da casa `erro`, `mensagem`, `detalhe` e `req_id` como
extensão. Chave expirada devolve `401` com `erro: token_expirado`; chave de leitura em rota de escrita
devolve `403` com `erro: escopo_insuficiente`, `detalhe.exigido` e `detalhe.token_tem`.

### 22.6 Exemplos executáveis

O portal lista 20 programas — 10 em Python (biblioteca padrão) e 10 em JavaScript (Node 18 ou mais novo,
`fetch` nativo) — lidos de `exemplos/python/` e `exemplos/js/`. Não são texto de documentação: a suíte os
executa contra a API viva (`tests/e2e/test_portal.py::test_os_vinte_exemplos_rodam_de_verdade`), então
exemplo que apodrecer reprova o e2e. Duas variáveis: `PLAT_URL` e `PLAT_CHAVE`.

    PLAT_URL=https://exemplo PLAT_CHAVE=plat_... python3 exemplos/python/03_catalogo_listar.py
    PLAT_URL=https://exemplo PLAT_CHAVE=plat_... node exemplos/js/03_catalogo_listar.mjs

Os de número 09 e 10 são exemplos de recusa: o 09 prova que uma chave de leitura não escreve, o 10 prova
o formato de erro. Terminam com código 0 quando a recusa acontece.

### 22.7 O que este item NÃO resolveu

Duas rotas declaram `x-auth: S/T` no esquema e respondem 200 sem credencial nenhuma:
`GET /api/uploads/tipos` e `GET /api/importacoes/formatos`. As duas devolvem só vocabulário estático (tipos
de arquivo aceitos), sem nenhum dado de inquilino, então não há vazamento — mas a etiqueta `x-auth` delas
está errada, e o `x-plat-escopo` derivado diz a verdade (`publico`). O conserto é dos itens donos desses
arquivos (L0-04-a e L0-04), não deste.
## 22. Achar tudo o que aconteceu num pedido (item L7-06-c-logs-consulta-req-id)

Toda resposta da plataforma volta com o cabeçalho `X-Req-Id`. Esse identificador nasce no nginx e é o
mesmo em todos os serviços, o que permite ver, de uma vez, o que cada um escreveu sobre o mesmo pedido:

    scripts/plat logs --req-id 3cf202aaffb6dd447ab01b42dfab0596
    scripts/plat logs --req-id 3cf202aaffb6dd447ab01b42dfab0596 --desde=-2h --json

A saída traz uma linha por serviço, em ordem de relógio: `nginx` (linha de acesso em JSON, com o estado
e quem atendeu), `api` (linha JSON da aplicação), `worker` (linha do job que aquele pedido enfileirou) e
`postgres` (a linha do banco, achada pelo `application_name`, que a aplicação preenche com `plat:` mais
doze caracteres do identificador). Quem serve tile é o Martin, que não registra identificador de pedido
próprio: para ele, a linha que vale é a do nginx, onde aparece o endereço do servidor de tiles.

Numa falha em que a aplicação nem chega a responder (o serviço de trás está fora, por exemplo), o cliente
não recebe `X-Req-Id`. O identificador do pedido está na linha do nginx, e é por ela que se começa.

Na tela **Log de acesso** (`/admin/log`) há a coluna `req_id` e um filtro com o mesmo nome: cola-se ali o
identificador que o usuário informou. O administrador do inquilino só vê as linhas do próprio inquilino,
mesmo digitando o identificador de um pedido de outro — a consulta filtra pelo inquilino antes de tudo.

### Aumentar o detalhe do log sem reiniciar nada

    scripts/plat log nivel DEBUG --por 10min                       # tudo, por dez minutos
    scripts/plat log nivel DEBUG --componente app.db --por 30s     # só um componente
    scripts/plat log nivel WARNING --componente rota:/api/tiles    # por prefixo de rota, sem prazo
    scripts/plat log nivel --listar
    scripts/plat log nivel --remover app.db

Os níveis são `DEBUG`, `INFO`, `WARNING` e `ERROR`. O ajuste vale para o processo inteiro da API e do
worker (não para um inquilino), passa a valer em segundos e some sozinho quando o prazo acaba. Pela API,
as mesmas três operações são `GET`, `POST` e `DELETE` em `/api/log/nivel`, só para o superadmin da
plataforma. Sempre ponha prazo: nível `DEBUG` esquecido enche o disco.

### Por quanto tempo o log fica guardado

O alvo é 90 dias, escrito em `/etc/systemd/journald.conf.d/plat.conf` pelo instalador. Duas ressalvas
medidas nesta instalação, em setembro de 2026: o journal é compartilhado com o resto da máquina e
guardava 2,9 dias em 2,34 GB; e o systemd não tem teto por serviço, só por máquina. As unidades da
plataforma escrevem 0,83 MB por dia somadas, ou seja 90 dias delas caberiam em cerca de 75 MB — o que não
cabe é o log dos outros serviços do servidor. Guardar 90 dias de verdade exige dar às unidades `plat-*`
um journal próprio (`LogNamespace=plat`) ou mandar o log para fora.
## 22. Sistema de referência — CRS (item L2-17-crs-transformacoes)

Serviço transversal de CRS: registro (lista curada + banco EPSG do PROJ), transformação de ponto/bbox e
definição proj4 — sem tabela `plat.*` própria (mesmo padrão da rota/matriz/isócrona, seção 14).

### 22.1 API

- `GET /api/crs` — lista curada brasileira PRIMEIRO (SIRGAS2000 geográfico, WGS84, Web Mercator,
  Policônica 5880, as 21 zonas UTM SIRGAS2000 31965-31985, SAD69 e Córrego Alegre 1961/1970-72 legados),
  depois o resto do registro EPSG (Geographic 2D/Projected, sem deprecados). Ordem é a que os seletores
  do navegador respeitam sem reordenar.
- `GET /api/crs/{epsg}` — nome, tipo, área de uso, se é curada e por quê.
- `GET /api/crs/{epsg}.proj4` — texto proj4 puro (`text/plain`), a MESMA definição que o navegador usa
  via proj4js (`web/js/crs/crs.js`) — nunca uma segunda cópia digitada à mão.
- `POST /api/crs/transformar` — `{origem, destino, tipo: "ponto"|"bbox", coordenadas}`. Resposta sempre
  declara `transformacao_usada` e `cobertura` (`direta` | `dentro_da_grade` |
  `fora_da_grade_usou_parametros`). Todas exigem sessão ou token com o escopo `crs:usar`.

### 22.2 Datum legado (SAD69, Córrego Alegre) — grade oficial do IBGE, sem CDN

`grades_ibge/*.GSB` (NTv2, ProGriD do IBGE, dado aberto) vendorizadas no repositório, sha256 conferido por
`grades_ibge/instalar.sh` (chamado pelo `install.sh` seção h5). Lidas por CAMINHO ABSOLUTO num pipeline
PROJ sem CRS nas pontas (`app/crs/grades.py::Grade.pipeline`), funcionando idêntico em `pyproj` e em
`ST_Transform` (mesma libproj) — sem depender de `cdn.proj.org` (PostGIS deste ambiente já roda com
`NETWORK_ENABLED=OFF`) nem de `PROJ_DATA` compartilhado fora do repositório. A grade certa é escolhida
por área (`bounds` de cada uma, lidos do registro EPSG); fora de qualquer cobertura, cai nos parâmetros
geocêntricos do R.PR IBGE 01/2005 (sem grade, 5,0 m) e DECLARA isso na resposta — nunca falha nem
esconde. Prova contra o serviço oficial ao vivo do IBGE e proveniência completa em
`grades_ibge/PROVENIENCIA.md` e ADR `docs/adr/20260907T1630-crs-transversal.md`.

### 22.3 Tela `/crs`

Dois seletores (origem/destino) com a curada marcada ★ primeiro, formulário de ponto ou bbox, resultado
com a transformação usada e a cobertura, e uma prévia em Web Mercator calculada NO NAVEGADOR por proj4js
(`web/vendor/proj4-2.15.0.js`) a partir das definições de `/api/crs/{epsg}.proj4` — nunca uma reprojeção
de datum legado no navegador (isso fica no backend, que tem a grade).

### 22.4 Limites desta fatia

`transformar_bbox` devolve o ENVELOPE dos 4 cantos transformados — cresce de verdade num round-trip
(convergência meridiana do UTM/Policônica: medido ~700 m de crescimento num bbox de 0,2°×0,2° perto de
São Paulo, ida e volta por 31982). Quem reprojetar uma FEIÇÃO real (não um bbox de consulta) precisa
reprojetar cada vértice, não só o envelope — é o que a ferramenta "reprojetar" do L2-05-b (ainda não
construída) vai ter de fazer. Sentido inverso SIRGAS2000 -> Córrego Alegre não suportado (a ingestão só
lê dado legado, nunca grava nele). Mapa (seção 13, MapLibre) desenha SEMPRE em Web Mercator — não existe
"trocar a projeção do mapa" nesta pilha, mesma limitação do Map Viewer da Esri sem mapa-base compatível.


### 22.4 Rótulos (item L2-02-d-rotulos)

`plat_construtor.rotulos` (quando `visivel: true`) tem uma ou mais `classes`, cada uma com filtro opcional
(`{campo, operador, valor}` — sem filtro, é a classe padrão da camada), o texto (por `campo` direto ou por
`expressao` na linguagem própria do item L2-10-c), fonte, tamanho, cor, halo, âncora e deslocamento (útil em
camadas de ponto), rótulo ao longo da linha com distância de repetição (camadas de linha), várias linhas,
maiúsculas, sufixo de unidade, prioridade e permitir-sobreposição, e faixa de escala própria (independente da
faixa da camada inteira). Cada classe vira um layer `symbol` da MapLibre Style Spec.

**Expressão compilável ou coluna do servidor.** Quando `texto.expressao` usa só as operações que a Style
Spec também tem (aritmética, comparação, `Se`/`SeNulo`/`EhNulo`, `Concatenar`/`Texto`/`Maiuscula`/
`Minuscula`, `Absoluto`/`Minimo`/`Maximo`/`Arredondar`), o texto é calculado pelo próprio MapLibre no
navegador. Quando usa algo sem equivalente nativo — a começar pela formatação de número em pt-BR
(`TextoNumero`, "1.234,5") — o texto é calculado no servidor e o rótulo lê uma coluna pré-calculada; as duas
formas dão o MESMO texto para a MESMA expressão (é o que garante que trocar de forma nunca muda o que o
usuário vê). Uma feição com campo nulo, divisão por zero ou erro de avaliação nunca mostra "null"/"NaN" —
fica com rótulo vazio, sem derrubar as demais.

**Prioridade e colisão entre classes.** Quando duas classes competem pelo mesmo espaço, a de prioridade
numericamente menor (mais importante) é exibida e a outra é suprimida — testado com dois pontos no mesmo
lugar. Por trás, isso não é feito só com o atributo de prioridade da Style Spec (que só decide entre feições
de uma MESMA classe): o servidor ordena os layers das classes na ordem certa para o motor de desenho resolver
a colisão do jeito esperado.

**Faixa de escala por classe.** Uma classe pode ter sua própria faixa de escala (além da faixa da camada
inteira) — útil para mostrar um rótulo resumido de longe e um mais detalhado de perto, por exemplo. Testado
com o mesmo rótulo aparecendo dentro da faixa e sumindo fora dela.

O que ficou de fora: filtro de classe só cobre comparação simples (não uma expressão booleana qualquer);
posição no centro geométrico do polígono não é distinta de "ponto garantido dentro do polígono" (o motor de
desenho sempre garante o ponto dentro); o glifário definitivo (fontes com licença documentada, servidas em
produção) é o item L2-02-e — aqui o mecanismo foi provado com um servidor de fontes real e fontes abertas.
## 22. Modo somente-leitura/manutenção (item L7-33-modo-somente-leitura)

### 22.1 O que é

Uma bandeira liga/desliga o modo somente-leitura para a plataforma inteira ou para um inquilino. Ligado,
toda escrita (`POST`/`PUT`/`PATCH`/`DELETE`) devolve `503` com o motivo, exceto login/logout, `/api/modo`,
`/saude`, `/api/versao` e a exportação de catálogo (`catalogo.exportar_lista`, que só lê); leitura, mapa e
tiles continuam normais. Quem tem sessão aberta e quem ainda não entrou veem uma faixa no topo da tela com
o motivo. É o mecanismo que a atualização (L7-14), o failover (L7-07-c) e a licença vencida (L7-11-a)
usarão para pausar escrita antes de mexer na plataforma — nenhum dos três existe ainda; este item entrega
só o interruptor e a CLI.

### 22.2 Operar (`plat modo`, CLI — não existe rota HTTP para ligar/desligar)

```
plat modo ligar    --motivo "troca da versão 2026.09" [--inquilino SLUG] [--retry-after S] [--quem N]
plat modo desligar --motivo "troca concluída, smoke ok" [--inquilino SLUG] [--quem N]
plat modo estado   [--inquilino SLUG]
```

Motivo é obrigatório nos dois sentidos (ligar E desligar) — recusado tanto pelo `argparse` quanto pela
função SQL, e cada chamada grava uma linha em `plat.sistema_trilha` (quem, quando, motivo). Só a role do
worker (`plat_worker`) tem `EXECUTE` nas funções `plat.modo_ligar`/`modo_desligar`: é operação de
infraestrutura, a API nunca liga o próprio modo. Global vence sobre o de um inquilino específico.

### 22.3 `GET /api/modo` (público, sempre 200)

`{"ativo": bool, "escopo": "global"|"inquilino", "motivo": "...", "quem": "...", "desde": "...",
"retry_after_s": N}` (ou só `{"ativo": false}`). É o que a faixa do front consulta — o texto que o usuário
lê na faixa é o MESMO motivo devolvido no `detalhe` do `503` de uma escrita bloqueada.

### 22.4 Jobs sob o modo

Um job já `rodando` no momento de ligar termina normalmente (nunca é tocado). Um job comum pendente na fila
fica retido (não é retirado) enquanto o modo estiver ligado para o inquilino dele — mesmo que a cota de
simultâneos abra vaga — e só é pego na próxima varredura depois de desligar. `POST /api/jobs` de um tipo
comum é escrita e devolve `503` como qualquer outra rota; só um tipo declarado `somente_leitura=True` no
registro (hoje `catalogo.exportar_lista`) atravessa tanto o middleware quanto a fila.

### 22.5 O que ficou de fora

Nenhum consumidor automático (atualização, failover, licença vencida) liga o modo sozinho — hoje é sempre
operação manual pela CLI. O silenciamento de alerta durante o modo (L7-06-b) tem o ponto de leitura pronto
(`/saude` expõe `manutencao.ativo`), mas não há motor de alerta construído nesta plataforma para provar o
silenciamento ponta a ponta. Ver ADR `20260907T1434-modo-manutencao.md`.
## 28. Localizar regiões sobre a favorabilidade (item L3-05-localizar-regioes)

Depois de rodar o motor multicritério (execução macro ou micro), a pergunta "onde ficam as N áreas" tem rota
própria:

```
POST /api/multiescala/execucoes/{id}/regioes
{
  "n_regioes": 3, "area_total_m2": 3750000, "area_min_m2": null, "area_max_m2": null,
  "distancia_min_m": 2000, "distancia_max_m": null, "compromisso": 50,
  "forma": "circulo|quadrado|hexagono", "metodo": "maior_media|maior_soma|mediana|maior_area_nucleo",
  "selecao": "sequencial|combinatoria", "vizinhanca": 8, "sem_ilhas": true,
  "sementes": "auto|poucas|medias|muitas|maximo", "semente_aleatoria": 7, "so_aprovadas": false
}
```

A resposta traz, por região: o polígono (união das células, GeoJSON 4326), um ponto interno, área, favorabilidade
média, soma, mediana, área de núcleo, compacidade contra a forma-alvo e o centróide em índice de célula. Fora das
regiões vêm os parâmetros usados, a área alvo, a área total obtida e as observações (por exemplo, quando a área
mínima ou a distância impediram chegar ao alvo ou a N regiões).

- `compromisso` 0 escolhe só pela favorabilidade; 100 escolhe só pela forma; 50 é o padrão.
- Célula sem nota ou vetada nunca entra em região, nem quando o preenchimento de buracos passa por cima dela.
- `so_aprovadas` restringe a busca às células que a própria execução aprovou.
- Mesma `semente_aleatoria` = mesma resposta.
Recusas com código próprio (HTTP 422): `area_maior_que_a_disponivel`, `n_regioes_fora_do_limite` (1 a 30),
`area_min_impossivel`, `area_max_impossivel`, `distancia_min_maior_que_max`, `sem_regiao_possivel`,
`sem_combinacao_possivel`, `grade_grande_demais` (teto de 4 milhões de células por chamada), `execucao_sem_nota`.
Nada é gravado: a rota responde a uma pergunta sobre a execução; para guardar, crie um item com o GeoJSON.
Exportação de VISTA de camada (o tipo `vista_de_camada` existe no catálogo, mas o item `L0-04-j` que o
implementa ainda não foi entregue — quando for, o filtro da vista entra como mais um `where` neste mesmo
motor) e exportação de camada REFERENCIADA (recusada com 422 `camada_nao_hospedada`, nunca silenciosa).
---

## 21. Identidade visual, tema e a régua (item L0-14-identidade-visual)

A página `/estilo` (com ou sem sessão) é o sistema de design vivo: lê `web/estilo/tokens.css` no momento em que
abre e desenha a paleta do tema em uso com a razão de contraste medida no navegador, a escala tipográfica, a
grade de espaçamento, a forma, a família de ícones inteira e os 6 componentes de base nos 7 estados. O que se lê
nela é o que está no arquivo; não existe cópia.

Tema: os três botões na barra lateral (sistema, claro, escuro) valem para todas as telas e ficam guardados no
navegador (`localStorage`, chave `plat_tema`); "sistema" segue a preferência do sistema operacional. Densidade
(compacta, normal, confortável) escolhe-se em `/estilo` (chave `plat_densidade`).

A régua: todo número mostrado com uma régua embaixo (traços em âmbar) carrega a procedência. Passe o cursor ou
leve o foco de teclado até ele para ver a rota que o produziu, o instante (UTC) e, quando existe, o comando de
conferência na linha de comando. No rodapé de toda tela com sessão, a linha "régua" lista as últimas chamadas à
API da tela (rota, código HTTP, hora UTC, duração). Regras completas em `docs/IDENTIDADE.md`; medidas em
`tests/medidas/L0-14.json`.
## 22. Publicação de documento de construtor (item L5-14-publicacao-links-embed)

Um documento `app`/`painel` (seção 17) publica numa URL fixa e anônima `/p/<inquilino>/<slug>`:

```
POST   /api/itens/{id}/publicacao                # publica/republica; body {slug, dominios_permitidos?, versao?}
GET    /api/itens/{id}/publicacao                # estado atual (slug, url, domínios, camadas citadas)
DELETE /api/itens/{id}/publicacao                # despublica: revoga o token do app, apaga a linha
GET    /api/itens/{id}/publicacao/visualizacoes  # contagem por dia (padrão 30 dias)
GET    /api/itens/{id}/publicacao/exportacao     # HTML autocontido: abre de file://, sem chamada de rede
GET    /api/p/{inquilino}/{slug}?link=<token>    # o documento (JSON), sem sessão
GET    /p/{inquilino}/{slug}                     # a casca HTML (a mesma que embute em <iframe>)
```

Publicar faz três coisas na mesma chamada: aponta `plat.item.versao_publicada` para a versão escolhida (a
leitura pública nunca mostra o rascunho — editar o item depois de publicar não muda `/p/` até um novo
`POST .../publicacao`); reserva o slug (único por inquilino); e emite um **token de serviço próprio da
publicação** (mesma tabela `plat.token_servico` do item de tokens, seção 7) com escopo calculado
automaticamente — as camadas citadas pelo documento (fecho de `plat.item_relacao` até a família `camada`,
tipicamente app → mapa → camada) — e `restricao.referer` = a lista `dominios_permitidos`. Esse token vem
embutido no JSON que `/api/p/...` devolve (é uma "chave publicável": qualquer visitante da página já a vê
no HTML/JS servido, então escondê-la do banco não protegeria nada — o que protege é o escopo e a
restrição de domínio; ver `docs/adr/20260907T1410-publicacao-links-embed.md` seção 3).

Acesso à página: **público** (quando `item.acesso = 'publico'` e o inquilino permite) ou **por link**
(reaproveita o mesmo `plat.compartilhamento_link`/`/api/itens/{id}/links` da seção de compartilhamento —
não é um segundo tipo de link). Sem link e sem ser público: `401`. Link revogado, expirado ou de outro
item: `403`. Acesso por sessão de inquilino/grupo autenticada a `/p/` fica fora desta rodada (a navegação
autenticada já usa os endpoints normais do item).

`GET /p/{inquilino}/{slug}` manda `Content-Security-Policy: frame-ancestors 'self' <dominios_permitidos>`
— nunca `X-Frame-Options: DENY` — então só carrega em `<iframe>` nos domínios cadastrados no app; qualquer
outra origem tem o carregamento bloqueado pelo PRÓPRIO NAVEGADOR do visitante. A exportação estática
(`.../publicacao/exportacao`) embute o grafo e o metadado das camadas citadas como
`<script type="application/json">`, sem `<script src>` externo nem `fetch` — abre por `file://` com o
mesmo conteúdo porque não há rede para falhar (não inclui geometria/feição: é um retrato do DOCUMENTO).

O que ficou fora deste turno (ver ADR seção 6): miniatura por captura headless no publish (o portão não
pede; a miniatura própria do item, seção de catálogo, continua valendo), acesso a `/p/` por sessão
autenticada, e o envio automático da exportação para hub/appliance (o endpoint devolve o arquivo; a
distribuição é integração de outro item). O token gerado pela SEÇÃO 7 (`/admin/tokens`) e o desta seção
usam a MESMA tabela e o MESMO mecanismo de escopo/restrição — nenhuma autorização nova nasceu aqui.
## 29. Backtest contra decisão real (item L3-09-backtest-decisao-real)

Depois de uma execução do motor multicritério, dá para perguntar o quanto o modelo concorda com escolhas que já
aconteceram (galpões construídos, linhas existentes, agências abertas):

```
POST /api/multiescala/execucoes/{id}/backtest
{ "escolhas_item_id": "<uuid de camada vetorial hospedada>",   // OU
  "pontos": [{"lon": -46.5, "lat": -23.5}, ...],
  "n_permutacoes": 1000, "semente": 0,
  "data_decisao": "2018-06-01", "data_camada": "2026-09-01",
  "preferencia_revelada": true }
```

A resposta traz `auc` (probabilidade de uma escolha ser mais favorável que uma não-escolha sorteada),
`percentil_mediano` e `percentil_medio` das escolhas no ranking, o `nulo` por permutação (média e faixa de 5 % a
95 % da AUC sorteada, e o percentil mediano do nulo), o `p_valor`, `n_escolhas`, `n_unidades`, `n_fora` (escolhas
que não caíram em nenhuma célula) e, por fator, a preferência revelada: `evitamento` positivo (a escolha evitou o
fator) ou negativo (procurou), com as duas frações que geraram o número. Nunca há peso na resposta.

Ressalvas que vêm sempre em `ressalvas`: o backtest mede concordância com a decisão passada, não acerto futuro;
fatores de distância se confundem entre si e com a escolha. Quando `data_camada` é mais nova que `data_decisao`,
`anacronica` fica verdadeiro e a primeira ressalva diz por quê.

Casos que a resposta nomeia em vez de esconder: com TODAS as células marcadas como escolhidas, `auc` vem `null`
e `auc_indefinida` explica que sem não-escolhas a AUC não existe (não é 0,5 nem 1,0); com nenhuma escolha dentro
da grade, `auc` vem `null` e `n_fora` mostra quantas ficaram de fora. Nada é gravado.
## 22. Banco externo: PostgreSQL/PostGIS referenciado e consulta SQL do cliente (item L6-02-j-bancos-externos)

Complementa a seção 18.2a (conector `postgres_fdw`). A tabela PostGIS remota aparece em
`GET /api/conexoes/{id}/tabelas` com `geometria` (`coluna`, `tipo`, `srid`, lidos de `geometry_columns` do
banco remoto) e é publicada como camada referenciada por `publicar-em-massa`. Sobre a mesma conexão, o
cliente pode rodar uma consulta SQL de leitura no banco dele:

```
POST /api/conexoes/{id}/consulta    {"sql": "SELECT id, nome FROM sedes WHERE uf = 'BA' ORDER BY id LIMIT 100",
                                      "schema_remoto": "public"}
→ {"colunas": [...], "linhas": [[...]], "n": 100, "limite": 100, "tabelas": ["sedes"], "tempo_ms": 12}
```

Regras, todas verificadas ANTES de abrir a conexão (422 com o código entre parênteses):
- um comando só, começando por `SELECT` ou `WITH`; sem `;`, sem comentário (`--`, `/*`), sem bloco `$$`
  (`consulta_recusada`);
- nenhuma palavra de escrita ou de sessão em qualquer posição — INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/
  TRUNCATE/GRANT/REVOKE/COPY/SET/LOCK/FOR UPDATE... — e nenhuma função de sistema (`pg_sleep`,
  `pg_read_file`, `dblink`, `lo_import`, `current_setting`...) (`consulta_recusada`);
- só tabelas que a própria conexão lista no `schema_remoto` (`tabela_fora_da_lista`); `pg_catalog`,
  `information_schema` e outros schemas são recusados;
- `LIMIT <n>` explícito no fim, com 1 <= n <= 5.000 (`limit_obrigatorio` / `limit_acima_do_teto`);
- texto de até 4.000 caracteres (`consulta_longa`).
A execução usa a conexão só-leitura do conector (`statement_timeout` de 8 s): erro do banco do cliente
volta como 422 `consulta_invalida`, tempo esgotado como 422 `tempo_esgotado`, banco fora do ar como 503 e
marca a saúde da conexão. O evento `conexoes/consultar` guarda tabelas, nº de linhas e tempo — nunca o texto
da consulta nem o resultado. **SQL Server e Oracle não foram construídos** (sem container liberado; pendente).
## 22. Acervo (`/acervo`, item L6-01-c-tela-acervo)

A tela **Acervo** mostra as fontes oficiais que a casa já carregou e documentou. É o lugar de responder três
perguntas antes de usar um dado: de onde ele vem, sob que licença, e quando foi atualizado pela última vez.

### 22.1 Achar uma fonte

O campo de busca procura no **nome** e no **órgão** (não no texto da descrição). A lista suspensa ao lado
filtra por **domínio**: ela traz a taxonomia inteira do acervo, com a contagem de fontes visíveis entre
parênteses. Um domínio que hoje não tem nenhuma fonte visível aparece com zero — a categoria continua na lista
em vez de sumir.

Uma fonte **sem licença escrita não aparece nesta tela**, nem na busca, nem pelo endereço direto da ficha (a
resposta é 404, igual à de uma fonte que não existe). Isso é regra do produto, não defeito: sem licença
registrada a casa não afirma que pode redistribuir o dado.

### 22.2 A ficha

Um clique no cartão abre a ficha de procedência: órgão, domínio, licença, frescor, número de tabelas e de
registros, data do dado, método de carga, confiança, o que aquele dado **não** sustenta, sha256, comando de
reexecução, próxima verificação, completude de procedência (x/10) e quantos endereços da fonte foram
confirmados e estão vivos. Quando existe um endereço vivo confirmado, a pré-visualização mostra o link.

### 22.3 Licença e atribuição obrigatória

A etiqueta de licença do cartão traz o tipo **curado** — verificado por HTTP na página do órgão (item
L6-01-g), de um vocabulário fechado (CC0, CC-BY, CC-BY-SA, ODbL, Copernicus, dado aberto com termo do órgão,
licença própria, não declarada). Quando a curadoria ainda não passou pela fonte, a etiqueta diz "declarada em
texto livre" e o texto que o órgão publicou fica no título da etiqueta e na ficha. O tipo curado nunca é
adivinhado a partir do texto livre.

Se o tipo curado for **ODbL** ou **CC-BY-SA**, a ficha mostra um aviso de **atribuição obrigatória**: usar o
dado exige citar a fonte e o órgão.

### 22.4 Adicionar ao meu mapa

O botão "adicionar ao meu mapa" cria, no catálogo do seu inquilino, um item do tipo conexão que **referencia**
a fonte — nunca copia o dado. O item guarda um instantâneo do que valia na hora de adicionar (licença, tipo
curado, frescor, sha256, comando de reexecução). Fonte marcada com risco de dado pessoal exige uma
confirmação explícita antes de qualquer item ser criado.

Na tela **Mapa**, a legenda no canto inferior direito lista as camadas do acervo que você adicionou, com a
licença de cada uma; para ODbL e CC-BY-SA a linha de atribuição obrigatória aparece ali, que é onde o dado é
visto. Sem nenhuma camada adicionada, a legenda não aparece.

### 22.5 O que ficou de fora

A camada adicionada aparece na **legenda** e no catálogo; ela ainda não é desenhada como geometria sobre o
mapa — isso depende do serviço de tiles das fontes do acervo, que é item de outra frente.

## 26. Diretório LDAP pela tela (item UX-17-login-sem-controle)

Em `/admin/organizacao`, seção "Diretório (LDAP / Active Directory)": quem tem o privilégio `org.integracoes`
configura o servidor (`ldap://` ou `ldaps://`), a base de busca, StartTLS, a conta de serviço (a senha nunca
volta; vazio preserva a guardada), o filtro de usuário (`{login}` é substituído), o atributo de grupos, o perfil
padrão e o mapa grupo → perfil (uma linha por grupo: `nome-do-grupo = admin | editor | visualizador | campo`).
Abaixo, "Importar um grupo do diretório" cria os membros como usuários desabilitados, ativados no primeiro
login pela rede; o resultado diz encontrados, criados, já existentes e recusados. Sem o privilégio a seção mostra
"sem permissão"; sem diretório configurado, mostra o formulário com os padrões.
Em `/entrar`, com o diretório habilitado, aparece "Entrar com o diretório da organização (LDAP)": o botão
alterna o modo, o "Entrar" vira "Entrar pelo diretório" e o mesmo usuário e senha vão a `POST /api/login/ldap`.
Diretório fora do ar e diretório não configurado aparecem com a mensagem própria; senha errada marca o campo.

## 23. Ramos de versão e reconciliação (`/versoes`, item L2-13-a-versoes-ramo-reconciliar)

Um **ramo** é uma linha de trabalho paralela sobre uma camada: as edições ficam guardadas fora do
padrão até alguém decidir publicá-las. É o equivalente ao *branch versioning* do ArcGIS Enterprise, e
serve para o caso comum de campo — três equipes revisando o mesmo cadastro sem uma pisar na outra.

### Ligar o versionamento numa camada

    POST /api/camadas/{id}/versionar          {"ramos_max": 10}

Só camada vetorial hospedada. Cria a tabela onde as linhas de ramo vão morar e grava o metadado em
`dados.versionamento`. É idempotente: chamar de novo só reafirma, e permite mudar o teto de ramos.
Sem `ramos_max`, vale o teto da plataforma (50 ramos ABERTOS por camada).

### Criar, listar e apagar ramo

    POST   /api/camadas/{id}/versoes          {"nome": "revisao-norte", "acesso": "protegido"}
    GET    /api/camadas/{id}/versoes
    GET    /api/camadas/{id}/versoes/{nome ou id}
    DELETE /api/camadas/{id}/versoes/{nome ou id}

`acesso` diz quem faz o quê: `privado` — só o dono lê e escreve; `protegido` (padrão) — todos leem, só
o dono escreve; `publico` — todos leem e escrevem. Quem tem `feicoes.editar_total` passa em tudo.
Apagar **descarta as edições do ramo**: nada vai para o padrão.

### Editar dentro do ramo

A porta de escrita é a de sempre; o que muda é um campo:

    POST /api/camadas/{id}/edicoes
    {"versao": "revisao-norte", "atualizar": [{"id": "<globalid>", "versao": 3, "atributos": {...}}]}

Vale igual para o `applyEdits` do FeatureServer, com `gdbVersion=revisao-norte`. Uma feição criada no
ramo só existe no ramo; uma apagada no ramo some do ramo e continua no padrão.

### Ler dentro do ramo, e ler o passado

    GET /rest/services/{item}/FeatureServer/0/query?where=1=1&gdbVersion=revisao-norte
    GET /rest/services/{item}/FeatureServer/0/query?where=1=1&historicMoment=1757332800000

A leitura no ramo mostra as edições do ramo mais o padrão **como estava no momento em que o ramo
nasceu**: uma mudança feita no padrão depois disso só aparece no ramo depois de reconciliar.
`historicMoment` (epoch em milissegundos, ou data ISO 8601) devolve o padrão como estava naquele
instante, incluindo feição que já foi apagada. Os dois juntos são recusados: o momento histórico é do
padrão.

### Reconciliar, resolver e publicar

    POST /api/camadas/{id}/versoes/{ramo}/reconciliar
    GET  /api/camadas/{id}/versoes/{ramo}/conflitos
    POST /api/camadas/{id}/versoes/{ramo}/conflitos/{globalid}/resolver   {"decisao": "ramo"}
    POST /api/camadas/{id}/versoes/{ramo}/publicar                        {"modo": "fechar"}

**Reconciliar** compara ramo e padrão desde o momento base e lista as feições alteradas dos dois lados,
atributo a atributo e geometria. Sem conflito, o momento base avança — é assim que o ramo passa a
enxergar o padrão de agora nas feições que ele não tocou.

**Resolver** decide uma feição: `ramo` mantém o que o ramo tem, `padrao` traz o estado atual do padrão
para dentro do ramo, `manual` grava no ramo os valores enviados em `atributos`/`geometria`. A decisão
fica gravada com o momento do padrão em que foi tomada: **se o padrão mudar de novo, o conflito
reabre**.

**Publicar** reconcilia antes (é obrigatório) e recusa com 409 se sobrar conflito sem decisão; a lista
vem no corpo do erro. `modo=fechar` encerra o ramo; `modo=rebasear` mantém o ramo aberto, descarta as
linhas já publicadas e reposiciona o momento base no agora.

### A tela

`/versoes?camada=<id>` mostra os ramos da camada e, depois de reconciliar, um cartão por conflito com o
diff lado a lado: **base** (o valor no momento do ramo), **no ramo** e **no padrão**, sempre nessas três
colunas e na mesma ordem. O lado que mudou é marcado. A decisão é tomada ali, com a opção `decidir
campo a campo` abrindo um formulário já preenchido com os valores do ramo.

### VersionManagementServer (compatibilidade Esri)

`/rest/services/{item}/VersionManagementServer` com `versions`, `versionInfos`, `create`,
`{guid}/reconcile`, `{guid}/conflicts`, `{guid}/post`, `{guid}/delete` e as sessões
`startReading`/`stopReading`/`startEditing`/`stopEditing`. As sessões conferem o ramo e a permissão e
devolvem o momento do servidor; não guardam sessão, porque a leitura consistente e a escrita atômica
vêm da transação do banco.

### O que NÃO está aqui

Ramo de ramo (a coluna `pai` existe e é sempre o padrão); detecção de conflito por atributo
(`conflictDetection=byAttribute` é aceito e ignorado — a detecção é por objeto); `historicMoment`
dentro de um ramo; e coluna acrescentada à camada depois de ela ser versionada, que exige reversionar.
Ver `docs/adr/20260908T1323-versionamento-por-ramo.md`.

## 23. Entrada de eventos em tempo real (`/api/fluxos`, processo `plat-fluxo`, item L2-14-a-ingestao-de-fluxos)

Uma FONTE de fluxo é um objeto do inquilino que recebe evento sem parar: veículo de frota, sensor, embarcação
por AIS, serviço de terceiro que publica posição. Equivale ao *feed* do ArcGIS Velocity/GeoEvent; a comparação
linha a linha está em `docs/PARIDADE.md`.

### 23.1 Os oito tipos de fonte

Quatro RECEBEM (o remetente vem até a plataforma):

- **`http`** — o remetente faz `POST` no endereço da fonte, com JSON, NDJSON, CSV ou GeoJSON.
- **`websocket_servidor`** — o remetente abre um WebSocket e manda um evento (ou um lote) por quadro de texto.
- **`gps_frota`** — o mesmo `POST`, aceitando também GPX 1.1 (`trkpt`, `wpt`, `rtept`).
- **`sensor`** — o mesmo `POST`, com JSON de valor e unidade mapeados como campos.

Quatro VÃO BUSCAR (a plataforma se conecta ao terceiro):

- **`mqtt`** — assina um tópico de um broker externo, com TLS, usuário e senha, QoS 0 ou 1. A plataforma nunca
  publica no broker; ela só assina. Broker próprio na nossa máquina depende da decisão D31 do dono.
- **`websocket_cliente`** — assina um WebSocket de terceiro, com cabeçalho de credencial e mensagem de
  assinatura opcionais.
- **`sondagem`** — busca uma URL no intervalo declarado (5 s a 24 h). Com `campo_atualizacao`, cada rodada só
  ingere o registro cujo valor daquele campo é maior que o da rodada anterior — sem isso a mesma lista entraria
  de novo a cada busca. `caminho_lista` aponta a lista dentro do documento. Aceita JSON, NDJSON, CSV, GeoJSON e
  a resposta `f=json` de um FeatureServer.
- **`ais`** — lê sentenças NMEA por TCP e decodifica as mensagens de POSIÇÃO (1, 2, 3 e 18). Mensagens de dado
  estático (5, 24) chegam, são ignoradas e contadas.

Todo endereço declarado — URL, e também o par host/porta do MQTT e do AIS — passa pela defesa contra SSRF do
item L6-02-a antes de a fonte ser gravada: uma fonte nunca fica registrada apontando para a rede interna, para
o serviço de metadado da nuvem ou para o loopback da máquina.

### 23.2 Mapeamento e esquema de destino

O `mapeamento` diz como o registro cru vira evento:

- `campo_tempo`: `caminho` (caminho JSON, com ponto e índice: `a.b[0].c`), `tipo` (`iso`, `epoch_s`,
  `epoch_ms`, `texto` com `formato`) e `fuso` (nome IANA, por exemplo `America/Sao_Paulo`). O fuso vale para
  texto SEM deslocamento; texto COM deslocamento manda no próprio dado. Sem `caminho`, o tempo do evento é o
  do recebimento.
- `campo_rastro`: o caminho do identificador que liga os eventos do mesmo objeto (placa, MMSI, número de série).
- `geometria`: `{"modo": "lonlat", "lon": ..., "lat": ...}`, `{"modo": "wkt", "caminho": ...}` (só `POINT`),
  `{"modo": "geojson", "caminho": ...}` (só `Point`) ou `{"modo": "nenhum"}`.
- `campos`: lista de `{caminho, coluna, tipo}` com tipo em `texto`, `inteiro`, `numero`, `booleano`, `data`.

Disso a plataforma GERA o `esquema_destino` (nome, tipo e origem por campo), que é o que a API devolve e o que
quem consome o fluxo pode contar que existe. Os valores já convertidos ficam em `atributos` da tabela de
eventos; não há uma tabela com colunas por fonte (o porquê está no ADR do item, seção 2).

Antes de apontar o remetente, `POST /api/fluxos/{id}/simular` com um registro de exemplo mostra o que sai do
mapeamento e do filtro **sem gravar nada e sem gastar o teto por segundo**. É como se confere um fuso.

### 23.3 Filtro na entrada

`filtro` é uma expressão da linguagem da casa (`docs/EXPRESSAO.md`) avaliada por evento, sobre os campos
mapeados mais `rastro_id`, `tempo_evento` (milissegundos desde a época), `lon` e `lat`. Exemplo:
`$velocidade > 40 && $lat < -20`. Evento que não passa é descartado e contado em `descartados_filtro`. Campo
fora dessa lista é erro nomeado, nunca nulo silencioso.

### 23.4 Teto por segundo, e o que o teto significa

`limite_eventos_s` (1 a 100.000, padrão 1.000) é um balde de fichas por fonte: passado o teto, o evento é
descartado e CONTADO em `descartados_limite` — nunca enfileirado, porque enfileirar o excesso é o mesmo que
não ter teto. O teto é **por processo `plat-fluxo`**: com N processos, o teto efetivo do inquilino é N vezes o
valor. Hoje o serviço é um processo só.

O teto é conferido ANTES do mapeamento: numa rajada, converter o evento é o trabalho que não se quer gastar.
Por isso a contagem de inválidos vale só sobre o que passou pelo teto.

### 23.5 Pausar e retomar

`PATCH /api/fluxos/{id}` com `{"estado": "pausada"}` para a GRAVAÇÃO, não a conexão: o conector continua
assinado e o evento vai para um buffer em memória com teto declarado — `limite_eventos_s × 30 s`, nunca acima
de 50.000 eventos. Retomada, o buffer é drenado na ordem de chegada. Cheio, o evento novo é descartado e
contado como `buffer_de_pausa_cheio`: pausa não é armazenamento.

⚠ O buffer vive na memória do processo. **Uma parada do `plat-fluxo` com fonte pausada perde o buffer.**

### 23.6 Como o remetente se autentica

Token de serviço (`/api/tokens`) com o escopo **`fluxo:escrever`**. O escopo aceita o sufixo de uma fonte —
`fluxo:escrever:<uuid>` — e é assim que se entrega um token a um veículo sem lhe dar as outras fontes da casa.
Para ler evento e métrica pela API basta `fluxo:ler`.

    curl -X POST https://<host>/fluxo/<id-da-fonte>/eventos \
      -H "Authorization: Bearer plat_..." -H "Content-Type: application/json" \
      -d '[{"ts":"2026-01-15T09:00:00","placa":"AAA0A00","lon":-46.6,"lat":-23.5,"velocidade":50}]'

A resposta é o resumo do lote: `recebidos`, `aceitos`, `descartados_limite`, `descartados_invalido`,
`descartados_filtro`, `em_buffer`. No WebSocket, o mesmo resumo volta por quadro. Token de um inquilino que
aponta para fonte de outro recebe **404** (não 403): a existência do identificador alheio não vaza.

Tetos do receptor: 4 MiB por pedido (e por quadro), 20.000 eventos por lote, 200 caracteres no identificador
de rastro, 4.096 caracteres por valor de texto, 5 minutos de folga de relógio para tempo à frente e 10 anos
para trás. Fora disso, o evento é recusado com motivo nomeado e contado.

### 23.7 Ler o que entrou, e a métrica

- `GET /api/fluxos/{id}/eventos?desde=&ate=&rastro=&limite=` — os eventos gravados, mais recentes primeiro.
- `DELETE /api/fluxos/{id}/eventos?antes_de=<instante>` — expurga por corte de tempo.
- `GET /api/fluxos/{id}` — traz `metrica`: recebidos, aceitos, descartados por motivo, atraso do último evento
  e mediana, e quando a métrica foi atualizada (o processo a espelha no banco a cada segundo).
- `GET http://127.0.0.1:8155/saude` — estado do processo; com `Authorization` de um token, também a métrica
  viva por fonte **daquele inquilino**, com o tamanho do buffer e a contagem por motivo de descarte.

Apagar a fonte apaga os eventos dela junto (não há chave estrangeira entre as duas tabelas: uma verificação
por linha custaria caro no lote, então o expurgo é explícito na rota).

### 23.8 Onde o evento fica

`plat.fluxo_evento`, particionada por MÊS de recebimento, com índice BRIN em tempo, GIST em geometria e índice
por fonte e por rastro. Cada mês é uma partição (`plat.fluxo_particao_garantir()`), mais uma partição padrão
que garante que nada se perca na virada do mês. Expurgo de histórico antigo é `DROP` da partição inteira, que
é barato; o `DELETE` por corte de tempo da rota serve para janelas curtas.

Medido em 8 de setembro de 2026, contra o processo de verdade em uma máquina de 12 núcleos com carga 6,8:
**600.000 eventos em 60,0 s (10.000 por segundo, em lotes de 2.000), perda zero, atraso mediano de 30,9 ms**
(percentil 95 em 44,3 ms), fila drenada 0,4 s depois do último envio, memória residente do processo em
78,5 MB. Os números e a carga da máquina ao lado deles estão em
`tests/medidas/L2-14-a-ingestao-de-fluxos.json`.
## 22. Transformações do motor multicritério: valor bruto → favorabilidade 0-100 (item L3-01-d-transformacoes)

`app/amc/transformacoes.py` implementa os 16 tipos de `docs/esquemas/amc_modelo.v1.json#/$defs/transformacao`
em numpy (pré-visualização e recomputação); `db/migracoes/20260907T1602_amc_transformacoes.sql` implementa os
mesmos 16 em PL/pgSQL (`plat.amc_transformar_num`/`plat.amc_transformar_cat`, para materializar sem trazer a
coluna para o Python). As duas têm de bater, célula a célula, a ≤ 0,01 — provado em
`tests/unit/test_amc_transformacoes.py`.

### 22.1 Os 16 tipos

| tipo | parâmetros | o que faz |
|---|---|---|
| `categoria` | `notas` (objeto texto→nota), `outros` | Unique Categories: valor não listado usa `outros`; sem os dois, fica NULL |
| `faixas` | `quebras`, `notas`, `metodo` (manual/quantil/intervalo_igual/quebras_naturais) | Range of Classes: degrau, `quebras[i-1] < x ≤ quebras[i]` |
| `linear` | `minimo`, `maximo`, `direcao` | rampa 0-100 (ou `saida_min`/`saida_max`, extensão deste item) |
| `linear_simetrica` | `minimo`, `maximo` | pico no ponto médio, cai para as duas pontas (Symmetric Linear) |
| `degraus` | `bandas` (`{ate, nota}`), `acima` | bandas do motor logístico (ex.: tempo de viagem em faixas) |
| `potencia` | `minimo`, `maximo`, `expoente`, `deslocamento` | Power |
| `logaritmo` | `minimo`, `maximo`, `fator`, `deslocamento` | Logarithm |
| `exponencial` | `minimo`, `maximo`, `base`, `deslocamento` | Exponential |
| `crescimento_logistico` | `minimo`, `maximo`, `y_intercepto_percentual` | Logistic Growth (S crescente) |
| `decaimento_logistico` | idem | Logistic Decay (S decrescente, espelho da anterior) |
| `gaussiana` | `midpoint`, `spread` | Gaussian |
| `proxima` | `midpoint`, `spread` | Near (mais estreita que a Gaussian) |
| `grande` | `midpoint`, `spread` | Large (sigmoide crescente) |
| `pequena` | `midpoint`, `spread` | Small (sigmoide decrescente) |
| `ms_grande` | `multiplicador_media`, `multiplicador_desvio` (+ `media`/`desvio` resolvidos da amostra) | MSLarge |
| `ms_pequena` | idem | MSSmall |

Comuns a todos: `abaixo`/`acima` (nota fixa fora do domínio; ausente = usa a borda da própria curva) e NULL de
entrada sempre sai NULL. `saida_min`/`saida_max` (padrão 0/100) são uma extensão ADITIVA deste item — o
esquema não fecha `additionalProperties` no objeto `transformacao`, então isto não quebra nenhum modelo já
gravado.

**Fórmula declarada, não engenharia reversa** (ver ADR `20260907T1602`): a Esri documenta propósito e nome de
parâmetro das 12 funções contínuas do Rescale by Function, mas não publica a fórmula fechada (verificado em
07/09/2026, `doc.esri.com/.../the-transformation-functions-available-for-rescale-by-function.html`). Este
módulo declara uma fórmula concreta e documentada para cada uma, com os mesmos parâmetros e o mesmo efeito
qualitativo descrito — nunca afirma reproduzir o produto fechado da Esri byte a byte.

### 22.2 Gráfico de cada função

`venv/bin/python scripts/amc_transformacoes_graficos.py` gera `docs/graficos/amc_transformacoes/<tipo>.svg`
(16 arquivos, um por tipo, com a fórmula no título) a partir do próprio `app.amc.transformacoes.transformar` —
não há desenho manual, se a fórmula mudar o gráfico muda ao rodar de novo.

### 22.3 Pré-visualização

`app.amc.transformacoes.pre_visualizar(valores, transformacao)` devolve histograma de entrada, histograma de
saída, contagem de nulos e o tempo gasto — portão de pronto: ≤ 300 ms para 100 mil valores (medido:
`tests/unit/test_amc_transformacoes_desempenho.py`, ~20-35 ms conforme o tipo, sem banco).

### 22.4 O que reproduz do motor logístico real (CBRE) — e o que não reproduz

Os fatores do motor territorial do projeto CBRE (`cbre.hex_fav`, outro projeto, lido só leitura) que eram
uma transformação declarativa de UMA coluna bruta E cuja coluna bate com a favorabilidade oficial reproduzem
a ≤ 0,5 em 100 % das células: `decl` (declividade, `linear`), `rod` (distância a rodovia, `linear` com
`saida_min`/`saida_max`), `agua` (faixa de 30 m, `categoria`), `press` (pressão urbana, `linear`) — provado em
`tests/unit/test_amc_transformacoes_cbre.py`. Dos 19 fatores que o motor tinha em 29/08/2026, os outros 15
ficam de fora, cada um com o motivo medido e nomeado no próprio teste e em
`tests/medidas/L3-01-d-transformacoes.json` — a maioria combina várias colunas/veto/bônus antes de virar
nota (fora do escopo de uma biblioteca de transformação), e dois (`gru`, `se`) têm coluna candidata com a
forma certa mas divergência real medida (3,90 % e 80,1 % das células, respectivamente) que sugere que a
coluna gravada não é a mesma que o pipeline daquele fator usa — apurar isso é trabalho do projeto CBRE, não
deste item.

### 22.5 Limites desta fatia

`faixas` por quantil/intervalo igual/quebras naturais e `ms_grande`/`ms_pequena` sem `media`/`desvio`
gravados só funcionam com uma amostra em mãos (resolvidos em Python antes de qualquer SQL — ver ADR); a
biblioteca não tem UI de pré-visualização no navegador ainda (só a função Python/o histograma; a tela fica
para outro item). Ver `laco/handoffs/T3/L3-01-d-transformacoes.md`.
