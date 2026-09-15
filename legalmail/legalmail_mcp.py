#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor MCP da Legal Mail — LEITURA + PROTOCOLO AUTORIZADO
Escritorio Maralisa Souza Advocacia

Expoe as 49 consultas da API da Legal Mail e, desde 15/09/2026, as 7 operacoes
que compoem o fluxo de protocolo de peticao. Autorizado pela Dra. Maralisa
Souza Barboza Gomes, titular do workspace.

GARANTIAS DE SEGURANCA (todas verificaveis lendo este arquivo):

  1. LISTA BRANCA FECHADA. Apenas os 7 caminhos de ESCRITA_PERMITIDA aceitam
     POST. Qualquer outra escrita e recusada pelo servidor mesmo que apareca
     na especificacao. As 33 demais operacoes de escrita da API — entre elas
     TODAS as 9 de exclusao, incluindo /api/v1/lawsuit/delete — continuam
     inalcancaveis.

  2. A ESPECIFICACAO SO TEM GET E OS 7 POST. O openapi.json nao contem
     nenhum PUT, PATCH ou DELETE. O servidor nao alcanca o que nao existe
     no arquivo que ele le.

  3. O ATO IRREVERSIVEL EXIGE AUTORIZACAO NOMINAL. Os dois envios que de fato
     protocolam no tribunal (/pleading/send e /complaint/send) so executam com
     o campo `autorizacao_advogado` preenchido com o nome de quem autorizou.
     Sem ele, o servidor recusa e nao toca a rede. O campo nunca e enviado a
     API: serve a auditoria da casa.

  4. TODO PROTOCOLO FICA REGISTRADO. Cada envio grava uma linha em
     auditoria-protocolos.log — data, peticao, processo e quem autorizou.

  5. A CHAVE NUNCA E EXPOSTA. Nao entra na lista de ferramentas, nem nos
     parametros que o modelo preenche, e e removida de mensagens de erro.

REGRA DA CASA, inegociavel: a autorizacao vem de advogada ou advogado da
equipe, dita expressamente na conversa, peca a peca. Autorizacao generica
("pode protocolar tudo") nao vale. O certificado usado e o da Dra. Maralisa,
entao quem autoriza responde junto com quem assina.

Onde o servidor procura a chave, nesta ordem:
  1. variavel de ambiente LEGALMAIL_API_KEY   (forma recomendada)
  2. arquivo .api_key ao lado deste script    (uso local; nunca versionado)
