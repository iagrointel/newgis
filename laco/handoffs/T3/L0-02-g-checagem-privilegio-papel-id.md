# L0-02-g-checagem-privilegio-papel-id — handoff (trilha `valida`, ramo `wt/valida`)

Papéis: backend, adversario. Base de teste PRÓPRIA (`trilha_ambiente.sh t02g`, schema `plat_tt02g`), nunca a
suíte contra o schema `plat` de produção. O schema de trilha foi APAGADO no fim (comando no rodapé).

## 1. O que se afirmava e o que se mediu

A hipótese do adversário irmão (T3) era: atribuir `papel_id` não confere se o ATOR pode conceder aqueles
privilégios. **Confirmada**, com uma correção de redação: o ator não é um "editor". `membros.gerir` e
`membros.papel` só existem no teto do perfil `admin` (`plat.perfil_privilegio`), então um editor toma 403
`sem_privilegio` antes de chegar à conferência. O ator real é o **administrador restrito por papel
personalizado** — e o buraco é maior do que a hipótese dizia, porque o papel é uma RESTRIÇÃO
(`plat.privilegios_de` = teto do perfil ∩ papel). Quatro caminhos, todos medidos abertos antes da correção:

1. atribuir a outro um papel personalizado mais amplo que o seu;
2. atribuir `papel_id` nulo a outro — devolve o teto inteiro do perfil;
3. atribuir `papel_id` nulo **a si mesmo** (auto-promoção);
4. promover um editor a admin com papel nulo — concede o mesmo conjunto pelo caminho do perfil;
   e os quatro em massa por `POST /api/usuarios/lote`, que passa pelo mesmo `_editar`.

## 2. O que foi construído

| arquivo | o quê |
|---|---|
| `app/auth/rotas_usuarios.py` | `_privilegios_concedidos` + `_nao_conceder_alem_do_proprio`, chamadas em `criar_usuario` e em `_editar` (que serve PUT e lote) |
| `docs/adr/0016-nao-conceder-privilegio-que-nao-se-tem.md` | decisão, alternativas e o que ela NÃO resolve |
| `tests/api/test_privilegio_escalonamento.py` | 10 casos: 6 de escalonamento, 2 de não-regressão, 1 da cláusula literal do editor, 1 de refutação completa |
| `tests/api/test_privilegio_cobrado.py` | varredura das 138 rotas do OpenAPI em duas camadas |
| `app/schema_ambiente.py` | `executemany` e `mogrify` também reescrevem o schema |
| `tests/conftest.py` | `conexao_plat_app` passa a usar `CursorSchemaAmbiente` |
| `tests/unit/test_schema_ambiente_metodos.py` | guarda: método de cursor usado em `app/` sem sobrescrita reprova |
| `tests/medidas/L0-02-g-checagem-privilegio-papel-id.json` | 9 medidas |

O conjunto do ator é lido do BANCO, com a mesma consulta de `plat.privilegios_de`, não da lista em Python de
`app/auth/privilegios.py` — manter duas verdades sobre o teto de cada perfil seria criar a próxima brecha.

## 3. Portão de pronto, cláusula por cláusula

**Cláusula 1** — "toda rota que atribui papel_id (POST e PUT /api/usuarios) confere que o ator possui TODOS os
privilégios do papel que está concedendo (nunca conceder privilégio que o próprio ator não tem)".

PASSA. Prova: `venv/bin/pytest tests/api/test_privilegio_escalonamento.py` → **10 passed**. Casos:
`test_ator_restrito_nao_cria_usuario_com_papel_mais_amplo` (403 `privilegio_proprio_insuficiente`, detalhe
`["org.integracoes"]`), `..._nao_cria_administrador_sem_papel`, `..._nao_atribui_papel_mais_amplo_em_edicao`,
`..._nao_tira_o_proprio_papel`, `..._nao_promove_editor_a_administrador_sem_papel`, `..._nao_escapa_pelo_lote`
(0 alterados, recusa com o mesmo erro). Cobre POST, PUT e o lote, que o portão não citava e é a mesma porta.
Contraprova de que os testes mordem: apagando as duas linhas de chamada de `_nao_conceder_alem_do_proprio`,
**7 dos 10 casos reprovam** (rodado e conferido antes de comitar).

