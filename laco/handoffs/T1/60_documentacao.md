# T1 · 60_documentacao — cronista · item L0-01-repo

## Objetivo

Fechar a cláusula "git com README/ARQUITETURA/MANUAL/CHANGELOG" do portão próprio e o portão P9
(documentado no mesmo turno): escrever, no repositório, `ARQUITETURA.md`, `MANUAL.md`, `CHANGELOG.md` e
`README.md` para o que EXISTE em 0.1.0, sem nome de cliente/parceiro/piloto, sem marcador de pendência,
com número só de `tests/medidas/L0-01-repo.json` e o comando que o gerou; e criar o painel do laço
(`laco/PAINEL.md`) gerado por script (`laco/gera_painel.py`) a partir de `laco/estado.json`.

## O que fiz

1. Li a skill, o `estado.json` (57 itens), os handoffs 00/20/30/40 e `refutacao.json`, o repositório
   inteiro (ADR, `install.sh`, `app/`, `db/`, `deploy/`, `web/`, `tests/`), o `/saude` ao vivo, a
   captura do e2e (`tests/e2e/capturas/L0-01-repo_inicio.png`, lida a olho: versão 0.1.0, git
   `3b53c24e4c12`, ambiente producao, saúde ok, sem botão) e a tabela `plat.versao_migracao`.
2. `ARQUITETURA.md` (13 seções): componentes e portas (api 8150; 8151/8152/8153 reservadas e
   **inexistentes**, dito com essas palavras), repositório, schema `plat` (6 tabelas, RLS, 11 funções
   com o que devolvem, contexto por inquilino, pool), migrações com sha256 (do `sha256sum` e da tabela,
   iguais), `install.sh` passo a passo (a-j) com como conferir, systemd, nginx (noindex em toda
   `location`, 11/11 rotas), contrato de `/saude` e `/api/versao`, `.env`, log JSON, venv e testes
   (58 coletados = 17 unit + 40 api + 1 e2e), medidas, front, convenções, correções em curso (seção 12)
   e "o que ainda não existe" (seção 13) apontando para `laco/PAINEL.md`.
3. `MANUAL.md`: "Acesso e saúde do serviço" (URL, captura referenciada, tabela campo a campo de
   `/saude`, como ler `versao`/`git_sha`/migrações, 200 × 503, conferência por linha de comando) e
   "Instalação e atualização" (comando, o que cria, como conferir, atualizar, limites conhecidos).
4. `CHANGELOG.md`: entrada 0.1.0 (turno 1) com o que entrou, tabela de 14 medições com comando,
   veredito do adversário (PARCIAL) com as cláusulas derrubadas, correções em curso e os 6 commits.
5. `README.md`: lista de arquivos ajustada ao que existe; nenhuma promessa.
6. `laco/gera_painel.py` + `laco/PAINEL.md` (232 linhas): placar por estado (lido do `estado.json`),
   placar por linha, "o que o produto faz hoje" (7 frases do L0-01, marcado `tentando; veredito
   pendente`), fronteira por linha (8 linhas, L0 a L7, com os ids não entregues), tabela dos 57 itens
   por linha (prioridade, estado, tentativas, turno, dependências abertas, bloqueio), D18-D21, medidas
   disponíveis, ledger (vazio), notas do estado. O script neutraliza nomes de cliente/parceiro que
   vêm do `estado.json` e para com código 2 se um item `entregue`/`parcial` não tiver frase em
   `FUNCOES` (obriga o cronista do turno a escrever a frase). Detecta se `99_veredito.md` existe.
7. `make check` sobre a árvore de trabalho antes do commit: verde (57 + 1). Commit `7092755` só dos
   quatro `.md` (`git commit --only`). Não toquei em `app/`, `db/`, `install.sh`, `tests/`.
8. Conferência independente do commit `7092755` em worktree isolado (apagado depois): ruff ok,
   `sem-marcador` ok, e2e 1 passed, rápidos 56 passed + 1 falha explicada em Riscos 1.

## Evidência (comando + saída literal)

```
$ python3 laco/gera_painel.py
/home/dev/plataforma/laco/PAINEL.md: 232 linhas · entregue 0 · parcial 0 · tentando 1 · refutado 0 · pendente 56

$ grep -nE 'TODO|FIXME|XXX|lorem ipsum|em breve|coming soon|placeholder|mock[A-Z_(]|not implemented|NotImplemented' \
    laco/PAINEL.md laco/gera_painel.py enterprise/README.md enterprise/ARQUITETURA.md enterprise/MANUAL.md enterprise/CHANGELOG.md
(nada)  rc=1
$ grep -nEi 'fgr|cbre|novaterra|certel|edp|sigcorp' <os mesmos 6 arquivos>
(nada)  rc=1

$ cd enterprise && /usr/bin/time -f "tempo_make_check_s=%e" make check      (árvore de trabalho, 13:05 UTC)
All checks passed!
! grep -rnI ... -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md
57 passed, 1 deselected, 1 warning in 1.09s
1 passed, 57 deselected in 0.57s
tempo_make_check_s=2.45
rc=0

$ git commit -q --only README.md ARQUITETURA.md MANUAL.md CHANGELOG.md -F -   (mensagem em português + rodapé)
$ git log --oneline -2
7092755 Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG e README descrevem o que existe em 0.1.0
3b53c24 P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1
$ git show --stat HEAD | tail -5
 ARQUITETURA.md | 476 +++  CHANGELOG.md | 80 +  MANUAL.md | 158 +  README.md | 56 +-   4 files changed, 754 insertions(+), 16 deletions(-)

$ git worktree add <scratchpad>/verif_head HEAD; (venv por symlink; .env exportado; PLAT_GIT_SHA=$(git rev-parse HEAD))
== HEAD 7092755ed25a
All checks passed!                      (ruff)
sem-marcador ok
FAILED tests/api/test_cabecalhos.py::test_noindex_em_toda_rota[/static/vendor/maplibre-gl.js]   (56 passed)
.   1 passed                             (e2e)
$ git worktree remove --force ...; git worktree prune

$ sha256sum db/migracoes/*.sql ; SELECT nome, sha256 FROM plat.versao_migracao
74fcdc90a28c470953f952b190168c75fe712dde78a09b0a5fbf32bbbbe4b3eb  001_fundacao   (iguais nos dois lados)
418736611e8a1256e95603b7cdf188a008d6da579606d778393e9450648ddce2  002_identidade
$ curl -sS https://plat.iagrointel.com/saude
{"versao":"0.1.0","git_sha":"3b53c24e4c12",...,"banco":"ok","migracoes_aplicadas":2,"migracoes_pendentes":0,...}
```

