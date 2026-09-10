# Protocolo de teste em ArcGIS Pro e ArcGIS Online

resultado: pendente

Este documento existe porque ArcGIS Pro e ArcGIS Online não podem ser testados por esta máquina:
os dois exigem licença nominal e credencial de organização, e a credencial ainda não foi decidida
(decisão D20). Enquanto não houver evidência devolvida, a linha correspondente da matriz de
conformidade (`tests/esri/conformidade.json`, seção "Clientes" de `docs/PARIDADE.md`) fica **não
medida** — nunca "suportado".

O protocolo abaixo é para quem tem os dois programas instalados executar em meia hora e devolver
os arquivos pedidos. Quem executa não precisa saber nada da implementação: só seguir os passos.

## O que se recebe antes de começar

Três coisas, entregues pela equipe que opera a plataforma:

1. `BASE` — o endereço público do ambiente (por exemplo `https://exemplo.invalido`).
2. `TOKEN` — um token de serviço com escopo de leitura de catálogo e de camada.
3. `ITEM` — o identificador da camada de teste (um UUID).

Com isso, as quatro URLs do teste são:

| serviço | URL |
|---|---|
| diretório de serviços | `BASE/svc/TOKEN/rest/services` |
| FeatureServer | `BASE/svc/TOKEN/rest/services/ITEM/FeatureServer` |
| VectorTileServer | `BASE/svc/TOKEN/rest/services/ITEM/VectorTileServer` |
| OGC API Features | `BASE/ogc/features/ITEM` |

## Passos no ArcGIS Pro

1. **Conectar ao servidor.** Catálogo → Servidores → Nova conexão ArcGIS Server. Cole
   `BASE/svc/TOKEN/rest/services`. Capturar: a árvore de serviços que aparecer.
2. **Abrir a camada.** Arraste o FeatureServer para um mapa novo. Capturar: o mapa desenhado e a
   contagem de feições que o Pro mostra na tabela de atributos.
3. **Tabela de atributos.** Abra a tabela, ordene por uma coluna de texto e por uma numérica.
   Capturar: as duas ordenações e o tempo até a tabela abrir.
4. **Seleção por atributo.** Use "Selecionar por atributo" com uma condição simples
   (`populacao > 1000`). Capturar: quantas feições ficaram selecionadas.
5. **Seleção por local.** Desenhe um retângulo e selecione o que ele cruza. Capturar: a contagem.
6. **Simbologia.** Troque a simbologia para valores únicos por uma coluna de texto. Capturar: a
   legenda gerada.
7. **Edição.** Se o token entregue tiver escopo de escrita: inicie uma sessão de edição, mova um
   vértice, salve, e depois desfaça. Capturar: se o Pro aceitou salvar e a mensagem exibida.
8. **Tile vetorial.** Adicione o VectorTileServer como camada. Capturar: o desenho em três níveis
   de aproximação diferentes.
9. **OGC API Features.** Catálogo → conexão OGC API Features com a URL do quadro acima. Capturar:
   a lista de coleções e a camada desenhada.

## Passos no ArcGIS Online

1. Conteúdo → Adicionar item → De uma URL. Cole a URL do FeatureServer, tipo "ArcGIS Server web
   service". Capturar: se o item foi criado e o que a pré-visualização mostrou.
2. Abra o item no Map Viewer. Capturar: o desenho, a janela de atributos de uma feição e o filtro
   aplicado por uma expressão simples.
3. Repita para o VectorTileServer.
4. Tente compartilhar o item com a organização. Capturar: a mensagem (esperado: o AGOL avisa que o
   serviço é externo e exige que o destinatário tenha o token).

## O que devolver

Para cada passo, três coisas: **a captura de tela**, **a mensagem de erro na íntegra** quando
houver, e **o tempo** que o passo levou. Erro é o resultado mais útil deste teste — não vale pular
um passo que falhou.

Devolver também a versão exata dos programas (Pro: Ajuda → Sobre; AGOL: rodapé da organização),
porque o comportamento do cliente muda entre versões.

## Como o resultado entra na matriz

Quem receber a devolução acrescenta um arquivo `tests/medidas/L2-04-j-parceiro-pro-agol.json` com
um registro por passo (passo, resultado, versão do programa, data) e troca, em
`tests/esri/conformidade.py`, a linha "ArcGIS Pro e ArcGIS Online reais" para apontar esse arquivo
como prova. Só então a linha sai de "não medido". Enquanto isso não acontecer, este documento
continua dizendo `resultado: pendente`, e o teste
`tests/unit/test_conformidade_matriz.py::test_protocolo_do_parceiro_existe_e_esta_pendente`
reprova qualquer tentativa de escrever "feito" aqui sem a evidência.
