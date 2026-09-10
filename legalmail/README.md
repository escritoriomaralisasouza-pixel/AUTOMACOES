# Servidor MCP da Legal Mail — somente leitura

Escritório Maralisa Souza Advocacia · Corinto/MG

Conecta o Claude Code à API da Legal Mail para **consultar** processos,
intimações, prazos, protocolos e partes. Não protocola, não altera e não apaga
nada.

## Arquivos

| Arquivo | O que é |
|---|---|
| `legalmail_mcp.py` | O servidor. ~230 linhas, sem dependência obrigatória. |
| `openapi.json` | Especificação da API, **só com as operações de leitura**. |
| `.api_key` | A chave. **Nunca versionada** (bloqueada no `.gitignore`). |

## As quatro travas de segurança

A API da Legal Mail expõe **89 operações**: 49 de leitura e **40 de escrita**,
incluindo 9 de exclusão — entre elas `/api/v1/lawsuit/delete`. Este servidor
expõe apenas as 49 de leitura, e isso é garantido em quatro camadas
independentes:

1. **A especificação não tem escrita.** O `openapi.json` foi gerado removendo
   as 40 operações de POST/PUT/PATCH/DELETE. O servidor não alcança o que não
   existe no arquivo que ele lê.
2. **O código só faz GET.** Há um único ponto de rede (`consultar`) e ele tem
   `method="GET"` fixo. Não existe outro método no arquivo inteiro.
3. **O gerador de ferramentas descarta escrita.** Em `montar_ferramentas`,
   qualquer método diferente de `get` é ignorado, mesmo que apareça na spec.
4. **A chave nunca é exposta.** Não entra na lista de ferramentas, não entra
   nos parâmetros que o modelo preenche, e é removida de mensagens de erro.

Confira você mesma:

```bash
python3 legalmail/legalmail_mcp.py --autoteste
```

Saída esperada:

```
ferramentas de consulta .....: 49
operacoes de escrita expostas: 0 (nenhuma)
chave de API ................: encontrada
teste real (/balance) .......: OK
```

## A chave de API

O servidor procura nesta ordem:

1. Variável de ambiente **`LEGALMAIL_API_KEY`** — forma recomendada.
   Em sessões na nuvem, configure em `claude.ai/code` → ícone de nuvem →
   engrenagem no ambiente → **Environment variables**.
2. Arquivo **`.api_key`** ao lado do script — uso local. Permissão `600`.

> **Atenção:** a API da Legal Mail recebe a chave por *query string*
> (`?api_key=...`) em 88 dos 89 endpoints. URLs vão para log de acesso de
> servidor, proxy e CDN. Isso é característica do desenho da API deles, não
> desta integração. Rotacione a chave periodicamente.
>
> Por esse mesmo motivo, o recurso **API credentials** do ambiente (que injeta
> *cabeçalhos*) **não funciona** aqui: serviria para 1 endpoint apenas.

## Exemplos de uso

Depois de conectado, basta perguntar em português:

- "Quais intimações estão com prazo pendente?"
- "Quantas intimações pendentes temos no TRT-3?"
- "Me mostra os detalhes do processo 0001039-42.2026.5.11.0017"
- "Quais processos foram distribuídos este mês?"
- "Qual o saldo de créditos da API?"

## Ferramentas principais

| Ferramenta | Para quê |
|---|---|
| `notices` | Intimações capturadas — filtra por `prazo_status` (`pendente`, `cumprido`, `excedido`), tribunal, processo, período |
| `pleading_notices_to_comply` | Intimações pendentes de cumprimento |
| `lawsuit_search` | Busca processos por número, parte, advogado, classe, tribunal, valor da causa, data |
| `lawsuit_detail` | Dados completos de um processo |
| `lawsuit_summary` | Resumo agregado da carteira |
| `filings` | Protocolos do workspace |
| `balance` | Saldo de créditos da API |

Mais 42 consultas (partes, autos, documentos, comarcas, tribunais, usuários).
Rode `--autoteste` ou peça a lista completa ao Claude.

## Manutenção

Quando a Legal Mail publicar novos endpoints, regere a especificação a partir
da fonte oficial (`https://app.legalmail.com.br/assets/docs/openapi.yaml`),
mantendo **apenas** as operações `get`. Nunca inclua operações de escrita.