## Riscos

1. **Sessão concorrente na mesma árvore.** Enquanto eu escrevia, outra sessão (backend, corrigindo os
   achados do adversário) alterou sem commit: `install.sh`, `Makefile`, `requirements.txt`,
   `app/main.py`, `app/versao.py`, `deploy/*`, `web/index.html`, `web/vendor/*` (renomeados com
   versão no nome, Swagger 5.32.15 local, favicon), `tests/api/test_cabecalhos.py`,
   `tests/unit/test_versao.py` e quatro testes novos. Consequências: (a) a falha do worktree de HEAD
   em `/static/vendor/maplibre-gl.js` é porque o arquivo já foi renomeado no disco que o nginx serve
   (404 na URL antiga); não é defeito do commit `7092755` nem dos documentos; (b) no momento em que
   terminei, `make lint` na árvore de trabalho acusava 4 erros de ruff (ordem de importação) em
   arquivos de teste da outra sessão, ainda em edição; o `make check` que rodei antes do commit
   estava verde. O gerente tem de rodar `make check` de novo depois que a outra sessão comitar.
2. **Documentos descrevem `3b53c24`; a seção 12 de `ARQUITETURA.md` lista o que muda com o commit
   pendente.** Quando ele entrar, sete frases (listadas na tabela da seção 12) passam a valer e as
   seções 5, 6, 7, 8, 9, 10 e 13 precisam de um passe curto do cronista para incorporar o texto e
   apagar a seção 12 (ou o gerente faz o passe ao integrar). `CHANGELOG.md` e `MANUAL.md` 2.5 têm a
   mesma marcação "commit pendente".
3. `git_sha` de `/saude` ainda é `3b53c24e4c12` (o serviço não foi reiniciado após o meu commit;
   regra já documentada no MANUAL 1.2). O `install.sh` da outra sessão reinicia.
4. A captura do e2e é regravada a cada `make e2e` e está fora do git; o MANUAL referencia o caminho,
   não uma cópia versionada. Se um dia a captura precisar ser estável, o `.gitignore` muda.
5. `docs/PARIDADE.md` continua só com o cabeçalho; eu não o preenchi porque não há capacidade de
   usuário para comparar, e a paridade-alvo de L0-02/L0-03 está no `21_esri.md`. Escrevi isso no
   ARQUITETURA (seção 13) e no README, não na tabela.
6. `laco/PAINEL.md` mostra `L0-01-repo` como `tentando` porque é o que está no `estado.json`;
   depois do `99_veredito.md` e da atualização do estado, basta `python3 laco/gera_painel.py`.

## Pendências

- Gerente: comitar (ou descartar) as correções da outra sessão; rodar `make check` completo;
  reiniciar `plat-api`; depois um passe curto no ARQUITETURA/MANUAL/CHANGELOG para absorver a seção
  12 (as frases já estão escritas na tabela; é mover, não pesquisar).
- Gerente: escrever `99_veredito.md`, atualizar `estado.json` (estado do item, placar, ledger) e
  rodar `python3 laco/gera_painel.py` para o painel refletir o veredito.
- Próximo cronista: quando um item for `entregue` ou `parcial`, acrescentar as frases em `FUNCOES`
  do `gera_painel.py` (o script para com código 2 se faltar).
- `laco/README.md` diz "backlog de 38 itens"; o estado tem 57. Não editei (não é meu arquivo); fica
  para o gerente.

## Para o próximo papel (gerente)

1. Cláusula "git com README/ARQUITETURA/MANUAL/CHANGELOG": os quatro estão escritos e comitados em
   `7092755` (754 linhas inseridas), sem marcador de pendência, sem nome de cliente, com número só do
   JSON de medidas. P9 fechado para o commit `3b53c24`; para o commit pendente da outra sessão, ver
   Riscos 2.
2. `laco/PAINEL.md` existe e é gerado por `laco/gera_painel.py`; a URL interna, D18-D21, o placar
   (0 entregue · 0 parcial · 1 tentando · 0 refutado · 56 pendente de 57) e a fronteira por linha
   estão lá.
3. O que eu não pude fechar e que continua sendo cláusula aberta do portão: nada do lado da
   documentação; do lado do código, o veredito PARCIAL do adversário (dependências, senha no journal)
   é o que a outra sessão está corrigindo.
