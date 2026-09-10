# Paridade do pacote de gás com a Gas Utility Network Foundation

Item `L4-05-e-gas-e-esgoto`. Uma linha por elemento do modelo de gás da Esri; a coluna "nós" descreve o que
existe hoje no repositório (pacote `gas-br` e as rotas de `app/rede_utilidades/`), e "estado" é `feito`,
`parcial` ou `fora` (fora do escopo por decisão, com o motivo escrito).

⛔ **O que NÃO foi conferido nesta entrega.** A fonte declarada pelo item
(`https://solutions.arcgis.com/utilities/gas/help/gas-utility-network-foundation/`) foi buscada por HTTP em
08/09/2026 e respondeu **HTTP 200 com o conteúdo do índice geral do ArcGIS Solutions**, não com a página do
modelo de gás: nenhum nome de classe, campo, código de subtipo ou regra da Esri pôde ser lido de lá nesta
passagem. A coluna "Esri" abaixo descreve a ESTRUTURA da Utility Network (rede de domínio, tier, classe de
ativo, configuração de terminal, regra de conectividade, controlador de subrede), que é a moldura pública do
produto, e **não** cita nome de campo nem código de subtipo do pacote deles. Nenhuma linha desta tabela vale
como medição contra o produto da Esri: paridade de verdade exige o pacote de ativos deles, que este item não
tem — a mesma fronteira já registrada no item irmão do EPANET (`tests/medidas/L4-05-d-epanet-inp.json`).

| elemento do modelo | Esri (estrutura da Utility Network) | nós (`gas-br`) | estado |
|---|---|---|---|
| rede de domínio de gás | uma rede de domínio para o gás | `gas_distribuicao`, disciplina `gas` | feito |
| rede de domínio de estrutura | rede de estrutura separada (poste, duto, câmara), sem fluido | não existe no pacote de gás | fora (decisão: a rede de estrutura é do pacote elétrico `eletrica-br`, onde há dado real) |
| tier por pressão | tiers hierárquicos do transporte à baixa pressão | 4 tiers hierárquicos: `transporte` (1), `alta_pressao` (2), `media_pressao` (3), `baixa_pressao` (4) | feito |
| classe de dispositivo (device) | ativo pontual que controla o fluido | grupos `regulador`, `valvula_de_gas`, `estacao_de_medicao`, `ponto_de_entrega` | feito |
| classe de junção (junction) | ponto de conexão sem equipamento | grupo `juncao_de_gas`, um tipo por tier | feito |
| classe de linha (line) | trecho condutor | grupo `tubulacao_de_gas`, um tipo por tier mais ramal e trecho desativado | feito |
| classe de conjunto (assembly) | agrupamento de ativos que se opera junto | grupos `city_gate` e `estacao_de_medicao`, com regras `conectividade_entre_nos` ligando os componentes | parcial (o conjunto é declarado por regra, não é um objeto que contém os filhos) |
| subtipo com código inteiro | subtipo numerado por classe | `tipos[].codigo` inteiro por grupo, com `chave` estável | feito |
| configuração de terminal | terminal único, duplo, caminhos válidos | 3 configurações: `um_terminal`, `dois_terminais` (1→2), `dois_terminais_bidirecional` (1→2 e 2→1) | feito |
| regra de conectividade | o que se liga a quê | 29 regras `conectividade_no_trecho` e `conectividade_entre_nos` | feito |
| regra de contenção e de fixação | associação de contenção/fixação estrutural | o formato aceita (`contencao`, `fixacao_estrutural`) e o pacote de gás não usa nenhuma | parcial (formato pronto, dado ausente) |
| controlador de subrede | o ativo que define a subrede e por onde a pressão entra | o `city_gate` é a `fonte` do tier de transporte e o `regulador` muda de tier; não há tabela de subrede calculada para gás | parcial (o traçado `conectado`/`subrede` do L4-02-a roda sobre a topologia derivada, sem estado de válvula) |
| atributo de rede (network attribute) | atributo propagado pela rede, como pressão | não existe propagação | fora (L4-02 e seguintes; a conferência de pressão deste item é por tier declarado, não por propagação) |
| validação de topologia com área suja | dirty areas e validação | `plat.rede_topo_area_suja` mais `POST /api/rede/{id}/topologia/habilitar` (item L4-01-b) | feito |
| conferência de degrau de pressão | regra de rede que impede ligar tiers diferentes sem controlador | `GET /api/rede/{id}/gas/pressao`: regulador que eleva pressão, regulador sem transição, tier desconhecido e emenda entre tiers sem controlador a menos da tolerância da rede | feito (nós conferimos e NOMEAMOS; não impedimos a gravação) |

## O que esta tabela não diz

- Não diz que somos compatíveis com o pacote de ativos da Esri: importar o modelo deles exigiria o de-para
  campo a campo, que depende do arquivo do produto.
- Não diz que a conferência de pressão substitui a validação de topologia da Utility Network: ela olha o tier
  declarado no pacote e a distância entre as pontas, não um grafo de subrede com estado de válvula.
- O pacote `esgoto-teksi`, ao contrário deste, tem coluna de origem em todo atributo, porque o modelo TEKSI é
  aberto e a definição de tabela do projeto pôde ser lida (ver `docs/PACOTE_REDE.md` e o ADR do item).
