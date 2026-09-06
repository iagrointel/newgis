# L4-privado — infraestrutura interna de empreendimento fechado (via privada, drenagem, iluminação, água/esgoto) — decisões de conceito

Data: 06/09/2026. Pesquisa (não construção): leitura de um SIG de teste interno já construído para uma incorporadora
(condomínios horizontais fechados, ontologia Empreendimento → Quadra → Lote → Casa → Tipologia → Personalização,
schema `sigcorp`, só leitura) e do que existe hoje sobre GABARITO (motor de BIM paramétrico de casa/tipologia, no GPU
box, só por memória — o repositório não está acessível desta máquina). Nomes de cliente/parceiro não aparecem: o SIG
lido é "SIG de teste interno" (mesmo alias já usado em `L4_CONCEITO.md`, decisão C16), e o produto aqui desenhado é
GENÉRICO — vale para qualquer incorporadora de loteamento/condomínio fechado, nunca para o caso específico lido.

Pergunta do dono: a infraestrutura de via PRIVADA dentro de loteamento/condomínio fechado deve virar um MÓDULO da
plataforma, aproveitando o L4 (rede de utilidades, já especificado em `L4_CONCEITO.md`) e o GABARITO (tipologia de
casa)? Resposta curta: **sim, mas como combinação de três peças que já existem em esboço, mais quatro peças que não
existem ainda** — ver C12 (veredito).

## 0. O que foi lido e sustenta as escolhas

- **O SIG de teste interno modela a via, mas não como rede.** `sistema_viario` (`/home/dev/fgr/sig/db/schema.sql` linha
  198) é uma tabela de `LineString` com `tipo` (rua/avenida/acesso/pedestre/ciclovia/outra), `interna boolean` e
  `comprimento_m` — sem nó, sem aresta, sem terminal, sem conectividade. É simbologia e medida, não topologia. A tabela
  de domínios (`schema_v3.sql`, `dominio`) confirma o mesmo vocabulário (`via_tipo`), também sem campo de conectividade.
- **Não existe drenagem pluvial em lugar nenhum do schema.** A única menção a água superficial é `dist_curso_dagua_m`
  em `derivado_empreendimento` (`schema.sql` linha 279) — distância ao curso d'água NATURAL, para calcular APP, e
  `area_especial` tipo `'represa/lago'` — nenhuma das duas é a rede de boca-de-lobo/tubulação/bacia de detenção do
  empreendimento.
- **Não existe iluminação privada como camada.** `equipamento` (`schema.sql` linha 214) tem os tipos declarados em
  `dominio.equipamento_tipo` (`schema_v3.sql`): academia, quadra esportiva, piscina, área verde, portaria, quiosque,
  restaurante, petplace, playground, feirinha, clube, estacionamento, outro — **nenhum item de poste/luminária**.
- **Água/esgoto aparecem só como percentual DERIVADO, não como rede.** `derivado_empreendimento.cobertura_agua_pct` e
  `cobertura_esgoto_pct` (`schema.sql` linhas 289-290) são estimativas de cobertura (tipo censitário), ao lado de
  `dist_rede_mt_m`/`rede_mt_dentro_m` — que são distância à rede de MÉDIA TENSÃO PÚBLICA da concessionária, não à rede
  interna do condomínio. Nenhuma tabela guarda tubo, poço de visita, caixa de passagem, poste ou luminária do
  empreendimento.
- **A própria pesquisa que gerou o SIG de teste já registrou o gap e chamou pelo nome certo.** `DOSSIE_incorporadora-de-teste_SIG.md`
  seção 5 (T1/T2/T3): "T3 — pesquisa/digitalização. Apontar e ver a rede hidráulica/elétrica exige as-built
  georreferenciado das REDES. [O cliente] provavelmente tem isso só em DWG 2D, sem georreferência consistente e sem
  padrão de layer. O custo e o prazo aqui são de DIGITALIZAÇÃO, não de software. Nunca prometer T3 antes de abrir um
  DWG deles." E a mesma seção nomeia o segundo comprador: "a rede de água, esgoto, drenagem, iluminação e gás do
  condomínio é mantida por décadas pelo condomínio/administradora, não pela incorporadora... entrega única para a
  incorporadora, assinatura para cada condomínio entregue."
