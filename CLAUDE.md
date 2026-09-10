# AUTOMACOES — Maralisa Souza Advocacia

Repositório de automações do escritório **Maralisa Souza Advocacia** (Corinto/MG).
Atuação nacional em Previdenciário (carro-chefe), Trabalhista, Cível, Família e
Sucessões e Consumidor.

---

## ⚡ Legal Mail está integrada — use a API, não o e-mail

**Este repositório já traz o servidor MCP da Legal Mail conectado.** Toda sessão
nova nasce com as ferramentas `mcp__legalmail__*` disponíveis, via `.mcp.json`.

**Sempre que precisar de dado processual, consulte a Legal Mail primeiro.**
Não monte relatório a partir do push por e-mail dos tribunais: essa fonte é
incompleta — ela não cobre o TRT-3, não traz o resultado das sentenças, não
diz quem protocolou e não conhece o passivo de prazos.

### Ferramentas que mais importam

| Ferramenta | Para quê |
|---|---|
| `notices` | Intimações capturadas. Filtra por `prazo_status` (`pendente`, `cumprido`, `excedido`), `tribunal`, `processo`, `data_captura_inicio`/`fim`, `data_disponibilizacao_inicio`/`fim` |
| `pleading_notices_to_comply` | Intimações pendentes de cumprimento |
| `filings` | Protocolos enviados. **`usuario` = quem enviou; `titular_certificado` = de quem é o certificado. São coisas diferentes.** |
| `lawsuit_search` | Processos por número, parte, advogado, classe, tribunal, valor, data |
| `lawsuit_detail` | Dados completos de um processo |
| `lawsuit_summary` | Resumo agregado da carteira |
| `balance` | Saldo de créditos da API |

Mais 42 consultas. Rode `python3 legalmail/legalmail_mcp.py --autoteste` para a lista.

### Como ler os dados

- O campo **`teor`** de cada intimação é onde está o que importa: sentenças,
  resultado (procedente/improcedente), prazos fatais ("sob pena de extinção",
  "sob pena de indeferimento"), audiências designadas ou canceladas, acordos
  homologados, laudos. **Sempre leia o teor**, não pare no tipo da intimação.
- `notices` devolve no máximo 50 por página. **Pagine com `offset`** até cobrir
  o `total`.
- Para o passivo de prazos, chame `notices` com `prazo_status="pendente"` e
  `limit=1`, e leia só o campo `total`.
- A cobrança da API é **por requisição**, não por resultado. Reduzir o `limit`
  só aumenta o custo. Use sempre `limit=50`.

### Somente leitura — quatro travas

O servidor expõe **apenas as 49 consultas**. As 40 operações de escrita da API
(25 POST, 9 DELETE, 6 PUT — inclusive `/api/v1/lawsuit/delete`) estão fora, em
quatro camadas: a spec não as contém, o código só faz GET, o gerador de
ferramentas descarta métodos ≠ get, e a chave nunca é exposta ao modelo.
Detalhes em `legalmail/README.md`. **Não altere isso.**

### Chave de API

O servidor lê, nesta ordem: variável de ambiente **`LEGALMAIL_API_KEY`**, depois
o arquivo `legalmail/.api_key`. O arquivo está bloqueado no `.gitignore` e
**nunca deve ser versionado**.

⚠️ A API recebe a chave por *query string* em 88 dos 89 endpoints. URLs vão para
log de servidor, proxy e CDN. Por isso o recurso "API credentials" do ambiente
(que injeta cabeçalhos) **não funciona** aqui — use variável de ambiente.
Rotacione a chave periodicamente.

---

## 📅 Rotina de fechamento de semana

Roda **toda sexta-feira às 17h30** (Brasília), sozinha, em sessão nova.
Configurável em `claude.ai/code/routines`.

1. Apura a semana na Legal Mail — intimações, protocolos, audiências, prazos
2. Publica o relatório como página privada (Artifact)
3. Grava cópia em **Meu Drive › CONTROLADORIA › RELATORIOS FECHAMENTO SEMANA**
   `parentId = 1NkYQEpoYtgltjOF5qX72pRvJ05tbJG38`
