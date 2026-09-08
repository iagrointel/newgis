# Handoff — item L0-07-b-papeis-privilegios (papéis esri+backend+frontend+testador+adversário, sessão única)

**Veredito: ENTREGUE.** Todas as cláusulas do portão de pronto e todas as do vetor de refutação estão cobertas
por teste automatizado que passou nesta sessão (evidência literal abaixo). Sem subagentes: o item, apesar de
tamanho `G`, já tinha o grosso construído por trilhas anteriores do L0-02 (vocabulário, papéis personalizados,
tela `/admin/papeis`) — o trabalho real deste turno foi fechar as 5 lacunas nomeadas no portão que ainda faltavam,
o que coube numa sessão jogando os papéis pedidos sequencialmente.

## 0. Ponto de partida (confira antes de reconstruir)

Achado logo no início: a migração 003 (`db/migracoes/003_identidade_acesso.sql`) já semeia `plat.privilegio`
(47 nomes), `plat.perfil_privilegio` (teto dos 4 perfis) e `plat.papel_personalizado`/`plat.papel_privilegio`
(papel por inquilino); `app/auth/rotas_usuarios.py` já tem o CRUD completo de `/api/papeis` com
`_papel_compativel` (422 `papel_incompativel`), `_validar_papel` (422 `privilegio_fora_do_teto`, 403
`privilegio_proprio_insuficiente`), `409 papel_em_uso`; `web/admin/papeis.html` + `web/js/auth/papeis.js` já
existem; `tests/api/test_privilegios_declarados.py` já provava que toda rota do OpenAPI declara `x-auth`/
`x-privilegio` e que o vocabulário Python bate com o banco; `tests/e2e/test_papeis.py::test_papel_criar_editar_apagar`
já existia. Isso é herança do ADR 0002 (item L0-02-tenant-auth, trilha A, T2) — **não reconstruído**, só
estendido. `git log --oneline -- app/auth/rotas_usuarios.py` mostra a linha do tempo real.

## 1. O que fechei (mapeado cláusula a cláusula do portão)

| cláusula do portão | estado ao começar | o que fiz |
|---|---|---|
| `docs/PRIVILEGIOS.md` gerado do banco | não existia | `docs/gerar_privilegios.py` conecta em `PLAT_DSN` (role `plat_app`, sem contexto de inquilino — `privilegio`/`perfil_privilegio` são globais, sem RLS) e escreve o arquivo; `tests/api/test_privilegios_doc.py` prova que o comitado bate com o banco agora, mesmo padrão de `docs/gerar_limites.py`/`LIMITES.md`. `make privilegios` gera. |
| teste que percorre toda rota do OpenAPI e exige privilégio declarado | parcial (só a DECLARAÇÃO era testada) | `tests/api/test_privilegios_matriz.py`: para cada rota cujo `x-privilegio` é um nome puro do vocabulário (ou composição `a\|b`), monta dois clientes fixos (um só com `tokens.gerar`, outro só com `membros.ver` — interseção perfil×papel do ADR 0002 seção 3.2 faz o resto do vocabulário faltar a um dos dois) e chama a rota com o corpo dummy construído do próprio esquema OpenAPI; exige `403` em todas (~40 rotas testadas). Rotas com mecanismo especial (`grupo:*`, `token:*`, `rls:*`, `proprio`, `publico`, `vocabulario`, `superadmin`) ficam fora do escopo — são ownership/escopo de token, não o vocabulário fechado, e já são cobertas pelas suítes do próprio domínio (`test_grupos.py`, `test_tokens.py` etc.). |
| e2e "Curador" (categoriza mas não publica), com captura | não existia | `tests/e2e/test_papeis.py::test_papel_curador_categoriza_mas_nao_publica`. Nome real do privilégio de categorias é `conteudo.categorias` (não `categorias.gerir` — o nome do rascunho do concept virou este na migração 003; `conteudo.categorias` é **administrativo**, então o papel só cabe em perfil `admin`). Fluxo: admin cria o papel pela tela → cria o usuário (perfil admin, papel Curador) pela tela → troca de sessão para o Curador → `PUT /api/categorias` com a árvore existente sem alteração (200 — categoriza, sem mexer nas categorias reais do inquilino demo) → `POST /api/itens` tipo `camada_vetorial` (403 `sem_privilegio`, exigido `conteudo.publicar_camada` — não publica) → `POST /api/itens` tipo `mapa` (201 — continua criando conteúdo comum). Captura `tests/e2e/capturas/L0-02-tenant-auth_papel_curador.png` (nome fixo por convenção de `tests/e2e/apoio.py`, compartilhado por todo e2e do L0-02/L0-07 — não é meu de propósito, é como o arquivo já funciona). |
| rebaixar tipo de usuário com conteúdo é recusado | **FALTAVA — gap real, não só de teste** | `_editar` (`app/auth/rotas_usuarios.py`) só recusava rebaixamento por grupos (`409 possui_grupos`); a regra Esri (E12-members) é "não possui conteúdo NEM grupos". Corrigido: mesma checagem que `apagar_usuario` já fazia (`_itens_do_dono`), agora também no downgrade de perfil, com `409 possui_itens`. `tests/api/test_usuarios.py::test_rebaixar_perfil_com_itens_e_recusado` prova a recusa, que SUBIR de perfil não esbarra na regra (só descer), e que a purga física do item destrava o rebaixamento. Frontend (`web/js/auth/usuarios.js`) ganhou o mesmo tratamento de mensagem que `possui_grupos` já tinha. ADR 0002 (seção 15.3, tabela de contrato) documenta o novo `409`. |
| paridade linha a linha contra "Privileges for roles" 11.4 | parcial (fonte já extraída em `laco/handoffs/T1/21_esri.md`, nunca tabulada linha a linha) | Nova seção em `docs/PARIDADE.md` ("Privilégios e papéis personalizados"): 43 privilégios gerais + 33 administrativos = **76 linhas**, cada uma com o nosso privilégio equivalente (ou `—`) e estado `feito`/`parcial`/`fora`. Contagem conferida programaticamente linha a linha (não de cabeça) antes de publicar: **35 feito · 11 parcial · 30 fora** (46,1%/14,5%/39,5%). Nenhum `fora` é lacuna nova — todos já são decisão de escopo nomeada em outro lugar (D5/D16 sem assento/licença, roadmap L2/L5 sem notebook/3D/OAuth app/pipeline/versionamento/colaboração entre orgs, L0-07-e sem relatório de uso). |

