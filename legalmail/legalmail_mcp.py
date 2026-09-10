#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor MCP da Legal Mail — SOMENTE LEITURA
Escritorio Maralisa Souza Advocacia

Expoe as consultas da API da Legal Mail como ferramentas MCP.

GARANTIAS DE SEGURANCA (todas verificaveis lendo este arquivo):

  1. O openapi.json ao lado deste script contem APENAS operacoes GET.
     As 40 operacoes de escrita da API (25 POST, 9 DELETE, 6 PUT) foram
     removidas do arquivo. O servidor nao consegue alcancar o que nao existe
     na especificacao que ele le.

  2. Este arquivo nao contem nenhuma chamada HTTP que nao seja GET.
     Procure por "method=" abaixo: so existe GET, fixo no codigo.

  3. Ao montar a lista de ferramentas, qualquer metodo diferente de "get"
     encontrado na especificacao e ignorado (ver montar_ferramentas).

  4. A chave de API nunca aparece na lista de ferramentas, nem nos parametros
     que o modelo preenche, nem em mensagem de erro. Ela e lida do ambiente e
     anexada a requisicao no ultimo instante.

Onde o servidor procura a chave, nesta ordem:
  1. variavel de ambiente LEGALMAIL_API_KEY   (forma recomendada)
  2. arquivo .api_key ao lado deste script    (uso local; nunca versionado)
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(AQUI, "openapi.json")
ARQUIVO_CHAVE = os.path.join(AQUI, ".api_key")

VERSAO_PROTOCOLO = "2024-11-05"
TIMEOUT = 60


# --------------------------------------------------------------------- chave

