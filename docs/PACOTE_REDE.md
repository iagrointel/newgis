# Pacote de ativos da rede de utilidades

Documento gerado de `app/rede_utilidades/pacotes/*.json` por `docs/gerar_pacote_rede.py`. Não edite à mão: mude
o pacote e rode o gerador.

Um pacote de ativos descreve o ESQUEMA de uma rede — redes de domínio, tiers, grupos e tipos de ativo,
categorias, atributos e configurações de terminal — como dado versionado, não como código. O mesmo formato serve
para elétrica, água, gás, esgoto e telecom; é ele que se importa e se exporta entre inquilinos
(`POST`/`GET /api/rede/{rede_id}/pacote`). O contrato do formato está no ADR 0019.

Coluna **conferida**: `sim` quando a coluna de origem foi lida numa extração real do esquema citado; `não`
quando a coluna vem do documento da fonte e ainda não foi vista em dado real. Nenhum atributo com `não` deve ser
usado para decidir carga de dado sem antes conferir o dicionário da entrega.


## `agua-epanet` — Água de abastecimento (modelo EPANET 2.2)

Pacote de ativos da rede de água de abastecimento no vocabulário do EPANET 2.2: nó, tubulação, bomba, válvula, reservatório de nível variável e reservatório de nível fixo. Os atributos seguem os campos das seções do arquivo .inp. Nenhum campo foi conferido contra um arquivo real nesta entrega: todo atributo sai com origem.conferida = false.

| campo | valor |
|---|---|
| versão do pacote | 1.0.0 |
| versão do esquema | 1 |
| disciplina | agua |
| fonte | https://www.epa.gov/water-research/epanet |
| tamanho | 27765 bytes |
| sha256 | `1a6bbe11731451a38f58df1e0ba264c3b2959666fd5a8ea8eb340937c5a26789` |

### Redes de domínio e tiers

| domínio | tipo do domínio | tier | ordem | tipo do tier | o que é |
|---|---|---|---|---|---|
| `agua_distribuicao` | dominio | `aducao` | 1 | hierarquico | Da fonte ao reservatório de distribuição. |
| `agua_distribuicao` | dominio | `distribuicao` | 2 | hierarquico | Do reservatório ao ponto de consumo. |

### Categorias de rede

| categoria | nome | o que significa no traçado |
|---|---|---|
| `armazenamento` | Armazenamento | Guarda volume e amortece a variação de demanda. |
| `bombeamento` | Bombeamento | Acrescenta carga hidráulica. |
| `conducao` | Condução | Conduz sem bombear nem controlar. |
| `consumo` | Consumo | Ponto final que retira água da rede. |
| `controle_de_pressao` | Controle de pressão | Impõe pressão a montante ou a jusante. |
| `controle_de_vazao` | Controle de vazão | Limita ou impõe vazão. |
| `fonte` | Fonte | Onde a água entra na rede; o traçado a montante termina aqui. |
| `seccionamento` | Seccionamento | Abre ou fecha o escoamento por manobra. |

### Configurações de terminal

| configuração | nome | terminais | caminhos válidos |
|---|---|---|---|
| `dois_terminais` | Dois terminais | 1=montante, 2=jusante | 1→2 (aberto) |
| `um_terminal` | Um terminal | 1=conexao | — |

### Grupos e tipos de ativo

| grupo | geometria | camada de origem | código do tipo | chave | nome | tier | categorias | códigos na fonte |
|---|---|---|---|---|---|---|---|---|
| `bomba` | ponto | [PUMPS] | 1 | `bomba_com_curva` | Bomba com curva característica | aducao | bombeamento | HEAD |
| `bomba` | ponto | [PUMPS] | 2 | `bomba_de_potencia_constante` | Bomba de potência constante | aducao | bombeamento | POWER |
| `no` | ponto | [JUNCTIONS] | 1 | `no_de_demanda` | Nó de demanda | distribuicao | consumo | — |
| `no` | ponto | [JUNCTIONS] | 2 | `no_com_emissor` | Nó com emissor | distribuicao | consumo | EMITTER |
| `reservatorio_de_nivel_fixo` | ponto | [RESERVOIRS] | 1 | `reservatorio_de_nivel_fixo` | Reservatório de nível fixo | aducao | fonte | — |
| `reservatorio_de_nivel_variavel` | ponto | [TANKS] | 1 | `reservatorio_de_nivel_variavel` | Reservatório de nível variável | aducao | armazenamento | — |
| `tubulacao` | linha | [PIPES] | 1 | `tubulacao` | Tubulação | distribuicao | conducao | Closed, Open |
| `tubulacao` | linha | [PIPES] | 2 | `tubulacao_com_valvula_de_retencao` | Tubulação com válvula de retenção | distribuicao | conducao | CV |
| `valvula` | ponto | [VALVES] | 1 | `valvula_redutora_de_pressao` | Válvula redutora de pressão | distribuicao | controle_de_pressao | PRV |
| `valvula` | ponto | [VALVES] | 2 | `valvula_sustentadora_de_pressao` | Válvula sustentadora de pressão | distribuicao | controle_de_pressao | PSV |
| `valvula` | ponto | [VALVES] | 3 | `valvula_de_quebra_de_pressao` | Válvula de quebra de pressão | distribuicao | controle_de_pressao | PBV |
| `valvula` | ponto | [VALVES] | 4 | `valvula_controladora_de_vazao` | Válvula controladora de vazão | distribuicao | controle_de_vazao | FCV |
| `valvula` | ponto | [VALVES] | 5 | `valvula_de_perda_de_carga` | Válvula de perda de carga | distribuicao | controle_de_vazao, seccionamento | TCV |
| `valvula` | ponto | [VALVES] | 6 | `valvula_de_curva_geral` | Válvula de curva geral | distribuicao | controle_de_vazao | GPV |

### Atributos: mapeamento coluna a coluna

