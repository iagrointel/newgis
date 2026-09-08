# T2 · preparação · L0-03-catalogo · 20_arquitetura (arquiteto)

## Objetivo

Fixar, antes de qualquer linha de código, o modelo, o contrato de API, o esquema, as bibliotecas e os testes do
catálogo de conteúdo (item L0-03-catalogo e os 12 filhos L0-03-a … L0-03-l), no ADR
`/home/dev/plataforma/enterprise/docs/adr/0004-catalogo-de-conteudo.md`, de modo que backend e frontend construam em
paralelo, com arquivos disjuntos, sem tocar no que as trilhas A (identidade, migrações 003/005, `app/auth`) e B
(jobs, migração 004, `app/jobs`) estão construindo agora.

## O que fiz

1. Li a skill, o estado (`L0-03-catalogo` + 12 filhos + `L0-10`, `L0-11`, `L0-12`, `L0-13`), `L0_CONCEITO.md`
   (D1, D2, D3, D7, D8, D9, D10, D13, D14), `L1_CONCEITO.md` C1/C2/C12, `L2_CONCEITO.md` C1/C2, `L5_CONCEITO.md`
   D1-D3, o handoff `T1/21_esri.md` seções 2 e 3, os ADRs 0001/0002/0003 inteiros nas seções que o catálogo usa, e o
   código vivo das trilhas A e B (`app/main.py`, `app/db.py`, `app/erros.py`, `app/limites.py`, `app/paginas.py`,
   `app/auth/comum.py`, `app/auth/escopos.py`, `app/auth/privilegios.py`, `app/jobs/tipos.py`,
   `app/jobs/periodicos.py`, `db/migracoes/003_identidade_acesso.sql`, `004_jobs.sql`, `tests/conftest.py`,
   `tests/api/conftest.py`, `tests/e2e/apoio.py`, árvore de `web/js`).
2. Medi nesta máquina, em schema temporário apagado no fim, o que sustenta as decisões: FTS com pesos + unaccent,
   trigram, `pode_ler` por EXISTS, grafo de 30 mil relações, custo de versão por gatilho, cursor × deslocamento,
   bbox, validação por JSON Schema (anexo A do ADR). Achado que teria quebrado a migração do backend:
   `array_to_string` é `STABLE` e a coluna `tsvector` gerada com tags não compila sem invólucro `IMMUTABLE`.
3. Testei por HTTP as 41 URLs citadas nos filhos e no ADR (todas 200, anexo B).
4. Escrevi o ADR 0004 (19 seções + 2 anexos): modelo `plat.item`, registro `plat.tipo_item` com JSON Schema
   por tipo (14 tipos, quem completa em que linha), `plat.item_versao` imutável com sha256, `plat.item_relacao` com
   vocabulário em `plat.relacao_tipo` (11) e ciclo recusado, compartilhamento em 5 níveis com `plat.pode_ler`/
   `pode_editar` na RLS, link por token (64 hex, revogável, validade, contagem, dependências incluídas
   explicitamente), busca (configuração `plat.pt_sem_acento`, gramática por campo, título exato antes do rank,
   reforço de status, trigram como reserva), pastas hierárquicas, tags, categorias com modelos ISO 19115 (19) e
   INSPIRE (34), classificação, favoritos, lixeira 30 d por `plat.lixeira = on`, proteção, status, transferência de
   dono com pré-checagem, eventos (vocabulário novo em `evento_tipo`), miniaturas (síncrona por Pillow com limite de
   pixels; por job para camada), 6 tipos de job, limites, contrato de API completo com cursor, 5 telas em wireframe,
   19 arquivos de teste com medidas nomeadas, paridade prevista, ordem da migração 006, custo de mudar.
5. Escrevi este handoff com as listas de arquivos disjuntas para backend e frontend e as colisões declaradas.

## Evidência (comando + saída literal)

