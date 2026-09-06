# ADR 0011 — Documento de construtor: grafo de nós com ULID (item L5-05-documento-versoes)

Estado: aceito (arquiteto+backend, passagem única, turno 3, 06/09/2026).

## 1. Contexto

`laco/decomposicao/L5_CONCEITO.md` D2/D3 fixa a base que todo construtor do L5 (app, painel, e depois
formulário, fluxo) usa para gravar o que o usuário monta: um documento com envelope
`{tipo, esquema_versao, corpo}`, ULID imutável por nó, versão imutável com sha256, publicar como ponteiro.
`plat.item.dados` (envelope), `plat.tipo_item.esquema`/`esquema_versao` (JSON Schema por tipo) e
`plat.item_versao` (versão imutável, sha256, `versao_publicada`) já existem, entregues e testados pelo item
L0-03-catalogo. A decisão deste item é **não criar mecanismo novo nenhum**: só o que falta, específico de
documento de construtor.

## 2. O que falta que JSON Schema puro não expressa

JSON Schema (Draft 2020-12, `jsonschema` 4.26.0, já na venv) valida a FORMA de cada nó isoladamente (um `id`
casa com o padrão de ULID, um `tipo` é uma string dentro do tamanho); não valida propriedades que dependem de
OLHAR A LISTA INTEIRA: dois nós com o mesmo `id`, ou uma `ligacao` apontando para um `id` que não existe em
`corpo.nos`. Isso vive em `app/catalogo/documento.py::validar_grafo`, chamado logo depois de `tipos.validar`
nas duas rotas que escrevem `dados` (`criar`, núcleo do PUT/PATCH). Erro: `422 grafo_invalido`, com uma
entrada por nó/ligação problemático (`campo`, `erro`, `regra` — `ulid`/`id_duplicado`/`referencia_pendente`).

ULID (Crockford base32, 26 caracteres, `^[0-7][0-9A-HJKMNP-TV-Z]{25}$`) foi escolhido sobre UUID v4 porque
D2 do L5_CONCEITO já fixou "ULID imutável por nó" como regra 1, e porque é ordenável por tempo de criação sem
campo extra — útil para o editor de arrasto (D9 do L5_CONCEITO) mostrar histórico de nós na ordem em que
foram criados. `app/catalogo/documento.py::gerar_ulid()` é a implementação de referência (servidor e testes);
o editor (JavaScript, fase futura) gera o seu próprio ULID — os dois lados só precisam concordar no FORMATO,
nunca compartilhar código.

## 3. Dois hashes, propósitos diferentes

`plat.item_versao.sha256` (gatilho `plat.tg_item_versao`, ADR 0004) vem de `digest(corpo::text, 'sha256')`,
onde `corpo` é o jsonb inteiro do item (`item_retrato`). MEDIDO nesta máquina: a serialização de texto do
jsonb do Postgres ordena as chaves por **comprimento e depois alfabeticamente** (não por ordem de inserção
nem puramente alfabética) e insere espaço depois de `:` e de `,` — determinístico DENTRO deste Postgres, mas
não é o que `json.dumps`/`sha256sum` de fora reproduzem sem reimplementar esse formato interno. Exemplo
medido: `jsonb_build_object('b',1,'a',2,'zebra',3,'alpha',4)::text` = `{"a": 2, "b": 1, "alpha": 4, "zebra":
3}` (chaves de 1 caractere antes das de 5, alfabético dentro do mesmo comprimento).

O portão deste item pede um sha256 **igual ao calculado fora** — por isso `sha256_canonico(corpo)`
(`app/catalogo/documento.py`) é um hash À PARTE, sobre `dados.corpo` (não o `item_versao.corpo` inteiro),
numa forma canônica simples e documentada: `json.dumps(corpo, sort_keys=True, ensure_ascii=False,
separators=(",", ":"))`. Testado byte a byte contra `sha256sum` de verdade em
`tests/api/catalogo/test_documento.py::test_sha256_canonico_reproduz_fora_do_banco_com_sha256sum` (grava o
corpo num arquivo, roda um subprocesso Python que serializa com a MESMA fórmula e não com `print` — `print`
acrescenta `\n` e muda o hash, achado desta sessão). Os dois hashes aparecem lado a lado em
`GET /api/itens/{id}/versoes/{n}`: `sha256` (o de sempre, estável dentro do banco) e `sha256_canonico`
(verificável fora).

