# Matriz de conformidade viva dos serviços Esri/OGC

Item L2-04-j. Estado: aceito.

## Problema

A seção de serviços do `docs/PARIDADE.md` era escrita à mão, uma por item. Escrita à mão, ela
envelhece em silêncio: quando este item juntou os cinco ramos da família, a seção do item dos
serviços ainda dizia que `applyEdits`, anexos e relacionamentos estavam fora — o item da edição já
os tinha construído havia um dia. Um documento de paridade que erra para menos é tão ruim quanto um
que erra para mais: os dois deixam de ser consultáveis.

Havia também um problema de método. "Suportado" era uma palavra escrita por quem construiu, ao lado
de um teste que talvez existisse. Sem amarrar a palavra à execução, não há como um terceiro conferir.

## Decisão

A lista de serviços do `PARIDADE.md` passa a ser **gerada**, e a geração é uma execução de provas.

`tests/esri/conformidade.py` declara a matriz (102 linhas hoje: 45 parâmetros da operação `query`,
mais diretório, edição, anexos, OGC API Features, WFS, tiles vetoriais, os serviços que ainda não
existem e os clientes). Cada linha nomeia a prova: um nó de teste (`arquivo::funcao`) ou uma chave
de veredito dos dois roteiros de sonda que já existiam (`conformidade_query.py`,
`conformidade_servicos.py`). Rodar o script executa os nós numa passagem só, lê o relatório JUnit,
executa as sondas, e então:

- prova que falhou → a linha vira **refutado**, e `make check` reprova;
- prova que passou → a linha fica no estado mais conservador entre o declarado e o medido (uma sonda
  que diz `fora` derruba um `suportado` declarado);
- nenhuma prova executada → **não medido**, nunca `suportado`.

A saída é `tests/esri/conformidade.json`, com data, versão do repositório e o resultado por linha; a
seção do `PARIDADE.md` é escrita dessa saída, entre marcadores. `tests/unit/test_conformidade_matriz.py`
reprova se o documento divergir do JSON, se alguma linha afirmada não tiver prova que passou, se um
parâmetro da doc Esri sumir da matriz, ou se um item irmão construído não aparecer.

## Consequências

O que a plataforma tem passa a ser afirmável só na medida em que foi executado, e a lista deixa de
depender de alguém lembrar de atualizá-la. Em troca, `make conformidade` é caro: roda cerca de cem
testes e duas sondas, e precisa de banco de trilha e de um worker de pé. Por isso ele não entra em
`make check`; o que entra é a conferência barata do documento contra o JSON já gravado.

Três limites ficam declarados na própria matriz, e não em rodapé: QGIS e o cliente Python `arcgis`
não estão nesta máquina e não cabem no disco disponível; ArcGIS Pro e ArcGIS Online exigem licença
de parceiro, e o protocolo para quem os tem está em `docs/TESTE_PARCEIRO_PRO_AGOL.md`, com resultado
pendente; a suíte oficial de conformidade do OGC (teamengine) também não roda aqui. Nenhum dos três
aparece como "suportado" em lugar nenhum.
