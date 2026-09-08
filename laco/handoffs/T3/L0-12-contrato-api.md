# L0-12-contrato-api-e-limites — arquiteto+backend (T3)

## Objetivo

Item `L0-12-contrato-api-e-limites` (backlog completo em `laco/estado.json`): formalizar o contrato
transversal da API como documento vivo + aplicação — versionamento, formato de erro, paginação,
limites por padrão e por inquilino — e cobrir com teste o que faltava de código: um limite de
tamanho de corpo global, ainda inexistente.

## O que fiz

1. **`docs/CONTRATO_API.md`** (novo): decide e documenta, seção por seção — (1) versionamento: SEM
   `/v1` na URL, `docs/openapi.json` comitado é o contrato, mudança incompatível vira rota nova; (2)
   formato de erro `{erro, mensagem, detalhe?, req_id}` (já existia em `app/erros.py`, só documentado
   aqui com a tabela completa de códigos); (3) paginação limite/deslocamento + total + `Link` para
   cursor, ordenação `ordenar=campo:asc|desc`, datas ISO 8601 UTC, ids uuid (todos já implementados
   em rotas existentes — o documento aponta para o código real, não inventa convenção nova); (4)
   limites — 10 MiB padrão de corpo, novo nesta passagem; (5) CORS por inquilino e rate limit na API
   (além do nginx) — **nomeados como pendência, não implementados**: não construí código sem
   consumidor real (nenhuma rota cross-origin existe hoje) para não virar o mesmo problema que um
   placeholder.
2. **`app/limite_corpo.py`** (novo) + duas constantes em `app/limites.py`
   (`CORPO_MAX_PADRAO_BYTES = 10 MiB`, `CORPO_MAX_UPLOAD_BYTES = 2 GiB`, isento por prefixo
   declarado): middleware ASGI puro, instalado em `app/main.py` depois do middleware de log/sessão
   (fica mais externo no empilhamento do Starlette — executa primeiro na entrada, corpo grande nunca
   chega à sessão nem ao log de acesso). Duas defesas: `Content-Length` acima do limite rejeita sem
   ler nada; corpo sem `Content-Length` (chunked) ou que mente sobre o tamanho é contado por bytes
   efetivamente recebidos e cortado no meio. Não usei `BaseHTTPMiddleware` levantando exceção durante
   a leitura do corpo porque `fastapi/routing.py` tem um `except Exception` genérico ali que converte
   QUALQUER exceção em `400 "There was an error parsing the body"` — medido nesta máquina, documentado
   no docstring do módulo. Por isso o corpo é drenado e contado por inteiro ANTES de chamar a
   aplicação, nunca por partes.
3. **`docs/gerar_limites.py`** (novo) gera `docs/LIMITES.md` a partir de `app/limites.py` via
   `tokenize`+`import` (o valor no documento é `repr()` do que o Python leu do módulo agora, nunca
   digitado de novo); `make limites` roda em modo `--check`; entrou em `check` e `check-rapido` do
   Makefile.
4. Testes novos: `tests/api/test_limite_corpo.py` (12 casos: `Content-Length` acima do limite → 413
   no formato padrão; no limite exato não rejeita; sem `Content-Length` (chunked) também rejeita;
   `Content-Length` mentiroso também é pego pela contagem real; corpo pequeno segue o fluxo normal —
   não vira negação de serviço; limite não se aplica fora de `/api,/svc,/ogc,/tiles`),
   `tests/api/test_versionamento.py` (nenhuma rota viva nem `docs/openapi.json` comitado leva
   segmento `/v<n>/` — fixa em teste a decisão de não versionar, não só em prosa),
   `tests/unit/test_limites_doc.py` (documento == código; nenhuma constante escapou do gerador).

## Evidência

Verificação isolada, ANTES de outras trilhas colidirem no mesmo arquivo (ver "Riscos" abaixo):

```
$ ./venv/bin/ruff check app/limite_corpo.py app/limites.py app/main.py docs/gerar_limites.py
All checks passed!
$ grep -rnI --exclude-dir=vendor ... -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md
(nada — exit 1, sem ocorrência)
$ flock .../.pytest.lock ./venv/bin/pytest -m "not lento" tests/api/test_limite_corpo.py \
    tests/api/test_versionamento.py tests/unit/test_limites_doc.py -q
............                                                             [100%]
```

