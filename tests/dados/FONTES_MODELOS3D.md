# Fonte do IFC de teste (item L2-09-c-modelos-gltf-ifc-3dtiles)

| arquivo | `Building-Architecture.ifc` |
|---|---|
| origem | buildingSMART International, repositório público `Sample-Test-Files`, pasta `IFC 4.0.2.1 (IFC 4 ADD2 TC1)/Simple-Scene/` |
| endereço | https://github.com/buildingSMART/Sample-Test-Files |
| licença | Creative Commons Attribution 4.0 International (CC BY 4.0), declarada no `LICENSE` do repositório |
| esquema | IFC4 (`FILE_SCHEMA(('IFC4'))`), unidade de comprimento milímetro |
| bytes | 142.325 |
| sha256 | `8790a1e193e82b8e7e7f337ec2633cd40f2120590317a1443503a25b079e2e80` |
| baixado em | 08/09/2026 |

Conferir: `sha256sum tests/dados/Building-Architecture.ifc`.

É a cena de demonstração do próprio órgão de normalização (uma casa: paredes, lajes, elementos genéricos,
mobiliário), não um projeto de cliente nem de parceiro. A geometria vem em malha tesselada
(`IfcTriangulatedFaceSet`) e em sólido de extrusão (`IfcExtrudedAreaSolid`) — as duas formas que
`app/modelos3d/ifc.py` converte.
