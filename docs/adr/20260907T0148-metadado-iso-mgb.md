# ADR — editor de metadado no Perfil MGB 2.0 (item L0-09-b-editor-iso-mgb)

Data: 2026-09-07. Contexto: `app/catalogo/metadado.py` (item L0-09-metadado-catalogo) já exporta um XML
ISO 19139/GMD somente-leitura por item. Este item pede um EDITOR: abas 'essencial'/'completo', validação de
obrigatórios do perfil, sincronização com os campos do item, campos de linhagem alimentados pela procedência
e pelos jobs, e um estilo de apresentação por inquilino (MGB 2.0, ISO 19115-3, Dublin Core) sobre o MESMO
armazenamento.

## Decisão 1 — dois grupos de campo, não um jsonb genérico

`plat.item` já tem `titulo`, `resumo`, `tags`, `creditos`, `termos_de_uso`, `extent` — colunas reais, com
CHECK, índice de busca e regra de negócio (ex. `pode_editar`). Duplicar esses campos dentro de
`metadado_iso` criaria dois lugares de verdade, e a regra do item é explícita: "o título É sincronizado, ao
contrário da Esri" (na Esri, o "Title" do metadado ArcGIS Online é independente do nome do item). Por isso:

- **Sincronizados** (identificação: título, resumo, palavras-chave, créditos; restrições: termos de uso):
  computados AO VIVO a partir da linha do item em toda leitura (`app/catalogo/metadado_mgb.py:visao`).
  Gravados por `PUT /api/itens/{id}/metadado` só através do mesmo núcleo que o PUT/PATCH de item já usa
  (`rotas_itens.editar_item`) — nunca um caminho de escrita paralelo.
- **Próprios do metadado** (contato, licença, extensão temporal e espacial DECLARADA, sistema de referência,
  manutenção, formato de distribuição): vivem em `plat.item.metadado_iso` (jsonb, migração
  `20260907T0148_metadado_mgb.sql`), validados por `ESQUEMA_MGB` (JSON Schema Draft 2020-12,
  `additionalProperties: false` em cada nível — o mesmo padrão de `plat.tipo_item.esquema`).

Consequência testada: `PATCH /api/itens/{id}` mudando o título aparece na leitura do metadado no próximo
`GET`, e o editor de metadado mudando o título muda o item — os dois leem/escrevem a mesma coluna
(`tests/api/catalogo/test_metadado_mgb.py::test_titulo_sincronizado_editor_muda_item_e_vice_versa`).

## Decisão 2 — extensão espacial pode divergir do extent do item, de propósito

`extensao.espacial` é DECLARADA pelo produtor do dado, e é normal ela não bater exatamente com o extent
calculado do item (ex. margem de segurança, área de estudo maior que o dado publicado). A refutação do item
pede exatamente isto: divergência vira aviso, nunca bloqueio. `avisos_extent()` compara contra o extent real
do item com tolerância de 0,01 grau e devolve uma lista (nunca levanta erro).

## Decisão 3 — linhagem computada, nunca digitada

Não existe uma tabela "job por item" nesta plataforma. O rastro determinístico de o que mudou o item e
quando já é `plat.evento` (alvo_tipo='item'), que toda escrita de item já registra desde a migração 011.
`qualidade_linhagem` lê esse rastro (até 50 eventos, ordenados) e o bloco `dados.procedencia` (item
L0-09-a-procedencia, quando presente) — nunca aceita um `processStep` digitado à mão no editor, pela mesma
razão que motivou D17 do L0_CONCEITO ("procedência errada é pior que nenhuma").

**Fronteira honesta**: no momento deste turno, `L0-09-a-procedencia` (commit `ac4dbce`) ainda não está
mesclado em `master` — este worktree partiu de `master` antes dele. O código lê `dados.procedencia` como um
dicionário livre (mesmo contrato que `app/catalogo/metadado.py` já usa), então funciona OS DOIS ITENS JUNTOS
sem acoplamento de módulo; só não há, neste turno, um item real de camada importada com procedência de
verdade para provar a costura ponta a ponta — o teste usa `dados.procedencia` sintético (mesmo formato).

## Decisão 4 — estilo por inquilino é só apresentação

`plat.tenant.config.estilo_metadado` (mesmo padrão jsonb de configuração do item L0-07-a, sem coluna nova)
escolhe entre `mgb2` (padrão), `iso19115_3` e `dublin_core`. `formatar_estilo()` recebe a MESMA leitura
(`visao()`) e só reorganiza rótulo/caminho para apresentação — os três estilos nunca leem nem escrevem
armazenamento diferente. Dublin Core, por ser um vocabulário mais pobre (15 elementos), omite os campos sem
equivalente direto (ex. frequência de manutenção) em vez de inventar um mapeamento.

## Decisão 5 — exportação (L0-06-d) não existe ainda

O portão de pronto pede "metadado exportado no L0-06-d". `L0-06-d-exportar-inquilino` não existe no
repositório neste turno (não está em nenhuma linha entregue nem parcial do catálogo de itens). Não há como
cumprir essa cláusula sem inventar a rota do outro item. Fronteira honesta registrada no handoff e em
`tests/medidas/L0-09-b-editor-iso-mgb.json`; quando `L0-06-d` existir, a integração é: incluir
`GET /api/itens/{id}/metadado` (ou o XML de `metadado.py`) na lista de artefatos por item da exportação —
o formato já devolvido por este item não precisa mudar.

## Rotas novas

- `GET /api/itens/{id}/metadado?estilo=` — leitura completa + faltantes essencial/completo + avisos.
- `POST /api/itens/{id}/metadado/validar` — valida um rascunho (não grava); usado pelo botão "Validar".
- `PUT /api/itens/{id}/metadado` — grava; 422 estrutural com caminho, nunca bloqueia por essencial faltando.