## 2. Refutação (papel adversário, rigor total, feito por mim mesmo ao final)

| ataque pedido | resultado | evidência |
|---|---|---|
| criar papel com privilégio administrativo para tipo `visualizador` → 422 | **PASSA** | `tests/api/test_usuarios.py::test_so_admin_cria_altera_e_apaga_admin` — acrescentei a checagem literal (o teste já provava para `editor`; adicionei a chamada explícita com `perfil: visualizador`, mesmo papel administrativo, mesmo `422 papel_incompativel`). Mecanismo é perfil-agnóstico (`priv.ORDEM_PERFIL[perfil] < priv.ORDEM_PERFIL[papel_minimo]`), não há como um perfil menor escapar. |
| editor se dá `papeis.gerir` → 403 | **PASSA** | Duplamente coberto: (a) editor não tem `papeis.gerir` — `POST /api/papeis` nem entra na função (`autenticado("papeis.gerir")` nega na dependência); (b) admin restrito a `{membros.ver, papeis.gerir}` por papel tenta conceder `org.log_ver`, que não tem → `403 privilegio_proprio_insuficiente` (`test_privilegios_e_papeis`, já existia, cobre a intenção mais afiada do ataque: "conceder o que não se tem", não só "não ter o privilégio de gerir papel"). |
| apagar papel em uso → 409 | **PASSA** | `test_privilegios_e_papeis`, `test_so_admin_cria_altera_e_apaga_admin` — `409 papel_em_uso` com a contagem de usuários no `detalhe`. |
| chamar cada rota do OpenAPI com usuário sem o privilégio declarado → 403 em todas | **PASSA** | `tests/api/test_privilegios_matriz.py` — ver seção 1. Achado NO CAMINHO (documentado no próprio teste): duas rotas checam o privilégio DEPOIS de carregar o recurso (`PUT /api/usuarios/{id}`, `PUT /api/itens/{id}/compartilhamento`), então um id inexistente devolvia 404 antes da checagem rodar — não prova nem desprova o gate. A primeira ganhou um id de usuário real (`ids_reais` fixture) e passou a testar certo; a segunda tem um mecanismo genuinamente diferente (checa DONO do item antes de checar `compartilhar.*` — quem não é dono nem vê o item, então nunca alcança o privilégio de compartilhamento) e ganhou teste PRÓPRIO (`test_compartilhamento_exige_privilegio_mesmo_sendo_dono`) provando o gate real com o dono do item. |

Nenhuma reprovação nova além da já corrigida (`possui_itens`). Não achei escalada de privilégio nem bypass de
RLS nas rotas tocadas.

## 3. Evidência literal (comandos + saída)