```
$ cat medida_0004.sql | sudo -u postgres psql -d iagro_sat -v ON_ERROR_STOP=1 -q     (1ª tentativa, sem invólucro)
ERROR:  generation expression is not immutable

$ sudo -u postgres psql -d iagro_sat -tAc "SELECT proname, provolatile FROM pg_proc WHERE proname IN ('array_to_string','to_tsvector','unaccent','similarity') ORDER BY 1"
array_to_string|s
to_tsvector|i   (assinatura regconfig,text)   unaccent|s   similarity|i

$ cat medida_0004.sql | sudo -u postgres psql ...   (com plat.tags_texto IMMUTABLE)
 itens | relacoes | compart_grupo
 10000 |    30000 |          2500
--- FTS: municipio ... 50 primeiros                 p50 1.93  | p95 2.4115  | 50
--- FTS: só ts_rank_cd: título exato em 1º?         Município leste 7 / Município centro 14 / Município sul 21 (empate r=1)
--- FTS: com chave de título exato                  Município / Município leste 7 / ...   p95 2.59
--- reforço de status ±0,25                          p95 2.7055
--- bbox (GIST) + tipo                               p95 2.9315
--- OFFSET 4950 × cursor                             p95 2.0255 × p95 3.3875
--- "Município" × "municipio"                        1429 = 1429
--- trigram 'municpio'                               p95 20.8705 ; acha 1172
--- lista por tipo                                   p95 2.5875 ;  count(*) p95 0.0455
--- pode_ler por EXISTS, 10 mil linhas               p95 3.17 ; 2500 visíveis
--- pode_ler + busca + ordenação                     p95 3.1105
--- usado_por profundidade 2                         p95 0.9655 ; 12 linhas
--- fecho transitivo 6 níveis                        p95 2.824 ; 839 linhas
NOTICE:  update_media_ms=0.513 update_max_ms=6.849
NOTICE:  versao_media_ms=0.120
 item_total | gin_busca | gin_trgm | gist_extent
 37 MB      | 5544 kB   | 5488 kB  | 704 kB
 schemas_med0004
               0

$ venv/bin/python -c "... Draft202012Validator ... 1000 validações"
jsonschema 4.26.0 ; validacao_ms_por_doc 0.858 ; erro caminho: ['campos', 60, 'nome']
$ venv/bin/pip list | grep -iE 'jsonschema|pillow|markdown|bleach|nh3'
jsonschema 4.26.0 · Markdown 3.10.2 · markdown-it-py 3.0.0 · pillow 12.2.0 · pillow_heif 1.5.0   (bleach, nh3: ausentes)
$ systemctl is-active plataforma-garage ; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3900/
active
403
$ for u in <41 URLs>; do curl -sIL -m 12 -A '...' -o /dev/null -w '%{http_code}' "$u"; done
200 × 41   (2026-09-05 15:08 UTC; lista no anexo B do ADR)
$ wc -l docs/adr/0004-catalogo-de-conteudo.md
(ver o arquivo; > 1.300 linhas)
```

## Contrato fixado (o que backend e frontend NÃO renegociam entre si)

- Rotas, corpos, códigos de erro e o objeto `item` da seção 13 do ADR; paginação `limite/deslocamento` + `cursor`
  com `{total, itens, proximo_cursor}`.
- Nomes de tabela, coluna e função da seção 18 (migração 006) e das seções 2, 4, 5, 6, 8.
- Páginas e arquivos da seção 15 (`/conteudo`, `/conteudo/{id}`, `/conteudo/lixeira`, `/c/{token}`,
  `/admin/categorias`) registrados em `app/paginas.py` **pelo backend** (uma linha por página) e servidos de
  `web/conteudo*.html`, `web/compartilhado.html`, `web/admin/categorias.html` **pelo frontend**.
- Limites da seção 14 em `app/limites.py` (seção própria `# --- catálogo (L0-03)`; nenhuma constante de A/B é editada).
- Eventos da seção 12 e as entradas em `tests/api/eventos_esperados.py`.

## Backend (arquivos DESTE papel; nenhum deles existe hoje, exceto os marcados "acrescentar linha")