**Cláusula 2** — "teste que um editor tenta atribuir papel com privilégio administrativo a outro usuário e
recebe 403".

PASSA na letra, com ressalva registrada no próprio teste: `test_editor_nao_atribui_papel_administrativo` recebe
403 em POST (`exigido: membros.gerir`) e em PUT (`exigido: membros.papel`), mas esse 403 vem do PORTÃO DE
PRIVILÉGIO, não da conferência nova — um editor não consegue chegar até ela em nenhuma configuração, porque
`membros.*` administrativo não existe no teto do perfil editor. Quem exercita a conferência nova é o
administrador restrito. **Não considere a cláusula 2 como prova da correção**; a prova é a cláusula 1.

**Refutação exigida** — "adversário cria um segundo papel personalizado com 1 privilégio a mais que o do ator e
tenta atribuir; qualquer sucesso = refutado".

Rodada na forma COMPLETA, não em um caso: para **cada um dos 47 privilégios** do vocabulário, o papel do ator
vira "todos menos ele" e o papel oferecido vira "todos" — exatamente um privilégio a mais. **94 chamadas (POST e
PUT), 94 respostas 403, nenhuma 2xx.** 92 pela conferência nova (`privilegio_proprio_insuficiente`) e 2 por
`sem_privilegio`, que são exatamente os dois casos em que o privilégio retirado do ator era `membros.gerir` (o
POST) ou `membros.papel` (o PUT). Medidas `refutacao_*` no JSON. **Não refutado.**

## 3.1 Regressão

`pytest` com os 11 arquivos de teste que tocam identidade/acesso mais `tests/unit` inteiro, na base própria da
trilha: **809 casos coletados, 1 falha e 3 erros, todos PRÉ-EXISTENTES e reproduzidos com os meus três arquivos
revertidos para `615b75e~1`**:

- `tests/unit/test_raster_validacao_adversario.py::test_medida_de_ram_e_tempo_confere_com_o_arquivo_de_medidas`
  — compara RAM medida agora com `tests/medidas/L1-01-b.json`; a máquina está com outras três trilhas rodando
  suíte ao mesmo tempo e o pico deu 91.636 kB contra 159.664 kB gravados. É teste do item L1-01-b, não deste.
- `test_settings.py::test_rebaixa_debug_em_producao`, `test_politica.py::...`, `test_where_ast.py::...` —
  `ErroConfiguracao: chave obrigatória ausente: PLAT_SECRET`. Esses casos limpam o cache de `settings` e
  assumem que `PLAT_SECRET` está no `.env`; na trilha ele vem do ambiente. Também é de máquina, não de código.

⚠ Aviso ao gerente: `tests/medidas/L1-01-b.json` é REESCRITO por essa suíte de raster a cada rodada. Reverti o
arquivo (`git checkout -- tests/medidas/L1-01-b.json`) para não levar medida de máquina carregada para o ramo.
Vale conferir antes de qualquer merge que envolva a trilha de raster.

⚠ Duas rodadas de `pytest` ao MESMO TEMPO na mesma base de trilha se destroem: `limpeza_de_residuos` (fixture de
sessão) apaga os `zt-*` e `zt-inq-*` da outra rodada e produz uma cascata de erros que parece regressão e não é.
Uma rodada por trilha de cada vez.

## 4. Varredura do OpenAPI, rota por rota (pedido do gerente)

138 rotas de `docs/openapi.json`, duas camadas.

Camada estática: lê o fecho (closure) da dependência `autenticado(...)` de cada rota viva e compara com
`x-privilegio`. **41** cobram na dependência exatamente o privilégio nomeado que declaram; **72** declaram valor
especial (`proprio`, `vocabulario`, `rls:visibilidade`, `grupo:*`, `token:*`) ou alternativa e cobram no corpo;
**8** cobram na dependência um privilégio que a declaração não menciona.

