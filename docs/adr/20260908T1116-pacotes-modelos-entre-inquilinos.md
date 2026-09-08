# ADR 20260908T1116 — pacote de documentos entre inquilinos e galeria de modelos

Item `L5-37-pacotes-modelos-entre-inquilinos`. Depende de `L5-05-documento-versoes` (documento com grafo de
nós ULID e forma canônica com sha256) e de `L5-14-publicacao-links-embed` (é por ela que se prova que o app
importado FUNCIONA no inquilino de destino, e não só que a linha entrou no banco).

## 1. O que é um pacote

Um zip com exatamente duas coisas:

```
manifesto.json
documentos/<uuid do documento>.json
```

`manifesto.json` traz `formato`/`versao_formato`, a origem (só o slug do inquilino), o id da RAIZ, a lista de
documentos (id, tipo, título, arquivo, sha256 de cada um), a lista de FONTES declaradas e, por último,
`sha256_conteudo`.

Documento = item cujo tipo tem `tem_dado_fisico = false` (app, painel, formulário, fluxo, mapa, estilo,
modelo multicritério). Fonte = item cujo tipo tem `tem_dado_fisico = true` (camada, vista, imagem, arquivo,
rede): NUNCA entra no zip; é declarado com `campos`, `geometria` e `srid` — o esquema que o documento
assume existir — e quem importa diz qual item do destino faz esse papel.

Consequência que é o ponto do item: **o pacote não carrega dado**. O pacote do app de teste (2 documentos,
3 fontes) tem 1.622 bytes (`tests/medidas/L5-37-pacotes-modelos-entre-inquilinos.json`). Por isso ele
atravessa inquilino e atravessa instalação (o appliance do L7-11), e por isso não há questão de licença de
dado nem de LGPD no transporte.

## 2. Por que o fecho é lido do documento, e não só do extrator de relações

`app/catalogo/relacoes.py` mantém `plat.item_relacao` a partir de extratores por tipo. Para MONTAR o pacote,
percorrer os UUIDs citados no `dados` dá o mesmo resultado e não depende de haver extrator para cada tipo
novo de construtor. Para IMPORTAR, ler todos os UUIDs é uma decisão de segurança, não de conveniência: um id
que o extrator do tipo não conhece entraria no destino sem ser conferido. A regra fica: **todo UUID citado
em qualquer lugar do documento tem de ser outro documento do pacote ou uma fonte mapeada**; qualquer outro
para a importação inteira com `referencia_desconhecida`. É o que recusa o pacote montado com o id de um item
de outro inquilino, mesmo quando o adversário reassina o pacote corretamente.

O contrário — aceitar o id e deixar a RLS resolver — daria 404 na leitura e um app quebrado em silêncio, que
é exatamente o defeito que este item existe para não ter.

## 3. Ids: regerar tudo, numa passada

Na importação monta-se um mapa `antigo → novo` com três tipos de entrada: UUID de documento (uuid novo),
ULID de nó (ulid novo) e UUID de fonte (o item escolhido no destino). A substituição é uma única caminhada
em profundidade sobre o documento.

- UUID fora do mapa: para a importação (seção 2).
- ULID fora do mapa: fica como está. Os ids de nó do pacote INTEIRO entram no mapa antes da passada, então
  um ULID que sobra é texto do documento, não referência; trocá-lo seria corromper conteúdo.

Alternativa recusada: manter os ids da origem e só trocar em caso de colisão. Fica mais barato, mas importar
o mesmo pacote duas vezes no mesmo inquilino passaria a ser um caso especial, e o id do documento deixaria de
dizer em que instalação ele nasceu. Regerar sempre é a regra simples que não tem exceção.

## 4. Compatibilidade de esquema

Por fonte mapeada, `comparar_esquema` devolve uma lista de diferenças com `campo`, `regra`, `esperado`,
`encontrado` e `bloqueia`:

| regra | bloqueia | motivo |
|---|---|---|
| `campo_ausente` | sim | o documento cita um campo que o destino não tem: a tela abriria vazia ou com erro |
| `tipo_diferente` | sim | filtro, expressão e simbologia assumem o tipo |
| `geometria_diferente` | sim | um visor de polígono não desenha ponto |
| `srid_diferente` | **não** | reprojetar é rotina da plataforma e o documento não guarda coordenada de dado |

Campo A MAIS no destino não é diferença: o documento usa os que cita.

`POST /api/pacotes/verificar` não escreve nada e devolve essa lista com `pronto: false`; a importação recusa
com a MESMA lista dentro de `detalhe`. A tela `/modelos` desenha uma linha por fonte com o `<select>` do
destino e as diferenças embaixo.

## 5. Zip hostil

`app/catalogo/pacote.py::ler` não interpreta byte nenhum antes de `app/ingestao/formatos.py::conferir_zip`,
que já é a guarda do upload de dado (`..` no caminho, caminho absoluto, `\`, byte de controle, nome > 255
bytes, zip aninhado, link simbólico, número de entradas, tamanho descomprimido e razão de compressão).
Reusar essa função em vez de escrever outra é deliberado: guarda de segurança duplicada envelhece em ritmos
diferentes. Depois dela vêm, nesta ordem, formato, versão de formato, assinatura do manifesto e sha256 de
cada documento.

## 6. Assinatura

`sha256_conteudo` = sha256 da forma canônica do manifesto SEM esse campo, com a mesma canonização do L5-05
(`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`, reproduzível com `jq -cS |
sha256sum`). Como o manifesto contém o sha256 de cada documento, um byte trocado em qualquer arquivo do zip
muda um dos dois valores.

O que isto é: uma soma de verificação de integridade, conferida na leitura. O que isto **não** é: prova de
autoria. Pacote assinado com chave (Ed25519, como o L7-16 faz com o pacote de atualização) é outro item; o
adversário que reassina o manifesto continua sendo barrado, mas pela regra da seção 2, não pela assinatura.

## 7. Galeria de modelos

`plat.pacote_modelo` guarda o zip em `bytea`. Motivo: o pacote é pequeno (teto `PACOTE_BYTES_MAX` = 4 MiB, e
o real fica em quilobytes) e a galeria tem de funcionar no appliance, onde pode não haver armazenamento de
objetos. A tabela não aceita `UPDATE` (`REVOKE`): modelo é imutável, republicar é publicar outro — a mesma
disciplina de `versao_migracao` e de `item_versao`.

Escopo `inquilino` (só quem publicou enxerga) ou `plataforma` (todos enxergam). Quem recusa o escopo
`plataforma` de quem não é superadmin é a POLÍTICA DE LINHA (`plat.eh_superadmin()`), não um `if` na rota;
a rota só traduz a recusa do banco em 403.

**O que ficou de fora, e por quê**: a hipótese do item fala em "modelo do canal — parceiro publica modelo
para os inquilinos dele". Não existe hierarquia de inquilino nesta plataforma: há `plataforma`, há
`inquilino`, e nada entre os dois. Inventar um campo "parceiro" aqui seria inventar um modelo de negócio no
meio de uma migração. Quando o item que criar a relação parceiro→inquilinos chegar, isto é um valor a mais no
`CHECK` do escopo e uma cláusula a mais na política de leitura.