1. `db/migracoes/006_catalogo.sql` — seção 18 do ADR, na ordem; JSON Schema dos 14 tipos literal no SQL.
2. `app/catalogo/__init__.py`, `app/catalogo/modelos.py` (pydantic: `ItemEntrada`, `ItemSaida`, `PastaEntrada`,
   `CategoriaArvore`, `Compartilhamento`, `LinkEntrada`, `Transferencia`, `Lote`).
3. `app/catalogo/tipos.py` — cache de `tipo_item`, validação `jsonschema` → `422 dados_invalidos` com caminho.
4. `app/catalogo/texto.py` — Markdown → HTML saneado por lista de permissão (seção 2.4).
5. `app/catalogo/busca.py` — gramática por campo, `websearch_to_tsquery`, ordenação 7.3, trigram 7.4, facetas 7.5,
   cursor 13.1.
6. `app/catalogo/tipos_relacoes.py` — extratores de relações por tipo (`mapa`, `vista_de_camada`, `app`, `painel`,
   `modelo_amc`, `rede`).
7. `app/catalogo/diff.py` — JSON Patch entre versões.
8. `app/catalogo/transferencia.py` — plano e execução (seção 10).
9. `app/catalogo/miniatura.py` + `app/catalogo/objetos_local.py` — 11.1-11.3 (adaptador local com o contrato do L0-11).
10. `app/catalogo/tarefas.py` + `app/catalogo/periodicos.py` + `app/catalogo/destruidores.py` — 11.4 e 9.1.
11. `app/catalogo/rotas_itens.py`, `rotas_compartilhamento.py`, `rotas_pastas.py`, `rotas_categorias.py`,
    `rotas_favoritos.py`, `rotas_lixeira.py`, `rotas_publico.py` (`/compartilhado`, `/publico`), `rotas_tipos.py`.
12. `app/catalogo/modelos_categorias/iso19115.json`, `inspire.json`; `app/catalogo/modelos_classificacao/sigilo.json`.
13. **Acrescentar linha** (colisão declarada, ordem de commit com A/B): `app/main.py` (bloco `# --- catálogo (L0-03)`
    em `ROUTERS`, depois do bloco de jobs), `app/paginas.py` (5 linhas em `PAGINAS`), `app/limites.py` (seção
    própria no fim), `app/jobs/tipos.py` (uma importação: `from app.catalogo import tarefas, periodicos`),
    `app/auth/comum.py` (só **acrescentar** códigos em `ERROS_DO_BANCO`: `item_protegido`, `pasta_ciclo`,
    `pasta_profunda`, `pasta_nao_vazia`, `relacao_ciclo`, `relacao_com_outro_inquilino`, `relacao_familia_invalida`,
    `relacao_profunda`, `sem_contribuicao_no_grupo`, `publico_desligado`, `campo_imutavel`,
    `dono_so_por_transferencia`, `pasta_de_outro_inquilino`, `categoria_de_outro_inquilino`, `classificacao_invalida`),
    `app/auth/escopos.py` (só a validação do `<uuid>` na criação do token: função `item_legivel(uuid)` importada de
    `app.catalogo`), `app/jobs/worker.py` **não** se edita: o worker soma `PERIODICOS` de todo módulo registrado
    (se a trilha B não expuser esse gancho, o gerente pede a ela um `registrar_periodicos(lista)` em
    `app/jobs/periodicos.py`; declarado como pendência).
14. Testes: `tests/unit/test_busca_sintaxe.py`, `test_texto_saneado.py`, `test_diff_versoes.py`,
    `test_limites_catalogo.py`; `tests/api/test_itens_modelo.py`, `test_busca.py`, `test_compartilhamento.py`,
    `test_relacoes.py`, `test_pastas_categorias.py`, `test_lixeira.py`, `test_transferencia.py`, `test_versoes.py`,
    `test_miniatura.py`, `test_eventos_catalogo.py`; **acrescentar** casos em `tests/api/cruzado_casos.py` e
    entradas em `tests/api/eventos_esperados.py` (arquivos da trilha A: só acrescentar, nunca reescrever);
    `tests/api/semear_catalogo.py` (10 mil itens em demo, 1 mil em demo2, reutilizado pelo e2e).
