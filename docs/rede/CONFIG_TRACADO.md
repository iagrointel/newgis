# Configuração de traçado — o que é, e a paridade com a rede de utilidades da Esri

Item `L4-02-e-configuracoes-de-tracado`. A decisão de desenho está no ADR
`docs/adr/20260908T0145-configuracoes-de-tracado.md`; aqui ficam o formato do documento e a leitura de
paridade, peça por peça, contra a documentação pública do ArcGIS Pro 3.4 e do Utility Network Server.

## 1. O documento

```json
{
  "codigo": "kva_a_jusante",
  "nome": "kVA instalado a jusante",
  "tipo": "jusante",
  "compartilhada": true,
  "config": {
    "barreiras_condicao": [{"tipo": "chave_fusivel", "aplica_a": "ponto"}],
    "barreiras_filtro":   [{"atributo": "estado", "operador": "=", "valor": "aberto"}],
    "filtro_saida": {
      "condicoes": [{"grupo": "transformador_de_distribuicao"}],
      "incluir_estrutura": false,
      "categorias_estrutura": ["estrutura_de_suporte"]
    },
    "funcoes": [{"codigo": "kva_instalado", "nome": "Potência instalada", "funcao": "soma",
                 "atributo": "pot_nom", "unidade": "kVA", "onde": []}],
    "tipo_resultado": "elementos",
    "origem_direcao": "auto"
  }
}
```

Uma CONDIÇÃO cita exatamente um de `atributo`, `fase`, `categoria`, `grupo` ou `tipo`, e vale para `ponto`,
`linha` ou `ambos` (`aplica_a`). Operadores de atributo: `=`, `<>`, `>`, `>=`, `<`, `<=`, `contem`,
`comeca_com`, `existe`, `nao_existe`. Operadores de fase: `tem`, `nao_tem`. Funções: `soma`, `contagem`,
`minimo`, `maximo`, `media`. Tipos de resultado: `elementos`, `geometria`, `conectividade`.

## 2. Paridade, peça por peça

| Peça na rede de utilidades da Esri | Aqui | Leitura honesta |
|---|---|---|
| Trace configuration nomeada e reusável (`about-trace-configurations.htm`) | `plat.rede_config_tracado`, CRUD em `/api/rede/{id}/config_tracado`, uso por `config_id` | equivalente em papel: documento salvo, com dono e compartilhamento dentro do inquilino |
| Trace type: connected, subnetwork, upstream, downstream (`configure-a-trace.htm`) | `tipo` = `conectado`, `subrede`, `montante`, `jusante` | equivalente para estes quatro |
| Trace type: isolation, loops, shortest path, subnetwork controllers | `/tracar` atende `isolados`, `lacos` e `caminho_curto` por corpo, mas **não são configuráveis** | lacuna declarada: esses tipos não partem de um ponto e a coluna `tipo` os recusa na criação |
| Condition barriers por atributo de rede e operador (`barriers.htm`) | `barreiras_condicao` com atributo/operador/valor, e também fase, categoria, grupo e tipo | equivalente em papel; o "network attribute" lá é campo declarado no modelo, aqui é chave do `atributos` da feição, conferida contra `plat.rede_atributo` |
| Function barriers (parar quando uma soma acumulada passa de um valor) | **não existe** | lacuna declarada: as funções são calculadas sobre o resultado, não acumuladas ao longo da travessia |
| Filter barriers (`barriers.htm`) | `barreiras_filtro`, por segunda passagem e interseção | equivalente no efeito publicado; a implementação é uma segunda travessia, e a resposta diz `passagens` |
| Filter bitset / filter scope | **não existe** | lacuna declarada |
| Functions: ADD, AVERAGE, COUNT, MAX, MIN, SUBTRACT (`configure-a-trace.htm`) | `soma`, `media`, `contagem`, `maximo`, `minimo`; **sem SUBTRACT** | quase equivalente; cada função aceita um filtro próprio (`onde`), o que a Esri faz com function barriers/filtros separados |
| Output conditions e output filters | `filtro_saida.condicoes` (categoria, grupo, tipo, atributo, fase) | equivalente em papel |
| Include containers / include structures / include barriers (`results.htm`) | `filtro_saida.incluir_estrutura` | parcial: a estrutura entra por COINCIDÊNCIA DE POSIÇÃO com um nó alcançado, não por associação de contenção registrada — a tabela de associação pertence ao modelo importado, não ao modelo de feições que o traçado percorre |
| Result types: elements, aggregated geometry, connectivity (`results.htm`) | `tipo_resultado` = `elementos`, `geometria`, `conectividade` | equivalente em papel; a conectividade sai como pares de nós de topologia, não como grafo serializado da Esri |
| Starting points e barreiras pontuais (`starting-points.htm`) | `pontos_partida` e `barreiras` no corpo do pedido, por feição+terminal ou coordenada com tolerância | equivalente, e é deliberado que fiquem no PEDIDO e não na configuração: a mesma configuração serve a qualquer ponto |
| `createTraceConfiguration` do Utility Network Server (REST) | `POST /api/rede/{id}/config_tracado` | mesma operação; o caminho não leva versão na URL (ADR 0019 §6) |

## 3. O que a paridade não cobre

* Não há *function barrier* nem *filter bitset*: quem precisa parar por soma acumulada não é atendido.
* `SUBTRACT` não existe entre as funções.
* A configuração não guarda ponto de partida: ela descreve COMO traçar, nunca DE ONDE.
* A validação é contra o catálogo da rede, que vem do pacote. Rede sem pacote importado não tem atributo
  nenhum conhecido, e toda condição sobre atributo é recusada — o que é o comportamento certo, mas explica
  um 422 que pode surpreender numa rede vazia.

## 4. Medido em dado real (08/09/2026)

`tests/medidas/L4-02-e-configuracoes-de-tracado.json`, gerado por
`tests/api/test_rede_config_tracado_medida.py` (marcador `lento`), num alimentador da cooperativa de teste
com 451 trechos e 50 transformadores no arquivo, carregando SÓ as camadas de média tensão e de
transformadores:

* a função `soma(pot_nom)` devolve exatamente a soma de `POT_NOM` dos transformadores que o traçado
  ALCANÇOU — isso é conferido por consulta independente e é a igualdade que o teste exige;
* dos 50 transformadores que o cadastro filia ao alimentador, **34 são alcançados** pela topologia
  (940 kVA de 1.730 kVA, −45,7 %). Os 16 restantes não estão ligados à malha construída só com as duas
  camadas carregadas: o cadastro filia por campo (`ctmt`), o traçado anda pela rede;
* **alargar a tolerância não é conserto.** Com 1,0 m em vez dos 0,05 m padrão, os nós órfãos caem de 47 para
  22, mas a folga funde vértices vizinhos, o grafo ganha laço e o traçado a jusante passa a responder
  `indeterminado`: troca-se falta de alcance por falta de sentido. O experimento está registrado na
  constante `TOLERANCIA_M` do teste.

Logo, a cláusula "Σ kVA a jusante de um CTMT = Σ POT_NOM dos UNTRMT do CTMT no arquivo" está provada na rede
de teste (onde a malha é completa) e **parcialmente** no arquivo real: a função está certa, o alcance da
topologia construída com duas camadas não cobre o alimentador inteiro.
