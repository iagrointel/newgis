"""Modelos 3D no mapa (item L2-09-c-modelos-gltf-ifc-3dtiles).

Três coisas, um pacote:

* `glb` — o recipiente glTF 2.0 binário (GLB): ler, escrever, listar recurso externo e medir a caixa
  envolvente do modelo. É a moeda comum: o que o navegador desenha, o que o conversor de IFC produz e o
  que vira conteúdo de tile.
* `ifc` — leitor do arquivo IFC no formato STEP (ISO 10303-21), em Python puro: elementos com GUID, tipo,
  pavimento e propriedades, e a geometria dos casos que a casa precisa hoje (malha tesselada e sólido de
  extrusão). O que sai daqui é o mesmo material que o `glb` monta.
* `tiles3d` — OGC 3D Tiles 1.1 (Community Standard 18-053r2) gerado do GLB, com divisão em quadrantes
  quando o modelo é grande demais para um tile só.

`posicionamento` é a geodésia comum aos três: onde o modelo cai no globo (longitude, latitude, altura,
rotação e escala) e qual é a caixa que ele ocupa depois de posto lá.
"""