"""

import json
import mimetypes
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(AQUI, "openapi.json")
ARQUIVO_CHAVE = os.path.join(AQUI, ".api_key")
AUDITORIA = os.path.join(AQUI, "auditoria-protocolos.log")

VERSAO_PROTOCOLO = "2024-11-05"
TIMEOUT = 120
LIMITE_ARQUIVO = 50 * 1024 * 1024  # 50 MB


# ------------------------------------------------- trava 1: lista branca

# Os 7 caminhos do fluxo de protocolo. Nada fora desta lista escreve.
ESCRITA_PERMITIDA = {
    "/api/v1/pleading",                            # criar intermediaria
    "/api/v1/complaint",                           # criar inicial
    "/api/v1/complaintsandpleadings/file",         # PDF principal
    "/api/v1/complaintsandpleadings/attachments",  # anexos
    "/api/v1/complaintsandpleadings/status",       # status do envio
    "/api/v1/pleading/send",                       # ENVIA ao tribunal
    "/api/v1/complaint/send",                      # ENVIA ao tribunal
}

# Os dois atos irreversiveis: sao os que de fato protocolam.
EXIGEM_AUTORIZACAO = {
    "/api/v1/pleading/send",
    "/api/v1/complaint/send",
}

# Nomes explicitos para as ferramentas de escrita. O nome derivado do caminho
# colidiria com a consulta homonima e nao diria o que a ferramenta faz.
NOMES_ESCRITA = {
    "/api/v1/pleading": "protocolo_criar_intermediaria",
    "/api/v1/complaint": "protocolo_criar_inicial",
    "/api/v1/complaintsandpleadings/file": "protocolo_enviar_arquivo_principal",
    "/api/v1/complaintsandpleadings/attachments": "protocolo_enviar_anexo",
    "/api/v1/complaintsandpleadings/status": "protocolo_consultar_status",
    "/api/v1/pleading/send": "protocolo_PROTOCOLAR_intermediaria",
    "/api/v1/complaint/send": "protocolo_PROTOCOLAR_inicial",
}

# Parametros sinteticos: o modelo preenche, o servidor consome, a API nunca ve.
CAMPO_AUTORIZACAO = "autorizacao_advogado"
CAMPO_ARQUIVO = "arquivo_local"


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


def corpo_da_operacao(op):
    """Devolve (content_type, propriedades, obrigatorios) do requestBody."""
    conteudo = ((op.get("requestBody") or {}).get("content") or {})
    for ctype in ("application/json", "multipart/form-data"):
        if ctype in conteudo:
            esquema = (conteudo[ctype].get("schema") or {})
            return (ctype,
                    esquema.get("properties") or {},
                    list(esquema.get("required") or []))
    return (None, {}, [])


def montar_ferramentas(spec):
    """Uma ferramenta por operacao. GET livre; POST so na lista branca."""
    ferramentas, rotas = [], {}
    for caminho, item in sorted(spec.get("paths", {}).items()):
        for metodo, op in item.items():
            metodo = metodo.lower()

            if metodo == "get":
                escrita = False
            elif metodo == "post" and caminho in ESCRITA_PERMITIDA:
                escrita = True
            else:
                continue  # trava 1: nada mais vira ferramenta

            propriedades, obrigatorios, query = {}, [], set()
            for par in op.get("parameters", []):
                nome = par.get("name")
                # trava 5: a chave nunca e exposta ao modelo
                if not nome or nome == "api_key":
                    continue
                esquema = dict(par.get("schema") or {})
                if par.get("description"):
                    esquema["description"] = par["description"][:300]
                propriedades[nome] = esquema
                query.add(nome)
                if par.get("required"):
                    obrigatorios.append(nome)

            ctype, props_corpo, obrig_corpo = corpo_da_operacao(op)
            campos_corpo = set()
            for nome, esquema in props_corpo.items():
                if nome in propriedades:
                    continue
                detalhe = dict(esquema)
                if detalhe.get("format") == "binary":
                    continue  # binario nao trafega pelo modelo; ver CAMPO_ARQUIVO
                propriedades[nome] = detalhe
                campos_corpo.add(nome)
                if nome in obrig_corpo:
                    obrigatorios.append(nome)

            if escrita and ctype == "multipart/form-data":
                propriedades[CAMPO_ARQUIVO] = {
                    "type": "string",
                    "description": "Caminho do arquivo no disco desta sessao "
                                   "(PDF da peca ou do anexo).",
                }
                obrigatorios.append(CAMPO_ARQUIVO)

            if caminho in EXIGEM_AUTORIZACAO:
                propriedades[CAMPO_AUTORIZACAO] = {
                    "type": "string",
                    "description": "OBRIGATORIO. Nome da advogada ou advogado da "
                                   "equipe que autorizou ESTE protocolo na "
                                   "conversa. Sem isso o envio e recusado. "
                                   "Nunca preencha por conta propria.",
                }
                obrigatorios.append(CAMPO_AUTORIZACAO)

            if escrita:
                nome_t = NOMES_ESCRITA[caminho]
                rotulo = ("[PROTOCOLA NO TRIBUNAL — exige autorizacao] "
                          if caminho in EXIGEM_AUTORIZACAO else "[escrita] ")
            else:
                nome_t = nome_ferramenta(caminho)
                rotulo = "[somente leitura] "

            descricao = (op.get("summary") or caminho).strip()
            if op.get("description"):
                descricao += " — " + " ".join(op["description"].split())[:220]

            ferramentas.append({
                "name": nome_t,
                "description": rotulo + descricao,
                "inputSchema": {
                    "type": "object",
                    "properties": propriedades,
                    "required": obrigatorios,
                },
            })
            rotas[nome_t] = {
                "caminho": caminho,
                "metodo": metodo.upper(),
                "query": query,
                "corpo": campos_corpo,
                "ctype": ctype,
            }
    return ferramentas, rotas


# ------------------------------------------------------------------ chamada

def montar_multipart(campos, caminho_arquivo):
    """Monta o corpo multipart/form-data. Devolve (corpo, content_type)."""
    limite = "----legalmail" + uuid.uuid4().hex
    partes = []
    for nome, valor in campos.items():
        partes.append(
            ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
             % (limite, nome, valor)).encode("utf-8"))

    with open(caminho_arquivo, "rb") as fh:
        binario = fh.read()
    base = os.path.basename(caminho_arquivo)
    tipo = mimetypes.guess_type(base)[0] or "application/octet-stream"
    partes.append(
        ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\""
         "\r\nContent-Type: %s\r\n\r\n" % (limite, base, tipo)).encode("utf-8"))
    partes.append(binario)
    partes.append(("\r\n--%s--\r\n" % limite).encode("utf-8"))

    return b"".join(partes), "multipart/form-data; boundary=%s" % limite


def registrar_auditoria(caminho, argumentos, autorizador, resposta):
    """Trava 4: grava quem autorizou cada protocolo. Falha aqui nao derruba."""
    try:
        linha = json.dumps({
            "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rota": caminho,
            "idpeticoes": argumentos.get("idpeticoes"),
            "idprocessos": argumentos.get("idprocessos"),
            "autorizado_por": autorizador,
            "resposta": (resposta or "")[:400],
        }, ensure_ascii=False)
        with open(AUDITORIA, "a", encoding="utf-8") as fh:
            fh.write(linha + "\n")
    except OSError:
        pass


def chamar(url_base, rota, argumentos, chave):
    """Unico ponto de rede do servidor. GET para consulta, POST para protocolo."""
    caminho = rota["caminho"]
    metodo = rota["metodo"]
    argumentos = dict(argumentos or {})
    argumentos.pop("api_key", None)

    # trava 1, de novo e no ultimo instante: escrita fora da lista nao passa
    if metodo != "GET" and caminho not in ESCRITA_PERMITIDA:
        return "Recusado: %s nao esta na lista de escrita permitida." % caminho, True

    # trava 3: o ato irreversivel exige quem autorizou
    autorizador = str(argumentos.pop(CAMPO_AUTORIZACAO, "") or "").strip()
    if caminho in EXIGEM_AUTORIZACAO and not autorizador:
        return ("Recusado: este protocolo envia a peca ao tribunal e exige "
                "autorizacao expressa. Preencha '%s' com o nome da advogada ou "
                "advogado da equipe que autorizou na conversa." % CAMPO_AUTORIZACAO,
                True)

    arquivo = str(argumentos.pop(CAMPO_ARQUIVO, "") or "").strip()
    if rota["ctype"] == "multipart/form-data" and metodo == "POST":
        if not arquivo:
            return "Recusado: informe '%s' com o caminho do PDF." % CAMPO_ARQUIVO, True
        if not os.path.isfile(arquivo):
            return "Arquivo nao encontrado: %s" % arquivo, True
        if os.path.getsize(arquivo) > LIMITE_ARQUIVO:
            return "Arquivo acima de 50 MB: %s" % arquivo, True

    parametros, corpo_campos = {}, {}
    for nome, valor in argumentos.items():
        if valor is None:
            continue
        if nome in rota["corpo"] and nome not in rota["query"]:
            corpo_campos[nome] = valor
        else:
            parametros[nome] = valor
    parametros["api_key"] = chave  # anexada so agora, nunca antes

    url = url_base + caminho + "?" + urllib.parse.urlencode(parametros, doseq=True)
    cabecalhos = {"Accept": "application/json",
                  "User-Agent": "legalmail-mcp-protocolo-autorizado/2.0"}
    dados = None

    if metodo == "POST":
        if rota["ctype"] == "multipart/form-data":
            dados, ctype = montar_multipart(corpo_campos, arquivo)
            cabecalhos["Content-Type"] = ctype
        else:
            dados = json.dumps(corpo_campos, ensure_ascii=False).encode("utf-8")
            cabecalhos["Content-Type"] = "application/json"

    requisicao = urllib.request.Request(url, data=dados, method=metodo,
                                        headers=cabecalhos)
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT,
                                    context=contexto_ssl()) as resposta:
            texto, houve_erro = resposta.read().decode("utf-8", "replace"), False
    except urllib.error.HTTPError as exc:
        corpo = exc.read().decode("utf-8", "replace")[:1500]
        texto, houve_erro = "Erro HTTP %s em %s: %s" % (exc.code, caminho, corpo), True
    except Exception as exc:
        # censura defensiva: a chave jamais vai para uma mensagem de erro
        texto = "Falha de conexao em %s: %s" % (
            caminho, str(exc).replace(chave, "***") if chave else str(exc))
        houve_erro = True

    if caminho in EXIGEM_AUTORIZACAO:
        registrar_auditoria(caminho, argumentos, autorizador, texto)

    return texto, houve_erro


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
                "serverInfo": {"name": "legalmail-protocolo-autorizado",
                               "version": "2.0.0"},
            })

        elif metodo in ("notifications/initialized", "initialized"):
            continue  # notificacao: nao tem resposta

        elif metodo == "tools/list":
            responder(id_req, {"tools": ferramentas})

        elif metodo == "tools/call":
            parametros = req.get("params") or {}
            nome = parametros.get("name")
            rota = rotas.get(nome)
            if not rota:
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

            texto, houve_erro = chamar(url_base, rota,
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

    leitura = [n for n, r in rotas.items() if r["metodo"] == "GET"]
    escrita = [n for n, r in rotas.items() if r["metodo"] != "GET"]
    protocolam = [n for n, r in rotas.items()
                  if r["caminho"] in EXIGEM_AUTORIZACAO]
    fora = [f"{m.upper()} {p}" for p, it in spec.get("paths", {}).items()
            for m in it if m.lower() not in ("get", "post")]

    print("Servidor MCP Legal Mail — leitura + protocolo autorizado")
    print("  ferramentas de consulta .....: %d" % len(leitura))
    print("  ferramentas de protocolo ....: %d" % len(escrita))
    print("  exigem autorizacao nominal ..: %d %s" % (len(protocolam), protocolam))
    print("  PUT/PATCH/DELETE expostos ...: %d %s"
          % (len(fora), "(nenhum)" if not fora else fora))

    vazando = [n for n, r in rotas.items()
               if r["metodo"] != "GET" and r["caminho"] not in ESCRITA_PERMITIDA]
    print("  escrita fora da lista branca : %d %s"
          % (len(vazando), "(nenhuma)" if not vazando else vazando))

    # a recusa sem autorizacao tem de acontecer antes de qualquer rede
    rota_envio = rotas.get("protocolo_PROTOCOLAR_intermediaria")
    if rota_envio:
        texto, erro = chamar(base_url(spec), rota_envio,
                             {"idpeticoes": 0, "idprocessos": 0}, "")
        ok = erro and "autorizacao" in texto.lower()
        print("  recusa envio sem autorizacao : %s" % ("OK" if ok else "FALHOU"))

    chave = carregar_chave()
    print("  chave de API ................: %s"
          % ("encontrada" if chave else "NAO CONFIGURADA"))
    if not chave:
        return 1

    texto, erro = chamar(base_url(spec), rotas["balance"], {}, chave)
    print("  teste real (/balance) .......: %s" % ("FALHOU" if erro else "OK"))
    print("  resposta: %s" % texto[:220])
    return 1 if erro else 0


if __name__ == "__main__":
    sys.exit(autoteste() if "--autoteste" in sys.argv else (main() or 0))