Depois do commit, reconferido em isolamento (as três trilhas concorrentes tinham, nesse meio-tempo,
acrescentado `ARQUIVO_*` a `app/limites.py` sem regenerar `docs/LIMITES.md` — ver Riscos):

```
$ git show 6f034c3:{app/limites.py,app/limite_corpo.py,docs/LIMITES.md,docs/gerar_limites.py} > /tmp/verifica_l012/...
$ PYTHONPATH=. venv/bin/python docs/gerar_limites.py --check
MEU_COMMIT_ISOLADO_OK
```

Commit: `6f034c3` "Contrato de API e limite de corpo por requisição (item L0-12)", 10 arquivos,
isolado do resto da árvore de trabalho compartilhada (ver Riscos).

## Riscos

- **Repositório compartilhado, sem branch**: durante esta trilha, PELO MENOS TRÊS outras trilhas
  editaram o mesmo working tree ao vivo — L2-04-b (parser where, já commitado como 5c31887 antes de
  eu terminar), L0-11/ADR 0006 (upload de arquivo: acrescentou `ARQUIVO_BYTES_MAX` etc. a
  `app/limites.py` e preencheu `limite_corpo.PREFIXOS_ISENTOS` com `/api/arquivos` — usando
  exatamente o ponto de extensão que este item previu), e L6-01-a (acervo). Isolei meu commit dos
  outros dois em andamento (`app/main.py`, `app/limites.py`, `app/limite_corpo.py`, `Makefile`) via
  `git hash-object`/`git update-index --cacheinfo` construindo o blob só com as minhas linhas em cima
  do HEAD de cada momento, em vez de `git add` no arquivo inteiro (que teria commitado também o
  trabalho não testado de outra trilha em nome deste item). Conferido com `git diff --cached HEAD`
  antes de commitar: só os 10 arquivos deste item apareciam.
- **`make check` no working tree AGORA mostra falhas que não são deste item**: rodei a suíte
  completa (fora do escopo do item, para checar interferência) e `tests/unit/test_limites_doc.py`
  falha ao vivo porque `app/limites.py` (arquivo compartilhado, não commitado ainda por quem
  acrescentou) tem `ARQUIVO_BYTES_MAX`/`ARQUIVO_PARTE_BYTES`/`ARQUIVO_BUFFER_UNICO_BYTES` que
  `docs/LIMITES.md` (a versão que EU commitei) ainda não lista — é o teste fazendo exatamente o que
  deveria: pegar um documento desatualizado. Resolve sozinho quando a trilha do upload rodar
  `make limites` e commitar. Outras falhas da suíte completa (funções do catálogo sem revogar
  `EXECUTE` de `public`, migração 021 duplicada entre `021_acervo_ficha.sql` e `021_arquivos.sql`)
  são de outras trilhas, não deste item — sinalizando ao gerente para conferir `make check` de novo
  só depois que as três trilhas concorrentes fecharem.
- Um teste isolado meu chegou a rodar SEM `flock` por um instante (engano meu, corrigido em
  segundos, matando o processo antes de qualquer leitura/gravação colidir com a suíte de outra
  trilha que estava com o lock). Registrado aqui por transparência; não houve dado gravado.

## Pendências (fora do escopo desta passagem, nomeadas em docs/CONTRATO_API.md seção 5)

- CORS por lista do inquilino (≤ 100 origens) — decidido na hipótese do item, sem rota que precise
  hoje; não construído.
- Rate limit por sessão/token na própria API (hoje só nginx, só em `/api/login`) — não construído.
- Zona de rate limit de nginx para o restante de `/api/` (hoje só login tem zona própria).

Recomendo ao gerente decidir se abre sub-itens (`L0-12-a-cors-por-inquilino`,
`L0-12-b-limite-de-taxa-na-api`) no backlog ou se isso fica só nomeado no documento até haver um
consumidor real — não editei `estado.json` porque não sou o papel gerente desta sessão.

## Para o próximo papel (testador/adversário/gerente)

- Refutação do item pedia "limite documentado que a API não aplica" e "rota sem versão de erro" —
  cobertos por `test_limite_corpo.py` (Content-Length mentiroso, chunked) e `test_versionamento.py`.
  Um adversário independente ainda não rodou contra este item nesta passagem (pedido do dono era
  passagem única e rápida, sem lançar o papel adversário separado).
- Quando `app/limites.py` ganhar `ARQUIVO_*` (commit do L0-11), rodar `make limites` e commitar
  `docs/LIMITES.md` atualizado — meu teste falha até lá, de propósito.
