# Contrato de API do `plat`

Documento vivo (item L0-12-contrato-api-e-limites; ADR 0001 seção 12, ADR 0002 seção 14). "Vivo" quer dizer:
toda afirmação aqui é testada — `make check` falha se o código se afastar do que está escrito nesta página.
Onde uma decisão já tem o detalhe completo em outro lugar (o formato de erro em `app/erros.py`, os limites por
inquilino no ADR 0002 seção 11), este documento aponta para lá em vez de duplicar; o que é novo ou transversal
a toda rota fica aqui.

## 1. Versionamento

**Decisão: sem versão na URL.** Nenhuma rota leva `/v1/`, `/v2/` etc. Mudança incompatível de contrato vira
rota nova com outro nome (ex.: `/api/itens` e, se um dia precisar, `/api/itens2` ou um campo de saída
diferente atrás de outro caminho) — nunca uma rota substituída no mesmo endereço. O contrato de verdade é
`docs/openapi.json`, comitado a cada turno que mexe em rota (`make openapi`); é ele que os testes cruzados e
de paridade leem (`tests/api/conftest.py:arquivo_openapi`), não um número de versão solto.

Testado por `tests/api/test_versionamento.py`: nenhuma rota da aplicação viva (`app.routes`) nem do
`docs/openapi.json` comitado leva um segmento `/v<dígitos>/` — se algum dia uma trilha acrescentar
`/api/v1/...` por hábito (é o padrão mais comum de API REST, e o oposto do que foi decidido aqui), o teste
falha no código, não só nesta prosa.

## 2. Formato de erro

Toda resposta de erro é JSON: `{"erro": "<código_curto>", "mensagem": "<frase em português>", "detalhe": <opcional>, "req_id": "<16 hex>"}`.
Implementado em `app/erros.py` (`ErroAPI`, `tratar_http`, `tratar_validacao`); instalado uma vez em
`app/main.py` (`erros.instalar(app)`) e reusado por toda rota — nenhuma trilha redefine o formato. Cobre:

| status | código | quando |
|---|---|---|
| 400 | `pedido_invalido` | corpo ou parâmetro que não chega a ser um esquema válido (ex.: JSON quebrado) |
| 401 | `nao_autenticado` | sem sessão nem token válido |
| 403 | `sem_permissao` | sessão/token válidos, sem o privilégio ou escopo exigido |
| 404 | `nao_encontrado` | rota inexistente OU recurso que a RLS esconde (nunca revela "existe mas não é seu") |
| 405 | `metodo_nao_permitido` | verbo HTTP não implementado na rota |
| 409 | `conflito` (ou código específico, ex. `ultimo_admin`) | operação que violaria uma invariante de negócio |
| 410 | `expirado` (ou específico, ex. `desafio_expirado`) | recurso que existiu e não existe mais por prazo |
| 413 | `corpo_grande` | corpo da requisição acima do limite (seção 4 abaixo; novo neste item) |
| 415 | `tipo_nao_aceito` | `Content-Type` fora do que a rota aceita |
| 422 | `validacao` (lista pydantic) ou código específico (ex. `senha_fraca`) | esquema de entrada violado |
| 423 | `bloqueado` | conta ou recurso temporariamente bloqueado (política de senha, ADR 0002 seção 6) |
| 429 | `muitas_tentativas` | limite de taxa (nginx, `/api/login`; ver seção 5 — ainda não na API) |
| 503 | `indisponivel` (ou específico, ex. `inquilino_suspenso`) | dependência fora do ar ou inquilino suspenso |

`detalhe` só aparece quando informado (nunca `null` OU chave ausente ao mesmo tempo — é uma coisa ou outra).
Nenhuma rota devolve HTML nem traceback em erro: `tests/unit/test_erros.py` cobre cada código; `tests/api/`
confere em rotas reais. Campo de erro sempre em português (`erro`, `mensagem`) — nunca `"error"`/`"message"`.

## 3. Paginação, ordenação, datas, ids

- **Paginação por limite/deslocamento**, com `total` no corpo e, em listas que também aceitam cursor (hoje
  `GET /api/itens`), cabeçalho `Link: <url>; rel="next"` quando há próxima página (`app/catalogo/rotas_itens.py`).
  Rotas simples (ex. `GET /api/usuarios`) usam só `limite`/`deslocamento`, sem cursor — o cursor existe onde a
  ordenação pode mudar entre páginas (busca com relevância) e o deslocamento simples paginaria errado.
- **Ordenação por `ordenar=campo:asc|desc`** (`app/auth/comum.py`, `app/catalogo/busca.py`, `app/jobs/servico.py`):
  campo fora da lista permitida da rota é `422 campo_invalido`, nunca ignorado em silêncio.
- **Datas em ISO 8601 UTC** (`app/auth/sessao.py:iso`, sufixo `Z`), nunca timestamp epoch nem fuso local.
- **Ids em uuid** (`uuid.UUID` validado nas rotas que recebem id por parâmetro; `422 campo_invalido` fora do formato).
- **Filtros por query string**, um parâmetro por campo (nunca um único `filtro=` com sintaxe própria fora da
  busca textual, que tem sintaxe documentada à parte em `app/catalogo/busca.py`).

## 4. Limites