Camada dinâmica: administrador de um inquilino DESCARTÁVEL recebe papel com todos os privilégios menos um; as
**41** rotas de privilégio nomeado único respondem **403 `sem_privilegio` com `exigido` igual ao declarado**.
Controle positivo: com o papel completo, nenhuma das 41 responde `sem_privilegio`.

### 4.1 As 8 divergências encontradas — para o dono de cada rota, não são deste item

Todas APERTAM o acesso (exigem mais do que a documentação promete), logo não são falha de segurança; são
declaração incompleta. Estão CONGELADAS em `DIVERGENCIAS_CONHECIDAS` no teste — divergência nova reprova.

| rota | declara | cobra na dependência |
|---|---|---|
| `GET /api/tokens/{id}` | `token:dono\|tokens.gerir_todos` | `tokens.gerar` |
| `GET /api/tokens/{id}/log` | `token:dono\|tokens.gerir_todos` | `tokens.gerar` |
| `DELETE /api/tokens/{id}` | `token:dono\|tokens.gerir_todos` | `tokens.gerar` |
| `POST /api/tokens/{id}/renovar` | `token:dono` | `tokens.gerar` |
| `POST /api/acervo/{fonte_id}/adicionar` | `conteudo.criar\|conteudo.registrar_fonte` | `conteudo.criar` (a alternativa não vale: só `conteudo.registrar_fonte` não passa) |
| `POST /api/itens/{id}/miniatura/gerar` | `rls:visibilidade\|conteudo.editar_tudo` | `jobs.executar` |
| `POST /api/lixeira/esvaziar` | `rls:visibilidade\|conteudo.apagar_tudo` | `jobs.executar` |
| `POST /api/logout` | `proprio` | sem dependência `autenticado()` (correto: sair não pode depender de privilégio) |

Consequência prática: um papel personalizado sem `tokens.gerar` bloqueia o dono de VER e REVOGAR os próprios
tokens, coisa que a documentação promete a quem é dono. Quem mexer em `app/auth/rotas_tokens.py` decide se
conserta a declaração ou a cobrança.

## 5. Fronteira honesta — o que NÃO foi provado

- **31 rotas** de privilégio alternativo cobrado DEPOIS de carregar o recurso (conteúdo, grupos, tokens) ficam
  fora do alcance deste item: sem o recurso à mão a chamada responde 404 antes do 403, e montar o recurso de
  cada uma é o trabalho dos itens L0-03/L0-07. Está na medida `rotas_alternativas_nao_provadas`. As duas de
  `/api/usuarios` (`PUT /api/usuarios/{id}`, `POST /api/usuarios/lote`), que são as deste item, foram provadas.
- A camada estática não prova onde a cobrança acontece quando ela está no corpo — só que a dependência não
  cobra outra coisa por conta própria. Para essas 72 rotas a única prova é chamada real, e a chamada real deste
  item cobre 41 + 2.
- O provisionamento por LDAP (migração 025) insere usuário com `papel_id` nulo, mas define o PERFIL dentro do
  banco, a partir do mapeamento de grupo, sem passar por estas rotas. A conferência não é chamada lá. Quem
  edita o mapeamento precisa de `org.integracoes`; é a superfície que sobra, registrada no ADR 0016.
- `tests/api/test_docs.py` e `test_versionamento.py` não foram alterados; se outra trilha regerar
  `docs/openapi.json` com rota nova, a varredura passa a cobrir a rota nova sozinha (ela lê o arquivo).

## 6. Defeito de máquina corrigido no caminho (era bloqueio, não escolha)

