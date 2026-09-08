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

### 18.3 Limites desta fatia

Sem tela em nenhum dos dois; `acervo_camada` ainda não tem rota HTTP própria (só a tabela); lista branca de
coluna do acervo é por nome, não por conteúdo (L6-01-f); os 15 conectores concretos (o que de fato busca e
traduz WMS/WFS/STAC/... para camada do mapa) são itens futuros, L6-02-b em diante.

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
