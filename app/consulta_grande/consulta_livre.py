"""Ferramenta `consulta_sql`: SQL livre do usuário sobre os Parquet do inquilino
(item L2-15-b-consultas-duckdb-em-escala).

É uma ferramenta do MESMO catálogo das outras — nenhuma rota nova, nenhum tipo de job novo, nenhuma tabela
nova. Isso não é economia de esforço: é a decisão de que "rodar SQL grande" não é uma exceção do sistema, e
sim mais uma ferramenta. Com isso ela herda, sem uma linha a mais, o formulário gerado do manifesto, a
estimativa de custo, a fila com "1 pesado por vez", o cancelamento, a publicação do resultado como camada,
o `derivado_de` para cada fonte e o registro de evento `analises/executar`.

O usuário escreve `SELECT ... FROM fonte_a` — nunca um caminho de arquivo. As fontes entram como quatro
parâmetros nomeados (`fonte_a` obrigatória, `fonte_b`/`fonte_c`/`fonte_d` opcionais) e viram views com esses
mesmos nomes dentro do motor. Duas barreiras recusam qualquer outra forma de leitura: a árvore de sintaxe
(`app/consulta_grande/seguranca.py`) e o próprio motor com o acesso externo desligado e a configuração
trancada (`app/consulta_grande/duckdb_cli.py`).

O tamanho do SQL é o do vocabulário GP da Esri para `GPString` (2000 caracteres), e não um número escolhido
aqui: quem manda a consulta por um cliente Esri e quem manda pela API própria têm de caber no mesmo limite.
"""

from __future__ import annotations

from app import limites
from app.consulta_grande import execucao
from app.ferramentas.registro import Parametro, ferramenta

FONTES = ("fonte_a", "fonte_b", "fonte_c", "fonte_d")


@ferramenta(
    nome="consulta_sql", titulo="Consulta SQL sobre os Parquet do inquilino", categoria="resumo", versao=1,
    descricao="Roda um SELECT do usuário sobre as fontes Parquet escolhidas, que aparecem na consulta com os "
              "nomes fonte_a a fonte_d. Só leitura: nenhuma função de arquivo, de rede ou de catálogo é "
              "aceita, e o resultado vira uma camada com o SQL e o sha256 dos arquivos na proveniência.",
    parametros=(
        Parametro("fonte_a", "GPFeatureRecordSetLayer", "fonte Parquet A",
                  descricao="item de catálogo tipo parquet; na consulta chama-se fonte_a"),
        Parametro("fonte_b", "GPFeatureRecordSetLayer", "fonte Parquet B", obrigatorio=False),
        Parametro("fonte_c", "GPFeatureRecordSetLayer", "fonte Parquet C", obrigatorio=False),
        Parametro("fonte_d", "GPFeatureRecordSetLayer", "fonte Parquet D", obrigatorio=False),
        Parametro("sql", "GPString", "consulta",
                  descricao="um único SELECT; COPY, CREATE, ATTACH, INSTALL, LOAD, PRAGMA e SET são recusados"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: max(
        sum(int(e.get("feicoes") or 0) for e in entradas.values()),
        limites.FERRAMENTA_SINCRONO_CUSTO_MAX + 1),
    limites={"aceita_parquet": True, "sql_max": limites.CONSULTA_GRANDE_SQL_MAX,
             "linhas_saida_max": limites.CONSULTA_GRANDE_LINHAS_SAIDA_MAX,
             "tempo_s": limites.CONSULTA_GRANDE_TEMPO_S,
             "memoria_mb": limites.CONSULTA_GRANDE_MEMORIA_MB,
             "threads": limites.CONSULTA_GRANDE_THREADS},
)
def consulta_sql(ctx, entradas, parametros, destino):
    return execucao.rodar_sql_livre(ctx, entradas, parametros["sql"], destino)