`CursorSchemaAmbiente` sobrescrevia `execute` e `callproc`, mas **não `executemany`**. O INSERT em lote de
`plat.papel_privilegio` (`criar_papel`/`editar_papel`) ia ao servidor com o literal `plat.`, e todo ambiente
fora do schema de produção (homologação do item L7-31, e a base de trilha deste turno) respondia
InsufficientPrivilege, que `erro_do_banco` traduz para 403 "operação fora do inquilino da sessão". É exatamente
o sintoma que o adversário `ataque-g4-ADVERSARIO.md` (linha 278) reportou como "o servidor afirma sobre o
inquilino um fato que não mediu" — a causa raiz era esta. Sem o conserto, NENHUM teste de papel roda fora de
produção, e este item seria impossível de provar. `mogrify` recebeu a mesma sobrescrita, e
`tests/unit/test_schema_ambiente_metodos.py` varre `app/` atrás de método de cursor usado sem sobrescrita.
`conexao_plat_app` (tests/conftest.py) passou a usar o mesmo cursor, senão todo teste que escreve `plat.` na mão
falha fora de produção. Produção não muda: a reescrita é no-op quando o schema já é o padrão.

## 6.1 O que ficou aberto na mesma máquina (achado, não consertado)

A suíte INTEIRA continua sem rodar fora do schema `plat`, por causa da mesma família de defeito, em **9 lugares
de teste** que abrem conexão própria com `psycopg2.extras.RealDictCursor` em vez do cursor que reescreve o
schema: `tests/jobs_sessao.py:76`, `tests/api/test_acervo.py:14` e `:47`, `tests/api/catalogo/conftest.py:67`,
`tests/api/semear_catalogo.py:75` e `:107`, `tests/api/jobs/test_jobs_periodicos.py:86` e `:118`,
`tests/api/jobs/test_jobs_transicoes.py:75`. Sintoma: `permission denied for schema plat` em
`plat.auth_login(...)`. É de uma linha cada (trocar `cursor_factory`), mas são arquivos de outros itens (L0-03,
L0-05, L6-01) e fora da concessão desta trilha, então NÃO foram tocados. Sugestão ao gerente: item próprio de
uma sessão curta, com ganho grande — sem ele, homologação e trilha nunca rodam a suíte completa, e um defeito
como o do `executemany` volta a passar despercebido.

## 7. Como o adversário reproduz

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh t02g
set -a; source /home/dev/plataforma/laco/var/trilha/t02g.env; set +a
cd /home/dev/plataforma/wt/valida
venv/bin/pytest tests/api/test_privilegio_escalonamento.py tests/api/test_privilegio_cobrado.py -q   # 14 passed
venv/bin/pytest tests/unit/test_schema_ambiente_metodos.py tests/api/test_usuarios.py -q             # 10 passed
venv/bin/ruff check app tests docs/gerar_limites.py && make sem-marcador
# contraprova (o teste morde?): apagar as 2 linhas `_nao_conceder_alem_do_proprio(` de
# app/auth/rotas_usuarios.py e rodar de novo → 7 dos 10 casos de escalonamento reprovam
```

Ataque sugerido a quem for refutar: procurar uma QUINTA porta para (perfil, papel_id) que não passe por
`criar_usuario` nem por `_editar` — convite, importação LDAP, restauração de backup, `plataforma/inquilinos`.
`grep -rn "papel_id" app/` hoje devolve escrita só em `app/auth/rotas_usuarios.py` (linhas 104 e 349).

## 8. Commits do ramo `wt/valida`

- `615b75e` Reescrita de schema também em executemany e no cursor do teste
- `6ad841b` Ninguém concede privilégio que não tem ao atribuir papel a usuário
- `ca860b7` Varredura de privilégio rota por rota: o declarado é o cobrado

## 9. Risco de merge

`app/auth/rotas_usuarios.py` (três trechos localizados: duas chamadas de uma linha e um bloco de duas funções
novas), `CHANGELOG.md` (entrada nova no topo do turno 3), `tests/conftest.py` (uma linha, o cursor),
`app/schema_ambiente.py` (dois métodos novos na classe). Os quatro arquivos de teste e o ADR 0016 são novos.
Nenhuma migração foi criada — o item não precisou de mudança de esquema.
