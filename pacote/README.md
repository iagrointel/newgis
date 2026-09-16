# plat_geo — SDK Python geoespacial da plataforma

Pacote Python que consome a API da plataforma por **token de serviço**: catálogo de itens, acervo da
casa, fila de jobs e ferramentas geoespaciais (item L2-16-a-sdk-python-geo). Camada "geo" ao lado do
SDK genérico `plat` (`sdk/python`, item L7-08-b) — nome distinto por decisão do gerente (G3):
os dois pacotes existiam como `plat 0.1.0` com APIs incompatíveis; este é o `plat_geo`, o outro
continua `plat`. Distribuição interna (`make pacote` gera o wheel em `pacote/dist/`); sem PyPI até
decisão do dono.

## Instalação

```bash
pip install pacote/dist/plat_geo-<versão>.whl
```

ou, num checkout, apontando o `PYTHONPATH` para `pacote/`.

## Uso

```python
from plat_geo import Plataforma

pla = Plataforma("https://plataforma.exemplo", token="pt_…")

# catálogo: listagem paginada por cursor (iterar() pagina sozinho, em lotes)
pagina = pla.catalogo.listar(tipo="camada_vetorial", q="uso", limite=100)
for item in pla.catalogo.iterar(tipo="camada_vetorial", limite=100):
    print(item["id"], item["titulo"])

# acervo da casa: fontes oficiais com procedência; assinar cria item "conexao"
for fonte in pla.acervo.iterar(dominio="Ambiental"):
    ficha = pla.acervo.ficha(fonte["fonte_id"])
print(ficha["licenca"], ficha["frescor"])

# jobs: criar, esperar com progresso, resultado
job = pla.jobs.criar("ferramentas.buffer", {"geometria": ponto, "distancia_m": 100.0})
pronto = pla.jobs.esperar(job["id"], ao_progresso=lambda p, m: print(f"{p}%"))

# ferramentas: espera e devolve o resultado; a de catálogo traz item_id com procedência
r = pla.ferramentas.buffer(ponto, 100.0, srid=31983, titulo="área de 100 m em torno do poço")
item = pla.catalogo.abrir(r["item_id"])
print(item["dados"]["procedencia"]["sha256_geometria_entrada"])
```

## Erros

Toda recusa da API vira exceção tipada (`plat_geo.erros`), com `.status`, `.codigo` e `.detalhe`:

| classe | status | quando |
|---|---|---|
| `ErroAutenticacao` | 401 | token ausente, revogado, expirado |
| `ErroPermissao` | 403 | sem o privilégio (`.exigido`) ou o escopo (`.escopo`) |
| `NaoEncontrado` | 404 | inexistente ou de OUTRO inquilino (RLS devolve 404 de propósito) |
| `Conflito` | 409 | estado impede (fonte com risco de dado pessoal sem `confirma_risco_pii=True`) |
| `ErroLimite` | 413 | cota/tamanho excedido |
| `ErroValidacao` | 422 | parâmetro fora do esquema (ex.: srid geográfico em `buffer`) |
| `ErroServidor` | 5xx | falha da plataforma |
| `FalhaJob` | — | job terminou em `falhou` (`.job["erro"]`) ou `cancelado` (`.cancelado=True`) |

## Escopo desta versão (e o que NÃO tem)

A hipótese do item previa `Camada.ler/escrever` (GeoDataFrame via FeatureServer/edição transacional),
`Raster.ler` (TiTiler/STAC) e widget de mapa em notebook. Essas três partes dependem de itens ainda
não em master (L2-04-c parcial, L2-03-a refutado) e ficam de FORA com pendência registrada no
handoff — o SDK não expõe módulo morto: quem precisa de geometria hoje usa
`pla.ferramentas.buffer` e recebe GeoJSON puro.
