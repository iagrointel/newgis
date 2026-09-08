# ADR 20260908T1200 — ações configuráveis dos widgets (item L5-01-e)

## Contexto
O L5-07 fixou o contrato do barramento (gatilho {origem, evento} → ações [{alvo, ação, parâmetros, relação}]) e um
painel "Dados e mensagens" que edita a coleção inteira num formulário só, com origem/alvo/evento/ação em listas
completas. O Experience Builder configura ações POR WIDGET ("Action" tab): quem está no widget escolhe o gatilho
entre os que aquele widget emite e só vê alvos e ações compatíveis; o usuário final tem um botão "Actions" nos
widgets de dado (exportar, ver no mapa, zoom). Faltavam as duas coisas e as validações que só fazem sentido com o
contrato por tipo (gatilho já usado, alvo incompatível, referência quebrada ao renomear campo).

## Decisões
1. **O contrato do widget é o do registro.** `web/js/widgets/registro.js` já declara `eventos`/`acoes` por
   manifesto; o modelo (`web/js/app/modelo.js`) passa a lê-lo (`CONTRATOS`, `eventosDe`, `acoesDe`) e a recusar
   `evento_incompativel` (a origem não emite) e `alvo_incompativel` (o alvo não aceita); uma vista emite os cinco
   eventos de dado e aceita só as ações de dado. O servidor tem o mesmo contrato em `app/app_modelo/contratos.py`
   e um teste em node compara os dois: manifesto novo sem o espelho reprova.
2. **Uma mensagem = um gatilho, N ações; repetir gatilho+alvo+ação é erro.** O painel "Ações" agrupa na mesma
   mensagem tudo o que sai do mesmo (origem, evento) — como o EXB — e `gatilho_repetido` recusa a duplicata nos
   dois validadores, antes de entrar no documento.
3. **Condição na ação = CQL2 sobre os registros de origem.** `acoes[].parametros.condicao` (mesmo dialeto das
   vistas, validado com os campos da fonte de origem): ação de dado leva só os registros que passam; ação de
   widget não dispara se nenhum passa. Sem tipo novo de parâmetro nem segunda linguagem.
4. **Painel por widget, coleção única.** `web/js/app/painel_acoes.js` pendura-se ao painel de propriedades do
   editor por um gancho novo (`extensaoPropriedades`, L5-08) e escreve nas MESMAS `corpo.mensagens` do painel do
   L5-07 — os dois painéis são vistas da mesma coleção; a validação é uma. O editor passou a tolerar tipos de nó
   fora da paleta (widgets do motor gravados por outro construtor) em vez de quebrar ao selecioná-los.
5. **Ações do usuário fora do barramento.** "Exportar CSV/GeoJSON (filtradas)", "Ver na tabela", "Zoom à
   seleção" e "Criar item com a seleção" vivem em `PlatWidget.montarAcoesUsuario()` e agem sobre a vista e os
   widgets irmãos da mesma fonte; não são mensagens do documento (o documento descreve o app, não o que cada
   usuário faz nele). A exportação é local (Blob) das feições FILTRADAS da vista — exatamente o que o usuário vê.

## Consequências
- Os manifestos de widgets novos (L5-01-b/c/d) precisam do espelho em `contratos.py`, senão o teste reprova; é o
  preço de a API recusar o que o construtor recusaria.
- "Criar item com a seleção" grava tipo `selecao`; instalações sem esse tipo (ainda noutro ramo) recebem o erro
  nomeado no próprio menu — o e2e aceita as duas respostas e diz qual veio.
- O gatilho `localizacao` do EXB não tem emissor (widget de localização é do L5-01-b); consta no quadro de
  paridade como "sem emissor".
- Uma cadeia de 30 ações roda em recursão síncrona (profundidade 31 medida); acima de algumas centenas de níveis
  seria pilha — o limite de 500 mensagens por documento (L5-07) e o corte de recursão em uma volta seguram isso.
