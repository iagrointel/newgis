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
| versão do pacote | 1.0.0 |
| versão do esquema | 1 |
| disciplina | eletrica |
| fonte | https://dadosabertos.aneel.gov.br/dataset/base-de-dados-geografica-da-distribuidora-bdgd |
| tamanho | 96042 bytes |
| sha256 | `8bc3786c221e3ed5f0a40a85401301c266b15495c7444d5e64fa738f4d612663` |

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
| `unidade_consumidora` | ponto | UCBT_tab, UCMT_tab | 1 | `consumidor_de_baixa_tensao` | Consumidor de baixa tensão | baixa_tensao | consumo, medicao | — |
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

## `esgoto-teksi` — Esgoto sanitário e drenagem (esquema TEKSI)

Pacote de ativos de esgoto sanitário e drenagem pluvial, com o tier na BACIA (partição, não hierarquia) e o escoamento por gravidade: o trecho declara o sentido pela ordem dos vértices e carrega a cota de montante e a de jusante, e a plataforma confere se a cota concorda com o sentido declarado. Trecho de categoria recalque fica de fora dessa conferência, porque ali quem manda é a bomba. As colunas de origem são as do datamodel aberto TEKSI (views tww_app.vw_tww_reach e tww_app.vw_tww_wastewater_structure), lidas na definição de tabela do projeto e ainda não conferidas contra dado real: todo atributo sai com origem.conferida = false.

| campo | valor |
|---|---|
| versão do pacote | 1.0.0 |
| versão do esquema | 1 |
| disciplina | esgoto |
| fonte | https://teksi.github.io/wastewater/ |
| tamanho | 72442 bytes |
| sha256 | `308c5f038ad87f285804b1ce5a07f2b6b3bb9b2075c7c9399aeb0bd9bbd77e8b` |

### Redes de domínio e tiers

| domínio | tipo do domínio | tier | ordem | tipo do tier | o que é |
|---|---|---|---|---|---|
| `esgoto_sanitario` | dominio | `bacia_de_esgotamento` | 1 | particionado | Tudo o que escoa por gravidade para a mesma saída (emissário, elevatória ou estação de tratamento). Particionado: não há montante e jusante entre bacias, cada uma é uma partição. |
| `esgoto_sanitario` | dominio | `recalque_sanitario` | 2 | particionado | Trecho sob pressão a jusante de uma elevatória. A cota NÃO decide o sentido aqui: o sentido é o da bomba, e por isso a conferência de escoamento por gravidade não se aplica. |
| `drenagem_pluvial` | dominio | `bacia_de_drenagem` | 1 | particionado | Área que escoa por gravidade para o mesmo ponto de lançamento pluvial. |

### Categorias de rede

| categoria | nome | o que significa no traçado |
|---|---|---|
| `bombeamento` | Bombeamento | Acrescenta carga: a partir daqui a gravidade deixa de governar. |
| `captacao` | Captação | Ponto por onde a água de chuva entra na rede. |
| `coleta` | Coleta | Recebe a contribuição de um imóvel ou de uma via. |
| `conducao` | Condução | Conduz por gravidade, sem bombear nem controlar. |
| `extravasamento` | Extravasamento | Alivia a rede acima de uma vazão, desviando o excedente. |
| `inspecao` | Inspeção | Permite acesso à rede para inspeção e limpeza; é onde os trechos se encontram. |
| `lancamento` | Lançamento | Onde a rede devolve o efluente ao corpo receptor. |
| `medicao` | Medição | Mede vazão ou nível sem alterar o escoamento. |
| `recalque` | Recalque | Trecho sob pressão a jusante da bomba; a cota não decide o sentido. |
| `seccionamento` | Seccionamento | Interrompe o escoamento por manobra. |
| `tratamento` | Tratamento | Fim da rede coletora; o traçado a jusante termina aqui. |

### Configurações de terminal

| configuração | nome | terminais | caminhos válidos |
|---|---|---|---|
| `dois_terminais` | Dois terminais | 1=montante, 2=jusante | 1→2 (escoa) |
| `dois_terminais_bidirecional` | Dois terminais (sem sentido imposto) | 1=lado_1, 2=lado_2 | 1→2 (escoa), 2→1 (escoa_invertido) |
| `um_terminal` | Um terminal | 1=conexao | — |

### Grupos e tipos de ativo

