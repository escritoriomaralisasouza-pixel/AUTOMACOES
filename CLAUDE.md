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

Mais 42 consultas, e as 7 de protocolo (ver adiante). Rode
`python3 legalmail/legalmail_mcp.py --autoteste` para a lista.

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

### Protocolo: pode, com autorização expressa

**A IA protocola.** Autorizado pela Dra. Maralisa em 15/09/2026. O servidor
expõe as 49 consultas e **7 operações de protocolo** — criar intermediária,
criar inicial, subir o PDF, subir anexos, consultar status e os dois envios ao
tribunal.

| Ferramenta | O que faz |
|---|---|
| `protocolo_criar_intermediaria` | Cria a petição e devolve `idpeticoes` |
| `protocolo_criar_inicial` | Cria a inicial |
| `protocolo_enviar_arquivo_principal` | Sobe o PDF da peça |
| `protocolo_enviar_anexo` | Sobe cada documento |
| `protocolo_consultar_status` | Confere se entrou |
| `protocolo_PROTOCOLAR_intermediaria` | **Envia ao tribunal** |
| `protocolo_PROTOCOLAR_inicial` | **Envia ao tribunal** |

**A autorização é obrigatória e vem antes.** Os dois envios só executam com o
campo `autorizacao_advogado` preenchido com o nome de quem autorizou na
conversa. Sem ele o servidor recusa e não toca a rede. Todo envio fica
registrado em `legalmail/auditoria-protocolos.log`.

Quem autoriza: **qualquer advogada ou advogado da equipe**, expressamente, peça
a peça. Autorização genérica — "pode protocolar tudo", "daqui pra frente pode"
— não vale e não deve ser aceita. O certificado usado é sempre o da Dra.
Maralisa, então quem autoriza responde junto com quem assina.

Depois de enviar, **confirme com `protocolo_consultar_status`**. Um envio
cancelado sem ninguém conferir foi o que quase perdeu o prazo recursal da
Geraldinha em setembro de 2026.

### O que continua fora — não altere

As outras 33 operações de escrita da API seguem inalcançáveis, **inclusive
todas as 9 de exclusão** e `/api/v1/lawsuit/delete`. Cinco travas sustentam
isso: lista branca fechada de 7 caminhos conferida duas vezes, spec sem
PUT/PATCH/DELETE, autorização nominal nos envios, trilha de auditoria, e a
chave nunca exposta ao modelo. Detalhes em `legalmail/README.md`.

Ampliar esse conjunto é decisão da titular do workspace, nunca de manutenção
de rotina.

### Chave de API

O servidor lê, nesta ordem: variável de ambiente **`LEGALMAIL_API_KEY`**, depois
o arquivo `legalmail/.api_key`. O arquivo está bloqueado no `.gitignore` e
**nunca deve ser versionado**.

⚠️ A API recebe a chave por *query string* em 88 dos 89 endpoints. URLs vão para
log de servidor, proxy e CDN. Por isso o recurso "API credentials" do ambiente
(que injeta cabeçalhos) **não funciona** aqui — use variável de ambiente.
Rotacione a chave periodicamente.

---

## 📅 Rotinas agendadas

### ⚠️ A rotina NÃO enxerga o servidor MCP — leia antes de mexer

**Sessão de rotina nasce sem o repositório clonado.** Sem repositório não há
`.mcp.json`, e sem ele não existem as ferramentas `mcp__legalmail__*`. Isso é
do desenho da plataforma, não é falha.

Entre 10/09 e 29/09/2026 as três rotinas de fechamento caíram na fonte
alternativa (push por e-mail) e entregaram metade dos números:

| Indicador, semana 19–25/09 | Relatório | Real |
|---|---|---|
| Intimações | 35 | **73** |
| Protocolos | N/D | **23** |
| Processos na base | N/D | **300** |
| Passivo de prazos | N/D | **1011** |
| Atos do TRT-3 | 0 | **18** |