Todos os comandos rodaram dentro de `flock /home/dev/plataforma/laco/.pytest.lock`, exceto onde note o contrário
(a árvore está compartilhada com outra sessão supervisora rodando várias trilhas em paralelo; a fila do lock
ficou congestionada perto do fim do turno — ver seção 5).

```
$ venv/bin/python docs/gerar_privilegios.py
escrito: /home/dev/plataforma/enterprise/docs/PRIVILEGIOS.md
# 47 privilégios, 12 grupos, 20 administrativos (visualizador 8 / campo 12 / editor 27 / admin 47)

$ flock .../.pytest.lock venv/bin/pytest tests/api/test_privilegios_doc.py -q
.                                                                        [100%]

$ flock .../.pytest.lock venv/bin/pytest tests/api/test_privilegios_matriz.py -q
..                                                                       [100%]
# rodado 3x seguidas sem falha (isolamento por papel/usuário próprio, sufixo aleatório, limpeza em finally)

$ flock .../.pytest.lock venv/bin/pytest tests/api/test_usuarios.py -q
...........                                                             [100%]
# 11 testes, incluindo test_rebaixar_perfil_com_itens_e_recusado (novo)

$ flock .../.pytest.lock venv/bin/pytest tests/e2e/test_papeis.py -m lento --base-url https://plat.iagrointel.com -q
..                                                                       [100%]
# test_papel_criar_editar_apagar (já existia) + test_papel_curador_categoriza_mas_nao_publica (novo)
# captura tests/e2e/capturas/L0-02-tenant-auth_papel_curador.png (73.825 bytes, conferida visualmente)

$ venv/bin/ruff check app/auth/rotas_usuarios.py app/auth/privilegios.py app/auth/sessao.py \
    tests/api/test_privilegios_matriz.py tests/api/test_privilegios_doc.py \
    tests/api/test_privilegios_declarados.py tests/api/test_usuarios.py tests/e2e/test_papeis.py \
    docs/gerar_privilegios.py
All checks passed!

$ ! grep -rnI ... -f tests/marcadores.regex app web db docs deploy install.sh Makefile ... *.md
# 1 achado, PRÉ-EXISTENTE e alheio (app/settings.py:69, "TODOS" casa o regex de TODO; não é meu arquivo)
```

Verificação manual em banco (adversário confere o que o teste afirma): `sudo -u postgres psql -d iagro_sat`
— `SELECT count(*) FROM plat.privilegio` = 47; nenhum papel/usuário `zt-*` de teste ficou órfão depois das
rodadas (checado por `SELECT ... WHERE nome LIKE 'zt-%'` antes de fechar).

## 4. Achado ambiental resolvido no caminho (não é do item, registrado por transparência)

TOTP do superadmin `plataforma` estava dessincronizado (mesmo fenômeno já documentado em
`reference_laco-revisao-armadilhas` da memória — corrida entre trilhas ligando 2FA quase ao mesmo tempo,
`tests/credenciais_totp.txt` compartilhado). Contornado como a skill manda: resetei `totp_secret`/`totp_ativo`
do usuário `id=3` (`plataforma`/`admin`) via `sudo -u postgres psql` (mesmo UPDATE que `install.sh` faz a cada
instalação) e apaguei o arquivo stale — a suíte reconfigura 2FA sozinha no próximo login (código já escrito para
isso em `tests/api/conftest.py::sessao_plat`). Não travei nisso; registrado aqui para quem vir o mesmo sintoma.

## 5. Colisão de árvore compartilhada (transparência, sem dano ao produto)

Durante a sessão, outro agente concorrente tinha `MANUAL.md` e `docs/PARIDADE.md` **staged no índice
compartilhado** (seção "Geocodificador", item L2-11-b) no exato momento em que eu editei esses mesmos arquivos
(sem `git add` ainda). Quando esse outro agente rodou `git commit -- MANUAL.md docs/PARIDADE.md ...`, o
pathspec-scoped commit pegou o CONTEÚDO DA ÁRVORE DE TRABALHO inteiro daqueles arquivos — que incluía meu texto
não-commitado por cima do deles — e tudo foi para o commit `3a69591` ("Geocodificador próprio sobre CNEFE
2022"), não para um commit meu. **Nenhum conteúdo foi perdido** (conferido: `git show 3a69591 -- MANUAL.md`
contém minha seção 6 atualizada e a seção do Curador; `git show 3a69591 -- docs/PARIDADE.md` contém minha seção
de paridade inteira) — só a autoria do commit ficou errada. Não desfiz isso (`reset`/`rebase` num commit que já
pode ter trabalho de outra sessão em cima seria a operação destrutiva que a skill proíbe); registrado aqui para
quem ler o `git log` e estranhar não ver "MANUAL.md"/"PARIDADE.md" nos meus 5 commits. Lição para a skill: um
pathspec-scoped commit NÃO é suficiente quando o próprio arquivo tem hunks de outro agente misturados no
working tree — precisa `git add -p`/checagem de `git status` (`MM` = staged E unstaged) antes, não só depois.
Reforcei isso checando `git diff --stat`/`git diff --cached --stat` de cada arquivo antes de cada commit desta
sessão (por isso os outros 5 commits saíram limpos, um hunk por arquivo).

