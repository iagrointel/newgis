# 0021 — Traçado conectado e subrede sobre pgRouting (item L4-02-a-conectado-e-subrede)

## Contexto

A topologia derivada (ADR 0020) dá nós e arestas, mas cada terminal de um dispositivo multi-terminal
(chave, transformador) fica em nós separados, deliberadamente não fundidos pelo construtor de topologia.
Sem mais nada, um traçado que andasse só pela topologia pararia em todo dispositivo multi-terminal — não
haveria diferença entre "conectado" (tudo que se alcança) e "subrede" (o alimentador, parando na
transformação).

## Decisão

`app/rede_utilidades/tracado.py` soma ao grafo real, para cada chamada, uma ARESTA VIRTUAL por
`caminho_valido` declarado no `rede_terminal_config` do pacote instalado (ex.: chave "lado_1 → lado_2,
fechado"; transformador "alta → baixa"), condicionada a:

1. **travessabilidade** (os dois tipos): a feição não pode estar com `atributos.estado = "aberto"`;
2. **fronteira de subrede** (só `tipo=subrede`): uma feição de categoria `transformacao` nunca conduz;
3. **barreira**: nós citados pelo chamador são removidos do grafo inteiro antes do traçado.

O componente conexo é calculado por `public.pgr_connectedComponents` (pgRouting 4.0.1, `apt` já
instalado nesta base — não foi preciso instalar), sobre um texto SQL montado em `_montar_sql_arestas`
(arestas reais `UNION ALL` arestas virtuais), com uma tabela temporária (`tracado_mapa`) fazendo a
tradução uuid → bigint que a função exige e excluindo os nós de barreira ANTES da chamada.

## Dois defeitos corrigidos nesta trilha (achados ao medir, não de projeto)

Uma sessão anterior desta trilha caiu por cota de API com o código escrito mas nunca executado. Ao
rodar pela primeira vez:

1. `import psycopg2` estava local à função `tracar_rede` (rota `async`), mas usado dentro de
   `_tracar_sincrono` (função módulo, não fechamento sobre a rota) — `NameError` em toda chamada.
   Corrigido: import no topo do módulo.
2. `pgr_connectedComponents` exige uma coluna `cost` na consulta de arestas (contrato padrão de
   pgRouting) — `_montar_sql_arestas` não a tinha. Corrigido: `1.0::float AS cost` (custo uniforme; este
   item não pesa por comprimento, é só componente conexo).

Registrado aqui porque o portão do item exige rede sintética com resultado conhecido — só foi possível
fechar essa cláusula depois de corrigir os dois defeitos acima.

## Fronteira honesta: dispositivo em série no MESMO grupo colide com a fusão geométrica

`topologia.py::_resolver_uniao` funde diretamente dois trechos do MESMO grupo (ex.: dois trechos de
média tensão) que fiquem geometricamente próximos, independente de qualquer dispositivo entre eles. Se
uma chave em série fica EXATAMENTE na mesma coordenada dos dois trechos vizinhos (caso comum: switch
sem offset no arquivo de origem), os dois trechos se fundem DIRETO entre si (mesma regra que funde uma
linha contínua em dois segmentos), e os dois terminais da chave acabam absorvidos no mesmo nó — o
dispositivo desaparece da topologia como separação. Medido construindo a rede sintética deste item: com
os três candidatos (trecho-A, trecho-B, chave) exatamente coincidentes, a chave vira 1 nó só; com os
trechos deslocados ~0,049 m para cada lado da chave (menos que a tolerância da rede em relação à chave,
mais que a tolerância um em relação ao outro), a chave preserva os 2 terminais corretamente. Isso é
válido para o traçado (a tolerância real do BDGD raramente cai em zero exato) e está documentado nos
comentários de `tests/api/test_rede_tracado.py::_offset`, não é um defeito deste item — é uma
característica da fusão geométrica de série do item L4-01-b que este item herda.

## Cláusula não cumprida, declarada

Não existe front-end de rede de utilidades no repositório (`app/rede_utilidades/` não tem par em
`web/`) para acoplar "clicar → resultado destacado + tabela lateral" com captura e2e. A API do item
(`POST /api/rede/{id}/tracar`) está completa e testada; a cláusula de UI fica registrada como NÃO
CUMPRIDA em `tests/medidas/L4-02-a-conectado-e-subrede.json`, não fingida.

## Consequência

A cláusula de desempenho (p95 ≤ 2 s, 30 medições, maior alimentador da cooperativa de teste) tem teste
pronto (`tests/api/test_rede_tracado_medida.py`, marcador `lento`) mas não pôde medir nesta rodada: carga
de máquina 18-21 (regra do brief: não medir acima de 8) — registrado como `medido: false` com a carga ao
lado, não fingido como passando.