- **GABARITO modela instalações DENTRO da casa, não a rede do loteamento.** Pelas memórias do projeto (repositório no
  GPU box, inacessível desta máquina): a tipologia paramétrica calcula hidrossanitário por NBR 5626 (memória
  `project_gabarito-biblioteca-componentes.md`/`project_gabarito-quatro-tipologias.md`: erro real encontrado e
  corrigido foi tratar o edifício como alimentado por baixo quando tinha caixa superior — cálculo é POR EDIFÍCIO), e a
  "rede de incêndio modelada é traçado e diâmetro, não cálculo hidráulico" (`project_gabarito-model-gate.md`) — de novo,
  por edifício. O ponto de saída da casa (padrão de entrada de água/luz, caixa de inspeção de esgoto) é um objeto IFC
  dentro do modelo da casa, mas **nenhum código liga esse objeto a uma rede fora do lote** — mesma frase que já consta
  em `project_gabarito-coordenacao-federada.md` para o BIM em geral: "os motores não têm superfície de produto...
  0 rotas de coordenação no OpenAPI". A situação/onde a casa termina e o loteamento começa nunca foi modelada.
- **O motor de rede genérico (L4) já existe em especificação, provado noutro domínio.** `L4_CONCEITO.md` já decide
  topologia derivada (C1), motor de traçado por pgRouting (C2), esquema de rede como DADO — pacote de ativos JSON
  versionado (C3), terminal como nó (C4), atributos propagados (C5), subrede com controlador/tier (C6), contrato de
  traçado único (C7), versionamento com delta de topologia (C8), CRS/tolerância/comprimento geodésico (C10), RLS por
  inquilino (C11), formatos de troca incluindo EPANET .inp e "gás e esgoto" (C12, item `L4-05-e-gas-e-esgoto` já
  existe no `L4.json`), e a malha de PARCELAS como modelo à parte, não-rede (C16 — Parcel Fabric). Nenhuma linha de
  código foi escrita ainda para nada disso (todo item do `L4.json` está `"estado": "pendente"`, `"tentativas": 0`).
