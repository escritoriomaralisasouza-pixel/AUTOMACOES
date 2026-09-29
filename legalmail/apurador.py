#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apurador da Legal Mail — AUTONOMO.

Nao depende do repositorio, do .mcp.json nem do servidor MCP: fala direto com
a API. E por isso que ele existe. A rotina agendada nasce em sessao nova, SEM
o repositorio clonado — logo sem .mcp.json, logo sem as ferramentas
`mcp__legalmail__*`. Entre 10/09 e 29/09/2026 todo relatorio de fechamento caiu
na fonte alternativa (push por e-mail) e saiu com metade dos numeros: na semana
de 19 a 25/09 reportou 35 intimacoes contra as 73 reais, nenhum protocolo
contra os 23 reais, e nenhum dos 18 atos do TRT-3, que o push nao cobre.

DOIS DETALHES QUE QUEBRAM A RODADA SE IGNORADOS
  1. O proxy do container EXIGE o cabecalho User-Agent. Sem ele: HTTP 403.
     Nao e bloqueio de rede — o container alcanca api.legalmail.com.br sem
     problema (verificado em 29/09/2026).
  2. A API pune lote: 120 requisicoes por minuto em janela deslizante, e tres
     respostas 429 em 10 minutos disparam timeout de ate 1 hora. Uma
     requisicao por segundo, `limit=50` sempre — a cobranca e POR REQUISICAO,
     entao limit menor so aumenta o custo.

Modos:
  python3 apurador.py semana 2026-09-19 2026-09-25   # fechamento de sexta
  python3 apurador.py radar [paginas]                # fila de prazos de segunda