| camada de origem | coluna | grupo | atributo | nome | tipo | unidade | obrigatório | conferida | observação |
|---|---|---|---|---|---|---|---|---|---|
| [PUMPS] | `ID` | `bomba` | `bomba_id` | identificador da bomba | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PUMPS] | `Node1` | `bomba` | `bomba_no_1` | nó de sucção | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PUMPS] | `Node2` | `bomba` | `bomba_no_2` | nó de recalque | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PUMPS] | `PATTERN` | `bomba` | `bomba_padrao_de_operacao` | padrão temporal de operação | texto | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PUMPS] | `SPEED` | `bomba` | `bomba_rotacao_relativa` | rotação relativa | real | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PUMPS] | `HEAD` | `bomba` | `bomba_curva` | curva característica | texto | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PUMPS] | `POWER` | `bomba` | `bomba_potencia` | potência constante | real | kW | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [JUNCTIONS] | `Demand` | `no` | `no_demanda` | demanda de base | real | L/s | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [JUNCTIONS] | `Elev` | `no` | `no_elevacao` | cota do nó | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [JUNCTIONS] | `ID` | `no` | `no_id` | identificador do nó | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [JUNCTIONS] | `Pattern` | `no` | `no_padrao_de_demanda` | padrão temporal da demanda | texto | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [COORDINATES] | `X-Coord` | `no` | `no_x` | coordenada X do nó | real | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [COORDINATES] | `Y-Coord` | `no` | `no_y` | coordenada Y do nó | real | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [EMITTERS] | `Coefficient` | `no` | `no_coeficiente_de_emissor` | coeficiente do emissor | real | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [RESERVOIRS] | `Head` | `reservatorio_de_nivel_fixo` | `reservatorio_fixo_carga` | carga hidráulica | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [RESERVOIRS] | `ID` | `reservatorio_de_nivel_fixo` | `reservatorio_fixo_id` | identificador do reservatório | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [RESERVOIRS] | `Pattern` | `reservatorio_de_nivel_fixo` | `reservatorio_fixo_padrao_de_carga` | padrão temporal da carga | texto | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `Elevation` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_cota_de_fundo` | cota de fundo | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `VolCurve` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_curva_de_volume` | curva de volume | texto | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `Diameter` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_diametro` | diâmetro | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `Overflow` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_extravasa` | permite extravasamento | booleano | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `ID` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_id` | identificador do reservatório | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `InitLevel` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_nivel_inicial` | nível inicial | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `MaxLevel` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_nivel_maximo` | nível máximo | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `MinLevel` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_nivel_minimo` | nível mínimo | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [TANKS] | `MinVol` | `reservatorio_de_nivel_variavel` | `reservatorio_variavel_volume_minimo` | volume mínimo | real | m3 | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PIPES] | `Length` | `tubulacao` | `tubulacao_comprimento` | comprimento | real | m | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PIPES] | `Diameter` | `tubulacao` | `tubulacao_diametro` | diâmetro interno | real | mm | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PIPES] | `ID` | `tubulacao` | `tubulacao_id` | identificador da tubulação | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PIPES] | `Node1` | `tubulacao` | `tubulacao_no_1` | nó inicial | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PIPES] | `Node2` | `tubulacao` | `tubulacao_no_2` | nó final | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PIPES] | `MinorLoss` | `tubulacao` | `tubulacao_perda_localizada` | coeficiente de perda localizada | real | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [PIPES] | `Roughness` | `tubulacao` | `tubulacao_rugosidade` | coeficiente de rugosidade | real | — | sim | não | a unidade depende da fórmula de perda de carga escolhida em [OPTIONS] (Hazen-Williams, Darcy-Weisbach ou Chezy-Manning) |
| [PIPES] | `Status` | `tubulacao` | `tubulacao_situacao` | situação inicial | texto | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [VERTICES] | `X-Coord;Y-Coord` | `tubulacao` | `tubulacao_vertices` | vértices do traçado | geometria | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [VALVES] | `Setting` | `valvula` | `valvula_ajuste` | valor de ajuste | real | — | sim | não | a unidade depende do tipo: pressão (m) nas de pressão, vazão (L/s) na controladora de vazão, adimensional na de perda de carga |
| [VALVES] | `Diameter` | `valvula` | `valvula_diametro` | diâmetro | real | mm | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [VALVES] | `ID` | `valvula` | `valvula_id` | identificador da válvula | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [VALVES] | `Node1` | `valvula` | `valvula_no_1` | nó de montante | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [VALVES] | `Node2` | `valvula` | `valvula_no_2` | nó de jusante | texto | — | sim | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |
| [VALVES] | `MinorLoss` | `valvula` | `valvula_perda_localizada` | coeficiente de perda localizada | real | — | não | não | campo do arquivo .inp do EPANET 2.2; não conferido contra arquivo real nesta entrega |

Total: 41 atributos, 0 com origem conferida em extração real e 41 declarados da fonte sem conferência.


### Regras de conexão

| tipo de regra | de | para | o que diz |
|---|---|---|---|
| conectividade_no_trecho | `tubulacao/1` | `bomba/1` | bomba em série na tubulação |
| conectividade_no_trecho | `tubulacao/1` | `bomba/2` | bomba em série na tubulação |
| conectividade_no_trecho | `tubulacao/1` | `no/1` | tubulação ligada ao nó |
| conectividade_no_trecho | `tubulacao/1` | `no/2` | tubulação ligada ao nó |
| conectividade_no_trecho | `tubulacao/1` | `reservatorio_de_nivel_fixo/1` | tubulação ligada ao nó |
| conectividade_no_trecho | `tubulacao/1` | `reservatorio_de_nivel_variavel/1` | tubulação ligada ao nó |
| conectividade_no_trecho | `tubulacao/1` | `valvula/1` | válvula em série na tubulação |
| conectividade_no_trecho | `tubulacao/1` | `valvula/2` | válvula em série na tubulação |
| conectividade_no_trecho | `tubulacao/1` | `valvula/3` | válvula em série na tubulação |
| conectividade_no_trecho | `tubulacao/1` | `valvula/4` | válvula em série na tubulação |
| conectividade_no_trecho | `tubulacao/1` | `valvula/5` | válvula em série na tubulação |
| conectividade_no_trecho | `tubulacao/1` | `valvula/6` | válvula em série na tubulação |
| conectividade_no_trecho | `tubulacao/2` | `no/1` | tubulação com válvula de retenção ligada ao nó |
| conectividade_no_trecho | `tubulacao/2` | `no/2` | tubulação com válvula de retenção ligada ao nó |
| conectividade_no_trecho | `tubulacao/2` | `reservatorio_de_nivel_fixo/1` | tubulação com válvula de retenção ligada ao nó |
| conectividade_no_trecho | `tubulacao/2` | `reservatorio_de_nivel_variavel/1` | tubulação com válvula de retenção ligada ao nó |

## `eletrica-br` — Elétrica de distribuição (Brasil, BDGD Módulo 10)

Pacote de ativos da rede elétrica de distribuição brasileira, no recorte das 13 camadas de rede da BDGD (Módulo 10 do PRODIST). Dez camadas têm mapeamento coluna a coluna conferido contra uma extração real de distribuidora; cinco camadas (SUB, UNSEMT, UNCRMT, UNREMT, UGMT_tab) trazem colunas declaradas do Módulo 10, ainda não conferidas — cada atributo diz qual é o seu caso em origem.conferida.

| campo | valor |
|---|---|
| versão do pacote | 1.1.0 |
| versão do esquema | 1 |
| disciplina | eletrica |
| fonte | https://dadosabertos.aneel.gov.br/dataset/base-de-dados-geografica-da-distribuidora-bdgd |
| tamanho | 96372 bytes |
| sha256 | `036423f672a5f1710e41624fa707561924999e68fde7e8de691c19d491de74c1` |

