# ADR: regras de conectividade da rede de utilidades (item L4-03-a-regras-de-conectividade)

## Contexto

O item L4-01-a-pacote-de-ativos entregou o esquema (domínios, tiers, grupos, tipos, categorias,
atributos, terminais) e uma tabela `plat.rede_regra` já com quatro tipos, mas sem nada que a
imponha sobre feição: o pacote elétrico trazia 24 regras que nunca eram avaliadas na edição, e
o portão deste item pede paridade com a *utility network* da Esri, onde uma conexão ou associação
"can only exist if a rule exists" (`about-utility-network-restrictions-and-rules.htm`).

## Decisão

1. **Cinco tipos de regra**, não quatro: `juncao_juncao`, `juncao_aresta`, `aresta_juncao_aresta`,
   `contencao`, `estrutura` — os mesmos quatro grupos de regra da Esri (*Junction-Junction*,
   *Junction-Edge*, *Edge-Junction-Edge*, *Containment*, *Structural Attachment*), com
   `aresta_juncao_aresta` isolado de `juncao_aresta` porque o papel da junção do meio é distinto
   (via, não terminal). A migração `20260906T2058_rede_regras_conectividade.sql` troca
   `plat.rede_regra` para essa forma (`tipo`, `de_tipo_id`, `para_tipo_id`, `via_tipo_id`,
   `de_terminal`, `para_terminal`, `via_terminal`) e acrescenta `plat.rede_feicao`,
   `plat.rede_conexao` (derivada, nunca editada à mão) e `plat.rede_associacao` (explícita).
2. **"Sem regra = proibido" é a política padrão**, sem exceção por atributo de feição: a única
   comporta é `plat.rede.regras_ativas` (booleano, padrão `true`), e só o privilégio
   `rede.administrar` (migração `20260906T2219_rede_administrar_regras.sql`) liga/desliga. Isso
   separa quem edita feição (`rede.editar`) de quem pode desligar a avaliação em massa — o mesmo
   cuidado que a Esri registra em *"Manage editing options for a utility network"* sobre carga em
   lote sem regra.
3. **Conexão é DERIVADA da geometria, nunca recebida no corpo do `applyEdits`**: junção-junção por
   coincidência de ponto, junção-aresta pela ponta da aresta tocando a junção, aresta-junção-aresta
   por duas arestas na mesma junção — tolerância 0,5 m (geography), a mesma ordem de grandeza do
   que a Esri chama de *snapping* na edição de rede. Associação (contenção/estrutura) é sempre
   explícita e direcional (quem contém, quem é contido).
4. **CSV nas 13 colunas de Import/Export Rules do ArcGIS Pro 3.4** (`regras_csv.py`), com uma
   diferença documentada: a ferramenta da Esri ACRESCENTA ao importar; aqui a importação
   SUBSTITUI o conjunto inteiro numa transação (ato de `rede.administrar`). O motivo: sem
   histórico de regra por linha (a Esri tem `RuleID` estável entre exportações), acrescentar sem
   remover deixaria regra órfã sem forma de limpar pela mesma ferramenta.
5. Corpo do CSV não é JSON: sob sessão de navegador o CSRF (ADR 0002 §5.3, "corpo só JSON")
   recusa com 415 antes do privilégio — mesma regra já aplicada a upload de arquivo (ADR 0006,
   "upload só por token, nunca cookie"). Não é uma exceção nova, é o mesmo portão.

## Mensagem de recusa

Toda recusa (`sem_regra` ou `terminal_errado`) cita a regra ou as regras candidatas na mensagem e
no corpo JSON (`regras_candidatas`), no formato `<tipo> <grupo/tipo> -> <grupo/tipo>` — o
equivalente textual ao que a Esri mostra na paleta de erro do editor de rede. As funções de
avaliação (`app/rede_utilidades/regras.py`) são puras: recebem a lista de regras já carregada e o
pedido, devolvem a regra que casou ou a violação com as candidatas.

## Fronteira honesta

Regra `via_terminal` (terminal do lado VIA da aresta-junção-aresta) é aceita no esquema e no CSV
mas nenhuma regra do pacote `eletrica-br` a usa — não foi possível testar essa combinação com dado
real; fica como pendência nomeada, não como capacidade "feita". Validação de caminho válido dentro
de um terminal com múltiplos caminhos (*valid paths*, Esri) não está neste item — é o traçado.

A `descricao` de uma regra (existe no pacote JSON versão 2, citada na mensagem de recusa) NÃO é uma
das 13 colunas de Import/Export Rules — o round-trip "exportar e reimportar dá o mesmo conjunto" vale
para tipo/de/para/via/terminais (o que a Esri também garante), nunca para a descrição: uma regra
substituída por CSV perde a descrição que tinha (fica `NULL`) até que o pacote seja reimportado por
cima. `tests/api/test_regras_csv.py::test_exportar_e_reimportar_da_o_mesmo_conjunto_de_regras` prova
os dois lados: mesmo conjunto citável, descrição não sobrevive ao CSV.
