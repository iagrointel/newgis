# G5 — conserto do vazamento de credencial em redirecionamento (item L6-02-a-modelo-conexao-e-seguranca)

Ramo `wt/cred` (worktree `/home/dev/plataforma/wt/cred`), base `master` = `13b419f`.
Commit único: **`61b8aeb`** — "Credencial nao atravessa mudanca de origem em redirecionamento (achado G5-1)".
Base de teste própria: schema `plat_tcred` (`bash laco/trilha_ambiente.sh cred`). O schema `plat` de produção
não foi tocado; nenhuma migração nova foi criada (o conserto é só de código).

## 1. O achado, e o que ele valia

O adversário independente (ramo `wt/adv5`, commit `e62f3db9`) provou que `app/conexao/seguranca.buscar_seguro`
reenviava o cabeçalho `Authorization: Bearer <credencial decifrada>` em salto de redirecionamento para um HOST
de outra origem. Os dois chamadores que passam credencial da casa — a rota `POST /api/conexoes/{id}/testar`
(`app/conexao/rotas.py`) e o periódico `conexoes.saude_verificar` (`app/conexao/tarefas.py`) — decifram a
credencial do inquilino antes de chamar. Um serviço externo cadastrado que responda 302 para fora
(redirecionamento aberto ou desvio deliberado) recebia a credencial do cliente.

O resto da defesa aguentou: os 8 casos de requisição forjada pelo servidor e a fixação no endereço já validado
seguem verdes (26 testes de `tests/unit/test_conexao_seguranca.py`), e nada disso foi alterado.

## 2. O conserto (arquivos)

`app/conexao/seguranca.py`:
- constante `_CABECALHOS_CREDENCIAL = {"authorization", "cookie", "proxy-authorization"}` (comparação sempre em
  minúsculas: nome de cabeçalho HTTP não diferencia caixa);
- `_origem(validada)` devolve `(esquema, host, porta)` — a porta já vem normalizada de `validar_url`, então
  `https://h/` e `https://h:443/` são a mesma origem;
- `_sem_credenciais(cabecalhos, secretos)` devolve CÓPIA sem os cabeçalhos de segredo (o dicionário do chamador
  nunca é alterado — a rota o reusa depois);
- no laço de `buscar_seguro`: a origem de cada salto é comparada com a da URL ORIGINAL; mudou esquema, host ou
  porta, os cabeçalhos de segredo saem ANTES de a conexão ser aberta. Novo parâmetro
  `cabecalhos_secretos: Iterable[str] | None` para o conector declarar nomes próprios (`X-Api-Key`, `api-key`);
- `ResultadoBusca.credencial_retirada: bool` (padrão `False`) — o chamador passa a saber que um `401` depois de
  redirecionamento é esperado, não senha errada. Campo com padrão, nenhum construtor existente quebra;
- docstring do módulo ganhou o "caso 9", na mesma forma dos 8 do portão.

Decisões, ambas testadas como caso próprio:
- **a retirada é definitiva**: cadeia a→b→a NÃO devolve a credencial ao voltar à origem inicial. Devolver seria
  defensável (o destino final é a origem cadastrada), mas quem desenhou o desvio foi o servidor de destino; se
  ele pode fazer a requisição autenticada ser repetida quando quiser, o segredo passa a depender do
  comportamento de um terceiro. É o que `requests` faz (`Session.rebuild_auth` apaga o cabeçalho e não o
  remonta nos saltos seguintes);
- **mesma origem mantém a credencial**, inclusive com `Location` relativo (o caso comum de GetCapabilities e de
  catálogo STAC) — senão o conserto viraria uma quebra silenciosa do teste de saúde autenticado.

Divergência deliberada das bibliotecas: `requests` (`should_strip_auth`, 2.33.1) e `httpx`
(`_is_https_redirect`, 0.28.1) abrem exceção para a SUBIDA `http://h/` → `https://h/` em porta padrão e mantêm
a credencial ali. Aqui não: mudou o esquema, sai. Custo conhecido e aceito — conexão cadastrada com `http://`
num serviço que sobe para `https://` passa a ser testada sem credencial e pode voltar 401; o
`credencial_retirada=True` diz por quê e o conserto de operação é cadastrar a URL `https://`, a única que não
manda o segredo em claro no salto 0.

## 3. Outros caminhos da casa que seguem redirecionamento (item 3 do pedido)

Varredura: `grep -rln 'import requests|import httpx|urllib.request|import http.client|aiohttp' --include=*.py app`
→ **4 módulos**, e só um recebe credencial de inquilino.

| módulo | segue redirect? | leva credencial? | veredito |
|---|---|---|---|
| `app/conexao/seguranca.py` | sim, à mão | sim (credencial do inquilino) | **era o furo; consertado** |
| `app/garage.py` | sim (`requests`, `allow_redirects` padrão) | sim: `Authorization` SigV4 em `_requisicao` e `Bearer <token admin>` em `ClienteAdmin._chamar` | **achado menor, NÃO alterado** — ver abaixo |
| `app/rede/osrm.py` | não (`httpx.Client` sem `follow_redirects`) | não | sem risco |
| `app/saude.py` | sim (`urllib.request.urlopen`) | não (só sonda de status) | sem risco |