15. `make openapi` → `docs/openapi.json`; `docs/CONTRATO_API.md` ganha a seção do catálogo se o L0-12 já o tiver
    criado (senão a seção fica no ADR até lá).

## Frontend (arquivos DESTE papel; disjuntos do backend e das trilhas A/B)

1. `web/conteudo.html`, `web/conteudo_item.html`, `web/conteudo_lixeira.html`, `web/compartilhado.html`,
   `web/admin/categorias.html`, `web/conteudo.css` (folha própria; `web/style.css` não se edita).
2. `web/js/catalogo/api.js` (chamadas tipadas às rotas da seção 13; único lugar com URL), `conteudo.js`, `lista.js`
   (vistas tabela/lista/grade), `filtros.js` (facetas), `pastas.js` (árvore), `selecao.js` (massa),
   `busca_sintaxe.js` (validação local + ajuda), `item.js`, `item_dados.js` (formulário gerado do JSON Schema),
   `item_compartilhar.js` (diálogo com árvore de dependências), `item_versoes.js`, `item_relacoes.js`,
   `lixeira.js`, `compartilhado.js`, `categorias.js`, `formato.js` (datas, bytes, elipse de 2.048 caracteres),
   `icones.js` (ícones SVG por nome de `tipo_item.icone`),
   `tipos/<tipo>.js` (módulo de abertura por tipo registrado em `tipo_item.modulo_front`; neste item só o esqueleto
   funcional de `arquivo`, `conexao` e `mapa` = abre a página do item; L2/L5 entregam os deles).
3. Reuso sem edição: `web/js/base/*` (api, dom, estado, layout, componentes de tabela/paginação/diálogo/formulário/
   aviso/busca), `web/js/core.js`, `web/js/i18n/pt-BR.json` (**acrescentar chaves** com prefixo `catalogo.` — colisão
   declarada com A/B, só acréscimo).
4. Testes e2e: `tests/e2e/test_conteudo.py`, `test_conteudo_item.py`, `test_categorias.py`, `tests/e2e/apoio_catalogo.py`
   (login, semeadura via API, capturas `L0-03-catalogo_<tela>.png`).
5. Orçamento: cada módulo ≤ 60 kB; soma da tela `/conteudo` ≤ 400 kB (medida `soma_modulos_kb`).

## Ordem dentro da trilha

30 backend e 31 frontend em paralelo (o contrato está no ADR); o frontend começa por `api.js` + telas contra o
OpenAPI e usa `tests/api/semear_catalogo.py` assim que o backend comitar a migração; 40 testador depois dos dois; 50
adversário depois do 40; 60 cronista junto com o 50.

## Colisões declaradas (com quem, onde, como se resolve)

| arquivo | quem mais toca | regra |
|---|---|---|
| `app/main.py` `ROUTERS` | A, B | um bloco comentado por trilha; quem comita depois faz rebase; ordem: saúde, identidade, jobs, catálogo, páginas |
| `app/paginas.py` `PAGINAS` | A, B | idem, 5 linhas |
| `app/limites.py` | A, B | seção própria no fim; nunca editar constante alheia |
| `app/jobs/tipos.py` | B | uma linha de importação |
| `app/jobs/periodicos.py` / `worker.py` | B | **não editar**; pedir o gancho `registrar_periodicos` se não existir (pendência) |
| `app/auth/comum.py` `ERROS_DO_BANCO` | A | só acrescentar chaves |
| `app/auth/escopos.py` | A | só a validação de `<uuid>` na criação do token, via função importada do catálogo |
| `tests/api/cruzado_casos.py`, `eventos_esperados.py` | A | só acrescentar entradas |
| `web/js/i18n/pt-BR.json` | A, B | só acrescentar chaves `catalogo.*` |
| `db/migracoes/006_*.sql` | A pode publicar `005`; se A precisar de `006`, este item vira `007` | numeração decidida pelo gerente na integração |
| `plat.tenant.config` | A (`auth`), este item (`catalogo`) | chaves separadas por bloco; nenhum ALTER |
| L0-11 (`plat.arquivo`, cliente S3) | ainda não construído | adaptador local com o mesmo contrato (ADR 11.3); job de migração é do L0-11 |
| L0-10 (`plat.historico`, tela Auditoria) | ainda não construído | este item grava só `plat.evento`; `historico` por gatilho é do L0-10 |
| L0-12 (`docs/CONTRATO_API.md`, `docs/LIMITES.md`) | ainda não construído | contrato e limites vivem no ADR até o L0-12 gerar os documentos |
| L0-04 (camada física, upload) | ainda não construído | `catalogo.miniatura` de camada usa tabela semeada pelo teste em `d_demo` até a demonstração (L0-13) existir |