### Redes de domínio e tiers

| domínio | tipo do domínio | tier | ordem | tipo do tier | o que é |
|---|---|---|---|---|---|
| `estrutura` | estrutura | `estrutura` | 1 | particionado | Rede de estrutura: o que sustenta a rede elétrica, sem energia própria. |
| `eletrica_distribuicao` | dominio | `subtransmissao` | 1 | hierarquico | Alta tensão até a subestação de distribuição. |
| `eletrica_distribuicao` | dominio | `media_tensao` | 2 | hierarquico | Da saída da subestação ao primário do transformador de distribuição; a subrede é o alimentador. |
| `eletrica_distribuicao` | dominio | `baixa_tensao` | 3 | hierarquico | Do secundário do transformador de distribuição ao ponto de entrega. |

### Categorias de rede

| categoria | nome | o que significa no traçado |
|---|---|---|
| `conducao` | Condução | Conduz sem transformar nem interromper. |
| `consumo` | Consumo | Ponto final que retira energia da rede. |
| `controlador` | Controlador | Ajusta grandeza elétrica (tensão, reativo) sem interromper o circuito. |
| `derivacao` | Derivação | Ponto de derivação no meio do trecho (equivalente ao 'subnetwork tap' do modelo Esri): a derivação sai da linha principal e o traçado de subrede para nela. Só pode ser atribuída a tipo de ativo de ponto com um único terminal. |
| `dispositivo_de_protecao` | Dispositivo de proteção | Interrompe sozinho diante de defeito. |
| `estrutura_de_suporte` | Estrutura de suporte | Sustenta o condutor e o equipamento; não conduz. |
| `fonte` | Fonte | Onde a energia entra na rede; o traçado a montante termina aqui. |
| `geracao` | Geração | Ponto que injeta energia na rede de distribuição. |
| `iluminacao` | Iluminação pública | Carga de iluminação pública, faturada por estimativa. |
| `medicao` | Medição | Ponto onde a energia é medida para faturamento. |
| `seccionamento` | Seccionamento | Abre ou fecha o circuito por manobra. |
| `transformacao` | Transformação | Muda o nível de tensão e separa duas subredes. |

### Configurações de terminal

| configuração | nome | terminais | caminhos válidos |
|---|---|---|---|
| `dois_terminais` | Dois terminais | 1=lado_1, 2=lado_2 | 1→2 (fechado) |
| `dois_terminais_transformador` | Dois terminais (alta e baixa) | 1=alta, 2=baixa | 1→2 (alta_para_baixa) |
| `sem_terminal` | Sem terminal | — | — |
| `um_terminal` | Um terminal | 1=conexao | — |

### Grupos e tipos de ativo

| grupo | geometria | camada de origem | código do tipo | chave | nome | tier | categorias | códigos na fonte |
|---|---|---|---|---|---|---|---|---|
| `alimentador` | sem_geometria | CTMT | 1 | `alimentador_de_distribuicao` | Alimentador de distribuição | media_tensao | fonte | — |
| `banco_de_capacitores` | ponto | UNCRMT | 1 | `banco_de_capacitores` | Banco de capacitores | media_tensao | controlador | — |
| `chave_de_media_tensao` | ponto | UNSEMT | 1 | `chave_faca` | Chave faca | media_tensao | seccionamento | — |
| `chave_de_media_tensao` | ponto | UNSEMT | 2 | `chave_fusivel` | Chave fusível | media_tensao | dispositivo_de_protecao, seccionamento | — |
| `chave_de_media_tensao` | ponto | UNSEMT | 3 | `religador` | Religador | media_tensao | controlador, dispositivo_de_protecao | — |
| `chave_de_media_tensao` | ponto | UNSEMT | 4 | `disjuntor` | Disjuntor | media_tensao | dispositivo_de_protecao | — |
| `chave_de_media_tensao` | ponto | UNSEMT | 5 | `seccionalizador` | Seccionalizador | media_tensao | dispositivo_de_protecao, seccionamento | — |
| `equipamento_do_transformador` | sem_geometria | EQTRMT | 1 | `equipamento_do_transformador` | Equipamento do transformador | media_tensao | transformacao | — |
| `geracao_distribuida` | ponto | UGBT_tab, UGMT_tab | 1 | `geracao_em_baixa_tensao` | Geração em baixa tensão | baixa_tensao | geracao, medicao | — |
| `geracao_distribuida` | ponto | UGBT_tab, UGMT_tab | 2 | `geracao_em_media_tensao` | Geração em média tensão | baixa_tensao | geracao, medicao | — |
| `ponto_de_iluminacao_publica` | ponto | PIP | 1 | `ponto_de_iluminacao_publica` | Ponto de iluminação pública | baixa_tensao | consumo, iluminacao | — |
| `ponto_notavel` | ponto | PONNOT | 1 | `poste` | Poste | estrutura | estrutura_de_suporte | POS |
| `ponto_notavel` | ponto | PONNOT | 2 | `torre` | Torre | estrutura | estrutura_de_suporte | TOR |
| `ponto_notavel` | ponto | PONNOT | 3 | `ponto_notavel_nao_classificado` | Ponto notável ainda não classificado | estrutura | estrutura_de_suporte | — |
| `ramal_de_ligacao` | linha | RAMLIG | 1 | `ramal_de_ligacao` | Ramal de ligação | baixa_tensao | conducao | — |
| `regulador_de_tensao` | ponto | UNREMT | 1 | `regulador_de_tensao` | Regulador de tensão | media_tensao | controlador | — |
| `subestacao` | ponto | SUB | 1 | `subestacao_de_distribuicao` | Subestação de distribuição | subtransmissao | fonte | — |
| `transformador_de_distribuicao` | ponto | UNTRMT | 1 | `transformador_de_distribuicao` | Transformador de distribuição | media_tensao | transformacao | T |
| `transformador_de_distribuicao` | ponto | UNTRMT | 2 | `banco_de_transformadores` | Banco de transformadores | media_tensao | transformacao | B |
| `transformador_de_distribuicao` | ponto | UNTRMT | 3 | `transformador_nao_classificado` | Transformador ainda não classificado | media_tensao | transformacao | — |
| `trecho_de_baixa_tensao` | linha | SSDBT | 1 | `trecho_de_baixa_tensao` | Trecho de baixa tensão | baixa_tensao | conducao | — |
| `trecho_de_media_tensao` | linha | SSDMT | 1 | `trecho_de_media_tensao` | Trecho de média tensão | media_tensao | conducao | — |
| `unidade_consumidora` | ponto | UCBT_tab, UCMT_tab | 1 | `consumidor_de_baixa_tensao` | Consumidor de baixa tensão | baixa_tensao | consumo, derivacao, medicao | — |
| `unidade_consumidora` | ponto | UCBT_tab, UCMT_tab | 2 | `consumidor_de_media_tensao` | Consumidor de média tensão | baixa_tensao | consumo, medicao | — |

