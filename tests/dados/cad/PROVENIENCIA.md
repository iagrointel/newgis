# Procedência dos arquivos CAD de teste (item L0-04-e)

| arquivo | origem | licença |
|---|---|---|
| `blocos.dxf`, `polilinhas.dxf`, `textos.dxf`, `camada_longa.dxf`, `polegada.dxf`, `binario.dxf` | gerados por `tests/dados/cad/gerar.py` (ezdxf 1.4.4, saída normalizada para ser byte a byte determinística) | nossos |
| `r2000.dwg` | gerado de `polilinhas.dxf` por `dxf2dwg --as r2000` (GNU LibreDWG 0.14.8583) | nosso (conteúdo), ferramenta GPL-3 usada como programa separado |
| `r2018.dwg` | `test/test-data/2018/Polyline.dwg` do conjunto de teste do **GNU LibreDWG** (https://www.gnu.org/software/libredwg/) | GPL-3, do projeto LibreDWG |
| `r2018_ilegivel.dwg` | os 6 bytes de cabeçalho de `r2018.dwg` seguidos de 1.994 bytes embaralhados por conta própria | nosso |

Por que `r2018.dwg` não é nosso: **o LibreDWG só ESCREVE DWG até r2004** (`dxf2dwg --as` aceita r12, r14,
r2000, r2004; r2007 em diante são "planned"). Não há, nesta casa, ferramenta livre que grave um AC1032, e a
cláusula do portão exige um R2018 de verdade. O arquivo tem 27.691 bytes, é um desenho de uma polilinha, e
entra na árvore só como entrada de teste.

Isto é uma **fronteira declarada, não uma decisão tomada**: se o dono não quiser arquivo GPL-3 na árvore, a
saída é comprar/gerar um R2018 com ferramenta proprietária (ODA, AutoCAD) e trocar o arquivo — o teste não
muda, só o insumo. Enquanto não houver decisão, fica como está e está escrito aqui.

## Como refazer os gerados

    venv/bin/python tests/dados/cad/gerar.py
    LD_LIBRARY_PATH=/opt/plat/libredwg/lib /opt/plat/libredwg/bin/dxf2dwg -y --as r2000 \
        -o tests/dados/cad/r2000.dwg tests/dados/cad/polilinhas.dxf

O arquivo de 2 milhões de entidades do ataque do adversário NÃO fica na árvore (180 MB). Gere fora dela e
aponte `PLAT_CAD_GRANDE` para ele; sem a variável o teste é saltado, com a razão escrita.
