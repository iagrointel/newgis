"""Contrato de dado da BDGD (item L4-01-c-importador-bdgd): as expectativas do YAML da casa
(`contrato_bdgd.yaml`, cópia fiel de rs-coop/edp_es/contrato — a origem nunca é editada daqui),
avaliadas camada a camada sobre os dataframes já lidos do GDB, ANTES de a topologia ser habilitada.

Três severidades, como o YAML define: `bloqueia` (impossibilidade física ou referencial; tolerância
zero), `avisa` (contradição com explicação possível; a fração aceita é a do YAML) e `informa` (só
registra o número). O relatório sai por expectativa: {id, nome, camada, severidade, resultado,
medido, detalhe}. `resultado` é um de:

- `passa` / `falha`: avaliada, com o número medido;
- `nao_avaliada`: a expectativa existe no YAML mas esta versão não a calcula — o motivo vai em
  `detalhe`. As 17 expectativas de nível `transformador` (F01-F17, séries por trafo e fronteira de
  safra) e as que dependem de safra anterior ou de censo ficam aqui de propósito: dizer "não
  avaliada" é mais honesto que aproximar. O relatório conta quantas foram avaliadas.

O contrato NÃO decide sozinho se a importação prossegue: `bloqueia` com falha é devolvida ao job,
que decide (por padrão a carga segue e o relatório fica gravado com o job, porque a topologia é
útil mesmo com o dado a corrigir — e a decisão de bloquear a entrega à ANEEL é do operador, não
do importador).
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path

import yaml

ARQUIVO_YAML = Path(__file__).with_name("contrato_bdgd.yaml")

# camadas que o contrato pode pedir e que o importador NÃO lê para a topologia (PIP/UGBT):
# lidas aqui só para o contrato, sem geometria, quando existem no GDB
CAMADAS_DO_CONTRATO = ("UNTRMT", "UCBT_tab", "CTMT", "SSDBT", "PONNOT", "PIP", "UGBT_tab", "UCMT_tab")


def carregar_yaml(caminho: Path = ARQUIVO_YAML) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _col(df, nome):
    return df[nome] if df is not None and nome in df.columns else None


def _numerico(serie):
    """Série convertida para número; o que não converte vira NaN (contado pelo chamador)."""
    import pandas as pd

    return pd.to_numeric(serie, errors="coerce")


def _fracao(n_falha: int, n_total: int) -> float:
    return (n_falha / n_total) if n_total else 0.0


class Avaliador:
    """Uma instância por importação: recebe os dataframes por camada (já lidos) e os parâmetros
    globais do YAML; cada método `_e_<familia>` avalia uma família de expectativas."""

    def __init__(self, camadas: dict[str, object], globais: dict, safra_ano: int | None = None):
        self.c = camadas
        self.g = globais
        self.safra_ano = safra_ano

    # ------------------------------------------------------------------ utilidades
    def _df(self, camada):
        return self.c.get(camada)

    def _presente(self, camada) -> bool:
        df = self._df(camada)
        return df is not None and len(df) > 0

    def _codigos(self, camada, coluna="COD_ID") -> set:
        df = self._df(camada)
        s = _col(df, coluna)
        if s is None:
            return set()
        return {str(v).strip() for v in s.dropna() if str(v).strip()}

    # ------------------------------------------------------------------ famílias
    def colunas_obrigatorias(self, e, df):
        faltam = [c for c in e["parametros"]["colunas"] if c not in df.columns]
        return (not faltam), {"faltam": faltam, "presentes": len(df.columns)}

    def cod_id_unico(self, e, df):
        s = _col(df, "COD_ID")
        if s is None:
            return False, {"motivo": "sem coluna COD_ID"}
        dup = int(s.duplicated(keep=False).sum())
        return dup == 0, {"duplicados": dup, "linhas": int(len(s))}

    def pot_nom_positiva(self, e, df):
        tipos = set(e["parametros"].get("tip_trafo_distribuicao", ["T"]))
        if "POT_NOM" not in df.columns or "TIP_TRAFO" not in df.columns:
            return False, {"motivo": "sem POT_NOM ou TIP_TRAFO"}
        sel = df[df["TIP_TRAFO"].astype(str).str.strip().isin(tipos)]
        pot = _numerico(sel["POT_NOM"])
        falha = int(((pot.isna()) | (pot <= 0)).sum())
        return falha == 0, {"distribuicao": int(len(sel)), "sem_placa_ou_zero": falha}

    def pot_nom_catalogo(self, e, df):
        cat = set(float(x) for x in e["parametros"]["catalogo_kva"])
        pot = _numerico(_col(df, "POT_NOM")).dropna()
        fora = int((~pot.isin(cat)).sum())
        return True, {"fora_do_catalogo": fora, "fracao": round(_fracao(fora, len(pot)), 4)}

    def coordenada_brasil(self, e, df):
        bb = self.g["bbox_brasil"]
        x = _numerico(_col(df, "X")) if "X" in df.columns else None
        y = _numerico(_col(df, "Y")) if "Y" in df.columns else None
        if x is None or y is None:
            if getattr(df, "geometry", None) is not None:
                x, y = df.geometry.x, df.geometry.y
            else:
                return False, {"motivo": "sem X/Y nem geometria"}
        fora = int(((x < bb["lon_min"]) | (x > bb["lon_max"]) | (y < bb["lat_min"]) | (y > bb["lat_max"])).sum())
        nulos = int((x.isna() | y.isna()).sum())
        return (fora + nulos) == 0, {"fora_da_caixa": fora, "sem_coordenada": nulos, "linhas": int(len(df))}

    def referencia_existe(self, e, df, coluna, camada_alvo, alvo_coluna="COD_ID"):
        s = _col(df, coluna)
        if s is None:
            return False, {"motivo": f"sem coluna {coluna}"}
        alvo = self._codigos(camada_alvo, alvo_coluna)
        if not alvo:
            return None, {"motivo": f"camada {camada_alvo} ausente ou vazia: referência não conferível"}
        vals = s.dropna().astype(str).str.strip()
        falta = int((~vals.isin(alvo)).sum())
        frac = _fracao(falta, len(vals))
        tol = float(e["parametros"].get("fracao_max", 0.0))
        return frac <= tol, {"sem_alvo": falta, "linhas": int(len(vals)), "fracao": round(frac, 5), "tolerancia": tol}

    def ene_numericas(self, e, df):
        cols = [f"ENE_{i:02d}" for i in range(1, 13)]
        faltam = [c for c in cols if c not in df.columns]
        if faltam:
            return False, {"faltam": faltam}
        ruins = 0
        for c in cols:
            ruins += int(_numerico(df[c]).isna().sum() - df[c].isna().sum())
        return ruins == 0, {"texto_onde_vai_numero": ruins}

    def ene_nao_negativas(self, e, df):
        cols = [f"ENE_{i:02d}" for i in range(1, 13) if f"ENE_{i:02d}" in df.columns]
        neg = 0
        for c in cols:
            neg += int((_numerico(df[c]) < 0).sum())
        return neg == 0, {"negativas": neg, "colunas": len(cols)}

    def dominio(self, e, df, coluna):
        dom = set(str(v) for v in e["parametros"]["dominio"])
        s = _col(df, coluna)
        if s is None:
            return False, {"motivo": f"sem coluna {coluna}"}
        fora = int((~s.dropna().astype(str).str.strip().isin(dom)).sum())
        return fora == 0, {"fora_do_dominio": fora, "dominio": sorted(dom)}

    def episodios_por_codigo(self, e, df):
        s = _col(df, "COD_ID")
        if s is None:
            return None, {"motivo": "sem COD_ID"}
        vc = s.value_counts()
        return True, {
            "codigos": int(len(vc)),
            "com_mais_de_uma_linha": int((vc > 1).sum()),
            "max_linhas": int(vc.max()) if len(vc) else 0,
        }

    def forma_inteiros(self, e, df):
        cols = [f"ENE_{i:02d}" for i in range(1, 13) if f"ENE_{i:02d}" in df.columns]
        if not cols:
            return None, {"motivo": "sem ENE_*"}
        tot = dec = 0
        for c in cols:
            v = _numerico(df[c]).dropna()
            v = v[v > 0]
            tot += len(v)
            dec += int((v != v.round()).sum())
        frac = _fracao(dec, tot)
        tol = float(e["parametros"].get("fracao_max_decimais", 0.3))
        return frac <= tol, {"decimais": dec, "positivos": tot, "fracao": round(frac, 4), "tolerancia": tol}

    def mediana_ene(self, e, df):
        p = e["parametros"]
        cols = [f"ENE_{i:02d}" for i in range(1, 13) if f"ENE_{i:02d}" in df.columns]
        if not cols or "CLAS_SUB" not in df.columns:
            return None, {"motivo": "sem ENE_* ou CLAS_SUB"}
        pref = str(p.get("classe_prefixo", "RE"))
        sel = df[df["CLAS_SUB"].astype(str).str.upper().str.startswith(pref)]
        if "SIT_ATIV" in sel.columns:
            sel = sel[sel["SIT_ATIV"].astype(str).str.strip().str.upper() == "AT"]
        if sel.empty:
            return None, {"motivo": "sem UC residencial ativa"}
        soma = sum(_numerico(sel[c]).fillna(0) for c in cols)
        med = float((soma / 12).median())
        ok = float(p["mediana_min_kwh_mes"]) <= med <= float(p["mediana_max_kwh_mes"])
        return ok, {
            "mediana_kwh_mes": round(med, 2),
            "faixa": [p["mediana_min_kwh_mes"], p["mediana_max_kwh_mes"]],
            "ucs": int(len(sel)),
        }

    def ativas_zero(self, e, df):
        cols = [f"ENE_{i:02d}" for i in range(1, 13) if f"ENE_{i:02d}" in df.columns]
        if not cols or "SIT_ATIV" not in df.columns:
            return None, {"motivo": "sem ENE_* ou SIT_ATIV"}
        at = df[df["SIT_ATIV"].astype(str).str.strip().str.upper() == "AT"]
        soma = sum(_numerico(at[c]).fillna(0) for c in cols)
        n = int((soma == 0).sum())
        return True, {"ativas_com_zero_12m": n, "ativas": int(len(at)), "fracao": round(_fracao(n, len(at)), 4)}

    def desativadas_com_energia(self, e, df):
        cols = [f"ENE_{i:02d}" for i in range(1, 13) if f"ENE_{i:02d}" in df.columns]
        if not cols or "SIT_ATIV" not in df.columns:
            return None, {"motivo": "sem ENE_* ou SIT_ATIV"}
        de = df[df["SIT_ATIV"].astype(str).str.strip().str.upper() == "DS"]
        soma = sum(_numerico(de[c]).fillna(0) for c in cols)
        n = int((soma > 0).sum())
        return True, {"desativadas_com_energia": n, "desativadas": int(len(de))}

    def dat_con(self, e, df):
        s = _col(df, "DAT_CON")
        if s is None:
            return None, {"motivo": "sem DAT_CON"}
        fmts = self.g.get("formatos_data", ["%d/%m/%Y"])
        base = datetime(self.safra_ano, 12, 31) if self.safra_ano else None
        ileg = fut = 0
        for v in s.dropna().astype(str).str.strip():
            if not v:
                continue
            d = None
            for f in fmts:
                try:
                    d = datetime.strptime(v[:10], f)
                    break
                except ValueError:
                    continue
            if d is None:
                ileg += 1
            elif base and d > base:
                fut += 1
        return (ileg + fut) == 0, {
            "ilegiveis": ileg,
            "posteriores_a_data_base": fut,
            "data_base": base.date().isoformat() if base else None,
        }

    def comp_positivo(self, e, df):
        s = _numerico(_col(df, "COMP"))
        if s is None:
            return False, {"motivo": "sem COMP"}
        ruim = int(((s.isna()) | (s <= 0)).sum())
        frac = _fracao(ruim, len(s))
        tol = float(e["parametros"].get("fracao_max", 0.0))
        return frac <= tol, {
            "comp_nulo_ou_zero": ruim,
            "linhas": int(len(s)),
            "fracao": round(frac, 5),
            "tolerancia": tol,
        }

    def positivo(self, e, df, coluna):
        s = _numerico(_col(df, coluna))
        if s is None:
            return False, {"motivo": f"sem {coluna}"}
        ruim = int(((s.isna()) | (s <= 0)).sum())
        return ruim == 0, {"nulo_ou_zero": ruim, "linhas": int(len(s))}

    def trafo_sem_uc_nem_ip(self, e, df):
        trafos = self._codigos("UNTRMT")
        com_uc = self._codigos("UCBT_tab", "UNI_TR_MT")
        com_ip = self._codigos("PIP", "UNI_TR_MT")
        sem = trafos - com_uc - com_ip
        return True, {
            "trafos": len(trafos),
            "sem_uc_nem_ip": len(sem),
            "fracao": round(_fracao(len(sem), len(trafos)), 4),
        }

    def alimentador_com_trafo(self, e, df):
        ctmts = self._codigos("CTMT")
        usados = self._codigos("UNTRMT", "CTMT")
        sem = ctmts - usados
        frac = _fracao(len(sem), len(ctmts))
        tol = float(e["parametros"].get("fracao_max", 0.0))
        return frac <= tol, {
            "alimentadores": len(ctmts),
            "sem_transformador": len(sem),
            "fracao": round(frac, 4),
            "tolerancia": tol,
        }

    def pnt_negativa(self, e, df):
        cols = [c for c in df.columns if re.match(r"^PNT_\d{2}$", c)]
        if not cols:
            return None, {"motivo": "sem PNT_*"}
        n = sum(int((_numerico(df[c]) < 0).sum()) for c in cols)
        return True, {"meses_com_pnt_negativa": n}

    def injecao_nao_negativa(self, e, df):
        cols = [c for c in df.columns if re.match(r"^ENE_\d{2}$", c)]
        if not cols:
            return None, {"motivo": "sem ENE_* no CTMT"}
        soma = sum(_numerico(df[c]).fillna(0) for c in cols)
        n = int((soma < 0).sum())
        return True, {"alimentadores_com_injecao_anual_negativa": n}

    def gd_acima_da_placa(self, e, df):
        if "POT_INST" not in df.columns or "UNI_TR_MT" not in df.columns:
            return None, {"motivo": "sem POT_INST/UNI_TR_MT"}
        tr = self._df("UNTRMT")
        if tr is None or "POT_NOM" not in tr.columns:
            return None, {"motivo": "sem UNTRMT.POT_NOM"}
        placa = dict(zip(tr["COD_ID"].astype(str).str.strip(), _numerico(tr["POT_NOM"]), strict=False))
        pot = _numerico(df["POT_INST"])
        ref = df["UNI_TR_MT"].astype(str).str.strip().map(placa)
        n = int(((pot > ref) & ref.notna()).sum())
        return True, {"gd_acima_da_placa": n, "unidades": int(len(df))}

    def pn_con_existe(self, e, df):
        return self.referencia_existe(e, df, "PN_CON", "PONNOT")

    def pn_con_da_uc_igual_ao_trafo(self, e, df):
        # UCBT-15: exige a distância entre o ponto da UC e o do trafo (dist_max_km_poste). Precisa de
        # geometria dos pontos (PONNOT) — avaliável, mas custa uma junção espacial por UC; fica para a
        # versão com a topologia montada (aí a distância já está no grafo).
        return None, {"motivo": "distância UC-transformador é avaliada sobre a topologia montada, não aqui"}

    def pot_lamp_positiva(self, e, df):
        if "POT_LAMP" not in df.columns:
            return None, {"motivo": "sem POT_LAMP"}
        cols = [c for c in df.columns if re.match(r"^ENE_\d{2}$", c)]
        com_energia = df
        if cols:
            soma = sum(_numerico(df[c]).fillna(0) for c in cols)
            com_energia = df[soma > 0]
        pot = _numerico(com_energia["POT_LAMP"])
        ruim = int(((pot.isna()) | (pot <= 0)).sum())
        frac = _fracao(ruim, len(com_energia))
        tol = float(e["parametros"].get("fracao_max", 0.0))
        return frac <= tol, {
            "ip_com_energia": int(len(com_energia)),
            "sem_potencia_de_lampada": ruim,
            "fracao": round(frac, 5),
        }

    def uc_com_gd_tem_ugbt(self, e, df):
        if "CEG_GD" not in df.columns:
            return None, {"motivo": "sem CEG_GD"}
        com = df[df["CEG_GD"].notna() & (df["CEG_GD"].astype(str).str.strip() != "")]
        ug = self._codigos("UGBT_tab", "CEG_GD")
        if not ug:
            return None, {"motivo": "UGBT_tab ausente: referência não conferível"}
        falta = int((~com["CEG_GD"].astype(str).str.strip().isin(ug)).sum())
        frac = _fracao(falta, len(com))
        tol = float(e["parametros"].get("fracao_max", 0.0))
        return frac <= tol, {"uc_com_gd": int(len(com)), "sem_registro_ugbt": falta, "fracao": round(frac, 5)}

    def perfis_planos(self, e, df):
        cols = [f"ENE_{i:02d}" for i in range(1, 13) if f"ENE_{i:02d}" in df.columns]
        if len(cols) < 12:
            return None, {"motivo": "sem os 12 ENE_*"}
        m = df[cols].apply(_numerico)
        plano = (m.nunique(axis=1) == 1) & (m.iloc[:, 0] > 0)
        return True, {"perfis_planos_12m": int(plano.sum()), "ucs": int(len(df))}

    # ------------------------------------------------------------------ despacho
    def avaliar(self, e: dict):
        """(resultado, medido, detalhe). resultado ∈ passa|falha|nao_avaliada."""
        camada = e["camada"]
        df = self._df(camada) if camada != "externo" else None
        if e["nivel"] == "transformador":
            return (
                "nao_avaliada",
                None,
                "nível transformador (séries por trafo e fronteira de safra): fora desta versão do importador",
            )
        if camada == "externo":
            return "nao_avaliada", None, "depende de fonte externa (censo)"
        if df is None or len(df) == 0:
            return "nao_avaliada", None, f"camada {camada} ausente ou vazia no GDB"
        nome = e["nome"].lower()
        i = e["id"]
        try:
            if nome.startswith("colunas obrigat"):
                ok, med = self.colunas_obrigatorias(e, df)
            elif nome.startswith("cod_id único"):
                ok, med = self.cod_id_unico(e, df)
            elif i == "UNTRMT-03":
                ok, med = self.pot_nom_positiva(e, df)
            elif i == "UNTRMT-04":
                ok, med = self.pot_nom_catalogo(e, df)
            elif i in ("UNTRMT-05", "PONNOT-03"):
                ok, med = self.coordenada_brasil(e, df)
            elif i == "UNTRMT-06":
                ok, med = self.referencia_existe(e, df, "CTMT", "CTMT")
            elif i == "UNTRMT-08":
                ok, med = self.dat_con(e, df)
            elif i == "UNTRMT-09":
                ok, med = self.trafo_sem_uc_nem_ip(e, df)
            elif i == "UCBT-02":
                ok, med = self.ene_numericas(e, df)
            elif i == "UCBT-03":
                ok, med = self.ene_nao_negativas(e, df)
            elif i == "UCBT-04":
                ok, med = self.dominio(e, df, "SIT_ATIV")
            elif i in ("UCBT-05", "SSDBT-02", "PIP-02", "UGBT-03"):
                ok, med = self.referencia_existe(e, df, "UNI_TR_MT", "UNTRMT")
            elif i == "UCBT-06":
                ok, med = self.pn_con_existe(e, df)
            elif i == "UCBT-07":
                ok, med = self.episodios_por_codigo(e, df)
            elif i == "UCBT-08":
                ok, med = self.forma_inteiros(e, df)
            elif i == "UCBT-09":
                ok, med = self.mediana_ene(e, df)
            elif i == "UCBT-11":
                ok, med = self.perfis_planos(e, df)
            elif i == "UCBT-12":
                ok, med = self.ativas_zero(e, df)
            elif i == "UCBT-13":
                ok, med = self.desativadas_com_energia(e, df)
            elif i == "UCBT-14":
                ok, med = self.uc_com_gd_tem_ugbt(e, df)
            elif i == "UCBT-15":
                ok, med = self.pn_con_da_uc_igual_ao_trafo(e, df)
            elif i == "CTMT-03":
                ok, med = self.alimentador_com_trafo(e, df)
            elif i == "CTMT-05":
                ok, med = self.pnt_negativa(e, df)
            elif i == "CTMT-06":
                ok, med = self.injecao_nao_negativa(e, df)
            elif i == "SSDBT-03":
                ok, med = self.comp_positivo(e, df)
            elif i == "PIP-03":
                ok, med = self.pot_lamp_positiva(e, df)
            elif i == "UGBT-02":
                ok, med = self.positivo(e, df, "POT_INST")
            elif i == "UGBT-04":
                ok, med = self.gd_acima_da_placa(e, df)
            else:
                return (
                    "nao_avaliada",
                    None,
                    "sem avaliador nesta versão (balanço, safra anterior, CAR_INST, mínimos de faturamento)",
                )
        except Exception as exc:  # avaliador que quebra vira "não avaliada" com o erro, nunca "passa"
            return "nao_avaliada", None, f"erro ao avaliar: {type(exc).__name__}: {exc}"
        if ok is None:
            return "nao_avaliada", med, med.get("motivo", "") if isinstance(med, dict) else ""
        if e["severidade"] == "informa":
            return "passa", med, "informa: registra o número, nunca falha"
        return ("passa" if ok else "falha"), med, ""


def avaliar_contrato(
    camadas: dict[str, object], safra_ano: int | None = None, yaml_caminho: Path = ARQUIVO_YAML
) -> dict:
    """Relatório completo: lista por expectativa + resumo por severidade + contagem de avaliadas.
    `camadas` é {nome: dataframe} das camadas lidas (as ausentes podem faltar no dict)."""
    y = carregar_yaml(yaml_caminho)
    av = Avaliador(camadas, y.get("parametros_globais", {}), safra_ano)
    itens = []
    resumo = {
        "bloqueia": {"passa": 0, "falha": 0, "nao_avaliada": 0},
        "avisa": {"passa": 0, "falha": 0, "nao_avaliada": 0},
        "informa": {"passa": 0, "falha": 0, "nao_avaliada": 0},
    }
    for e in y["expectativas"]:
        res, med, det = av.avaliar(e)
        itens.append(
            {
                "id": e["id"],
                "camada": e["camada"],
                "nivel": e["nivel"],
                "nome": e["nome"],
                "severidade": e["severidade"],
                "resultado": res,
                "medido": _limpar(med),
                "detalhe": det,
            }
        )
        resumo[e["severidade"]][res] += 1
    avaliadas = sum(1 for i in itens if i["resultado"] != "nao_avaliada")
    return {
        "versao_contrato": y.get("versao"),
        "calibracao": y.get("calibracao"),
        "camadas_obrigatorias_ausentes": [c for c in y.get("camadas_obrigatorias", []) if not av._presente(c)],
        "total": len(itens),
        "avaliadas": avaliadas,
        "bloqueia_falhas": resumo["bloqueia"]["falha"],
        "resumo": resumo,
        "expectativas": itens,
    }


def _limpar(v):
    """JSON-seguro: numpy -> python, NaN -> None."""
    if v is None:
        return None
    if isinstance(v, dict):
        return {k: _limpar(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_limpar(x) for x in v]
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v