| grupo | geometria | camada de origem | código do tipo | chave | nome | tier | categorias | códigos na fonte |
|---|---|---|---|---|---|---|---|---|
| `boca_de_lobo` | ponto | vw_tww_wastewater_structure | 1 | `boca_de_lobo` | Boca de lobo | bacia_de_drenagem | captacao | manhole |
| `boca_de_lobo` | ponto | vw_tww_wastewater_structure | 2 | `poco_de_visita_pluvial` | Poço de visita pluvial | bacia_de_drenagem | inspecao | manhole |
| `coletor` | linha | vw_tww_reach | 1 | `coletor_de_rede` | Coletor de rede | bacia_de_esgotamento | conducao | reach |
| `coletor` | linha | vw_tww_reach | 2 | `coletor_tronco` | Coletor tronco | bacia_de_esgotamento | conducao | reach |
| `coletor` | linha | vw_tww_reach | 3 | `interceptor` | Interceptor | bacia_de_esgotamento | conducao | reach |
| `coletor` | linha | vw_tww_reach | 4 | `emissario` | Emissário | bacia_de_esgotamento | conducao | reach |
| `coletor` | linha | vw_tww_reach | 5 | `linha_de_recalque` | Linha de recalque | recalque_sanitario | recalque | reach |
| `coletor` | linha | vw_tww_reach | 6 | `sifao_invertido` | Sifão invertido | recalque_sanitario | recalque | reach |
| `elevatoria` | ponto | pump, vw_tww_wastewater_structure | 1 | `elevatoria` | Elevatória | bacia_de_esgotamento | bombeamento | pump |
| `elevatoria` | ponto | pump, vw_tww_wastewater_structure | 2 | `conjunto_moto_bomba` | Conjunto motobomba | recalque_sanitario | bombeamento | pump |
| `estacao_de_tratamento` | ponto | vw_tww_wastewater_structure | 1 | `estacao_de_tratamento` | Estação de tratamento | bacia_de_esgotamento | tratamento | wwtp_structure |
| `estrutura_especial` | ponto | vw_tww_wastewater_structure | 1 | `extravasor` | Extravasor | bacia_de_esgotamento | extravasamento | special_structure |
| `estrutura_especial` | ponto | vw_tww_wastewater_structure | 2 | `camara_de_transicao` | Câmara de transição | bacia_de_esgotamento | conducao | special_structure |
| `estrutura_especial` | ponto | vw_tww_wastewater_structure | 3 | `caixa_de_passagem` | Caixa de passagem | bacia_de_esgotamento | conducao, seccionamento | special_structure |
| `galeria_pluvial` | linha | vw_tww_reach | 1 | `galeria_pluvial` | Galeria pluvial | bacia_de_drenagem | conducao | reach |
| `galeria_pluvial` | linha | vw_tww_reach | 2 | `canal_de_drenagem` | Canal de drenagem | bacia_de_drenagem | conducao | reach |
| `ligacao_predial` | linha | vw_tww_reach | 1 | `ligacao_predial` | Ligação predial | bacia_de_esgotamento | coleta | reach |
| `poco_de_visita` | ponto | vw_tww_wastewater_structure | 1 | `poco_de_visita_simples` | Poço de visita | bacia_de_esgotamento | inspecao | manhole |
| `poco_de_visita` | ponto | vw_tww_wastewater_structure | 2 | `poco_de_queda` | Poço de queda | bacia_de_esgotamento | inspecao | manhole |
| `poco_de_visita` | ponto | vw_tww_wastewater_structure | 3 | `caixa_de_inspecao` | Caixa de inspeção | bacia_de_esgotamento | coleta, inspecao | manhole |
| `ponto_de_lancamento` | ponto | vw_tww_wastewater_structure | 1 | `ponto_de_lancamento` | Ponto de lançamento | bacia_de_esgotamento | lancamento | discharge_point |

### Atributos: mapeamento coluna a coluna

