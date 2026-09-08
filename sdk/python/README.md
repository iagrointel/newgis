# SDK Python `plat`

Análise / beta privado. SDK para a plataforma SIG (item `L7-08-b-sdk-python`).

```bash
pip install ./sdk/python
```

```python
from plat import Plataforma

# 1) primeira vez: login + criação de um token de serviço
p = Plataforma.entrar("https://SEU-INQUILINO.exemplo", "SEU-INQUILINO", "usuario", "senha")

# 2) uso normal, com o token já emitido
p = Plataforma("https://SEU-INQUILINO.exemplo", token="plat_...")

pagina = p.itens.listar(limite=20)
camada = p.camadas.criar(titulo="Minha camada", dados={})
for item in p.itens.todos(tipo="camada_vetorial"):
    print(item["id"], item["titulo"])

job = p.jobs.esperar(algum_job_id, tempo_limite_s=120)
```

## O que é gerado, o que é escrito à mão

- `src/plat_gerado/`: cliente gerado por `openapi-python-client` a partir de `docs/openapi.json`
  (raiz do repositório). **Nunca editar à mão** — regenere com `scripts/gerar_sdk.sh` (raiz do
  repositório) e comite o resultado. A configuração de geração (`config_geracao.yaml`, ao lado
  deste README) é a única fonte de verdade sobre nomes de classe/pacote.
- `src/plat/`: camada ergonômica escrita à mão (`Plataforma`, `.itens`, `.camadas`, `.mapas`,
  `.jobs.esperar()`, `.tokens`, erros como Problem Details). Devolve dicionários simples (o mesmo
  corpo que a API manda), não os objetos `attrs` do gerado — quem precisa do objeto tipado importa
  `plat_gerado` direto (instalado junto).

## O que NÃO existe ainda (e por quê o SDK não finge que existe)

A API hoje não tem rotas de `/api/camadas` (recurso próprio), `/api/mapas`, tiles nem exportação —
`camada` e `mapa` são só o campo `tipo` de um item do catálogo (`/api/itens`). `.camadas` e `.mapas`
neste SDK são por isso VISÕES (filtro de `tipo`) sobre `.itens`, não chamadas a rotas que não
existem. Um FeatureServer de verdade sobre a camada depende de `L2-04-servicos-esri-ogc`
(dependência aberta deste item — ver `docs/PARIDADE.md`); tiles e exportação são outros itens
(L1/L5) ainda não mesclados em `master`. Quando essas rotas existirem, o SDK regenerado ganha os
métodos correspondentes automaticamente — não é preciso reescrever esta camada à mão, só o
cliente gerado.

## Escopos de token

Tokens de serviço usam o vocabulário fechado de `app/auth/escopos.py`: `catalogo:ler`,
`camada:ler`, `camada:editar`, `tiles:ler`, `jobs:executar`, `rota:usar`, `geocodificar:usar`,
`admin:inquilino` (cobre tudo, exceto gerir os próprios tokens/senha/2FA/sessões). Um token só
com `catalogo:ler` lê o catálogo mas não cria, edita nem apaga item — ver `tests/sdk/test_adversario.py`.

## Regenerar

```bash
bash scripts/gerar_sdk.sh        # a partir da raiz do repositório
git diff --stat sdk/python/src/plat_gerado   # reprodutível: sem diff quando o OpenAPI não mudou
```