## Riscos

1. O gancho de periódicos no worker da trilha B pode não existir com o nome previsto; sem ele, os dois periódicos
   deste item (`lixeira_expurgar`, `versoes_compactar`) não entram na agenda → a cláusula "periódico com relógio
   simulado expurga" fica pendente até o gerente resolver (é uma função de 5 linhas).
2. `pode_ler` é `SECURITY DEFINER` e é chamada por política de RLS: qualquer bug nela vale para todo o produto. Por
   isso o teste `test_funcoes_seguras.py` é estendido e o adversário tem o roteiro (`set_config` direto,
   `plat.superadmin` sem sessão, link de outro inquilino).
3. A escala medida foi 10 mil itens; 50 mil (adversário do L0-03-f) e 100 mil (`COTA_ITENS`) não foram medidos:
   o testador grava `busca_50k_p95_ms` como fronteira, sem portão.
4. A miniatura de camada por Pillow (versão 1 do job) é legível mas não é o render do mapa; o L2-01 substitui pela
   captura headless (versão 2) — declarado na paridade como parcial até lá.
5. `tipo_item` global contraria uma frase do portão do L0-03-a ("tipo_item por inquilino"); a leitura adotada e o
   custo de mudar estão na seção 3.1 do ADR. O gerente confirma na integração ou o item acrescenta `tenant_id NULL`.
6. Sem `nh3`/`bleach`, o saneador é próprio; o teste unitário com os vetores clássicos é a única defesa até a venv
   ganhar uma biblioteca (não se instala nesta preparação).

## Pendências

- Gerente: confirmar numeração `006` × `007` conforme a trilha A; pedir o gancho `registrar_periodicos` à trilha B;
  confirmar a leitura "tipo_item global" (seção 3.1) ou mandar por inquilino.
- Decisão do dono já registrada e ainda aberta: **D24** (público anônimo por inquilino) — o ADR implementa
  `compartilhar_publico` com padrão `false` e a rota `/api/publico/itens/{id}` só responde quando o inquilino liga;
  se o dono decidir "nunca", basta remover a rota e o valor `publico` do CHECK. **D26** (Garage reusado × separado):
  o adaptador local do 11.3 é indiferente à decisão.
- L0-11 deve entregar o cliente com a assinatura da seção 11.3 e o job `objetos.migrar_local`.
- L0-10 deve acrescentar `plat.historico` por gatilho nas tabelas `pasta`, `categoria`, `item_grupo`,
  `compartilhamento_link` (o `item` já tem `item_versao`).

## Para o próximo papel

- **30 backend**: comece pela `006_catalogo.sql` na ordem da seção 18 (as políticas de `item` só depois de
  `pode_ler`), rode `make migrar` duas vezes (0 mudanças na segunda), depois `tipos.py` + `texto.py` + `busca.py`
  com os testes unitários, depois as rotas na ordem `rotas_tipos` → `rotas_itens` → `rotas_pastas` →
  `rotas_compartilhamento` → `rotas_lixeira` → `rotas_categorias` → `rotas_favoritos` → `rotas_publico`;
  `make openapi` a cada rota nova; casos em `cruzado_casos.py` e `eventos_esperados.py` no mesmo commit da rota.
  Semeie 10 mil itens com `tests/api/semear_catalogo.py` antes de medir. Nada de `to_tsquery` com texto do usuário.
