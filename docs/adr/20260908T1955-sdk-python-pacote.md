# ADR — SDK Python `plat` (pacote interno) e ferramenta por job

Item **L2-16-a-sdk-python-geo** (turno 48, trilha swl202). ADR 0001/0002/0003 continuam valendo;
este documento registra as decisões DESTA parte, com o motivo.

## 1. O que é

Pacote Python `plat` (`pacote/`), distribuição interna (`make pacote` → `pacote/dist/*.whl`; sem
PyPI até decisão do dono). Um ponto de entrada, `Plataforma(url, token)`, com quatro domínios:
`pla.catalogo`, `pla.acervo`, `pla.jobs` e `pla.ferramentas`. Autenticação SEMPRE por token de
serviço (`Authorization: Bearer`); o SDK não faz login com senha — token se cria pela UI ou por
`POST /api/tokens` numa sessão, que é o fluxo da ADR 0002 seção 8 (um token não se perpetua:
criação é `so_sessao=True`).

## 2. Decisões

### 2.1 Camada fina e tipada, não camada mágica

Cada método do SDK é um espelho honesto de UMA rota (mesmo nome, mesmos parâmetros de query, mesmo
corpo). O único conforto além do espelho é a paginação transparente (`Catalogo.iterar` segue
`proximo_cursor`; `Acervo.iterar` segue `deslocamento`) e `Jobs.esperar` (consulta num intervalo até
estado final, devolve o job completo). Motivo: a API já é o contrato versionado (OpenAPI); duplicar
um modelo de dados no SDK é criar dois lugares para dessincronizar. Quem precisa de GeoDataFrame
quando o FeatureServer existir (L2-04-c) adiciona a conversão FORA do SDK ou num método próprio —
sem molde morto no pacote.

### 2.2 Toda recusa é exceção tipada (plat.erros)

Status → classe: 401 `ErroAutenticacao`, 403 `ErroPermissao`, 404 `NaoEncontrado`, 409 `Conflito`,
413 `ErroLimite`, 422 `ErroValidacao`, 5xx `ErroServidor`, e `FalhaJob` para job terminado em
falha/cancelamento. O corpo da API (`{"erro": codigo, "detalhe": {...}}`) viaja na exceção:
`.codigo`, `.detalhe`, e as propriedades `.exigido`/`.escopo` para a recusa de permissão — o
programador trata o código nomeado da casa, não um número solto. **404 é o caso do adversário**:
item de outro inquilino é `NaoEncontrado` (RLS da casa devolve 404 de propósito; o SDK NÃO
"explica" 404 como 403 — isso vazaria existência).

### 2.3 Ferramenta = tipo de job, e resultado de ferramenta = item do catálogo

`ferramentas.buffer` é um tipo de job normal (`@tarefa` de ADR 0003: pydantic valida os parâmetros
na criação, worker executa, procedência do job é montada pelo worker). A diferença está no destino:
quando o resultado é um dado reutilizável, a tarefa grava um item do catálogo do tipo NOVO
`ferramenta_resultado` (migração 20260908T1847) direto em `plat.item` — o mesmo padrão de
`app/ingestao/carregar.py` — com `dados = {ferramenta, parametros, resultado, job_id, procedencia}`
e evento de domínio `ferramentas/buffer` (migração 20260908T1929). O retorno do job traz `item_id`,
e é isso que `pla.ferramentas.buffer(...)` devolve. Motivo: item tem RLS, lixeira, versão,
compartilhamento e catálogo de graça; uma tabela nova para resultado de ferramenta seria uma sexta
via sem nenhum desses.

### 2.4 Buffer é PLANO e MÉTRICO, e a recusa é na porta

`distancia_m` tem teto (`FERRAMENTA_BUFFER_MAX_M`, 100 km — análise regional já é, tudo acima é
erro de unidade) e `srid` é validado com pyproj: **srid geográfico (graus) é recusado com
FalhaDefinitiva/422**. Motivo: buffer em grau não tem unidade; reprojetar por dentro do job (decisão
que o SDK não vê) esconderia a escolha de projeção do responsável pelos dados. A aproximação
(plano, `quad_segs` padrão da biblioteca, shapely/GEOS) fica declarada na procedência do item.

### 2.5 Exemplos que rodam (doctest) contra a instalação de demo

Os exemplos dos docstrings são doctests executados por `tests/sdk/test_sdk_doctests.py` contra a
instalação de trilha (servidor uvicorn + worker em subprocesso, fixtures de `tests/sdk/conftest.py`),
com a variável `pla` injetada. Sem exemplo decorativo: se está no docstring, roda.

## 3. O que NÃO entrou (e por quê)

A hipótese do item previa `Camada.ler/escrever` (GeoDataFrame via FeatureServer e edição
transacional), `Raster.ler` (TiTiler/STAC) e widget de mapa em notebook. As três dependem de itens
que não estão em master: L2-04-c (FeatureServer, **parcial**, ramo `wt/fsquery` sem merge), L2-03-a
(edição transacional, **refutado**) e TiTiler/STAC (L2-04 restante). nbconvert/ipykernel não estão
na venv. O SDK não expõe módulo morto: sem essas rotas não existe `Camada` nem `Raster` no pacote.
Pendências registradas no handoff do item.

## 4. Consequências

- SDK versiona junto com o repositório (`__versao__` = versão do wheel; checkout sem instalação lê
  `PLAT_VERSAO` do ambiente ou marca `0.0.0.dev0`).
- `tests/sdk/` sobe servidor + worker próprios em portas efêmeras (mesma app, schema da trilha) —
  a suíte prova o HTTP de verdade, não um TestClient com atalhos.
- `make pacote` (sem segredos) constrói o wheel; `pacote/dist/` é ignorado pelo git.
- Evento novo `ferramentas/buffer` segue a regra da casa: tipo registrado em `plat.evento_tipo` por
  migração (as rotas de /api/jobs já estavam cobertas; a tarefa roda no worker, fora do OpenAPI).