## 4. Esquema de `app`/`painel`: opcional, não obrigatório

`corpo.nos`/`corpo.ligacoes` são propriedades OPCIONAIS do esquema (não `required`), decisão que reduz o
raio de quebra ao mínimo: os 1.573 itens `app` e 1.571 `painel` já semeados em demo/demo2 (`corpo: {}`,
`esquema_versao: 1`) continuam válidos contra o esquema NOVO sem qualquer migração de escrita — o que muda é
que, QUANDO `nos` existe, cada nó precisa de ULID único e toda `ligacao` precisa resolver. `corpo.mapas`/
`corpo.mapa_id` continuam declarados no esquema: são o contrato já entregue e testado de
`app/catalogo/relacoes.py::_app` (item L0-03-i, relação "usado-por" de app/painel→mapa) — um esquema que os
rejeitasse quebraria uma funcionalidade de OUTRO item já em produção. `additionalProperties: false` continua
valendo no nível de `corpo`: só essas quatro chaves são aceitas hoje; um construtor futuro (L5-01/L5-02/L5-03)
que precisar de mais campos bate esquema_versao de novo, mesma disciplina.

## 5. Migração de esquema: na leitura, nunca gravada

`migrar_<tipo>_v<N>_v<N+1>` (registro fechado `_MIGRACOES` em `documento.py`) é aplicada só quando o servidor
DEVOLVE o documento (`GET /api/itens/{id}`, função `ver()`), nunca no navegador e nunca gravada de volta em
`plat.item.dados` — quem salvar de novo grava a versão vigente por si, com o corpo que o editor já monta no
formato novo. Cada aplicação registra o evento `itens/esquema_migrado` com `{tipo, de, para}` (vocabulário
novo em `plat.evento_tipo`, migração 028). Precedente: Experience Builder migra app antigo ao abrir; Puck
documenta "Data Migration" entre versões com quebra — os dois fazem a migração no momento de ABRIR, nunca
alteram o artefato salvo por conta própria.

## 6. Verificação de integridade

`GET /api/itens/{id}/integridade` recomputa, em SQL (`digest(corpo::text, 'sha256')`), o sha256 de cada linha
de `plat.item_versao` e compara com a coluna `sha256` gravada. `plat_app` (o papel da própria API) tem
INSERT/UPDATE/DELETE revogados nessa tabela desde a migração 011 — só um acesso de superusuário direto ao
Postgres (fora da aplicação) consegue editar uma versão já gravada, e é exatamente esse cenário que o
endpoint expõe (`test_plat_app_nao_pode_editar_item_versao` prova a premissa; `test_integridade_acusa_linha_
de_versao_editada_direto_no_banco` tampera via `sudo -u postgres psql` e confere que a rota acusa).

## 7. Rotas novas e P6 (RLS/cruzado)

`GET /api/esquemas` (lista de tipos com esquema publicado) e `GET /api/esquemas/{tipo}?versao=N` são
vocabulário — não dado de inquilino, mesmo padrão de `GET /api/tipos-item` — cadastradas em
`tests/api/cruzado_casos.py` como `proprio=True`. `GET /api/itens/{id}/integridade` segue o padrão comum de
alvo de outro inquilino (`404`), também cadastrada. `docs/openapi.json` não foi regenerado nesta passagem: o
turno tinha outra trilha regravando o mesmo arquivo ao vivo (`app/catalogo/metadado.py`), e capturar o
estado parcial dela num `make openapi` fora de hora criaria um commit com rotas de outro item ainda em
construção — fica para a integração final do turno, mesma decisão registrada por aquela trilha em
`docs/PARIDADE.md`.

## 8. O que fica de fora desta passagem

- `formulario`/`fluxo` continuam com o envelope trivial (`corpo: object` livre): a forma dos nós desses dois
  é decisão do item que os constrói (L5-03, L5-02), não deste. Acrescentar a família ao `FAMILIAS_GRAFO` de
  `documento.py` quando decidirem é o único acoplamento — nada mais deste módulo é específico de app/painel.
- Editor de arrasto, motor de widgets, barramento de mensagens (D5, D9, D19 do L5_CONCEITO): outros itens.
- Compactação de versões de rascunho (`rotulo='rascunho'`, expurgo das últimas N): já existe genericamente
  (`plat.item_versoes_compactar`, L0-03); este item não adicionou política própria.
