# Modelos 3D: glTF por three.js, IFC lido em casa, 3D Tiles gerado em Python e conferido pelo validador oficial

- Item: L2-09-c-modelos-gltf-ifc-3dtiles
- Data: setembro de 2026
- Estado: aceito

## Contexto

O visualizador de cena do L2-09-b desenha terreno e volumes vindos de camada vetorial, e a decisão 4
daquele ADR deixou modelo (glTF, IFC, 3D Tiles) para este item. Falta, então, pôr no mapa o modelo em si:
um arquivo de projeto posicionado no globo, com os elementos consultáveis um a um.

A restrição de licença está na spec (DOC.md 22): o visualizador de BIM que o SIG de teste interno usa é
AGPL e não entra. O caminho aberto é three.js (MIT) para o modelo posicionado, deck.gl (MIT) para malha
grande e o padrão OGC 3D Tiles 1.1 (Community Standard 18-053r2) como formato — que é, ainda por cima, o
formato que o cliente pesado do produto concorrente lê por URL.

## Decisão

1. **glTF binário (GLB) é a moeda comum.** O que o navegador desenha, o que a conversão de IFC produz e o
   que vira conteúdo de tile é sempre GLB. O leitor e o escritor são de casa (`app/modelos3d/glb.py`,
   `web/js/cena/modelogltf.js`): o subconjunto do formato que a plataforma usa — recipiente, nós, malhas
   com posição/normal/índice, material com cor base — cabe em duas centenas de linhas sobre a biblioteca
   padrão, e trazer uma dependência de glTF custaria mais do que resolve. O carregador de exemplo do
   three.js foi considerado e recusado: mora em `examples/jsm`, importa por nome de módulo e puxa outros
   dois arquivos, o que obrigaria a vendorizar quatro arquivos e montar um mapa de importação.

2. **Modelo com recurso externo é recusado, no servidor e no navegador.** Um glTF que aponte `uri` de
   textura ou de buffer para fora de si mesmo faz o navegador do usuário buscar aquele endereço — um
   servidor de terceiro escolhido por quem enviou o arquivo. Ou está embutido em `data:`, ou não entra.
   A recusa está nos dois lados de propósito: o servidor é a defesa, o navegador é a rede de segurança
   para modelo que um dia entre por outro caminho.

3. **O IFC é lido em Python puro, e o que não converte sai CONTADO.** `app/modelos3d/ifc.py` analisa o
   arquivo STEP (ISO 10303-21) e devolve os elementos com identificador global, tipo, pavimento e
   propriedades; a geometria é convertida nas duas formas que o arquivo aberto da buildingSMART usa e que
   respondem pela maior parte do que sai de ferramenta de autoria: malha já tesselada
   (`IfcTriangulatedFaceSet`) e sólido de extrusão (`IfcExtrudedAreaSolid`) sobre perfil de polilinha,
   retângulo ou círculo. Fronteira genérica, booleana e varredura ao longo de curva NÃO são convertidas.

   O elemento com representação não convertida **entra na tabela assim mesmo**, marcado
   `tem_geometria = false`, e o modelo grava `elementos_sem_forma`. Medido no arquivo aberto de teste: 13
   elementos, 11 com forma, 2 sem — os dois são conjuntos (chaminé e telhado) que no próprio IFC não têm
   forma própria. Contar 13 e desenhar 11 é o resultado honesto; dizer que o modelo tem 11 elementos não
   seria.

4. **Onde a conversão roda (decisão D32).** No trabalhador comum da fila, porque o leitor não depende do
   IfcOpenShell. O que o IfcOpenShell resolveria é exatamente a fila do `elementos_sem_forma`, e a casa o
   tem no servidor de GPU; o registro de tarefas já sabe declarar `executor='gpu'`, mas o tipo NÃO se
   declara assim hoje: sem `PLAT_GPU_SSH` o registro recusa a importação do módulo e derrubaria a
   aplicação em toda instalação sem GPU. A ligação com o servidor de GPU é decisão do dono, não deste ADR.

   Medido no teto de memória do trabalhador (1.024 MB): IFC sintético de 50 MB com 62.038 elementos leva
   15,1 s de leitura mais 4,3 s de montagem e chega a 679 MB de pico. Cabe, com folga pequena. Arquivo
   bem maior exigirá leitura por partes — o número está em `tests/medidas/`, não numa promessa.

