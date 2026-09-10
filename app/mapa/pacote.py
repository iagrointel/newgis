"""Pacote de mapa (item L2-01-l, cláusula "mapa inteiro como pacote ... para levar a outra instalação").

Um pacote é um zip com quatro coisas e nada mais:

    MANIFESTO.json      o documento do mapa, a lista de camadas citadas e a simbologia de cada uma
    dados.gpkg          UM GeoPackage com uma tabela por camada citada (`cam_1`, `cam_2`, ...)
    estilos/<n>.json    o estilo MapLibre de cada camada (Style Spec pura)
    estilos/<n>.sld     o mesmo estilo em SLD 1.0.0, para quem lê o pacote em QGIS/GeoServer

Duas regras que o adversário vai atacar e que este módulo tem de garantir sozinho:

1. **Só o que o mapa cita.** O GeoPackage recebe uma tabela por camada REFERENCIADA no corpo do
   documento; nenhuma outra camada do inquilino entra, mesmo que seja da mesma tabela de catálogo. A
   contagem de tabelas do GeoPackage é a prova, e o teste do portão a mede com `ogrinfo`.
2. **Nada de outro inquilino.** As camadas são lidas pela mesma conexão do ogr2ogr da exportação
   (`motor.conninfo_pg`), com o inquilino na string de conexão e a RLS do PostgreSQL fazendo o corte
   dentro do banco (ver a decisão 1 do topo de `app/exportacao/motor.py`).

O identificador da camada dentro do pacote (`id_no_pacote`) é o uuid que ela tinha na instalação de
origem: ele serve para reescrever o corpo do mapa na importação (de-para) e para o leitor humano saber
de onde veio — nunca é reaproveitado como identificador na instalação de destino, que gera os seus.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.mapa import simbologia as simb_mod
from app.mapa import sld as sld_mod

VERSAO_PACOTE = 1
NOME_MANIFESTO = "MANIFESTO.json"
NOME_GPKG = "dados.gpkg"


class ErroPacote(Exception):
    """Pacote malformado (não é zip, falta manifesto, versão desconhecida, camada sem tabela)."""


def camadas_citadas(corpo: dict) -> list[str]:
    """Os uuid de camada que o documento de mapa cita, na ordem em que aparecem, sem repetição."""
    vistos: list[str] = []
    for c in (corpo or {}).get("camadas") or []:
        cid = c.get("camada_id") if isinstance(c, dict) else None
        if isinstance(cid, str) and cid not in vistos:
            vistos.append(cid)
    return vistos


def entrada_de_camada(indice: int, item: dict, dados: dict) -> dict:
    """Uma linha do manifesto a partir do item de catálogo da camada."""
    geometria = dados.get("geometria") or "Point"
    simb = simb_mod.normalizar(dados.get("simbologia"), geometria)
    return {
        "id_no_pacote": str(item["id"]),
        "titulo": item["titulo"],
        "tabela_no_pacote": f"cam_{indice}",
        "geometria": geometria,
        "srid": int(dados.get("srid") or 4326),
        "campos": dados.get("campos") or [],
        "simbologia": simb,
        "estilo_maplibre": f"estilos/cam_{indice}.json",
        "estilo_sld": f"estilos/cam_{indice}.sld",
    }


def manifesto(mapa: dict, camadas: list[dict], gerado_em: str) -> dict:
    return {
        "plat_pacote": VERSAO_PACOTE,
        "gerado_em": gerado_em,
        "mapa": {"titulo": mapa.get("titulo"), "descricao": mapa.get("descricao"),
                 "corpo": mapa.get("corpo") or {}},
        "camadas": camadas,
        "dados": NOME_GPKG,
    }


def escrever(destino_zip: Path, man: dict, gpkg: Path) -> None:
    """Monta o zip. O GeoPackage entra por `write` (leitura em blocos do disco), nunca em memória."""
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(NOME_MANIFESTO, json.dumps(man, ensure_ascii=False, indent=2))
        z.write(gpkg, NOME_GPKG)
        for camada in man["camadas"]:
            fonte = f"plat-{camada['id_no_pacote']}"
            estilo = {
                "version": 8,
                "name": camada["titulo"],
                "layers": simb_mod.camadas_maplibre(camada["simbologia"], camada["geometria"], fonte,
                                                    fonte, camada["tabela_no_pacote"]),
            }
            z.writestr(camada["estilo_maplibre"], json.dumps(estilo, ensure_ascii=False, indent=2))
            z.writestr(camada["estilo_sld"], sld_mod.gerar(camada["simbologia"], camada["geometria"],
                                                           nome=camada["tabela_no_pacote"],
                                                           titulo=camada["titulo"] or ""))


def ler_manifesto(caminho_zip: Path) -> dict:
    """Lê e confere o manifesto de um pacote. Levanta `ErroPacote` com a razão exata."""
    if not zipfile.is_zipfile(caminho_zip):
        raise ErroPacote("o arquivo enviado não é um zip")
    with zipfile.ZipFile(caminho_zip) as z:
        nomes = set(z.namelist())
        if NOME_MANIFESTO not in nomes:
            raise ErroPacote(f"zip sem {NOME_MANIFESTO}: não é um pacote de mapa")
        if NOME_GPKG not in nomes:
            raise ErroPacote(f"zip sem {NOME_GPKG}: o pacote não traz os dados citados")
        try:
            man = json.loads(z.read(NOME_MANIFESTO).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ErroPacote(f"{NOME_MANIFESTO} ilegível: {e}") from e
    if not isinstance(man, dict) or man.get("plat_pacote") != VERSAO_PACOTE:
        raise ErroPacote(f"versão de pacote desconhecida: {(man or {}).get('plat_pacote')!r}")
    if not isinstance(man.get("mapa"), dict) or not isinstance(man.get("camadas"), list):
        raise ErroPacote("manifesto sem 'mapa' ou sem 'camadas'")
    for camada in man["camadas"]:
        if not isinstance(camada, dict) or not camada.get("tabela_no_pacote") or not camada.get("titulo"):
            raise ErroPacote("camada do manifesto sem tabela_no_pacote ou sem título")
        if not str(camada["tabela_no_pacote"]).replace("_", "").isalnum():
            raise ErroPacote(f"nome de tabela inválido no pacote: {camada['tabela_no_pacote']!r}")
    return man


__all__ = ["ErroPacote", "NOME_GPKG", "NOME_MANIFESTO", "VERSAO_PACOTE", "camadas_citadas",
           "entrada_de_camada", "escrever", "ler_manifesto", "manifesto"]