Tabela completa gerada de `app/limites.py`: **`docs/LIMITES.md`** (`make limites`; `tests/unit/test_limites_doc.py`
falha se divergir — o número no documento é sempre `repr()` do valor que o Python leu do módulo, nunca um
número reescrito à mão). Esta seção só documenta os dois limites transversais que este item acrescenta:

| limite | valor padrão | onde | aplicado por |
|---|---|---|---|
| corpo da requisição, fora de upload | 10 MiB (`limites.CORPO_MAX_PADRAO_BYTES`) | toda rota `/api/`, `/svc/`, `/ogc/`, `/tiles/` | `app/limite_corpo.py` (novo) |
| corpo de upload | 2 GiB (`limites.CORPO_MAX_UPLOAD_BYTES`) | rotas em `limite_corpo.PREFIXOS_ISENTOS` | **pendente**: nenhuma rota de upload existe ainda (multipart entra no L1-01-e); a lista de isenção está vazia de propósito — ver seção 4.1 |

Todos os demais limites (por inquilino: cota de itens, tokens por usuário, tags por item, etc.) já existiam
antes deste item, decididos pelas trilhas de identidade (L0-02) e catálogo (L0-03); `docs/LIMITES.md` os lista
todos juntos porque o portão deste item pede um só lugar onde "número no doc = número no código" é verificável.

### 4.1 Corpo da requisição, fora de upload

Middleware ASGI puro `app.limite_corpo.LimiteCorpoMiddleware` (instalado em `app/main.py`, depois do
middleware de log/sessão — no empilhamento do Starlette isso o torna o mais externo, então corpo grande é
rejeitado ANTES de a sessão ou o log de acesso serem tocados). Dois níveis de defesa, os dois testados em
`tests/api/test_limite_corpo.py`:

1. `Content-Length` presente e acima do limite → `413` imediato, sem ler um byte do corpo.
2. corpo sem `Content-Length` (chunked) ou que declara um valor menor que o real → os bytes são contados
   conforme chegam pelo ASGI `receive()`; ao ultrapassar o limite a leitura para e o corpo NUNCA chega à
   aplicação — não existe caminho onde o limite documentado não seja aplicado (é literalmente o que a
   refutação do item pede para procurar).

Por que não é `BaseHTTPMiddleware` levantando exceção durante a leitura: o `fastapi/routing.py` tem um
`except Exception` genérico ao redor da leitura do corpo que converte QUALQUER exceção ali em
`400 "There was an error parsing the body"` (medido nesta máquina) — a exceção nunca chegaria a um handler
de middleware. Por isso o corpo é drenado e contado por completo ANTES de chamar a aplicação (nunca por
partes), e só repassado por um `receive()` de reprodução quando está dentro do limite.

Rotas de upload (L1-01-e, ainda não construídas) não devem simplesmente entrar na lista de isenção deste
middleware: a defesa acima bufferiza o corpo em memória antes de repassá-lo, aceitável até 10 MiB, ERRADO
para 2 GiB. A rota de upload grande precisa aplicar `CORPO_MAX_UPLOAD_BYTES` em streaming, gravando em disco
conforme recebe, e só então entrar em `limite_corpo.PREFIXOS_ISENTOS` para que este middleware pare de olhar
para ela.

## 5. Taxa (rate limit) e CORS — decididos, parcialmente aplicados

A hipótese original do item pede rate limit "por sessão/token/IP no nginx e na API" e CORS "por lista do
inquilino (≤ 100 origens, como a Esri)". Nesta passagem:

- **Rate limit no nginx**: já existe para `/api/login` e `/api/login/2fa` (`deploy/nginx.conf`, zona
  `plat_login`, 10 requisições/minuto por IP, `429` com `Retry-After` — ADR 0002 seção 6.2). **Pendente**: um
  limite equivalente na própria API (por sessão/token, não só por IP, para cobrir tráfego atrás de um proxy
  compartilhado) e uma zona de nginx para o restante de `/api/` (hoje só login tem zona própria).
- **CORS por lista do inquilino**: **não implementado nesta passagem**. Não há hoje nenhuma rota que sirva
  `/api/` fora do mesmo domínio da aplicação (o front é servido do mesmo `PLAT_URL_PUBLICA`), então o middleware
  de CORS ainda não tem consumidor real para testar contra — construí-lo agora seria código morto, sem uso
  verificável (o portão P2 do laço proíbe função visível que não faz nada; código sem consumidor é a mesma
  falta, do lado do servidor). Fica nomeado aqui para quando um cliente precisar consumir a API de outra
  origem (ex.: um mapa embutido no site dele).

Nenhum dos dois pontos acima está "feito": aparecem aqui para que a lacuna seja visível no documento, em vez
de ficar só na hipótese original do item.

## 6. O que este item testa

- `tests/unit/test_erros.py` — formato de erro, um caso por código (pré-existente, deste item em diante é o
  que a seção 2 acima descreve).
- `tests/api/test_limite_corpo.py` — corpo grande com e sem `Content-Length` → `413` no formato padrão; corpo
  no limite exato passa; corpo pequeno segue o fluxo normal da rota (não vira negação de serviço); o limite
  não se aplica fora de `/api,/svc,/ogc,/tiles`.
- `tests/api/test_versionamento.py` — nenhuma rota viva nem comitada leva segmento de versão na URL.
- `tests/unit/test_limites_doc.py` — `docs/LIMITES.md` bate com `app/limites.py` agora, e nenhuma constante
  nova do módulo escapou do documento.