5. **A árvore 3D Tiles é gerada em Python; quem confere é o validador oficial.** O padrão 1.1 admite
   glTF/GLB como conteúdo de tile diretamente, então o gerador (`app/modelos3d/tiles3d.py`) cabe em umas
   poucas dezenas de linhas sobre o módulo de GLB que já existe: raiz com `transform` geocêntrico, filhos
   divididos em quadrantes enquanto passarem do teto de nós por tile, conteúdo citado por URI relativa.

   Exigir o `3d-tiles-tools` (Node, Apache-2.0) em PRODUÇÃO significaria pôr um segundo runtime dentro do
   trabalhador da fila para escrever um `tileset.json`. Ele entra pelo outro lado, que é o que importa:
   o `3d-tiles-validator` oficial é instalado por `deploy/tiles3d_validador_instalar.sh` fora do
   repositório versionado e REPROVA o que este gerador escreveu, em vez de um validador nosso se olhando
   no espelho. Medido: 0 erros e 0 avisos, tanto com a árvore de 1 tile quanto com a de 8; e o controle
   negativo (tileset sem `geometricError`) é reprovado pelo mesmo validador, o que mostra que ele não
   aprova qualquer coisa.

6. **Nenhuma tabela por modelo.** `plat.modelo3d` guarda a ficha (arquivo, posição, estado, caixa) e
   `plat.modelo3d_elemento` guarda uma linha por elemento, com o GUID que o próprio arquivo carrega. O
   arquivo em si vive no armazenamento de objetos por inquilino do L0-11; esta tabela guarda só o sha256.
   O GUID é a chave do produto: o nó do glTF leva `extras.guid`, o clique na tela pergunta por aquele
   GUID, e o índice do nó — que muda a cada conversão — nunca aparece em contrato nenhum.

7. **A convenção de eixos é declarada em um lugar só.** X do modelo é o leste, Y é cima, -Z é o norte;
   `rotacao_graus` é azimute horário a partir do norte. Está escrita em
   `app/modelos3d/posicionamento.py` e é a mesma no navegador. A tradução para o Mercator do MapLibre
   troca os eixos Y e Z **sem inverter sinal** (o Mercator tem Y para o sul e Z para cima): errar esse
   sinal põe o modelo do outro lado da rua sem nenhum erro na tela, e foi o que aconteceu na primeira
   versão. A prova é a cláusula do portão — a caixa que o navegador desenhou contra a que o servidor
   calculou, canto a canto: **0,097 m de erro**, contra a folga de 0,5 m.

8. **A altura do modelo é elipsoidal.** A plataforma não aplica ondulação do geoide em lugar nenhum, e
   dizer o contrário seria prometer precisão vertical que não existe aqui.

## Consequências

- A cena ganha o bloco `modelos` no documento (acrescentado ao esquema do tipo por `jsonb_set`, sem
  reescrever o esquema inteiro), com `modo` em `gltf` ou `tileset`.
- `make check` passa a rodar `make sem-agpl`, que varre código e manifestos de dependência atrás de
  licença AGPL e ignora linha de comentário — licença nunca é declarada dentro de comentário, e o próprio
  arquivo que explica a regra cita a sigla.
- **i3s fica FORA, declarado.** Não há produtor aberto do formato na pilha; o que existe é a
  especificação e implementações do fabricante. Consumo do tileset pelo cliente pesado do concorrente
  segue **PENDENTE (D20)**: depende de credencial do parceiro e não foi medido — a rota do tileset é
  autenticada pela porta padrão da casa (sessão ou token de serviço com escopo `catalogo:ler`).