4. Envia para **controladoriamaralisasouza@gmail.com** (destinatário único)

A pasta do Drive está compartilhada com a controladoria em modo leitura.
O documento é gravado em `contentMimeType: "text/html"` para sair formatado.

**Trava de ordem:** o e-mail só sai depois que a cópia do Drive estiver salva.
Se a gravação falhar, o envio é cancelado e o erro é reportado.

---

## 🎨 Padrão visual dos relatórios

| Papel | Cor |
|---|---|
| Tinta | `#13211C` |
| Verde do escritório | `#1F5C47` |
| Alerta crítico | `#A3302B` sobre `#F7E4E2` |
| Atenção | `#8A6415` sobre `#F7EEDA` |
| Apoio | `#E9EEEA` · linhas alternadas `#F4F7F5` |
| Barras de gráfico | `#2F7A5F` |

Tipografia das páginas: **Newsreader** nos títulos, **IBM Plex Sans** no texto,
**IBM Plex Mono** nos números de processo — numeração CNJ só alinha em
monoespaçada, com `font-variant-numeric: tabular-nums`.

Estrutura: seções numeradas (01, 02…), quadros de números no topo, barras por
tribunal, pontos de atenção com tarja lateral colorida por severidade.

No Google Docs, use `bgcolor` **e** `style="background-color:"` juntos — o
conversor precisa dos dois. Barras de gráfico: caractere `▉` repetido
proporcionalmente.

---

## ⚖️ Regras da casa — inegociáveis

- **Nunca inventar** fato, processo, cliente, dispositivo legal, jurisprudência
  ou súmula. Toda citação de jurisprudência vem com fonte e link.
- **A IA não define estratégia de caso.** Toda peça e todo relatório seguem para
  revisão da advogada humana responsável. Double check jurídico: nada sai do
  escritório sem segunda leitura humana.
- **Nunca prometer resultado.** Marketing observa o Provimento 205/2021 da OAB.
- Provas devem estar explícitas na peça — use a skill `recorte-de-documentos`.
- Peças são assinadas em **Corinto, Minas Gerais**.
- Relatórios de gestão **não substituem** o controle oficial de prazos, que
  continua sendo o DJe/PJe. Diga isso em todo relatório.
- **Distinga sempre** titular do certificado de quem executou o protocolo.

### Sigilo profissional

Relatórios trazem nome de cliente e número de processo. **Não versione isso.**
O `.gitignore` bloqueia `legalmail/preview-*.html` e `legalmail/relatorio-*.html`.
Histórico de git é permanente e difícil de expurgar. O lugar desses arquivos é a
pasta CONTROLADORIA do Drive, com acesso controlado.

---

## 👥 Equipe identificada nos dados

| Pessoa | Papel nos sistemas |
|---|---|
| Maralisa Souza Barboza Gomes | OAB/MG 230.030 · titular do certificado digital · destinatária das intimações |
| Aline Silveira de Freitas Rodrigues | OAB/MG 242.214 · protocola |
| Marcos Matheus Oliveira Silva | protocola |
| Cinara de Campos Bastos | OAB/MG 229.818 |
| Jéssica Talita Celestino | OAB/MG 226.581 |
| Fabiano Rafael de Oliveira | OAB/MG 216.297 |
| Gabriela Monteiro da Silva | OAB/RJ 148.318 |

Tribunais com movimentação recorrente: TJMG, TRT-3 (Vara do Trabalho de Curvelo),
TRF-6, TRF-1, TRF-3, TRF-2/JFES, TJSC, TRT-11, TRT-15.

---

## 📌 Pendências abertas

- [ ] Gravar `LEGALMAIL_API_KEY` nas *Environment variables* do ambiente em
      `claude.ai/code` — sem isso, sessões novas dependem do `.api_key` local,
      que não sobrevive ao contêiner
- [ ] Rotacionar a chave da Legal Mail e apagar o `INSTALAR-LEGALMAIL.py` do
      Drive, que a carrega em texto puro
- [ ] Atacar o passivo de **849 intimações com prazo pendente** contra 265
      processos cadastrados