| camada de origem | coluna | grupo | atributo | nome | tipo | unidade | obrigatório | conferida | observação |
|---|---|---|---|---|---|---|---|---|---|
| vw_tww_wastewater_structure | `year_of_construction` | `boca_de_lobo` | `ano_de_construcao` | ano de construção | inteiro | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `identifier` | `boca_de_lobo` | `codigo_de_cadastro` | código da estrutura no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_level` | `boca_de_lobo` | `cota_da_tampa` | cota da tampa | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `wn_bottom_level` | `boca_de_lobo` | `cota_de_fundo` | cota de fundo do nó | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_diameter` | `boca_de_lobo` | `diametro_da_tampa` | diâmetro da tampa | real | mm | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ws_type` | `boca_de_lobo` | `especie` | espécie da estrutura na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `obj_id` | `boca_de_lobo` | `identificador` | identificador da estrutura | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_material` | `boca_de_lobo` | `material_da_tampa` | material da tampa | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `status` | `boca_de_lobo` | `situacao` | situação operacional | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `clear_height` | `coletor` | `altura_livre` | altura livre da seção | real | mm | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `identifier` | `coletor` | `codigo_de_cadastro` | código do trecho no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `coefficient_of_friction` | `coletor` | `coeficiente_de_atrito` | coeficiente de atrito | real | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `length_effective` | `coletor` | `comprimento` | comprimento efetivo | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_to_level` | `coletor` | `cota_jusante` | cota da geratriz interna inferior no ponto de jusante | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_from_level` | `coletor` | `cota_montante` | cota da geratriz interna inferior no ponto de montante | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `_slope_per_mill` | `coletor` | `declividade` | declividade calculada pela fonte | real | mm/m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ch_function_hierarchic` | `coletor` | `funcao_hierarquica` | função hierárquica do canal | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `obj_id` | `coletor` | `identificador` | identificador do trecho | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `material` | `coletor` | `material` | material do tubo | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_to_obj_id` | `coletor` | `no_jusante` | nó de jusante | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_from_obj_id` | `coletor` | `no_montante` | nó de montante | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ws_status` | `coletor` | `situacao` | situação da estrutura a que o trecho pertence | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ch_usage_current` | `coletor` | `uso_atual` | uso atual do canal | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `year_of_construction` | `elevatoria` | `ano_de_construcao` | ano de construção | inteiro | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `identifier` | `elevatoria` | `codigo_de_cadastro` | código da estrutura no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_level` | `elevatoria` | `cota_da_tampa` | cota da tampa | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `wn_bottom_level` | `elevatoria` | `cota_de_fundo` | cota de fundo do nó | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ws_type` | `elevatoria` | `especie` | espécie da estrutura na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `obj_id` | `elevatoria` | `identificador` | identificador da estrutura | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| pump | `stop_level` | `elevatoria` | `nivel_de_desliga` | nível que desliga a bomba | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| pump | `start_level` | `elevatoria` | `nivel_de_liga` | nível que liga a bomba | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| pump | `placement_of_pump` | `elevatoria` | `posicao_da_bomba` | posição da bomba | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `status` | `elevatoria` | `situacao` | situação operacional | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| pump | `construction_type` | `elevatoria` | `tipo_construtivo` | tipo construtivo da bomba | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| pump | `pump_flow_max_single` | `elevatoria` | `vazao_maxima_por_bomba` | vazão máxima de uma bomba | real | L/s | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `year_of_construction` | `estacao_de_tratamento` | `ano_de_construcao` | ano de construção | inteiro | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| — | `—` | `estacao_de_tratamento` | `capacidade` | capacidade de tratamento | real | L/s | não | não |  |
| vw_tww_wastewater_structure | `identifier` | `estacao_de_tratamento` | `codigo_de_cadastro` | código da estrutura no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_level` | `estacao_de_tratamento` | `cota_da_tampa` | cota da tampa | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `wn_bottom_level` | `estacao_de_tratamento` | `cota_de_fundo` | cota de fundo do nó | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ws_type` | `estacao_de_tratamento` | `especie` | espécie da estrutura na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `obj_id` | `estacao_de_tratamento` | `identificador` | identificador da estrutura | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `status` | `estacao_de_tratamento` | `situacao` | situação operacional | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `year_of_construction` | `estrutura_especial` | `ano_de_construcao` | ano de construção | inteiro | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `identifier` | `estrutura_especial` | `codigo_de_cadastro` | código da estrutura no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_level` | `estrutura_especial` | `cota_da_tampa` | cota da tampa | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `wn_bottom_level` | `estrutura_especial` | `cota_de_fundo` | cota de fundo do nó | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ss_upper_elevation` | `estrutura_especial` | `cota_superior` | cota superior da estrutura | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ws_type` | `estrutura_especial` | `especie` | espécie da estrutura na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `obj_id` | `estrutura_especial` | `identificador` | identificador da estrutura | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ss_depth` | `estrutura_especial` | `profundidade` | profundidade da estrutura | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `status` | `estrutura_especial` | `situacao` | situação operacional | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ss_bypass` | `estrutura_especial` | `tem_desvio` | tem desvio (bypass) | booleano | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `clear_height` | `galeria_pluvial` | `altura_livre` | altura livre da seção | real | mm | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `identifier` | `galeria_pluvial` | `codigo_de_cadastro` | código do trecho no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `coefficient_of_friction` | `galeria_pluvial` | `coeficiente_de_atrito` | coeficiente de atrito | real | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `length_effective` | `galeria_pluvial` | `comprimento` | comprimento efetivo | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_to_level` | `galeria_pluvial` | `cota_jusante` | cota da geratriz interna inferior no ponto de jusante | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_from_level` | `galeria_pluvial` | `cota_montante` | cota da geratriz interna inferior no ponto de montante | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `_slope_per_mill` | `galeria_pluvial` | `declividade` | declividade calculada pela fonte | real | mm/m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ch_function_hierarchic` | `galeria_pluvial` | `funcao_hierarquica` | função hierárquica do canal | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `obj_id` | `galeria_pluvial` | `identificador` | identificador do trecho | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `material` | `galeria_pluvial` | `material` | material do tubo | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_to_obj_id` | `galeria_pluvial` | `no_jusante` | nó de jusante | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_from_obj_id` | `galeria_pluvial` | `no_montante` | nó de montante | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ws_status` | `galeria_pluvial` | `situacao` | situação da estrutura a que o trecho pertence | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ch_usage_current` | `galeria_pluvial` | `uso_atual` | uso atual do canal | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `clear_height` | `ligacao_predial` | `altura_livre` | altura livre da seção | real | mm | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `identifier` | `ligacao_predial` | `codigo_de_cadastro` | código do trecho no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `coefficient_of_friction` | `ligacao_predial` | `coeficiente_de_atrito` | coeficiente de atrito | real | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `length_effective` | `ligacao_predial` | `comprimento` | comprimento efetivo | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_to_level` | `ligacao_predial` | `cota_jusante` | cota da geratriz interna inferior no ponto de jusante | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_from_level` | `ligacao_predial` | `cota_montante` | cota da geratriz interna inferior no ponto de montante | real | m | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `_slope_per_mill` | `ligacao_predial` | `declividade` | declividade calculada pela fonte | real | mm/m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ch_function_hierarchic` | `ligacao_predial` | `funcao_hierarquica` | função hierárquica do canal | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `obj_id` | `ligacao_predial` | `identificador` | identificador do trecho | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `material` | `ligacao_predial` | `material` | material do tubo | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_to_obj_id` | `ligacao_predial` | `no_jusante` | nó de jusante | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `rp_from_obj_id` | `ligacao_predial` | `no_montante` | nó de montante | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ws_status` | `ligacao_predial` | `situacao` | situação da estrutura a que o trecho pertence | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_reach | `ch_usage_current` | `ligacao_predial` | `uso_atual` | uso atual do canal | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `year_of_construction` | `poco_de_visita` | `ano_de_construcao` | ano de construção | inteiro | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `identifier` | `poco_de_visita` | `codigo_de_cadastro` | código da estrutura no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_level` | `poco_de_visita` | `cota_da_tampa` | cota da tampa | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `wn_bottom_level` | `poco_de_visita` | `cota_de_fundo` | cota de fundo do nó | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `wn_backflow_level_current` | `poco_de_visita` | `cota_de_remanso` | cota de remanso atual | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ma_dimension1` | `poco_de_visita` | `dimensao_1` | primeira dimensão em planta | real | mm | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ma_dimension2` | `poco_de_visita` | `dimensao_2` | segunda dimensão em planta | real | mm | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ws_type` | `poco_de_visita` | `especie` | espécie da estrutura na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ma_function` | `poco_de_visita` | `funcao` | função do poço na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `obj_id` | `poco_de_visita` | `identificador` | identificador da estrutura | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ma_material` | `poco_de_visita` | `material` | material do poço | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ma_depth` | `poco_de_visita` | `profundidade` | profundidade do poço | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `status` | `poco_de_visita` | `situacao` | situação operacional | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `year_of_construction` | `ponto_de_lancamento` | `ano_de_construcao` | ano de construção | inteiro | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `identifier` | `ponto_de_lancamento` | `codigo_de_cadastro` | código da estrutura no cadastro | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `co_level` | `ponto_de_lancamento` | `cota_da_tampa` | cota da tampa | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `dp_highwater_level` | `ponto_de_lancamento` | `cota_de_cheia` | cota de cheia do corpo receptor | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `wn_bottom_level` | `ponto_de_lancamento` | `cota_de_fundo` | cota de fundo do nó | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `dp_terrain_level` | `ponto_de_lancamento` | `cota_do_terreno` | cota do terreno no lançamento | real | m | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `ws_type` | `ponto_de_lancamento` | `especie` | espécie da estrutura na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `obj_id` | `ponto_de_lancamento` | `identificador` | identificador da estrutura | texto | — | sim | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `dp_water_course_number` | `ponto_de_lancamento` | `numero_do_curso_de_agua` | número do curso de água na fonte | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |
| vw_tww_wastewater_structure | `status` | `ponto_de_lancamento` | `situacao` | situação operacional | texto | — | não | não | coluna lida na definição de tabela do datamodel TEKSI (changelog 2025.0.1, arquivo 03_tww_db_dss.sql, e views em datamodel/app/view); ainda não vista em GeoPackage de dado real |

Total: 104 atributos, 0 com origem conferida em extração real e 104 declarados da fonte sem conferência.


### Regras de conexão

| tipo de regra | de | para | o que diz |
|---|---|---|---|
| conectividade_entre_nos | `elevatoria/1` | `elevatoria/2` | conjunto motobomba faz parte da elevatória |
| conectividade_no_trecho | `boca_de_lobo/1` | `galeria_pluvial/1` | boca de lobo entrega na galeria pluvial |
| conectividade_no_trecho | `boca_de_lobo/2` | `galeria_pluvial/1` | poço de visita pluvial recebe e entrega galeria pluvial |
| conectividade_no_trecho | `boca_de_lobo/2` | `galeria_pluvial/2` | poço de visita pluvial entrega no canal de drenagem |
| conectividade_no_trecho | `elevatoria/1` | `coletor/2` | elevatória recebe coletor tronco por gravidade |
| conectividade_no_trecho | `elevatoria/1` | `coletor/3` | elevatória recebe o interceptor por gravidade |
| conectividade_no_trecho | `elevatoria/1` | `coletor/5` | elevatória entrega na linha de recalque, e daí em diante a cota não decide o sentido |
| conectividade_no_trecho | `estacao_de_tratamento/1` | `coletor/3` | interceptor termina na estação de tratamento |
| conectividade_no_trecho | `estacao_de_tratamento/1` | `coletor/4` | emissário termina na estação de tratamento |
| conectividade_no_trecho | `estrutura_especial/1` | `coletor/3` | extravasor instalado no interceptor |
| conectividade_no_trecho | `estrutura_especial/1` | `coletor/4` | extravasor desvia o excedente para o emissário |
| conectividade_no_trecho | `estrutura_especial/2` | `coletor/1` | câmara de transição entre dois coletores de rede |
| conectividade_no_trecho | `estrutura_especial/3` | `coletor/2` | caixa de passagem no coletor tronco |
| conectividade_no_trecho | `poco_de_visita/1` | `coletor/1` | poço de visita recebe e entrega coletor de rede |
| conectividade_no_trecho | `poco_de_visita/1` | `coletor/2` | poço de visita recebe e entrega coletor tronco |
| conectividade_no_trecho | `poco_de_visita/1` | `coletor/3` | poço de visita recebe e entrega interceptor |
| conectividade_no_trecho | `poco_de_visita/1` | `coletor/4` | poço de visita recebe e entrega emissário |
| conectividade_no_trecho | `poco_de_visita/1` | `coletor/5` | a linha de recalque termina num poço de visita, onde volta a escoar por gravidade |
| conectividade_no_trecho | `poco_de_visita/1` | `coletor/6` | sifão invertido começa e termina em poço de visita |
| conectividade_no_trecho | `poco_de_visita/1` | `ligacao_predial/1` | ligação predial pode chegar direto no poço de visita |
| conectividade_no_trecho | `poco_de_visita/2` | `coletor/1` | poço de queda recebe coletor de rede com desnível |
| conectividade_no_trecho | `poco_de_visita/2` | `coletor/2` | poço de queda recebe coletor tronco com desnível |
| conectividade_no_trecho | `poco_de_visita/3` | `coletor/1` | caixa de inspeção entrega no coletor de rede |
| conectividade_no_trecho | `poco_de_visita/3` | `ligacao_predial/1` | caixa de inspeção recebe a ligação predial |
| conectividade_no_trecho | `ponto_de_lancamento/1` | `coletor/4` | emissário termina no ponto de lançamento |
| conectividade_no_trecho | `ponto_de_lancamento/1` | `galeria_pluvial/1` | galeria pluvial termina no ponto de lançamento |
| conectividade_no_trecho | `ponto_de_lancamento/1` | `galeria_pluvial/2` | canal de drenagem termina no ponto de lançamento |
| contencao | `poco_de_visita/1` | `poco_de_visita/3` | caixa de inspeção pode estar contida no mesmo conjunto do poço de visita |
| fixacao_estrutural | `elevatoria/1` | `estrutura_especial/3` | caixa de passagem apoiada na estrutura da elevatória |

## `gas-br` — Gás canalizado (tiers por pressão)

Pacote de ativos da rede de gás canalizado. O tier é o degrau de pressão (transporte, alta, média e baixa) e o regulador é o ativo que muda de tier: é ele que controla o degrau, e é por isso que a conferência de pressão da plataforma o exige em toda transição. Os atributos são o vocabulário próprio do pacote, não a cópia de um esquema externo: nenhum tem coluna de origem, e a paridade com a Gas Utility Network Foundation da Esri está escrita em docs/rede/PARIDADE_GAS.md.

| campo | valor |
|---|---|
| versão do pacote | 1.0.0 |
| versão do esquema | 1 |
| disciplina | gas |
| fonte | https://solutions.arcgis.com/utilities/gas/help/gas-utility-network-foundation/ |
| tamanho | 28749 bytes |
| sha256 | `d7d3ccac26d832ded8e423b068b2bc54865770b2f3b98f051b67b0df5e725843` |

### Redes de domínio e tiers

| domínio | tipo do domínio | tier | ordem | tipo do tier | o que é |
|---|---|---|---|---|---|
| `gas_distribuicao` | dominio | `transporte` | 1 | hierarquico | Malha de transporte a montante do city gate; a pressão mais alta da rede. |
| `gas_distribuicao` | dominio | `alta_pressao` | 2 | hierarquico | Entre o city gate e o regulador de rede. A subrede é o trecho alimentado por um city gate. |
| `gas_distribuicao` | dominio | `media_pressao` | 3 | hierarquico | Entre o regulador de rede e o regulador de ramal. |
| `gas_distribuicao` | dominio | `baixa_pressao` | 4 | hierarquico | Do regulador de ramal ao ponto de entrega. |

### Categorias de rede

| categoria | nome | o que significa no traçado |
|---|---|---|
| `alivio` | Alívio | Libera gás para a atmosfera acima de uma pressão de ajuste. |
| `conducao` | Condução | Conduz sem controlar pressão nem seccionar. |
| `consumo` | Consumo | Ponto final que retira gás da rede. |
| `controle_de_pressao` | Controle de pressão | Impõe a pressão a jusante e separa dois tiers. |
| `fonte` | Fonte | Onde o gás entra na rede; o traçado a montante termina aqui. |
| `medicao` | Medição | Mede volume ou vazão sem alterar o escoamento. |
| `odorizacao` | Odorização | Injeta odorante para tornar o vazamento perceptível. |
| `protecao` | Proteção | Impede escoamento em sentido indevido ou isola por falha. |
| `purga` | Purga | Ponto de esvaziamento do trecho para manutenção. |
| `seccionamento` | Seccionamento | Abre ou fecha o escoamento por manobra. |

### Configurações de terminal

| configuração | nome | terminais | caminhos válidos |
|---|---|---|---|
| `dois_terminais` | Dois terminais | 1=montante, 2=jusante | 1→2 (aberto) |
| `dois_terminais_bidirecional` | Dois terminais (sem sentido imposto) | 1=lado_1, 2=lado_2 | 1→2 (aberto), 2→1 (aberto_invertido) |
| `um_terminal` | Um terminal | 1=conexao | — |

### Grupos e tipos de ativo

| grupo | geometria | camada de origem | código do tipo | chave | nome | tier | categorias | códigos na fonte |
|---|---|---|---|---|---|---|---|---|
| `city_gate` | ponto | GasAssembly | 1 | `city_gate` | City gate | transporte | controle_de_pressao, fonte, medicao, odorizacao | gasStation |
| `estacao_de_medicao` | ponto | GasAssembly | 1 | `medidor_de_transferencia` | Medidor de transferência | alta_pressao | medicao | gasMeter |
| `estacao_de_medicao` | ponto | GasAssembly | 2 | `medidor_de_faturamento` | Medidor de faturamento | baixa_pressao | consumo, medicao | gasMeter |
| `juncao_de_gas` | ponto | GasJunction | 1 | `juncao_de_transporte` | Junção de transporte | transporte | conducao | gasJunction |
| `juncao_de_gas` | ponto | GasJunction | 2 | `juncao_de_alta_pressao` | Junção de alta pressão | alta_pressao | conducao | gasJunction |
| `juncao_de_gas` | ponto | GasJunction | 3 | `juncao_de_media_pressao` | Junção de média pressão | media_pressao | conducao | gasJunction |
| `juncao_de_gas` | ponto | GasJunction | 4 | `juncao_de_baixa_pressao` | Junção de baixa pressão | baixa_pressao | conducao | gasJunction |
| `ponto_de_entrega` | ponto | GasDevice | 1 | `ponto_de_entrega_residencial` | Ponto de entrega residencial | baixa_pressao | consumo | gasServicePoint |
| `ponto_de_entrega` | ponto | GasDevice | 2 | `ponto_de_entrega_comercial` | Ponto de entrega comercial | baixa_pressao | consumo | gasServicePoint |
| `ponto_de_entrega` | ponto | GasDevice | 3 | `ponto_de_entrega_industrial` | Ponto de entrega industrial | media_pressao | consumo | gasServicePoint |
| `regulador` | ponto | GasDevice | 1 | `regulador_de_city_gate` | Regulador de city gate | alta_pressao | controle_de_pressao | gasRegulator |
| `regulador` | ponto | GasDevice | 2 | `regulador_de_rede` | Regulador de rede | media_pressao | controle_de_pressao | gasRegulator |
| `regulador` | ponto | GasDevice | 3 | `regulador_de_ramal` | Regulador de ramal | baixa_pressao | controle_de_pressao | gasRegulator |
| `regulador` | ponto | GasDevice | 4 | `regulador_monitor` | Regulador monitor | alta_pressao | controle_de_pressao, protecao | gasRegulator |
| `tubulacao_de_gas` | linha | GasLine | 1 | `rede_de_transporte` | Rede de transporte | transporte | conducao | gasMain |
| `tubulacao_de_gas` | linha | GasLine | 2 | `rede_de_alta_pressao` | Rede de alta pressão | alta_pressao | conducao | gasMain |
| `tubulacao_de_gas` | linha | GasLine | 3 | `rede_de_media_pressao` | Rede de média pressão | media_pressao | conducao | gasMain |
| `tubulacao_de_gas` | linha | GasLine | 4 | `rede_de_baixa_pressao` | Rede de baixa pressão | baixa_pressao | conducao | gasMain |
| `tubulacao_de_gas` | linha | GasLine | 5 | `ramal_de_servico` | Ramal de serviço | baixa_pressao | conducao | gasService |
| `tubulacao_de_gas` | linha | GasLine | 6 | `tubulacao_desativada` | Tubulação desativada | baixa_pressao | conducao | gasMainAbandoned |
| `valvula_de_gas` | ponto | GasDevice | 1 | `valvula_de_bloqueio` | Válvula de bloqueio | media_pressao | seccionamento | gasValve |
| `valvula_de_gas` | ponto | GasDevice | 2 | `valvula_de_alivio` | Válvula de alívio | alta_pressao | alivio | gasValve |
| `valvula_de_gas` | ponto | GasDevice | 3 | `valvula_de_purga` | Válvula de purga | media_pressao | purga | gasValve |
| `valvula_de_gas` | ponto | GasDevice | 4 | `valvula_de_retencao` | Válvula de retenção | alta_pressao | protecao | gasValve |

### Atributos: mapeamento coluna a coluna

| camada de origem | coluna | grupo | atributo | nome | tipo | unidade | obrigatório | conferida | observação |
|---|---|---|---|---|---|---|---|---|---|
| — | `—` | `city_gate` | `ano_de_instalacao` | ano de instalação | inteiro | — | não | não |  |
| — | `—` | `city_gate` | `capacidade` | capacidade nominal | real | m3/h | sim | não |  |
| — | `—` | `city_gate` | `identificador` | identificador do ativo | texto | — | sim | não |  |
| — | `—` | `city_gate` | `odorizacao` | odoriza o gás | booleano | — | não | não |  |
| — | `—` | `city_gate` | `pressao_de_entrada` | pressão de entrada de projeto | real | kPa | sim | não |  |
| — | `—` | `city_gate` | `pressao_de_saida` | pressão de saída ajustada | real | kPa | sim | não |  |
| — | `—` | `city_gate` | `situacao` | situação operacional | texto | — | não | não |  |
| — | `—` | `city_gate` | `tier_jusante` | tier de pressão a jusante | texto | — | sim | não |  |
| — | `—` | `city_gate` | `tier_montante` | tier de pressão a montante | texto | — | sim | não |  |
| — | `—` | `estacao_de_medicao` | `ano_de_instalacao` | ano de instalação | inteiro | — | não | não |  |
| — | `—` | `estacao_de_medicao` | `correcao_ptz` | corrige pressão, temperatura e compressibilidade | booleano | — | não | não |  |
| — | `—` | `estacao_de_medicao` | `identificador` | identificador do ativo | texto | — | sim | não |  |
| — | `—` | `estacao_de_medicao` | `situacao` | situação operacional | texto | — | não | não |  |
| — | `—` | `estacao_de_medicao` | `tipo_de_medidor` | tecnologia do medidor | texto | — | não | não |  |
| — | `—` | `estacao_de_medicao` | `vazao_maxima` | vazão máxima medida | real | m3/h | não | não |  |
| — | `—` | `juncao_de_gas` | `ano_de_instalacao` | ano de instalação | inteiro | — | não | não |  |
| — | `—` | `juncao_de_gas` | `identificador` | identificador do ativo | texto | — | sim | não |  |
| — | `—` | `juncao_de_gas` | `situacao` | situação operacional | texto | — | não | não |  |
| — | `—` | `juncao_de_gas` | `tipo_de_conexao` | tipo de conexão | texto | — | não | não |  |
| — | `—` | `ponto_de_entrega` | `ano_de_instalacao` | ano de instalação | inteiro | — | não | não |  |
| — | `—` | `ponto_de_entrega` | `classe_de_consumo` | classe de consumo | texto | — | não | não |  |
| — | `—` | `ponto_de_entrega` | `identificador` | identificador do ativo | texto | — | sim | não |  |
| — | `—` | `ponto_de_entrega` | `situacao` | situação operacional | texto | — | não | não |  |
| — | `—` | `ponto_de_entrega` | `vazao_contratada` | vazão contratada | real | m3/h | não | não |  |
| — | `—` | `regulador` | `ano_de_instalacao` | ano de instalação | inteiro | — | não | não |  |
| — | `—` | `regulador` | `fabricante` | fabricante | texto | — | não | não |  |
| — | `—` | `regulador` | `identificador` | identificador do ativo | texto | — | sim | não |  |
| — | `—` | `regulador` | `pressao_de_entrada` | pressão de entrada de projeto | real | kPa | sim | não |  |
| — | `—` | `regulador` | `pressao_de_saida` | pressão de saída ajustada | real | kPa | sim | não |  |
| — | `—` | `regulador` | `situacao` | situação operacional | texto | — | não | não |  |
| — | `—` | `regulador` | `tem_valvula_de_bloqueio_automatico` | tem bloqueio automático por sobrepressão | booleano | — | não | não |  |
| — | `—` | `regulador` | `tier_jusante` | tier de pressão a jusante | texto | — | sim | não |  |
| — | `—` | `regulador` | `tier_montante` | tier de pressão a montante | texto | — | sim | não |  |
| — | `—` | `regulador` | `vazao_maxima` | vazão máxima | real | m3/h | não | não |  |
| — | `—` | `tubulacao_de_gas` | `ano_de_instalacao` | ano de instalação | inteiro | — | não | não |  |
| — | `—` | `tubulacao_de_gas` | `comprimento` | comprimento do trecho | real | m | sim | não |  |
| — | `—` | `tubulacao_de_gas` | `diametro_nominal` | diâmetro nominal | real | mm | sim | não |  |
| — | `—` | `tubulacao_de_gas` | `identificador` | identificador do ativo | texto | — | sim | não |  |
| — | `—` | `tubulacao_de_gas` | `material` | material do tubo | texto | — | sim | não |  |
| — | `—` | `tubulacao_de_gas` | `pressao_maxima_de_operacao` | pressão máxima de operação admissível | real | kPa | sim | não |  |
| — | `—` | `tubulacao_de_gas` | `profundidade_de_assentamento` | profundidade de assentamento | real | m | não | não |  |
| — | `—` | `tubulacao_de_gas` | `protecao_catodica` | tem proteção catódica | booleano | — | não | não |  |
| — | `—` | `tubulacao_de_gas` | `revestimento` | revestimento externo | texto | — | não | não |  |
| — | `—` | `tubulacao_de_gas` | `situacao` | situação operacional | texto | — | não | não |  |
| — | `—` | `valvula_de_gas` | `acionamento` | forma de acionamento | texto | — | não | não |  |
| — | `—` | `valvula_de_gas` | `ano_de_instalacao` | ano de instalação | inteiro | — | não | não |  |
| — | `—` | `valvula_de_gas` | `diametro_nominal` | diâmetro nominal | real | mm | sim | não |  |
| — | `—` | `valvula_de_gas` | `estado` | estado da manobra | texto | — | sim | não |  |
| — | `—` | `valvula_de_gas` | `identificador` | identificador do ativo | texto | — | sim | não |  |
| — | `—` | `valvula_de_gas` | `situacao` | situação operacional | texto | — | não | não |  |
| — | `—` | `valvula_de_gas` | `pressao_de_ajuste` | pressão de ajuste | real | kPa | não | não |  |

Total: 51 atributos, 0 com origem conferida em extração real e 51 declarados da fonte sem conferência.


### Regras de conexão

| tipo de regra | de | para | o que diz |
|---|---|---|---|
| conectividade_entre_nos | `city_gate/1` | `estacao_de_medicao/1` | o medidor de transferência faz parte do conjunto do city gate |
| conectividade_entre_nos | `city_gate/1` | `regulador/1` | o regulador de city gate faz parte do conjunto do city gate |
| conectividade_entre_nos | `regulador/3` | `estacao_de_medicao/2` | regulador de ramal e medidor de faturamento no mesmo abrigo |
| conectividade_entre_nos | `regulador/4` | `regulador/1` | regulador monitor em série com o regulador de city gate |
| conectividade_no_trecho | `city_gate/1` | `tubulacao_de_gas/1` | city gate recebe da rede de transporte |
| conectividade_no_trecho | `city_gate/1` | `tubulacao_de_gas/2` | city gate entrega na rede de alta pressão |
| conectividade_no_trecho | `estacao_de_medicao/1` | `tubulacao_de_gas/2` | medidor de transferência instalado na rede de alta pressão |
| conectividade_no_trecho | `estacao_de_medicao/2` | `tubulacao_de_gas/5` | medidor de faturamento instalado no ramal de serviço |
| conectividade_no_trecho | `juncao_de_gas/1` | `tubulacao_de_gas/1` | junção conecta tubulações no tier de transporte |
| conectividade_no_trecho | `juncao_de_gas/2` | `tubulacao_de_gas/2` | junção conecta tubulações no tier de alta pressão |
| conectividade_no_trecho | `juncao_de_gas/3` | `tubulacao_de_gas/3` | junção conecta tubulações no tier de média pressão |
| conectividade_no_trecho | `juncao_de_gas/4` | `tubulacao_de_gas/4` | junção conecta tubulações no tier de baixa pressão |
| conectividade_no_trecho | `juncao_de_gas/4` | `tubulacao_de_gas/5` | ramal de serviço derivado por junção na baixa pressão |
| conectividade_no_trecho | `juncao_de_gas/4` | `tubulacao_de_gas/6` | tubulação desativada permanece ligada à junção que a derivava |
| conectividade_no_trecho | `ponto_de_entrega/1` | `tubulacao_de_gas/5` | entrega residencial no fim do ramal de serviço |
| conectividade_no_trecho | `ponto_de_entrega/2` | `tubulacao_de_gas/5` | entrega comercial no fim do ramal de serviço |
| conectividade_no_trecho | `ponto_de_entrega/3` | `tubulacao_de_gas/3` | entrega industrial direto da rede de média pressão |
| conectividade_no_trecho | `regulador/1` | `tubulacao_de_gas/1` | regulador de city gate recebe da rede de transporte |
| conectividade_no_trecho | `regulador/1` | `tubulacao_de_gas/2` | regulador de city gate entrega na rede de alta pressão |
| conectividade_no_trecho | `regulador/2` | `tubulacao_de_gas/2` | regulador de rede recebe da rede de alta pressão |
| conectividade_no_trecho | `regulador/2` | `tubulacao_de_gas/3` | regulador de rede entrega na rede de média pressão |
| conectividade_no_trecho | `regulador/3` | `tubulacao_de_gas/3` | regulador de ramal recebe da rede de média pressão |
| conectividade_no_trecho | `regulador/3` | `tubulacao_de_gas/4` | regulador de ramal entrega na rede de baixa pressão |
| conectividade_no_trecho | `regulador/4` | `tubulacao_de_gas/2` | regulador monitor fica em série na rede de alta pressão |
| conectividade_no_trecho | `valvula_de_gas/1` | `tubulacao_de_gas/3` | válvula de bloqueio instalada na rede de média pressão |
| conectividade_no_trecho | `valvula_de_gas/1` | `tubulacao_de_gas/4` | válvula de bloqueio instalada na rede de baixa pressão |
| conectividade_no_trecho | `valvula_de_gas/2` | `tubulacao_de_gas/2` | válvula de alívio derivada da rede de alta pressão |
| conectividade_no_trecho | `valvula_de_gas/3` | `tubulacao_de_gas/3` | válvula de purga derivada da rede de média pressão |
| conectividade_no_trecho | `valvula_de_gas/4` | `tubulacao_de_gas/2` | válvula de retenção instalada na rede de alta pressão |