### Atributos: mapeamento coluna a coluna

| camada de origem | coluna | grupo | atributo | nome | tipo | unidade | obrigatório | conferida | observação |
|---|---|---|---|---|---|---|---|---|---|
| CTMT | `COD_ID` | `alimentador` | `ctmt_cod_id` | código do objeto | texto | — | sim | sim |  |
| CTMT | `DIST` | `alimentador` | `ctmt_dist` | código da distribuidora na ANEEL | texto | — | não | sim |  |
| CTMT | `SUB` | `alimentador` | `ctmt_sub` | subestação a que pertence | texto | — | não | sim |  |
| CTMT | `TEN_NOM` | `alimentador` | `ctmt_ten_nom` | tensão nominal | real | kV | não | sim |  |
| CTMT | `TEN_OPE` | `alimentador` | `ctmt_ten_ope` | tensão de operação | real | kV | não | sim |  |
| UNCRMT | `COD_ID` | `banco_de_capacitores` | `uncrmt_cod_id` | código do objeto | texto | — | sim | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `CTMT` | `banco_de_capacitores` | `uncrmt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `DAT_CON` | `banco_de_capacitores` | `uncrmt_dat_con` | data de conexão | data | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `FAS_CON` | `banco_de_capacitores` | `uncrmt_fas_con` | fases conectadas | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `PAC_1` | `banco_de_capacitores` | `uncrmt_pac_1` | ponto de atendimento da conexão 1 | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `POT_NOM` | `banco_de_capacitores` | `uncrmt_pot_nom` | potência nominal | real | kVA | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `SIT_ATIV` | `banco_de_capacitores` | `uncrmt_sit_ativ` | situação de ativação | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `SUB` | `banco_de_capacitores` | `uncrmt_sub` | subestação a que pertence | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `TEN_NOM` | `banco_de_capacitores` | `uncrmt_ten_nom` | tensão nominal | real | kV | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `TIP_UNID` | `banco_de_capacitores` | `uncrmt_tip_unid` | tipo de unidade de cadastro | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `UNI_TR_AT` | `banco_de_capacitores` | `uncrmt_uni_tr_at` | unidade transformadora de alta tensão | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNCRMT | `X` | `banco_de_capacitores` | `uncrmt_x` | longitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| UNCRMT | `Y` | `banco_de_capacitores` | `uncrmt_y` | latitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| UNSEMT | `COD_ID` | `chave_de_media_tensao` | `unsemt_cod_id` | código do objeto | texto | — | sim | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `CTMT` | `chave_de_media_tensao` | `unsemt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `DAT_CON` | `chave_de_media_tensao` | `unsemt_dat_con` | data de conexão | data | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `FAS_CON` | `chave_de_media_tensao` | `unsemt_fas_con` | fases conectadas | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `P_N_OPE` | `chave_de_media_tensao` | `unsemt_p_n_ope` | posição normal de operação | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `PAC_1` | `chave_de_media_tensao` | `unsemt_pac_1` | ponto de atendimento da conexão 1 | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `PAC_2` | `chave_de_media_tensao` | `unsemt_pac_2` | ponto de atendimento da conexão 2 | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `POS` | `chave_de_media_tensao` | `unsemt_pos` | posição | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `SIT_ATIV` | `chave_de_media_tensao` | `unsemt_sit_ativ` | situação de ativação | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `SUB` | `chave_de_media_tensao` | `unsemt_sub` | subestação a que pertence | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `TIP_UNID` | `chave_de_media_tensao` | `unsemt_tip_unid` | tipo de unidade de cadastro | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `UNI_TR_AT` | `chave_de_media_tensao` | `unsemt_uni_tr_at` | unidade transformadora de alta tensão | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNSEMT | `X` | `chave_de_media_tensao` | `unsemt_x` | longitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| UNSEMT | `Y` | `chave_de_media_tensao` | `unsemt_y` | latitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| EQTRMT | `COD_ID` | `equipamento_do_transformador` | `eqtrmt_cod_id` | código do objeto | texto | — | sim | sim |  |
| EQTRMT | `FAS_CON` | `equipamento_do_transformador` | `eqtrmt_fas_con` | fases conectadas | texto | — | não | sim |  |
| EQTRMT | `PER_FER` | `equipamento_do_transformador` | `eqtrmt_per_fer` | perdas no ferro | real | kW | não | sim |  |
| EQTRMT | `PER_TOT` | `equipamento_do_transformador` | `eqtrmt_per_tot` | perdas totais | real | kW | não | sim |  |
| EQTRMT | `POT_NOM` | `equipamento_do_transformador` | `eqtrmt_pot_nom` | potência nominal | real | kVA | não | sim |  |
| EQTRMT | `TEN_PRI` | `equipamento_do_transformador` | `eqtrmt_ten_pri` | tensão do primário | real | kV | não | sim |  |
| EQTRMT | `TEN_SEC` | `equipamento_do_transformador` | `eqtrmt_ten_sec` | tensão do secundário | real | kV | não | sim |  |
| EQTRMT | `UNI_TR_MT` | `equipamento_do_transformador` | `eqtrmt_uni_tr_mt` | unidade transformadora de média tensão | texto | — | não | sim |  |
| UGBT_tab | `CEG_GD` | `geracao_distribuida` | `ugbt_ceg_gd` | código do empreendimento de geração distribuída | texto | — | não | sim |  |
| UGBT_tab | `CNAE` | `geracao_distribuida` | `ugbt_cnae` | atividade econômica (CNAE) | texto | — | não | sim |  |
| UGBT_tab | `COD_ID` | `geracao_distribuida` | `ugbt_cod_id` | código do objeto | texto | — | sim | sim |  |
| UGBT_tab | `CONJ` | `geracao_distribuida` | `ugbt_conj` | conjunto elétrico | texto | — | não | sim |  |
| UGBT_tab | `CTMT` | `geracao_distribuida` | `ugbt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| UGBT_tab | `DAT_CON` | `geracao_distribuida` | `ugbt_dat_con` | data de conexão | data | — | não | sim |  |
| UGBT_tab | `ENE_SUM` | `geracao_distribuida` | `ugbt_ene_sum` | energia anual | real | MWh | não | sim | soma de ENE_01..ENE_12 feita pela extração |
| UGBT_tab | `ENE_ZERO` | `geracao_distribuida` | `ugbt_ene_zero` | meses com energia zero | inteiro | meses | não | sim | contagem sobre ENE_01..ENE_12 feita pela extração |
| UGBT_tab | `MUN` | `geracao_distribuida` | `ugbt_mun` | município (código IBGE) | texto | — | não | sim |  |
| UGBT_tab | `PN_CON` | `geracao_distribuida` | `ugbt_pn_con` | ponto notável de conexão | texto | — | não | sim |  |
| UGBT_tab | `POT_SUM` | `geracao_distribuida` | `ugbt_pot_sum` | potência anual da geração | real | kW | não | sim | soma de POT_01..POT_12 feita pela extração |
| UGBT_tab | `POT_ZERO` | `geracao_distribuida` | `ugbt_pot_zero` | meses com potência zero | inteiro | meses | não | sim | contagem sobre POT_01..POT_12 feita pela extração |
| UGBT_tab | `SIT_ATIV` | `geracao_distribuida` | `ugbt_sit_ativ` | situação de ativação | texto | — | não | sim |  |
| UGBT_tab | `SUB` | `geracao_distribuida` | `ugbt_sub` | subestação a que pertence | texto | — | não | sim |  |
| UGBT_tab | `UNI_TR_MT` | `geracao_distribuida` | `ugbt_uni_tr_mt` | unidade transformadora de média tensão | texto | — | não | sim |  |
| UGMT_tab | `CEG_GD` | `geracao_distribuida` | `ugmt_ceg_gd` | código do empreendimento de geração distribuída | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `CNAE` | `geracao_distribuida` | `ugmt_cnae` | atividade econômica (CNAE) | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `COD_ID` | `geracao_distribuida` | `ugmt_cod_id` | código do objeto | texto | — | sim | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `CONJ` | `geracao_distribuida` | `ugmt_conj` | conjunto elétrico | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `CTMT` | `geracao_distribuida` | `ugmt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `DAT_CON` | `geracao_distribuida` | `ugmt_dat_con` | data de conexão | data | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `ENE_SUM` | `geracao_distribuida` | `ugmt_ene_sum` | energia anual | real | MWh | não | não | soma de ENE_01..ENE_12 feita pela extração |
| UGMT_tab | `MUN` | `geracao_distribuida` | `ugmt_mun` | município (código IBGE) | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `PN_CON` | `geracao_distribuida` | `ugmt_pn_con` | ponto notável de conexão | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `POT_INST` | `geracao_distribuida` | `ugmt_pot_inst` | potência instalada | real | kVA | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `SIT_ATIV` | `geracao_distribuida` | `ugmt_sit_ativ` | situação de ativação | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UGMT_tab | `SUB` | `geracao_distribuida` | `ugmt_sub` | subestação a que pertence | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| PIP | `ARE_LOC` | `ponto_de_iluminacao_publica` | `pip_are_loc` | área de localização | texto | — | não | sim |  |
| PIP | `CAR_INST` | `ponto_de_iluminacao_publica` | `pip_car_inst` | carga instalada | real | kW | não | sim |  |
| PIP | `CLAS_SUB` | `ponto_de_iluminacao_publica` | `pip_clas_sub` | classe e subclasse de consumo | texto | — | não | sim |  |
| PIP | `COD_ID` | `ponto_de_iluminacao_publica` | `pip_cod_id` | código do objeto | texto | — | sim | sim |  |
| PIP | `CONJ` | `ponto_de_iluminacao_publica` | `pip_conj` | conjunto elétrico | texto | — | não | sim |  |
| PIP | `CONTROLE` | `ponto_de_iluminacao_publica` | `pip_controle` | tipo de controle do acionamento | texto | — | não | sim |  |
| PIP | `CTMT` | `ponto_de_iluminacao_publica` | `pip_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| PIP | `ENE_SUM` | `ponto_de_iluminacao_publica` | `pip_ene_sum` | energia anual | real | MWh | não | sim | soma de ENE_01..ENE_12 feita pela extração |
| PIP | `ENE_ZERO` | `ponto_de_iluminacao_publica` | `pip_ene_zero` | meses com energia zero | inteiro | meses | não | sim | contagem sobre ENE_01..ENE_12 feita pela extração |
| PIP | `MUN` | `ponto_de_iluminacao_publica` | `pip_mun` | município (código IBGE) | texto | — | não | sim |  |
| PIP | `PN_CON` | `ponto_de_iluminacao_publica` | `pip_pn_con` | ponto notável de conexão | texto | — | não | sim |  |
| PIP | `SUB` | `ponto_de_iluminacao_publica` | `pip_sub` | subestação a que pertence | texto | — | não | sim |  |
| PIP | `TIPO_LAMP` | `ponto_de_iluminacao_publica` | `pip_tipo_lamp` | tipo de lâmpada | texto | — | não | sim |  |
| PIP | `UNI_TR_MT` | `ponto_de_iluminacao_publica` | `pip_uni_tr_mt` | unidade transformadora de média tensão | texto | — | não | sim |  |
| PONNOT | `ALT` | `ponto_notavel` | `ponnot_alt` | altura | real | m | não | sim |  |
| PONNOT | `ARE_LOC` | `ponto_notavel` | `ponnot_are_loc` | área de localização | texto | — | não | sim |  |
| PONNOT | `COD_ID` | `ponto_notavel` | `ponnot_cod_id` | código do objeto | texto | — | sim | sim |  |
| PONNOT | `CONJ` | `ponto_notavel` | `ponnot_conj` | conjunto elétrico | texto | — | não | sim |  |
| PONNOT | `DIST` | `ponto_notavel` | `ponnot_dist` | código da distribuidora na ANEEL | texto | — | não | sim |  |
| PONNOT | `ESF` | `ponto_notavel` | `ponnot_esf` | esforço nominal | real | — | não | sim |  |
| PONNOT | `ESTR` | `ponto_notavel` | `ponnot_estr` | estrutura | texto | — | não | sim |  |
| PONNOT | `MAT` | `ponto_notavel` | `ponnot_mat` | material | texto | — | não | sim |  |
| PONNOT | `MUN` | `ponto_notavel` | `ponnot_mun` | município (código IBGE) | texto | — | não | sim |  |
| PONNOT | `POS` | `ponto_notavel` | `ponnot_pos` | posição | texto | — | não | sim |  |
| PONNOT | `SITCONT` | `ponto_notavel` | `ponnot_sitcont` | situação contábil | texto | — | não | sim |  |
| PONNOT | `TIP_INST` | `ponto_notavel` | `ponnot_tip_inst` | tipo de instalação | texto | — | não | sim |  |
| PONNOT | `TIP_PN` | `ponto_notavel` | `ponnot_tip_pn` | tipo de ponto notável | texto | — | não | sim |  |
| PONNOT | `TUC` | `ponto_notavel` | `ponnot_tuc` | tipo de unidade de cadastro (TUC) | texto | — | não | sim |  |
| PONNOT | `X` | `ponto_notavel` | `ponnot_x` | longitude do ponto | real | graus | não | sim | derivada da geometria do ponto pela extração |
| PONNOT | `Y` | `ponto_notavel` | `ponnot_y` | latitude do ponto | real | graus | não | sim | derivada da geometria do ponto pela extração |
| RAMLIG | `COD_ID` | `ramal_de_ligacao` | `ramlig_cod_id` | código do objeto | texto | — | sim | sim |  |
| RAMLIG | `COMP` | `ramal_de_ligacao` | `ramlig_comp` | comprimento do trecho | real | km | não | sim |  |
| RAMLIG | `CTMT` | `ramal_de_ligacao` | `ramlig_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| RAMLIG | `FAS_CON` | `ramal_de_ligacao` | `ramlig_fas_con` | fases conectadas | texto | — | não | sim |  |
| RAMLIG | `TIP_CND` | `ramal_de_ligacao` | `ramlig_tip_cnd` | tipo de condutor (código do cadastro de condutores) | texto | — | não | sim |  |
| RAMLIG | `UNI_TR_MT` | `ramal_de_ligacao` | `ramlig_uni_tr_mt` | unidade transformadora de média tensão | texto | — | não | sim |  |
| RAMLIG | `WKT` | `ramal_de_ligacao` | `ramlig_wkt` | geometria do trecho | geometria | — | não | sim | geometria da linha serializada em WKT pela extração |
| UNREMT | `COD_ID` | `regulador_de_tensao` | `unremt_cod_id` | código do objeto | texto | — | sim | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `CTMT` | `regulador_de_tensao` | `unremt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `DAT_CON` | `regulador_de_tensao` | `unremt_dat_con` | data de conexão | data | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `FAS_CON` | `regulador_de_tensao` | `unremt_fas_con` | fases conectadas | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `PAC_1` | `regulador_de_tensao` | `unremt_pac_1` | ponto de atendimento da conexão 1 | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `PAC_2` | `regulador_de_tensao` | `unremt_pac_2` | ponto de atendimento da conexão 2 | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `POT_NOM` | `regulador_de_tensao` | `unremt_pot_nom` | potência nominal | real | kVA | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `SIT_ATIV` | `regulador_de_tensao` | `unremt_sit_ativ` | situação de ativação | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `SUB` | `regulador_de_tensao` | `unremt_sub` | subestação a que pertence | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `TEN_REG` | `regulador_de_tensao` | `unremt_ten_reg` | tensão de regulação | real | kV | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `TIP_UNID` | `regulador_de_tensao` | `unremt_tip_unid` | tipo de unidade de cadastro | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `UNI_TR_AT` | `regulador_de_tensao` | `unremt_uni_tr_at` | unidade transformadora de alta tensão | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| UNREMT | `X` | `regulador_de_tensao` | `unremt_x` | longitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| UNREMT | `Y` | `regulador_de_tensao` | `unremt_y` | latitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| SUB | `COD_ID` | `subestacao` | `sub_cod_id` | código do objeto | texto | — | sim | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| SUB | `DIST` | `subestacao` | `sub_dist` | código da distribuidora na ANEEL | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| SUB | `MUN` | `subestacao` | `sub_mun` | município (código IBGE) | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| SUB | `NOME` | `subestacao` | `sub_nome` | nome da instalação | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| SUB | `POS` | `subestacao` | `sub_pos` | posição | texto | — | não | não | coluna declarada do Módulo 10, ainda não conferida contra extração real |
| SUB | `X` | `subestacao` | `sub_x` | longitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| SUB | `Y` | `subestacao` | `sub_y` | latitude do ponto | real | graus | não | não | derivada da geometria do ponto pela extração |
| UNTRMT | `ARE_LOC` | `transformador_de_distribuicao` | `untrmt_are_loc` | área de localização | texto | — | não | sim |  |
| UNTRMT | `BANC` | `transformador_de_distribuicao` | `untrmt_banc` | identificação do banco de transformadores | texto | — | não | sim |  |
| UNTRMT | `CAP_ELO` | `transformador_de_distribuicao` | `untrmt_cap_elo` | capacidade do elo fusível | texto | — | não | sim |  |
| UNTRMT | `COD_ID` | `transformador_de_distribuicao` | `untrmt_cod_id` | código do objeto | texto | — | sim | sim |  |
| UNTRMT | `CONF` | `transformador_de_distribuicao` | `untrmt_conf` | configuração de ligação | texto | — | não | sim |  |
| UNTRMT | `CONJ` | `transformador_de_distribuicao` | `untrmt_conj` | conjunto elétrico | texto | — | não | sim |  |
| UNTRMT | `CTMT` | `transformador_de_distribuicao` | `untrmt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| UNTRMT | `DAT_CON` | `transformador_de_distribuicao` | `untrmt_dat_con` | data de conexão | data | — | não | sim |  |
| UNTRMT | `DIST` | `transformador_de_distribuicao` | `untrmt_dist` | código da distribuidora na ANEEL | texto | — | não | sim |  |
| UNTRMT | `MUN` | `transformador_de_distribuicao` | `untrmt_mun` | município (código IBGE) | texto | — | não | sim |  |
| UNTRMT | `PAC_1` | `transformador_de_distribuicao` | `untrmt_pac_1` | ponto de atendimento da conexão 1 | texto | — | não | sim |  |
| UNTRMT | `PAC_2` | `transformador_de_distribuicao` | `untrmt_pac_2` | ponto de atendimento da conexão 2 | texto | — | não | sim |  |
| UNTRMT | `PAC_3` | `transformador_de_distribuicao` | `untrmt_pac_3` | ponto de atendimento da conexão 3 | texto | — | não | sim |  |
| UNTRMT | `PER_FER` | `transformador_de_distribuicao` | `untrmt_per_fer` | perdas no ferro | real | kW | não | sim |  |
| UNTRMT | `PER_TOT` | `transformador_de_distribuicao` | `untrmt_per_tot` | perdas totais | real | kW | não | sim |  |
| UNTRMT | `POS` | `transformador_de_distribuicao` | `untrmt_pos` | posição | texto | — | não | sim |  |
| UNTRMT | `POSTO` | `transformador_de_distribuicao` | `untrmt_posto` | tipo de posto | texto | — | não | sim |  |
| UNTRMT | `POT_NOM` | `transformador_de_distribuicao` | `untrmt_pot_nom` | potência nominal | real | kVA | não | sim |  |
| UNTRMT | `SIT_ATIV` | `transformador_de_distribuicao` | `untrmt_sit_ativ` | situação de ativação | texto | — | não | sim |  |
| UNTRMT | `SUB` | `transformador_de_distribuicao` | `untrmt_sub` | subestação a que pertence | texto | — | não | sim |  |
| UNTRMT | `TEN_LIN_SE` | `transformador_de_distribuicao` | `untrmt_ten_lin_se` | tensão de linha na saída da subestação | real | kV | não | sim |  |
| UNTRMT | `TIP_TRAFO` | `transformador_de_distribuicao` | `untrmt_tip_trafo` | tipo de transformador | texto | — | não | sim |  |
| UNTRMT | `TIP_UNID` | `transformador_de_distribuicao` | `untrmt_tip_unid` | tipo de unidade de cadastro | texto | — | não | sim |  |
| UNTRMT | `UNI_TR_AT` | `transformador_de_distribuicao` | `untrmt_uni_tr_at` | unidade transformadora de alta tensão | texto | — | não | sim |  |
| UNTRMT | `X` | `transformador_de_distribuicao` | `untrmt_x` | longitude do ponto | real | graus | não | sim | derivada da geometria do ponto pela extração |
| UNTRMT | `Y` | `transformador_de_distribuicao` | `untrmt_y` | latitude do ponto | real | graus | não | sim | derivada da geometria do ponto pela extração |
| SSDBT | `COD_ID` | `trecho_de_baixa_tensao` | `ssdbt_cod_id` | código do objeto | texto | — | sim | sim |  |
| SSDBT | `COMP` | `trecho_de_baixa_tensao` | `ssdbt_comp` | comprimento do trecho | real | km | não | sim |  |
| SSDBT | `CTMT` | `trecho_de_baixa_tensao` | `ssdbt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| SSDBT | `FAS_CON` | `trecho_de_baixa_tensao` | `ssdbt_fas_con` | fases conectadas | texto | — | não | sim |  |
| SSDBT | `TIP_CND` | `trecho_de_baixa_tensao` | `ssdbt_tip_cnd` | tipo de condutor (código do cadastro de condutores) | texto | — | não | sim |  |
| SSDBT | `UNI_TR_MT` | `trecho_de_baixa_tensao` | `ssdbt_uni_tr_mt` | unidade transformadora de média tensão | texto | — | não | sim |  |
| SSDBT | `WKT` | `trecho_de_baixa_tensao` | `ssdbt_wkt` | geometria do trecho | geometria | — | não | sim | geometria da linha serializada em WKT pela extração |
| SSDMT | `COD_ID` | `trecho_de_media_tensao` | `ssdmt_cod_id` | código do objeto | texto | — | sim | sim |  |
| SSDMT | `COMP` | `trecho_de_media_tensao` | `ssdmt_comp` | comprimento do trecho | real | km | não | sim |  |
| SSDMT | `CONJ` | `trecho_de_media_tensao` | `ssdmt_conj` | conjunto elétrico | texto | — | não | sim |  |
| SSDMT | `CTMT` | `trecho_de_media_tensao` | `ssdmt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| SSDMT | `FAS_CON` | `trecho_de_media_tensao` | `ssdmt_fas_con` | fases conectadas | texto | — | não | sim |  |
| SSDMT | `POS` | `trecho_de_media_tensao` | `ssdmt_pos` | posição | texto | — | não | sim |  |
| SSDMT | `SUB` | `trecho_de_media_tensao` | `ssdmt_sub` | subestação a que pertence | texto | — | não | sim |  |
| SSDMT | `UNI_TR_AT` | `trecho_de_media_tensao` | `ssdmt_uni_tr_at` | unidade transformadora de alta tensão | texto | — | não | sim |  |
| SSDMT | `WKT` | `trecho_de_media_tensao` | `ssdmt_wkt` | geometria do trecho | geometria | — | não | sim | geometria da linha serializada em WKT pela extração |
| UCBT_tab | `ARE_LOC` | `unidade_consumidora` | `ucbt_are_loc` | área de localização | texto | — | não | sim |  |
| UCBT_tab | `BRR` | `unidade_consumidora` | `ucbt_brr` | bairro | texto | — | não | sim |  |
| UCBT_tab | `CAR_INST` | `unidade_consumidora` | `ucbt_car_inst` | carga instalada | real | kW | não | sim |  |
| UCBT_tab | `CEG_GD` | `unidade_consumidora` | `ucbt_ceg_gd` | código do empreendimento de geração distribuída | texto | — | não | sim |  |
| UCBT_tab | `CEP` | `unidade_consumidora` | `ucbt_cep` | CEP | texto | — | não | sim |  |
| UCBT_tab | `CLAS_SUB` | `unidade_consumidora` | `ucbt_clas_sub` | classe e subclasse de consumo | texto | — | não | sim |  |
| UCBT_tab | `CNAE` | `unidade_consumidora` | `ucbt_cnae` | atividade econômica (CNAE) | texto | — | não | sim |  |
| UCBT_tab | `COD_ID` | `unidade_consumidora` | `ucbt_cod_id` | código do objeto | texto | — | sim | sim |  |
| UCBT_tab | `CONJ` | `unidade_consumidora` | `ucbt_conj` | conjunto elétrico | texto | — | não | sim |  |
| UCBT_tab | `CTMT` | `unidade_consumidora` | `ucbt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| UCBT_tab | `DAT_CON` | `unidade_consumidora` | `ucbt_dat_con` | data de conexão | data | — | não | sim |  |
| UCBT_tab | `DIC_SUM` | `unidade_consumidora` | `ucbt_dic_sum` | DIC anual | real | h | não | sim | soma de DIC_01..DIC_12 feita pela extração |
| UCBT_tab | `DIC_ZERO` | `unidade_consumidora` | `ucbt_dic_zero` | meses com DIC zero | inteiro | meses | não | sim | contagem sobre DIC_01..DIC_12 feita pela extração |
| UCBT_tab | `ENE_SUM` | `unidade_consumidora` | `ucbt_ene_sum` | energia anual | real | MWh | não | sim | soma de ENE_01..ENE_12 feita pela extração |
| UCBT_tab | `ENE_ZERO` | `unidade_consumidora` | `ucbt_ene_zero` | meses com energia zero | inteiro | meses | não | sim | contagem sobre ENE_01..ENE_12 feita pela extração |
| UCBT_tab | `FAS_CON` | `unidade_consumidora` | `ucbt_fas_con` | fases conectadas | texto | — | não | sim |  |
| UCBT_tab | `FIC_SUM` | `unidade_consumidora` | `ucbt_fic_sum` | FIC anual | real | interrupções | não | sim | soma de FIC_01..FIC_12 feita pela extração |
| UCBT_tab | `FIC_ZERO` | `unidade_consumidora` | `ucbt_fic_zero` | meses com FIC zero | inteiro | meses | não | sim | contagem sobre FIC_01..FIC_12 feita pela extração |
| UCBT_tab | `GRU_TAR` | `unidade_consumidora` | `ucbt_gru_tar` | grupo tarifário | texto | — | não | sim |  |
| UCBT_tab | `GRU_TEN` | `unidade_consumidora` | `ucbt_gru_ten` | grupo de tensão | texto | — | não | sim |  |
| UCBT_tab | `LIV` | `unidade_consumidora` | `ucbt_liv` | consumidor livre | texto | — | não | sim |  |
| UCBT_tab | `MUN` | `unidade_consumidora` | `ucbt_mun` | município (código IBGE) | texto | — | não | sim |  |
| UCBT_tab | `PN_CON` | `unidade_consumidora` | `ucbt_pn_con` | ponto notável de conexão | texto | — | não | sim |  |
| UCBT_tab | `SEMRED` | `unidade_consumidora` | `ucbt_semred` | unidade sem rede | texto | — | não | sim |  |
| UCBT_tab | `SIT_ATIV` | `unidade_consumidora` | `ucbt_sit_ativ` | situação de ativação | texto | — | não | sim |  |
| UCBT_tab | `SUB` | `unidade_consumidora` | `ucbt_sub` | subestação a que pertence | texto | — | não | sim |  |
| UCBT_tab | `TIP_CC` | `unidade_consumidora` | `ucbt_tip_cc` | tipo de contrato de conexão | texto | — | não | sim |  |
| UCBT_tab | `TIP_SIST` | `unidade_consumidora` | `ucbt_tip_sist` | tipo de sistema de atendimento | texto | — | não | sim |  |
| UCBT_tab | `UNI_TR_MT` | `unidade_consumidora` | `ucbt_uni_tr_mt` | unidade transformadora de média tensão | texto | — | não | sim |  |
| UCMT_tab | `ARE_LOC` | `unidade_consumidora` | `ucmt_are_loc` | área de localização | texto | — | não | sim |  |
| UCMT_tab | `BRR` | `unidade_consumidora` | `ucmt_brr` | bairro | texto | — | não | sim |  |
| UCMT_tab | `CAR_INST` | `unidade_consumidora` | `ucmt_car_inst` | carga instalada | real | kW | não | sim |  |
| UCMT_tab | `CEG_GD` | `unidade_consumidora` | `ucmt_ceg_gd` | código do empreendimento de geração distribuída | texto | — | não | sim |  |
| UCMT_tab | `CEP` | `unidade_consumidora` | `ucmt_cep` | CEP | texto | — | não | sim |  |
| UCMT_tab | `CLAS_SUB` | `unidade_consumidora` | `ucmt_clas_sub` | classe e subclasse de consumo | texto | — | não | sim |  |
| UCMT_tab | `CNAE` | `unidade_consumidora` | `ucmt_cnae` | atividade econômica (CNAE) | texto | — | não | sim |  |
| UCMT_tab | `COD_ID` | `unidade_consumidora` | `ucmt_cod_id` | código do objeto | texto | — | sim | sim |  |
| UCMT_tab | `CONJ` | `unidade_consumidora` | `ucmt_conj` | conjunto elétrico | texto | — | não | sim |  |
| UCMT_tab | `CTMT` | `unidade_consumidora` | `ucmt_ctmt` | circuito de média tensão (alimentador) | texto | — | não | sim |  |
| UCMT_tab | `DAT_CON` | `unidade_consumidora` | `ucmt_dat_con` | data de conexão | data | — | não | sim |  |
| UCMT_tab | `ENE_SUM` | `unidade_consumidora` | `ucmt_ene_sum` | energia anual | real | MWh | não | sim | soma de ENE_01..ENE_12 feita pela extração |
| UCMT_tab | `ENE_ZERO` | `unidade_consumidora` | `ucmt_ene_zero` | meses com energia zero | inteiro | meses | não | sim | contagem sobre ENE_01..ENE_12 feita pela extração |
| UCMT_tab | `GRU_TAR` | `unidade_consumidora` | `ucmt_gru_tar` | grupo tarifário | texto | — | não | sim |  |
| UCMT_tab | `MUN` | `unidade_consumidora` | `ucmt_mun` | município (código IBGE) | texto | — | não | sim |  |
| UCMT_tab | `PN_CON` | `unidade_consumidora` | `ucmt_pn_con` | ponto notável de conexão | texto | — | não | sim |  |
| UCMT_tab | `SIT_ATIV` | `unidade_consumidora` | `ucmt_sit_ativ` | situação de ativação | texto | — | não | sim |  |
| UCMT_tab | `SUB` | `unidade_consumidora` | `ucmt_sub` | subestação a que pertence | texto | — | não | sim |  |

Total: 214 atributos, 154 com origem conferida em extração real e 60 declarados da fonte sem conferência.


### Regras de conexão

| tipo de regra | de | para | o que diz |
|---|---|---|---|
| conectividade_no_trecho | `ramal_de_ligacao/1` | `trecho_de_baixa_tensao/1` | ramal derivado do trecho de baixa tensão |
| conectividade_no_trecho | `ramal_de_ligacao/1` | `unidade_consumidora/1` | consumidor de baixa tensão ligado pelo ramal |
| conectividade_no_trecho | `trecho_de_baixa_tensao/1` | `geracao_distribuida/1` | geração em baixa tensão ligada ao trecho de baixa tensão |
| conectividade_no_trecho | `trecho_de_baixa_tensao/1` | `ponto_de_iluminacao_publica/1` | luminária ligada ao trecho de baixa tensão |
| conectividade_no_trecho | `trecho_de_baixa_tensao/1` | `transformador_de_distribuicao/1` | secundário do transformador no trecho de baixa tensão |
| conectividade_no_trecho | `trecho_de_baixa_tensao/1` | `transformador_de_distribuicao/2` | secundário do banco no trecho de baixa tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `banco_de_capacitores/1` | banco de capacitores derivado do trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `chave_de_media_tensao/1` | chave em série no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `chave_de_media_tensao/2` | chave fusível em série no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `chave_de_media_tensao/3` | religador em série no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `chave_de_media_tensao/4` | disjuntor em série no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `chave_de_media_tensao/5` | seccionalizador em série no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `regulador_de_tensao/1` | regulador em série no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `subestacao/1` | saída da subestação alimenta o trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `transformador_de_distribuicao/1` | primário do transformador no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `transformador_de_distribuicao/2` | primário do banco no trecho de média tensão |
| conectividade_no_trecho | `trecho_de_media_tensao/1` | `unidade_consumidora/2` | consumidor de média tensão ligado ao trecho de média tensão |
| contencao | `subestacao/1` | `chave_de_media_tensao/4` | disjuntor contido na subestação |
| contencao | `subestacao/1` | `regulador_de_tensao/1` | regulador contido na subestação |
| fixacao_estrutural | `ponto_notavel/1` | `ponto_de_iluminacao_publica/1` | luminária fixada no poste |
| fixacao_estrutural | `ponto_notavel/1` | `transformador_de_distribuicao/1` | transformador fixado no poste |
| fixacao_estrutural | `ponto_notavel/1` | `trecho_de_baixa_tensao/1` | trecho de baixa tensão fixado no poste |
| fixacao_estrutural | `ponto_notavel/1` | `trecho_de_media_tensao/1` | trecho de média tensão fixado no poste |
| fixacao_estrutural | `ponto_notavel/2` | `trecho_de_media_tensao/1` | trecho de média tensão fixado na torre |