Sobre o `garage.py`: o endereço vem do `.env` (`PLAT_GARAGE_URL` / `PLAT_GARAGE_ADMIN_URL`, hoje `127.0.0.1`),
não de dado de inquilino, e o `requests` já retira `Authorization` quando o redirecionamento muda hostname,
porta ou esquema — então não há vazamento hoje. O que sobra é o hábito: um endpoint de objeto mal configurado
poderia arrastar a requisição para outro lugar. **Não editei o arquivo** porque ele é território da trilha
`wt/garage` e o conserto certo ali é uma linha (`allow_redirects=False` nas duas chamadas, já que o Garage não
redireciona), que aquela trilha deve aplicar sem risco de conflito. Fica registrado como pendência de segurança
de baixa severidade.

Frente ao navegador: `web/js` não monta `Authorization` em lugar nenhum (a única ocorrência é texto de exemplo
na tela de tokens, `web/js/auth/tokens.js:96`); a sessão é por cookie de mesma origem.

## 4. Testes (marca trocada, nenhum teste do adversário afrouxado)

- `tests/adversario/test_g5_adversario.py` — **o teste do adversário, palavra por palavra**, com a única
  mudança de tirar `@pytest.mark.xfail(strict=True)`, que existia enquanto o achado estava aberto (mantê-lo
  derrubaria a suíte por XPASS). O cabeçalho do arquivo registra isso. Passa.
- `tests/unit/test_conexao_credencial_redirect.py` — 12 casos, offline e determinísticos (`getaddrinfo` e
  `cliente_pinado` trocados por `monkeypatch`; nenhum socket, nenhum banco):
  1. muda de host → retira; 2. muda de porta no mesmo host → retira; 3. porta padrão explícita
  (`https://h/` → `https://h:443/`) = mesma origem, mantém; 4. `https` → `http` → retira; 5. `http` → `https`
  → retira (a divergência deliberada); 6. cadeia de dois saltos a→b→c → retira e não recupera; 7. volta à
  origem a→b→a → NÃO devolve a credencial; 8. mesma origem com `Location` relativo → mantém; 9. `Cookie`,
  `Proxy-Authorization` e `X-Api-Key` declarado saem juntos, `Accept`/`User-Agent` ficam; 10. nome em caixa
  baixa sai igual; 11. sem credencial, a marca `credencial_retirada` fica falsa; 12. o dicionário do chamador
  não é alterado. A marca `credencial_retirada` é conferida dentro dos casos em que ela muda.

## 5. Provas (comando → resultado)

```
cd /home/dev/plataforma/wt/cred
export PLAT_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
venv/bin/pytest tests/adversario tests/unit/test_conexao_credencial_redirect.py \
                tests/unit/test_conexao_seguranca.py -q -o addopts=""     # 39 passed em 1,34 s

set -a; source /home/dev/plataforma/laco/var/trilha/cred.env; set +a
venv/bin/pytest tests/api/test_conexoes.py tests/unit/test_conexao_seguranca.py \
                tests/unit/test_conexao_credencial_redirect.py tests/adversario -q -o addopts=""
                                                                          # 64 passed em 6,52 s
venv/bin/pytest tests/unit -q -o addopts="" -k "proveniencia or conexao or saude"   # 40 passed
venv/bin/ruff check app/conexao/seguranca.py tests/unit/test_conexao_credencial_redirect.py \
                    tests/adversario/test_g5_adversario.py                # All checks passed
```
`ruff check app tests` devolve os MESMOS 11 erros de `master` (13b419f) e `make sem-marcador` aponta as MESMAS
2 linhas de `master` (`app/geocodificador/motor.py:207`, `app/settings.py:71`) — nenhuma regressão minha.
Medidas em `tests/medidas/L6-02-a-credencial-redirect.json`.

## 6. Documentação

- `docs/adr/0012-registro-do-acervo-e-conexao-externa.md`, seção nova "Decisão (setembro de 2026, turno T3): a
  credencial nunca atravessa uma mudança de origem": o achado, a regra, as duas escolhas (retirada definitiva;
  mesma origem mantém), a divergência de `requests`/`httpx` no `http`→`https`, e a citação de que as duas
  bibliotecas retiram a credencial ao mudar de origem. Regra que fica escrita ali: **toda vez que se
  reimplementa um comportamento de biblioteca por segurança, lista-se o que a biblioteca fazia ALÉM do motivo
  da troca** — foi exatamente o que aconteceu aqui, o laço manual existe para revalidar SSRF a cada salto e
  herdou a responsabilidade sem herdar a proteção.
- `CHANGELOG.md`: entrada no turno 3.

## 7. Limitações honestas

- A prova é no nível de `buscar_seguro`, que é onde os dois chamadores credenciados entram. Não montei o
  cenário fim-a-fim pela rota HTTP com um servidor externo redirecionando de verdade (o adversário também não).
- `app/garage.py` continua seguindo redirecionamento com `Authorization` (sem vazamento hoje: `requests` retira
  ao mudar de origem, e o endereço vem do `.env`). Deixado para a trilha `wt/garage`.
- Nenhum conector concreto usa ainda `cabecalhos_secretos`; o parâmetro existe para os 15 conectores de
  L6-02-b em diante (hoje só `Authorization`/`Cookie`/`Proxy-Authorization` entram sozinhos).
- Risco de merge: `app/conexao/seguranca.py` também é lido por L6-05 (`app/conexao/proveniencia.py`), que
  chama `buscar_seguro` SEM credencial — assinatura compatível, nada a mudar lá. `CHANGELOG.md` e o ADR 0012
  são arquivos que outras trilhas encostam: minha entrada é um bloco novo no topo da seção do turno 3 e uma
  seção nova antes de "O que fica para os itens seguintes", ambas sem tocar texto existente.