O push por e-mail não cobre o TRT-3. Três ações trabalhistas novas sumiram.

**A correção:** as rotinas chamam a API direto, por `python3`, com o apurador
embutido no próprio prompt. Referência versionada em `legalmail/apurador.py`
(modos `semana` e `radar`). Dois detalhes que quebram a rodada:

- **O proxy do container exige o cabeçalho `User-Agent`.** Sem ele, HTTP 403.
  Não é bloqueio de rede: o container alcança `api.legalmail.com.br`. A skill
  `esteira-legalmail` documenta esse caminho como fechado — **está errada**.
- **A API quase nunca preenche `data_limite_manifestacao`** (2 em 200 medidos
  em 29/09/2026). Ordenar prazo por esse campo não funciona.

**Regra:** se a apuração devolver erro, a rotina **para** e avisa. Nunca cai
para o Gmail. Relatório incompleto apresentado como completo é pior que
relatório nenhum.

### Segunda, 8h — Radar de Prazos

`trig_01JutAaFzR1qJPSFbNuNUPE2` · cron `0 11 * * 1` (UTC)

Fila de execução da semana, uma linha por processo, ordenada por gravidade do
teor e idade da intimação. Farol VERMELHO / LARANJA / AMARELO / VERDE. Vai a
**escritoriomaralisasouza@gmail.com** e **controladoriamaralisasouza@gmail.com**,
com a fila inteira, cada processo nominal.

### Sexta, 17h30 — Fechamento de Semana

`trig_01Nq7PV8uduEZHGDgoxfHMfy` · cron `30 20 * * 5` (UTC)

1. Apura a semana pela API — intimações, protocolos, audiências, passivo
2. Publica o relatório como página privada (Artifact)
3. Grava cópia em **Meu Drive › CONTROLADORIA › RELATORIOS FECHAMENTO SEMANA**
   `parentId = 1NkYQEpoYtgltjOF5qX72pRvJ05tbJG38`
4. Envia para **controladoriamaralisasouza@gmail.com** (destinatário único)

A pasta do Drive está compartilhada com a controladoria em modo leitura.
O documento é gravado em `contentMimeType: "text/html"` para sair formatado.

**Trava de ordem:** o e-mail só sai depois que a cópia do Drive estiver salva.
Se a gravação falhar, o envio é cancelado e o erro é reportado.

### Conectores: só se propagam na criação

Uma rotina criada por ferramenta MCP **não herda** os conectores da sessão que
a criou — ela nasce sem Gmail e sem Drive, e então não envia e-mail nem grava
no Drive. Conectores se adicionam na interface, em `claude.ai/code/routines`.
Ao criar rotina nova que precise enviar algo, **confira isso antes de confiar
que ela roda**.

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
- **Nenhum protocolo sai sem autorização expressa** de advogada ou advogado da
  equipe, dita na conversa, peça a peça. A peça passa pela revisão humana antes
  do envio — protocolar não dispensa o double check, é o passo depois dele.
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

- [x] ~~Gravar `LEGALMAIL_API_KEY` nas *Environment variables*~~ — feito, confirmado 29/09/2026
- [ ] Rotacionar a chave da Legal Mail e apagar o `INSTALAR-LEGALMAIL.py` do
      Drive, que a carrega em texto puro
- [ ] Atacar o passivo de **1.011 intimações com prazo pendente** contra 300
      processos cadastrados — o radar de segunda entrega a fila em ordem
- [ ] Adicionar os conectores Gmail e Google-Drive à rotina **Radar de Prazos**
      (`trig_01JutAaFzR1qJPSFbNuNUPE2`) em `claude.ai/code/routines` — criada
      por ferramenta, nasceu sem eles e **não envia e-mail** enquanto isso não
      for feito
- [ ] Corrigir a skill `esteira-legalmail`: ela diz que `curl`/`bash` do
      container em nuvem está bloqueado (403). Está errado — o 403 era falta do
      cabeçalho `User-Agent`. Verificado em 29/09/2026