## 6. Commits (todos em `/home/dev/plataforma/enterprise`, pathspec-escopados)

| sha | mensagem | arquivos |
|---|---|---|
| `2520afd` | Tabela de privilégios gerada do banco e teste que percorre toda rota do OpenAPI sem privilégio declarado | `docs/PRIVILEGIOS.md`, `docs/gerar_privilegios.py`, `tests/api/test_privilegios_doc.py`, `tests/api/test_privilegios_matriz.py` |
| `1b0ad94` | Rebaixar perfil de usuário com itens do catálogo passa a ser recusado (409 possui_itens) | `app/auth/rotas_usuarios.py`, `tests/api/test_usuarios.py`, `web/js/auth/usuarios.js`, `docs/adr/0002-identidade-e-acesso.md` |
| `90ab545` | E2e do papel Curador: categoriza mas não publica; alvo docs/PRIVILEGIOS.md no make | `tests/e2e/test_papeis.py`, `Makefile` |
| `a755cb7` | CHANGELOG do item L0-07-b-papeis-privilegios | `CHANGELOG.md` |
| `6f79901` | Prova explícita: papel administrativo atribuído a perfil visualizador também é 422 | `tests/api/test_usuarios.py` |
| (absorvido em `3a69591`, ver seção 5) | seção 6 do MANUAL + seção "Privilégios e papéis personalizados" do PARIDADE | `MANUAL.md`, `docs/PARIDADE.md` |

`laco/estado.json` atualizado sob `flock .../.estado.lock`: item → `entregue`, ledger com a nota completa,
placar `entregues` 40 → 41.

## 7. O que ficou pendente (nomeado, não forçado)

- **Nenhuma cláusula do portão ficou pendente.** As 5 do enunciado e as 4 do vetor de refutação passaram.
- Qualidade menor, não bloqueante: a mensagem de erro do frontend para `possui_itens` no formulário de EDIÇÃO
  de usuário (`web/js/auth/usuarios.js`) lista só os títulos dos itens, sem link para abri-los — mesma limitação
  que `possui_grupos` já tinha antes deste item; não é regressão, é o padrão existente.
- A fila do `flock /home/dev/plataforma/laco/.pytest.lock` ficou congestionada por ~20 minutos perto do fim do
  turno (outra sessão supervisora rodando `pytest -m "not lento"` completo + 3-4 outras invocações simultâneas
  de outras trilhas, 10 processos vivos disputando o mesmo mutex). A rodada que eu tinha deixado enfileirada
  (`tests/api/test_privilegios_matriz.py tests/api/test_privilegios_doc.py tests/api/test_privilegios_declarados.py
  tests/api/test_usuarios.py`) terminou depois que este handoff já estava escrito: **17 testes, 100% passou,
  exit code 0** — inclui `test_so_admin_cria_altera_e_apaga_admin` com a linha nova de `visualizador` (commit
  `6f79901`). Fecha a única lacuna formal que tinha ficado nomeada: não sobrou nenhuma cláusula sem saída de
  pytest literal.

## 8. Papéis jogados nesta sessão (sem subagentes — item coube numa sessão)

- **esri**: extraí a lista completa de privilégios gerais/administrativos de `laco/handoffs/T1/21_esri.md`
  §1.3 (já pesquisada e testada por HTTP em T1) e tabulei linha a linha contra o nosso vocabulário.
- **backend**: `docs/gerar_privilegios.py`, fix de `_editar` (possui_itens), matriz de rotas.
- **frontend**: mensagem de erro `possui_itens` em `usuarios.js` (reuso do padrão de `possui_grupos`).
- **testador**: os 3 arquivos de teste novos/estendidos, rodados de verdade (não só escritos).
- **adversário**: seção 2 desta nota, incluindo a correção que ele mesmo achou (possui_itens) antes de eu
  escrever o restante do trabalho — ordem real: escrevi a matriz de rotas primeiro, ela não pega esse tipo de
  bug de regra de negócio (só privilégio ausente), então fui ler `_editar` de propósito procurando exatamente
  este padrão (mesma classe do bug de escalada que o adversário de T3 já achou em `criar_usuario`) e achei.