- **A malha de parcelas já lista "servidão" e "área comum" como tipos candidatos.** `L4_CONCEITO.md` C16 ("tipos de
  parcela (lote, gleba, quadra, servidão, estrato/unidade)") e o item `L4-parcelas-01-modelo-de-parcelas` no
  `L4.json` já citam os 8.638 lotes do SIG de teste interno como dado de exemplo — ou seja, a ponte entre "o SIG que
  já existe" e "o motor de parcelas que ainda não existe" já estava desenhada antes desta pesquisa, só não fechada com
  a rede.

## C1. A via/rede interna hoje é camada simples (geometria + atributo), nunca grafo — e isso é uma lacuna real, não uma escolha de produto

- Evidência: seção 0 acima. `sistema_viario` não tem topologia; não há tabela de rede de água/esgoto/drenagem/luz.
- Opções: (a) aceitar que hoje não existe nada além da via como linha simples e desenhar o módulo do zero sobre o
  motor L4 já especificado; (b) tentar promover `sistema_viario`/`equipamento`/`derivado_empreendimento` a rede,
  reaproveitando as tabelas existentes; (c) esperar até um caso real trazer o DWG antes de desenhar qualquer coisa.
- Custo de mudar depois: (b) mistura cadastro de simbologia (o que a via PARECE no mapa) com topologia de fluxo (por
  onde a água CORRE) — os dois têm ciclo de vida e edição diferentes; a mesma lição já foi aprendida em C13/C15 do
  `L4_CONCEITO.md` ("resultado de simulação nunca sobrescreve atributo de camada" e "inspeção nunca vira atributo do
  cadastro"). (c) atrasa a decisão de arquitetura para quando já houver prazo comercial em cima.
- Recomendação: **(a)**. `sistema_viario` continua sendo a camada de simbologia da rua (o que se desenha no mapa);
  o que corre por baixo dela (água, esgoto, drenagem, elétrica de baixa tensão, iluminação) é um pacote de ativos novo
  do motor L4 (C4 abaixo), e a via vira, no máximo, uma referência geométrica para o traçado das linhas — nunca a
  própria rede.
- Obriga: nenhuma migração de dado — o gap é aditivo, não corretivo.

## C2. O regime jurídico (área comum privada) é um ATRIBUTO da rede, não um modelo diferente

- Pergunta do dono, respondida: NÃO existe um motivo físico para modelar rede privada diferente de rede pública — um
  poço de visita de esgoto de condomínio e um da concessionária têm o mesmo comportamento de nó/aresta/terminal. A
  diferença é jurídica (quem é dono, quem responde pela manutenção, quem tem direito de acesso), não topológica.
- Opções: (a) estender a subrede (`L4_CONCEITO.md` C6, tabela `plat.rede_subrede`) com `titularidade`
  ('pública'|'privada-condomínio'|'privada-empreendimento') e `responsavel_manutencao` (texto livre: condomínio,
  administradora, concessionária, incorporadora); (b) criar um schema de rede inteiro separado para "privado";
  (c) tratar como um `tenant` diferente por condomínio.
- Custo de mudar: (b) duplica todo o motor especificado em C1-C14 do L4 original (traçado, versionamento, conectores)
  sem ganho — o traçado de jusante não muda de algoritmo por ser privado. (c) já existe para OUTRA finalidade
  (isolamento comercial entre clientes da plataforma) e misturaria dois conceitos.
- Recomendação: **(a)**. Duas colunas na subrede resolvem o regime sem duplicar nada; o traçado/isolamento/exportação
  continuam sendo os mesmos endpoints do L4 original.
- Obriga: extensão pequena em `L4-04-a-controladores-e-tiers` (que já é o lugar onde subrede/controlador nascem).

## C3. O contêiner legal é a parcela (L4-parcelas), a malha física é a rede (L4) — duas peças, uma amarração, nunca uma peça só

- Opções: (a) a área comum/servidão onde a rede fica enterrada é modelada como uma `parcela` (L4-parcelas C16, tipo
  `área comum` ou `servidão`) e a rede (nó/aresta) referencia essa parcela por chave estrangeira, sem herdar geometria
  dela; (b) a rede vive dentro do polígono da parcela sem referência formal (implícito por sobreposição espacial);
  (c) abandonar o modelo de parcelas para este caso e desenhar a via/rede como um tipo de "lote" comum.
- Custo de mudar: (b) impede responder "que parcela responde pela manutenção deste trecho" sem uma consulta espacial
  cara a cada vez; (c) reintroduz a confusão que a regra da casa já proíbe ("parcela ≠ gleba ≠ lote ≠ matrícula",
  `L4_CONCEITO.md` C16).
- Recomendação: **(a)**. A parcela dá o histórico jurídico (que registro criou a área comum, quem é o titular
  registral — o próprio condomínio, ex.: `art. 1.358-A` do Código Civil, já citado como regime nas memórias do SIG de
  teste interno) e a rede dá o comportamento físico (por onde escoa, quem depende de quem). A chave estrangeira da
  rede para a parcela é o mesmo tipo de amarração que L4-parcelas já propõe para lote↔matrícula.
- Obriga: `L4-parcelas-01-modelo-de-parcelas` ganha os dois tipos citados como não-genéricos ("área comum",
  "servidão") explicitamente testados no portão de pronto, não só mencionados na nota.

## C4. Pacote de ativos novo: água/esgoto/drenagem/iluminação PRIVADOS — hoje não existe em lugar nenhum da casa

- Opções: (a) escrever um pacote de ativos (`L4_CONCEITO.md` C3: domínio/tier/grupo/tipo/terminal/regra em JSON
  versionado) chamado `infra-privada-loteamento`, com tipos de nó (caixa de passagem, poço de visita, boca de lobo,
  hidrante, poste, luminária, reservatório, casa de bombas, estação elevatória) e de aresta (tubulação de água,
  coletor de esgoto, galeria de drenagem, circuito de iluminação) — cada um com terminal e regra de conectividade;
  (b) reaproveitar o pacote `elétrica-BR` (mapeado à BDGD) fingindo que o condomínio é uma mini-distribuidora;
  (c) não tipar nada e deixar como atributo livre.
- Custo de mudar: (b) traz campos que não existem em condomínio (CTMT, PAC de BDGD são de rede de CONCESSIONÁRIA,
  não de instalação predial) e falta os que faltam (caixa de passagem, boca de lobo não têm equivalente na BDGD);
  (c) impede validação de regra (`network-rules.htm`, já citado em C3 do L4 original: "sem regra = proibido").
- Recomendação: **(a)**. É trabalho de CATÁLOGO (dado, não código) — o mesmo mecanismo genérico do L4 (C3) já
  aceita "um pacote por domínio"; falta escrever ESTE pacote, que hoje não existe (nem o `elétrica-BR` nem o
  `água-EPANET` cobrem instalação predial/condominial de baixa escala).
- Obriga: `L4-01-a-pacote-de-ativos` ganha este pacote como segundo exemplo (hoje só tem `elétrica-BR`); regra de
  conectividade específica (ex.: boca de lobo só liga a galeria, nunca a coletor de esgoto — separação sanitário ×
  pluvial é a primeira regra que qualquer auditoria de saneamento cobra).

## C5. Nó de interface público×privado (ponto de entrega) é o lugar onde a titularidade muda — precisa existir como tipo de terminal

- Opções: (a) um tipo de terminal especial "ponto de entrega/interface" que marca a transição de rede pública para
  privada (o poste de entrada de energia, o poço de visita onde o coletor do condomínio deságua no interceptor
  municipal, a válvula onde a adutora da concessionária termina e o reservatório do condomínio começa) — carrega os
  dois `titularidade` dos dois lados e é o ponto legal de responsabilidade; (b) não marcar interface nenhuma e deduzir
  na consulta por mudança de `titularidade` entre nós vizinhos; (c) modelar a interface como um "medidor" genérico.
- Custo de mudar: (b) é frágil (uma rede sem `titularidade` preenchida em algum trecho quebra silenciosamente a
  dedução); (c) confunde medição (C14 do L4 original, que já existe para telemetria) com fronteira jurídica.
- Recomendação: **(a)**, como extensão do terminal já decidido em C4 do L4 original (`device-terminals.htm`). O nó de
  interface é o candidato natural a virar ponto de medição (C14) e ponto de auditoria de qualidade — a mesma dupla
  função que a BDGD já cumpre com o padrão de entrada da unidade consumidora.
- Obriga: `L4-03-b-terminais` ganha este tipo; o pacote de C4 (acima) declara pelo menos um tipo de nó "interface".

## C6. Drenagem pluvial vira domínio de rede completo — hoje só existe a distância ao curso d'água NATURAL, nada da rede construída

- Opções: (a) tratar drenagem como um domínio do pacote de C4 (boca de lobo → poço de visita → galeria → bacia de
  detenção → corpo receptor), com traçado de jusante igual ao de água/esgoto (reaproveita C2/C7 do L4 original);
  (b) tratar drenagem só como polígono de bacia de contribuição (sem rede); (c) não modelar, ficar só com o dado que
  já existe (`dist_curso_dagua_m`, para APP).
- Custo de mudar: (b) não responde "que trecho alaga se este cano entope", que é a pergunta que justifica ter rede
  em vez de polígono; (c) é o estado de hoje, que não serve nem para diagnóstico de empreendimento existente.
- Recomendação: **(a)**. É o domínio que mais falta no SIG de teste interno hoje (nem como camada simples existe) e o
  que mais se conecta ao que a casa já sabe fazer fora deste módulo: o motor de espiga de loteamento já mede desnível,
  declividade e drenagem NATURAL por gleba (`ONTOLOGIA_REVERSA/README` do SIG de teste, spike de loteamento v1/v3:
  GLO-30 + `gdaldem slope` + `hidro_nacional_bc250`) — a rede CONSTRUÍDA de drenagem é o próximo passo lógico do MESMO
  pipeline, não uma frente nova.
- Obriga: o pacote de C4 declara o domínio "drenagem" com regra de não-mistura com esgoto sanitário (separação
  absoluta como regra, nunca "proibido implícito").

## C7. Iluminação privada: reaproveitar o MÉTODO de detecção por imagem, nunca o dado de faturamento público

- Opções: (a) usar o mesmo princípio de visão computacional já validado em outro produto da casa (reconhecer poste
  aceso/apagado por imagem de rua, projeto de iluminação pública COSIP) redirecionado para inventariar postes
  PRIVADOS de um condomínio, sem cruzar com a base de faturamento pública (que não se aplica: luz de condomínio não é
  COSIP); (b) copiar o pipeline inteiro, incluindo o casamento com a camada de Ponto de Iluminação Pública da BDGD;
  (c) não reaproveitar nada, escrever detector do zero.
- Custo de mudar: (b) tenta casar poste privado com um cadastro que é de rede PÚBLICA — não existe registro de poste
  de condomínio na BDGD, o casamento sempre falharia; (c) descarta um método já provado (câmera+GPS+fusão com
  cadastro) por medo de reaproveitar o produto errado.
- Recomendação: **(a)**. O ganho real está no MÉTODO (câmera de veículo ou drone, detecção de luminária acesa/apagada
  à noite), não na base de cobrança pública — que é o que o outro produto soma. Para o condomínio o produto é
  inventário + estado operacional (quantos postes existem, quantos estão apagados), sem nenhuma pretensão de receita
  de concessionária.
- Obriga: o pacote de C4 declara tipo de nó "luminária" com atributo `estado_operacional` e `fonte='drive-by'|
  'declarado'|'satélite'` (regra da casa de nunca confundir fonte).

## C8. Terminal casa↔rede: o ponto onde o objeto BIM da casa (GABARITO) vira nó da rede do empreendimento (L4) — não existe hoje

- Opções: (a) padronizar, no objeto BIM da tipologia de casa, um marcador explícito (posição + tipo) para cada ponto
  de saída (entrada de água, saída de esgoto, entrada de energia) e importar esse marcador como um nó-terminal do
  lote na rede do empreendimento, ligando a casa (de dentro para fora) à rede (de fora para dentro); (b) inferir o
  ponto de conexão pela geometria (mais próximo da rede) sem marcador explícito na casa; (c) não ligar — cada sistema
  fica isolado (a casa sabe da própria instalação, a rede do empreendimento não sabe que a casa existe).
- Custo de mudar: (b) é frágil contra qualquer casa fora do padrão (recuo diferente, lote de esquina); (c) é o estado
  de hoje e mantém duas ilhas de dado que não se cruzam nunca — nenhum diagnóstico "esta rua vai sobrecarregar com
  20 casas construídas" é possível.
- Recomendação: **(a)**. O trabalho não é modelar de novo o que já existe (GABARITO já resolve hidrossanitário e
  elétrico DENTRO da casa, por NBR); é padronizar UM marcador de saída por sistema e usar exatamente o "terminal como
  nó" que o motor de rede já decidiu (`L4_CONCEITO.md` C4). Hoje esse marcador não existe declarado em nenhum lugar —
  é o motivo pelo qual o BIM da casa e a rede do loteamento nunca se falam (mesma causa-raiz que a coordenação
  federada do BIM já documentou: motor pronto, sem rota de produto ligando as pontas).
- Obriga: dependência nova declarada — GABARITO precisa adicionar esse marcador ao pacote de exportação da tipologia
  (fora do escopo desta pesquisa: GABARITO é projeto separado, muda por decisão própria).

## C9. Digitalização de DWG 2D → rede georreferenciada é SERVIÇO, é o gargalo real, e nunca deve ser prometida como pronta

- Opções: (a) pipeline semi-automático com revisão humana obrigatória: converter DWG→DXF (LibreDWG, já instalado e
  provado no GPU box para outro fim), aplicar heurística de padrão de camada/layer quando existir, ancorar por pontos
  de controle no polígono do lote/quadra já georreferenciado, e devolver um relatório do que foi digitalizado
  automaticamente × o que precisa de revisão manual — nunca "pronto" sem o relatório; (b) prometer digitalização
  automática completa; (c) recusar qualquer DWG sem padrão e pedir para o cliente refazer o levantamento.
- Custo de mudar: (b) já foi a lição aprendida em outro produto da casa e queimou a demonstração (regra dura já
  registrada: "nunca prometer T3 antes de abrir um DWG deles" — `DOSSIE_incorporadora-de-teste_SIG.md` seção 5); (c) fecha a porta para
  o cliente mais comum (a maioria não tem as-built em padrão nem georreferenciado).
- Recomendação: **(a)**, com preço e prazo cotados como ETAPA SEPARADA (o mesmo padrão de "Fase 0" que o caso lido já
  usa: diagnóstico pago primeiro, antes de qualquer promessa sobre o resultado).
- Obriga: este item nunca entra no preço de assinatura do módulo (C11); é serviço por empreendimento, cotado à parte,
  igual ao resto do onboarding de dado que a plataforma já trata como serviço (BDGD, DWG de loteamento, etc.).

## C10. O segundo comprador (condomínio/administradora) precisa de um perfil de usuário e de um portal que hoje não existem

- Opções: (a) criar um quinto perfil (`síndico`/`administradora`) além dos quatro que já existem no SIG de teste
  interno (`admin`/`tecnico`/`consulta`/`cliente`, `schema.sql`/`schema_v2.sql`), com escopo de acesso limitado à
  infraestrutura comum do(s) empreendimento(s) sob sua gestão — nunca ao dado comercial/financeiro da incorporadora;
  (b) reaproveitar o perfil `cliente` (hoje ligado a lote individual) para a administradora também; (c) não separar,
  vender o mesmo acesso da incorporadora para a administradora.
- Custo de mudar: (b) mistura duas relações contratuais diferentes (o morador vê o próprio lote; a administradora
  precisa ver TODA a infraestrutura comum, nunca o dado privado dos lotes individuais) sob o mesmo modelo de permissão,
  que quebra a primeira vez que uma incorporadora quiser vender o módulo separado da administradora; (c) inviabiliza
  o modelo de receita descrito em C11 (a assinatura é de quem realmente usa e paga por décadas).
- Recomendação: **(a)**. É o comprador que justifica a receita recorrente (`DOSSIE_incorporadora-de-teste_SIG.md` seção 5: "a rede...
  é mantida por décadas pelo condomínio/administradora... isso muda o modelo de receita: entrega única para a
  incorporadora, assinatura para cada condomínio entregue"). Sem esse perfil o produto não tem para quem cobrar depois
  da entrega.
- Obriga: extensão do controle de acesso por papel já existente (RLS por perfil), não um sistema de permissão novo.

## C11. Modelo comercial: assinatura por condomínio entregue, separada e adicional ao preço por empreendimento da incorporadora

- Opções: (a) módulo de infraestrutura interna vendido como assinatura mensal POR CONDOMÍNIO após a entrega (o
  comprador de C10), independente do contrato com a incorporadora, cobrindo manutenção/consulta/alerta de ativo;
  (b) embutir no mesmo contrato da incorporadora sem discriminar; (c) vender como capex único, sem recorrência.
- Custo de mudar: (b) faz o módulo desaparecer do orçamento na primeira renegociação com a incorporadora (ele não é
  dela, é do condomínio); (c) descarta a única fonte de receita que sobrevive à entrega do empreendimento — a regra
  já registrada em outro caso da casa é que não se vende software como capex para quem financia por CRI/venda de
  carteira (o comprador certo daquele produto é outro).
- Recomendação: **(a)**. É a mesma disciplina de precificação por unidade de negócio já usada noutros módulos da
  plataforma (preço ancorado em quem usa e por quanto tempo, não em quem primeiro pediu).
- Obriga: nenhuma dependência de código; é decisão comercial que usa o perfil de C10 e o pacote de C4 como unidade de
  medida ("por condomínio, por ativo cadastrado").

## C12. Veredito: vale como módulo — mas o custo real está nas quatro peças que não existem, não no motor de rede

- O motor físico de rede (nó/aresta, topologia derivada, traçado, subrede, versionamento, conectores EPANET/OpenDSS,
  RLS por inquilino) **já está especificado** em `L4_CONCEITO.md`/`L4.json` para outro domínio (rede pública de
  energia/água) e se aplica sem alteração de arquitetura ao caso privado — só ganha duas colunas de regime (C2) e um
  tipo de terminal de interface (C5). Isso é a prova de que a decisão certa foi generalizar o L4 desde o início.
- A malha de parcelas (L4-parcelas) já contempla os tipos "área comum" e "servidão" necessários para o contêiner
  legal (C3) — falta só testar esses dois tipos explicitamente no portão de pronto, não desenhar nada novo.
- O que falta de verdade, e é onde está o esforço real deste módulo: (1) o pacote de ativos de infraestrutura privada
  em si (C4), que hoje não existe nem como rascunho; (2) o domínio de drenagem pluvial completo (C6), inexistente até
  como camada simples; (3) o terminal casa↔rede (C8), que depende de uma mudança do lado do GABARITO (fora desta
  pesquisa); (4) a digitalização de DWG como serviço cotado à parte (C9), que é o gargalo que já custou a lição em
  outro caso da casa; (5) o perfil comercial do segundo comprador (C10/C11), sem o qual não há para quem vender depois
  da entrega.
- **Recomendação: abrir como módulo, sequenciado atrás do L4 público** (a energia/água pública já está no roadmap por
  necessidade própria da plataforma; a versão privada herda quase tudo dela). Não vender como produto pronto até (1)
  e (2) estarem escritos e (3) ter ao menos um marcador combinado com o GABARITO — sem isso o módulo promete uma
  ligação casa↔rede que hoje não existe em nenhuma das duas pontas.

## O que fica FORA desta rodada (declarado)

- Qualquer dado real de um cliente específico — todo exemplo de execução usa dado aberto ou sintético, como o
  SIG de teste interno já faz hoje (regra da casa, sem exceção).
- Cálculo hidráulico da rede predial (dentro da casa) — isso é GABARITO, projeto separado; este módulo só recebe o
  ponto de saída da casa, não recalcula o que está dentro dela.
- Gás encanado privado — mencionado no pedido original só como parte do texto do caso lido; sem fonte de dado, sem
  pacote de ativos escrito, fica registrado como candidato futuro, mesmo tratamento que o L4 original deu a
  "circuitos de telecom" (fora desta rodada).
- Qualquer promessa de digitalização automática de DWG sem revisão humana (C9) — é a lição mais cara já registrada
  neste tipo de caso; nunca repetir.
- Preço específico — este documento decide arquitetura e sequenciamento, não numera contrato; C11 registra o
  MODELO de cobrança (assinatura por condomínio), nunca um valor.
