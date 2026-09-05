# plat — plataforma SIG corporativa, pilha aberta

Substitui o ArcGIS Enterprise para o cliente: imagens (COG/STAC/tiles por inquilino), plataforma de
dado do cliente (catálogo, mapas, edição, serviços Esri-compatíveis e OGC, análise, painéis, campo,
migração), motor multicritério explicável, rede de utilidades (modelo, traçado, edição com regras,
BDGD), construtores arrasta-e-solta (app, fluxo, formulário, narrativa), acervo e conectores, operação.

Construído pelo laço `plataforma/laco/` (estado, portões, adversário, ledger). Este README descreve o que
EXISTE; o que ainda não existe está em `plataforma/laco/PAINEL.md`, nunca aqui.

- `ARQUITETURA.md` — componentes, portas, esquema, decisões (ADR em `docs/adr/`).
- `MANUAL.md` — uma seção por tela, com captura real.
- `CHANGELOG.md` — por turno.
- `docs/PARIDADE.md` — tabela viva feito/parcial/fora contra o ArcGIS Enterprise.
- `install.sh` — instalação idempotente; `make check` — suíte inteira.
