# Aula 10 — Exercício final: Assistente de Gestão de Pessoas

Um sistema que recebe pedidos de férias, abonos e diárias em texto livre, protege a entrada, extrai os dados, consulta um
MCP Server, analisa com especialistas, pede a aprovação da chefia e registra a decisão com auditoria. Ele usa o conteúdo das
Aulas 1 a 9.

| Arquivo | Para quê |
|---|---|
| [`ENUNCIADO.md`](ENUNCIADO.md) | **o que** o sistema faz, cronograma (5 h) e critérios de avaliação |
| [`PASSO_A_PASSO.md`](PASSO_A_PASSO.md) | **como** fazer: a ordem das lacunas, o exemplo das aulas para cada uma e as saídas esperadas |
| `conferir.py` | **confere** o seu progresso, etapa por etapa (veja abaixo) |
| [`ENTREGA.md`](ENTREGA.md) | o relatório que você preenche e entrega |

## 1. Configurar o ambiente (faça ANTES da aula)

Você precisa de **Python 3.10 a 3.13** (o 3.11.0 não serve) e de uma **chave da OpenAI** (ou do Ollama instalado). O
**Node.js** é opcional: só serve para o MCP Inspector da Etapa 5.

### Baixar ou atualizar o material

Primeira vez:

```powershell
git clone https://github.com/franciscomduarte/material-pcdf.git
cd material-pcdf\aula10
```

Se você já tem o repositório (ex.: em `C:\pcdf`):

```powershell
cd C:\pcdf
git pull
cd aula10
```

### Opção A: script automático (recomendado)

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File .\configurar_ambiente.ps1
```

**Linux/Mac:**

```bash
bash configurar_ambiente.sh
```

O script confere o Python, cria o `.venv`, instala as dependências, cria o `.env` com um `TOKEN_REGISTRO` aleatório, pede a sua
`OPENAI_API_KEY` (cole e tecle Enter, ou só Enter para preencher depois) e roda a verificação. Pode rodar de novo sem medo:
o que já existe é mantido.

### Opção B: passo a passo manual

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1                  # Linux/Mac: source .venv/bin/activate
python -m pip install -r requirements.txt
copy .env.example .env                      # Linux/Mac: cp .env.example .env
```

Abra o `.env`, preencha `OPENAI_API_KEY` e troque `TOKEN_REGISTRO=troque-este-valor` por um valor seu. Para usar o Ollama
em vez da OpenAI: `PROVEDOR=ollama` e o modelo baixado (`ollama pull llama3.1`).

### Verificar

```powershell
python verificar_ambiente.py            # faz UMA chamada curta ao modelo
python verificar_ambiente.py --sem-llm  # sem chamar o modelo
```

Saída esperada (resumida):

```
1) Python e pasta
  [OK]    Python 3.12.3
  [OK]    rodando de dentro de aula10/
  [OK]    ambiente virtual ativo (.venv)
2) Bibliotecas
  [OK]    openai-agents 0.22.3
  ...
3) Arquivo .env
  PROVEDOR=openai
  [OK]    OPENAI_API_KEY preenchida (termina em ...a1b2)
  [OK]    TOKEN_REGISTRO definido
4) Dados do exercício
  [OK]    9 servidores, 3 afastamentos, 13 feriados locais, 10 regras
5) MCP Server sobe e lista as tools (sem chamar nenhuma)
  [OK]    etapa05_mcp_rh.py no ar com 6 tools: consultar_servidor, consultar_escala, ...
6) Node.js (só para o MCP Inspector da Etapa 5)
  [OK]    npx encontrado: o MCP Inspector vai funcionar
7) APIs externas (se falharem, o exercício usa o plano B)
  [OK]    BrasilAPI (feriados) respondeu
  [OK]    Frankfurter (câmbio) respondeu
8) Modelo de linguagem
  [OK]    openai:gpt-4o-mini respondeu: 'PRONTO'

Resultado: tudo certo, pode começar pelo PASSO_A_PASSO.md.
```

`[FALTA]` não impede o exercício (é algo opcional ou que tem plano B). `[ERRO]` precisa ser corrigido antes da aula.

**Em cada terminal novo**, antes de trabalhar: `cd` para `aula10` e ative o ambiente (`.venv\Scripts\Activate.ps1`). Se o
PowerShell bloquear a ativação, rode uma vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 2. Fazer o exercício

Siga o [`PASSO_A_PASSO.md`](PASSO_A_PASSO.md), na ordem. Cada lacuna do código é um comentário `# ETAPA n.m` com um
`raise NotImplementedError("ETAPA n.m: ...")`: troque o `raise` pelo seu código.

## 3. Conferir o progresso

```powershell
python conferir.py              # todas as etapas, sem chamar o LLM (uns 30 segundos, não gasta tokens)
python conferir.py 7            # só a Etapa 7 (pode passar várias: python conferir.py 5 7)
python conferir.py --llm        # inclui as conferências que chamam o modelo (Etapas 1, 2, 3 e 6)
python conferir.py --opcionais  # inclui os itens opcionais 🆕 A, B e C
```

Cada conferência sai como `[OK]`, `[PENDENTE]` (a lacuna ainda tem o `NotImplementedError`), `[FALHOU]` (rodou, mas o
resultado está errado: a mensagem diz o que veio e o que se esperava) ou `[ERRO]` (deu exceção: a mensagem diz qual e em que
linha do seu código). No fim aparece um resumo por etapa e se você atingiu o Marco mínimo e o Marco completo.

Exemplo, no meio do exercício:

```
Etapa 5: MCP Server do RH   (onde olhar: etapa05_mcp_rh.py e etapa05_cliente_mcp.py; aula6/desafio2/mcp_unidades.py)
  [OK]       5.4 chamar_mcp devolve um dict
  [FALHOU]   5.1 as 5 tools de leitura: consultar_servidor está devolvendo o salário (não pode)
  [OK]       5.2 registrar_decisao grava e não duplica
...
  Etapa 4    ✅ completa        APIs com resiliência (pronta)
  Etapa 5    🟡 em andamento    MCP Server do RH
  Etapa 6    ⬜ não iniciada    Especialistas e fluxo linear (Marco mínimo)
```

**Como ele confere o grafo sem gastar tokens:** nas Etapas 7 a 10, as respostas do LLM são trocadas por respostas **fixas**
(como num teste). Assim o resultado só depende do **seu** código: caminhos, decisões, pausas, retomadas e o que é enviado ao MCP.
Nada do que o `conferir.py` grava fica em `saidas/`.

> O `conferir.py` mostra se o código **faz o que o enunciado pede**. Ele não substitui rodar o sistema de verdade com o LLM
> (`python etapa07_grafo.py --todos`) nem preencher o `ENTREGA.md`.