Saida: JSON no stdout. Somente leitura — so faz GET.
"""
import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.legalmail.com.br"
UA = "maralisa-apurador/1.0"          # sem isto o proxy devolve 403
PAUSA = 1.0                            # ~1 req/s: o teto e 120/min deslizante
HOJE = dt.date.today()


def _contexto():
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        c = os.environ.get(var)
        if c and os.path.isfile(c):
            return ssl.create_default_context(cafile=c)
    if os.path.isfile("/root/.ccr/ca-bundle.crt"):
        return ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
    return ssl.create_default_context()


CTX = _contexto()
CHAVE = (os.environ.get("LEGALMAIL_API_KEY") or "").strip()


def get(caminho, **params):
    """Unica porta de rede. Devolve (dados, erro). So GET."""
    if not CHAVE:
        return None, "LEGALMAIL_API_KEY nao esta no ambiente"
    params = {k: v for k, v in params.items() if v is not None}
    params["api_key"] = CHAVE
    url = BASE + caminho + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:300]
        return None, "HTTP %s em %s: %s" % (e.code, caminho, corpo)
    except Exception as e:
        # a chave jamais vai para mensagem de erro
        return None, "falha em %s: %s" % (caminho, str(e).replace(CHAVE, "***"))


def paginar(caminho, chave_lista, teto_paginas=40, **params):
    """Percorre TODAS as paginas. Nunca para na primeira."""
    itens, offset, total, erro = [], 0, None, None
    while True:
        d, e = get(caminho, limit=50, offset=offset, **params)
        if e:
            erro = e
            break
        if total is None:
            total = d.get("total", 0)
        lote = d.get(chave_lista) or []
        itens.extend(lote)
        offset += len(lote)
        if not lote or offset >= (total or 0) or offset >= teto_paginas * 50:
            break
        time.sleep(PAUSA)
    return itens, (total or 0), erro


# ------------------------------------------------------------------ datas

def _data(txt):
    if not txt:
        return None
    try:
        return dt.datetime.strptime(str(txt)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def dias_uteis(de, ate):
    if not de or not ate:
        return None
    passo = 1 if ate >= de else -1
    d, n = de, 0
    while d != ate:
        d += dt.timedelta(days=passo)
        if d.weekday() < 5:
            n += passo
    return n


# ----------------------------------------------------- modo: fechamento

def apurar_semana(inicio, fim):
    r = {"modo": "semana", "periodo": {"inicio": inicio, "fim": fim}, "erros": []}

    def falha(e):
        if e:
            r["erros"].append(e)

    intimacoes, total_int, e = paginar(
        "/api/v1/notices", "notices",
        data_captura_inicio=inicio, data_captura_fim=fim)
    falha(e)
    r["intimacoes_total"] = total_int
    r["intimacoes_lidas"] = len(intimacoes)
    time.sleep(PAUSA)

    protocolos, total_prot, e = paginar(
        "/api/v1/filings", "protocols",
        enviado_em_inicio=inicio, enviado_em_fim=fim)
    falha(e)
    r["protocolos_total"] = total_prot
    time.sleep(PAUSA)

    d, e = get("/api/v1/notices", prazo_status="pendente", limit=1)
    falha(e)
    r["passivo_prazos_pendentes"] = (d or {}).get("total")
    time.sleep(PAUSA)

    d, e = get("/api/v1/lawsuit/summary")
    falha(e)
    r["acervo"] = d
    time.sleep(PAUSA)

    d, e = get("/api/v1/balance")
    falha(e)
    r["saldo_api"] = (d or {}).get("saldo_disponivel")

    def contar(itens, campo):
        c = {}
        for i in itens:
            v = i.get(campo) or "nao informado"
            c[v] = c.get(v, 0) + 1
        return dict(sorted(c.items(), key=lambda x: -x[1]))

    r["intimacoes_por_tribunal"] = contar(intimacoes, "tribunal")
    r["protocolos_por_executor"] = contar(protocolos, "usuario")
    r["protocolos_por_status"] = contar(protocolos, "status")
    r["protocolos_por_tribunal"] = contar(protocolos, "tribunal")

    # protocolo cancelado sem reenvio e o achado mais caro que existe aqui
    r["protocolos_cancelados"] = [
        {"processo": p.get("numero_processo"), "peca": p.get("tipo_peca"),
         "cliente": p.get("polo_ativo"), "executor": p.get("usuario"),
         "enviado_em": p.get("enviado_em"), "cancelado_em": p.get("cancelado_em")}
        for p in protocolos if p.get("status") in ("Cancelado", "Com pendências")]

    gat = ("sentença", "sentenca", "sob pena de extin", "sob pena de indeferimento",
           "improcedente", "procedente", "audiência", "audiencia", "acordo",
           "laudo", "extinto", "contrarraz", "recurso")
    r["intimacoes_com_gatilho"] = [
        {"processo": i.get("numero_processo"), "partes": i.get("partes"),
         "tribunal": i.get("tribunal"), "tipo": i.get("tipo"),
         "data_disponibilizacao": i.get("data_disponibilizacao"),
         "prazo_status": i.get("prazo_status"),
         "responsavel": (i.get("destinatario") or {}).get("nome"),
         "gatilhos": sorted({g for g in gat if g in (i.get("teor") or "").lower()}),
         "teor": (i.get("teor") or "")[:700]}
        for i in intimacoes
        if any(g in (i.get("teor") or "").lower() for g in gat)]

    r["protocolos"] = [
        {"enviado_em": p.get("enviado_em"), "peca": p.get("tipo_peca"),
         "cliente": p.get("polo_ativo"), "processo": p.get("numero_processo"),
         "tribunal": p.get("tribunal"), "executor": p.get("usuario"),
         "titular_certificado": p.get("titular_certificado"),
         "status": p.get("status")}
        for p in protocolos]
    return r


# ---------------------------------------------------------- modo: radar

FATAL = ("sob pena de extin", "sob pena de indeferimento",
         "sob pena de arquivamento", "sob pena de preclus")
GRAVE = ("sentença", "sentenca", "acórdão", "acordao", "improcedente",
         "julgo extinto", "contrarraz", "recurso", "embargos")
MEDIO = ("audiência", "audiencia", "laudo", "perícia", "pericia", "acordo",
         "cálculo", "calculo", "manifest", "impugna")


def classificar(i):
    """(farol, motivo, chave_de_ordem).

    A API quase nunca preenche `data_limite_manifestacao` — 2 em 200 na
    medicao de 29/09/2026. Entao a ordem sai da GRAVIDADE do teor e da IDADE
    da intimacao, contada da disponibilizacao, que e de onde o prazo corre.
    Quando a data limite vem preenchida, ela manda: e mais confiavel.
    """
    teor = (i.get("teor") or "").lower()
    status = i.get("prazo_status")
    limite = _data(i.get("data_limite_manifestacao"))
    disp = _data(i.get("data_disponibilizacao"))
    idade = dias_uteis(disp, HOJE) if disp and disp <= HOJE else None
    idade_txt = idade if idade is not None else "?"

    if limite is not None:
        n = dias_uteis(HOJE, limite)
        if status == "excedido" or n < 0:
            return "1 VERMELHO", "data limite venceu em %s" % limite, (0, n or 0)
        if n <= 1:
            return "1 VERMELHO", "data limite %s — %d dias uteis" % (limite, n), (0, n)
        if n <= 3:
            return "2 LARANJA", "data limite %s — %d dias uteis" % (limite, n), (1, n)
        if n <= 7:
            return "3 AMARELO", "data limite %s — %d dias uteis" % (limite, n), (2, n)
        return "4 VERDE", "data limite %s — %d dias uteis" % (limite, n), (3, n)

    if status == "excedido":
        return "1 VERMELHO", "marcada como prazo excedido", (0, 0)

    achou = [g for g in FATAL if g in teor]
    if achou:
        return ("1 VERMELHO", "teor traz '%s' — ha %s dias uteis" % (achou[0], idade_txt),
                (0, -(idade or 0)))
    achou = [g for g in GRAVE if g in teor]
    if achou:
        if idade is not None and idade >= 8:
            return ("1 VERMELHO",
                    "%s ha %d dias uteis — prazo recursal provavelmente correndo"
                    % (achou[0], idade), (0, -idade))
        return "2 LARANJA", "%s ha %s dias uteis" % (achou[0], idade_txt), (1, -(idade or 0))
    achou = [g for g in MEDIO if g in teor]
    if achou:
        if idade is not None and idade >= 10:
            return "2 LARANJA", "%s ha %d dias uteis" % (achou[0], idade), (1, -idade)
        return "3 AMARELO", "%s ha %s dias uteis" % (achou[0], idade_txt), (2, -(idade or 0))
    if idade is not None and idade >= 15:
        return "3 AMARELO", "pendente ha %d dias uteis, sem gatilho no teor" % idade, (2, -idade)
    return "4 VERDE", "pendente ha %s dias uteis" % idade_txt, (3, -(idade or 0))


def montar_radar(paginas=8):
    bruto, total, e = paginar(
        "/api/v1/notices", "notices", teto_paginas=paginas,
        prazo_status="pendente", ordenar_por="data_disponibilizacao", ordem="desc")
    if e:
        return None, e, 0

    # uma linha por PROCESSO: a intimacao mais grave manda; as outras viram contagem
    por_processo = {}
    for i in bruto:
        proc = i.get("numero_processo") or "sem numero"
        f, motivo, ordem = classificar(i)
        item = {"farol": f, "motivo": motivo, "_o": ordem, "processo": proc,
                "partes": i.get("partes"), "tribunal": i.get("tribunal"),
                "tipo": i.get("tipo"),
                "disponibilizacao": i.get("data_disponibilizacao"),
                "data_limite": i.get("data_limite_manifestacao"),
                "responsavel": (i.get("destinatario") or {}).get("nome"),
                "teor": (i.get("teor") or "")[:500],
                "outras_pendentes_no_processo": 0}
        atual = por_processo.get(proc)
        if atual is None:
            por_processo[proc] = item
        elif item["_o"] < atual["_o"]:
            item["outras_pendentes_no_processo"] = atual["outras_pendentes_no_processo"] + 1
            por_processo[proc] = item
        else:
            atual["outras_pendentes_no_processo"] += 1

    fila = sorted(por_processo.values(), key=lambda x: x["_o"])
    for i in fila:
        i.pop("_o", None)
    return fila, None, total


def apurar_radar(paginas=8):
    fila, erro, total = montar_radar(paginas)
    if erro:
        return {"modo": "radar", "erros": [erro]}
    resumo = {}
    for i in fila:
        resumo[i["farol"]] = resumo.get(i["farol"], 0) + 1
    time.sleep(PAUSA)
    acervo, _ = get("/api/v1/lawsuit/summary")
    return {"modo": "radar", "gerado_em": HOJE.isoformat(), "erros": [],
            "passivo_total_intimacoes": total, "intimacoes_analisadas": len(fila),
            "processos_na_fila": len(fila), "por_farol": dict(sorted(resumo.items())),
            "acervo": acervo, "fila": fila}


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "radar"
    if modo == "semana":
        if len(sys.argv) < 4:
            print("uso: apurador.py semana AAAA-MM-DD AAAA-MM-DD", file=sys.stderr)
            sys.exit(2)
        saida = apurar_semana(sys.argv[2], sys.argv[3])
    else:
        saida = apurar_radar(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    sys.exit(1 if saida.get("erros") else 0)
