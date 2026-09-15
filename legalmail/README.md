# Servidor MCP da Legal Mail — leitura + protocolo autorizado

Escritório Maralisa Souza Advocacia · Corinto/MG

Conecta o Claude Code à API da Legal Mail para **consultar** processos,
intimações, prazos, protocolos e partes, e para **protocolar petição** mediante
autorização expressa de advogada ou advogado da equipe.

Não altera e não apaga nada.

> **Mudança de 15/09/2026.** Até esta data o servidor era estritamente somente
> leitura. A Dra. Maralisa Souza Barboza Gomes, titular do workspace, autorizou
> a habilitação do fluxo de protocolo. O escopo foi mantido no mínimo
> necessário: 7 operações, todas do caminho de protocolo. As 33 demais
> operações de escrita da API — **incluindo todas as 9 de exclusão** — seguem
> inalcançáveis.

## Arquivos

| Arquivo | O que é |
|---|---|
| `legalmail_mcp.py` | O servidor. ~400 linhas, sem dependência obrigatória. |
| `openapi.json` | Especificação: as 49 operações de leitura e as 7 de protocolo. |
| `.api_key` | A chave. **Nunca versionada** (bloqueada no `.gitignore`). |
| `auditoria-protocolos.log` | Trilha de quem autorizou cada protocolo. **Nunca versionada.** |

## O que o servidor alcança

**49 consultas** (GET) e **7 operações de protocolo** (POST):

| Ferramenta | O que faz |
|---|---|
| `protocolo_criar_intermediaria` | Cria a petição intermediária e devolve `idpeticoes` |
| `protocolo_criar_inicial` | Cria a petição inicial |
| `protocolo_enviar_arquivo_principal` | Sobe o PDF da peça |
| `protocolo_enviar_anexo` | Sobe cada documento anexo |
| `protocolo_consultar_status` | Consulta a situação da petição |
| `protocolo_PROTOCOLAR_intermediaria` | **Envia ao tribunal.** Exige autorização |
| `protocolo_PROTOCOLAR_inicial` | **Envia ao tribunal.** Exige autorização |

O nome dos dois últimos está em maiúscula de propósito: são os atos
irreversíveis.

## As cinco travas de segurança

1. **Lista branca fechada.** Só os 7 caminhos de `ESCRITA_PERMITIDA` aceitam
   POST. Qualquer outra escrita é recusada pelo servidor mesmo que apareça na
   especificação. A verificação acontece duas vezes: ao montar as ferramentas
   e no último instante antes da rede.
2. **A especificação só tem GET e os 7 POST.** O `openapi.json` não contém
   nenhum PUT, PATCH ou DELETE. O servidor não alcança o que não existe no
   arquivo que ele lê. `/api/v1/lawsuit/delete` não está lá.
3. **O ato irreversível exige autorização nominal.** Os dois envios só executam
   com o campo `autorizacao_advogado` preenchido com o nome de quem autorizou.
   Sem ele, o servidor recusa e **não toca a rede**. O campo nunca vai para a
   API: serve à auditoria da casa.
4. **Todo protocolo fica registrado.** Cada envio grava uma linha em
   `auditoria-protocolos.log` — data, petição, processo, quem autorizou e a
   resposta do tribunal.
5. **A chave nunca é exposta.** Não entra na lista de ferramentas, não entra
   nos parâmetros que o modelo preenche, e é removida de mensagens de erro.

Confira você mesma:

```bash
python3 legalmail/legalmail_mcp.py --autoteste
```

Saída esperada:

```
ferramentas de consulta .....: 49
ferramentas de protocolo ....: 7
exigem autorizacao nominal ..: 2 [...]
PUT/PATCH/DELETE expostos ...: 0 (nenhum)
escrita fora da lista branca : 0 (nenhuma)
recusa envio sem autorizacao : OK
teste real (/balance) .......: OK
```

## O que a trava de autorização é, e o que ela não é

É uma **trava de processo**, não criptográfica. O servidor exige que o nome de
quem autorizou seja declarado e registrado; ele não tem como verificar
identidade — quem fala na conversa é quem está logado na sessão.

O que ela garante, na prática: nenhum protocolo sai por inércia do modelo, e
todo envio deixa rastro com nome. O que ela não garante: que a pessoa que
digitou seja mesmo quem diz ser. Por isso a autorização é peça a peça e a
responsabilidade continua humana.

## Fluxo de um protocolo

```
0. GET  pleading_notices_to_comply    → intimações a cumprir (guardar idintimacoes)
1. POST protocolo_criar_intermediaria → devolve idpeticoes
2. POST protocolo_enviar_arquivo_principal → o PDF da peça
3. POST protocolo_enviar_anexo        → um por documento (opcional)
4. GET  complaintsandpleadings_types  → escolher fk_peca
5. POST protocolo_PROTOCOLAR_intermediaria → ENVIA (exige autorizacao_advogado)
6. POST protocolo_consultar_status    → confirmar que entrou
```

O passo 6 não é opcional na prática da casa: um envio cancelado sem ninguém
conferir foi o que quase perdeu o prazo recursal em setembro de 2026.

Se o processo tiver mais de um sistema de tribunal cadastrado, o passo 1
devolve **422** com `sistemas_disponiveis`. Nesse caso o sistema precisa ser
definido na plataforma antes — o endpoint que faz isso **não** está exposto
aqui, de propósito.

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

Consulta, à vontade:

- "Quais intimações estão com prazo pendente?"
- "Me mostra os detalhes do processo 0001039-42.2026.5.11.0017"
- "Qual o saldo de créditos da API?"

Protocolo, só com autorização na conversa:

- "Protocola a manifestação da Geraldinha no 6005736-24.2025.4.06.3812.
  Autorizado por Maralisa Souza Barboza Gomes."

## Manutenção

Quando a Legal Mail publicar novos endpoints, regere a especificação a partir
da fonte oficial (`https://app.legalmail.com.br/assets/docs/openapi.yaml`),
mantendo as operações `get` e **apenas** os 7 POST listados em
`ESCRITA_PERMITIDA`. Ampliar esse conjunto é decisão da titular do workspace,
não de manutenção de rotina. Nunca inclua PUT, PATCH ou DELETE.