- **31 frontend**: `web/js/catalogo/api.js` primeiro (uma função por rota da seção 13, com os códigos de erro
  mapeados para mensagens do `pt-BR.json`), depois `/conteudo` (tabela → lista → grade), depois `/conteudo/{id}`,
  depois os diálogos. Capturas com o nome fixo da seção 16. Nunca `?v=` em `import`.
- **40 testador**: os 19 arquivos da seção 16 com as medidas nomeadas; `make check` inteiro; `make medidas` grava
  `tests/medidas/L0-03-catalogo.json`.
- **50 adversário**: roteiro sugerido está nas refutações dos 12 filhos e nas seções 6.3, 9.2, 11.1 e 16 do ADR
  (sem ler os handoffs 30/31).
- **60 cronista**: MANUAL (5 telas), CHANGELOG, ARQUITETURA (tabelas e funções novas), `docs/PARIDADE.md` (seção 17
  do ADR, "feito" só com teste).

## Resumo em 10 linhas

1. ADR 0004 escrito em `/home/dev/plataforma/enterprise/docs/adr/0004-catalogo-de-conteudo.md` (19 seções, 2 anexos, > 1.300 linhas), migração `006_catalogo.sql`, código em `app/catalogo/*` e `web/js/catalogo/*`.
2. Uma tabela `plat.item` (uuid estável, tenant + RLS, tipo, metadado Esri traduzido, extent 4326, miniatura no Garage, `dados` validado por JSON Schema por tipo, status, proteção, lixeira) e registro `plat.tipo_item` com 14 tipos e quem os completa.
3. `plat.item_versao` imutável por gatilho com sha256 (0,12 ms medido), restauração cria versão nova, compactação a 50.
4. `plat.item_relacao` com 11 tipos em `relacao_tipo`, ciclo recusado (2,8 ms para fecho de 6 níveis), `usado-por`, ordem de exclusão, aviso ao sobrescrever.
5. Compartilhamento privado/grupos/inquilino/link/público decidido por `plat.pode_ler`/`pode_editar` na RLS de `item` e dependentes (3,2 ms p95 em 10 mil linhas sem cache); link de 64 hex revogável com dependências incluídas explicitamente; 404 para sem acesso, 410 expirado.
6. Busca no PostgreSQL: `plat.pt_sem_acento`, `tsvector` gerado com pesos (índice na mesma transação; exigiu invólucro `IMMUTABLE` para tags, achado medido), 2,4 ms p95 em 10 mil itens, título exato antes do rank, reforço de status, trigram como reserva, gramática por campo sem `to_tsquery` com texto do usuário.
7. Pastas hierárquicas por inquilino (≤ 5, `uuid[]`), tags, categorias com ISO 19115 (19) e INSPIRE (34), classificação por esquema, favoritos com `pode_ler` no `WITH CHECK`.
8. Lixeira de 30 d visível só com `plat.lixeira = on`, expurgo por job pesado com destruidor por tipo, proteção como campo (superadmin passa com evento), status autoritativo/obsoleto, transferência com pré-checagem.
9. API completa (seção 13) com `limite/deslocamento` e `cursor`, 6 tipos de job, 25 eventos novos, 19 arquivos de teste com medidas, 5 telas em wireframe, paridade prevista, custo de mudar por decisão.
10. Colisões declaradas: `main.py`, `paginas.py`, `limites.py`, `jobs/tipos.py`, `auth/comum.py`, `escopos.py`, `cruzado_casos.py`, `eventos_esperados.py`, `pt-BR.json` (só acréscimo); pendências: gancho de periódicos na trilha B, numeração 006/007, leitura "tipo_item global", contrato do L0-11.