def carregar_chave():
    """Le a chave do ambiente ou do arquivo local. Nunca a imprime."""
    chave = (os.environ.get("LEGALMAIL_API_KEY") or "").strip()
    if chave:
        return chave
    try:
        with open(ARQUIVO_CHAVE, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def contexto_ssl():
    """Confia na CA correta: a do proxy quando houver, senao certifi."""
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        caminho = os.environ.get(var)
        if caminho and os.path.isfile(caminho):
            return ssl.create_default_context(cafile=caminho)
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


# ----------------------------------------------------------- especificacao

def carregar_spec():
    with open(SPEC, encoding="utf-8") as fh:
        return json.load(fh)


def base_url(spec):
    servidores = spec.get("servers") or [{}]
    return (servidores[0].get("url") or "https://api.legalmail.com.br/").rstrip("/")


def nome_ferramenta(caminho):
    """/api/v1/lawsuit/case-files/status -> lawsuit_case_files_status"""
    limpo = caminho.replace("/api/v1/", "", 1).strip("/")
    return limpo.replace("/", "_").replace("-", "_") or "raiz"


def montar_ferramentas(spec):
    """Uma ferramenta por operacao GET. Qualquer outro metodo e ignorado."""
    ferramentas, rotas = [], {}
    for caminho, item in sorted(spec.get("paths", {}).items()):
        for metodo, op in item.items():
            if metodo.lower() != "get":
                continue  # trava 3: escrita nunca vira ferramenta

            propriedades, obrigatorios = {}, []
            for par in op.get("parameters", []):
                nome = par.get("name")
                # trava 4: a chave nunca e exposta ao modelo
                if not nome or nome == "api_key":
                    continue
                esquema = dict(par.get("schema") or {})
                if par.get("description"):
                    esquema["description"] = par["description"][:300]
                propriedades[nome] = esquema
                if par.get("required"):
                    obrigatorios.append(nome)

            nome_t = nome_ferramenta(caminho)
            descricao = (op.get("summary") or caminho).strip()
            if op.get("description"):
                descricao += " — " + " ".join(op["description"].split())[:220]

            ferramentas.append({
                "name": nome_t,
                "description": "[somente leitura] " + descricao,
                "inputSchema": {
                    "type": "object",
                    "properties": propriedades,
                    "required": obrigatorios,
                },
            })
            rotas[nome_t] = caminho
    return ferramentas, rotas


# ------------------------------------------------------------------ chamada

def consultar(url_base, caminho, argumentos, chave):
    """Executa a consulta. Este e o unico ponto de rede do servidor."""
    parametros = {k: v for k, v in (argumentos or {}).items()
                  if v is not None and k != "api_key"}
    parametros["api_key"] = chave  # anexada so agora, nunca antes

    url = url_base + caminho + "?" + urllib.parse.urlencode(parametros, doseq=True)
    requisicao = urllib.request.Request(
        url,
        method="GET",  # trava 2: fixo. nao ha outro metodo neste arquivo.
        headers={"Accept": "application/json",
                 "User-Agent": "legalmail-mcp-somente-leitura/1.0"},
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT,
                                    context=contexto_ssl()) as resposta:
            return resposta.read().decode("utf-8", "replace"), False
    except urllib.error.HTTPError as exc:
        corpo = exc.read().decode("utf-8", "replace")[:1500]
        return "Erro HTTP %s em %s: %s" % (exc.code, caminho, corpo), True
    except Exception as exc:
        # censura defensiva: a chave jamais vai para uma mensagem de erro
        return "Falha de conexao em %s: %s" % (
            caminho, str(exc).replace(chave, "***")), True


# ------------------------------------------------------------ protocolo MCP

def responder(id_req, resultado=None, erro=None):
    msg = {"jsonrpc": "2.0", "id": id_req}
    if erro is not None:
        msg["error"] = erro
    else:
        msg["result"] = resultado
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    spec = carregar_spec()
    url_base = base_url(spec)
    ferramentas, rotas = montar_ferramentas(spec)

    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            req = json.loads(linha)
        except ValueError:
            continue

        metodo = req.get("method")
        id_req = req.get("id")

        if metodo == "initialize":
            responder(id_req, {
                "protocolVersion": VERSAO_PROTOCOLO,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "legalmail-somente-leitura",
                               "version": "1.0.0"},
            })

        elif metodo in ("notifications/initialized", "initialized"):
            continue  # notificacao: nao tem resposta

        elif metodo == "tools/list":
            responder(id_req, {"tools": ferramentas})

        elif metodo == "tools/call":
            parametros = req.get("params") or {}
            nome = parametros.get("name")
            caminho = rotas.get(nome)
            if not caminho:
                responder(id_req, {
                    "content": [{"type": "text",
                                 "text": "Ferramenta desconhecida: %s" % nome}],
                    "isError": True,
                })
                continue

            chave = carregar_chave()
            if not chave:
                responder(id_req, {
                    "content": [{"type": "text", "text":
                                 "Chave de API nao configurada. Defina a variavel "
                                 "de ambiente LEGALMAIL_API_KEY ou crie o arquivo "
                                 ".api_key ao lado do servidor."}],
                    "isError": True,
                })
                continue

            texto, houve_erro = consultar(url_base, caminho,
                                          parametros.get("arguments") or {}, chave)
            responder(id_req, {"content": [{"type": "text", "text": texto}],
                               "isError": houve_erro})

        elif id_req is not None:
            responder(id_req, erro={"code": -32601,
                                    "message": "Metodo nao suportado: %s" % metodo})


def autoteste():
    """python3 legalmail_mcp.py --autoteste — confere sem precisar do MCP."""
    spec = carregar_spec()
    ferramentas, rotas = montar_ferramentas(spec)
    escrita = [f"{m.upper()} {p}" for p, it in spec.get("paths", {}).items()
               for m in it if m.lower() != "get"]

    print("Servidor MCP Legal Mail — somente leitura")
    print("  ferramentas de consulta .....: %d" % len(ferramentas))
    print("  operacoes de escrita expostas: %d %s"
          % (len(escrita), "(nenhuma)" if not escrita else escrita))
    chave = carregar_chave()
    print("  chave de API ................: %s"
          % ("encontrada" if chave else "NAO CONFIGURADA"))
    if not chave:
        return 1

    texto, erro = consultar(base_url(spec), "/api/v1/balance", {}, chave)
    print("  teste real (/balance) .......: %s" % ("FALHOU" if erro else "OK"))
    print("  resposta: %s" % texto[:220])
    return 1 if erro else 0


if __name__ == "__main__":
    sys.exit(autoteste() if "--autoteste" in sys.argv else (main() or 0))
