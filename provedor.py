"""
provedor.py -- configura o SDK de agentes (openai-agents) para o provedor escolhido na variável PROVEDOR (.env).

Mesma ideia da Aula 7 (trocar de provedor sem mexer no grafo), agora sobre o SDK de agentes:
os agentes são `Agent(name=..., instructions=...)` e rodam com `Runner`. Só esta função muda entre provedores.

    PROVEDOR=openai  (padrão) OpenAI      -> OPENAI_API_KEY, OPENAI_DEFAULT_MODEL (gpt-4o-mini)
    PROVEDOR=ollama  Ollama local, grátis -> OLLAMA_BASE_URL, OLLAMA_MODEL (o modelo precisa estar baixado)

Diferenças em relação à Aula 7:
  - não há Mock nem Claude: só LLM real, compatível com a API da OpenAI;
  - sem chave (ou sem o Ollama no ar) o programa PARA e diz o que fazer.

Uso:
    from provedor import configurar, AJUSTES
    print("Modelo:", configurar())                       # chamar ANTES de criar os agentes
    agente = Agent(name=..., instructions=..., model_settings=AJUSTES)
"""
import json
import os
import urllib.request

import httpx
from agents import ModelSettings, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Carrega as variáveis do arquivo .env (PROVEDOR, chaves, modelos).
load_dotenv()

AJUSTES = ModelSettings(temperature=0, max_tokens=300)

AJUDA = (
    "Configure um provedor real: copie o .env.example para .env e preencha.\n"
    "  - OpenAI: PROVEDOR=openai e OPENAI_API_KEY=...\n"
    "  - Ollama (grátis, local): PROVEDOR=ollama, `ollama serve` no ar e o modelo baixado (`ollama pull <modelo>`)."
)


# Cria o cliente HTTP assíncrono que o SDK usa para falar com o LLM.
# Sem conexões persistentes: cada Runner.run_sync() (numa thread do LangGraph) cria o próprio laço de eventos,
# e conexões reaproveitadas entre laços diferentes travam o programa.
def _cliente(base_url: str | None, api_key: str) -> AsyncOpenAI:
    http = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=0), timeout=180)
    return AsyncOpenAI(base_url=base_url, api_key=api_key, http_client=http)


# Pergunta ao Ollama quais modelos estão baixados. Devolve a lista de nomes, ou None se o Ollama não responde.
def _modelos_do_ollama(base_url: str) -> list[str] | None:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=3) as r:
            return [m["id"] for m in json.load(r).get("data", [])]
    except (OSError, ValueError, KeyError):
        return None


# Define o modelo que todo Agent(...) usa quando é criado sem o parâmetro `model`.
def _usar_modelo(modelo: str) -> None:
    os.environ["OPENAI_DEFAULT_MODEL"] = modelo


# Configura a OpenAI: exige OPENAI_API_KEY, escolhe o modelo e registra o cliente no SDK.
def _configurar_openai() -> str:
    chave = os.getenv("OPENAI_API_KEY")
    if not chave:
        raise SystemExit("PROVEDOR=openai exige OPENAI_API_KEY.\n" + AJUDA)
    modelo = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")
    _usar_modelo(modelo)
    set_default_openai_client(_cliente(None, chave))
    return f"openai:{modelo}"


# Configura o Ollama local: confere se o servidor está no ar e se o modelo está baixado,
# registra o cliente no SDK e troca para a API chat_completions (o Ollama não tem a Responses API).
def _configurar_ollama() -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    modelo = os.getenv("OLLAMA_MODEL", "llama3.1")

    disponiveis = _modelos_do_ollama(base_url)
    if disponiveis is None:
        raise SystemExit(f"PROVEDOR=ollama, mas o Ollama não responde em {base_url}. Rode `ollama serve`.\n" + AJUDA)
    if not any(m == modelo or m.startswith(modelo + ":") for m in disponiveis):
        raise SystemExit(f"O modelo {modelo!r} não está no Ollama (há: {', '.join(disponiveis) or 'nenhum'}). "
                         f"Rode `ollama pull {modelo}` ou ajuste OLLAMA_MODEL no .env.")

    _usar_modelo(modelo)
    set_default_openai_client(_cliente(base_url, os.getenv("OLLAMA_API_KEY", "ollama")))  # api_key lida do .env
    set_default_openai_api("chat_completions")
    return f"ollama:{modelo}"


# Tabela de provedores aceitos em PROVEDOR. Para incluir um novo, crie a função e adicione aqui.
_PROVEDORES = {"openai": _configurar_openai, "ollama": _configurar_ollama}


# Ponto de entrada: lê PROVEDOR do .env, desliga o tracing, chama a configuração do provedor
# e devolve o modelo em uso (ex.: 'openai:gpt-4o-mini'). Chamar ANTES de criar os agentes.
def configurar() -> str:
    set_tracing_disabled(True)  # sem envio de traces para a OpenAI
    provedor = os.getenv("PROVEDOR", "openai").strip().lower()
    if provedor not in _PROVEDORES:
        raise SystemExit(f"PROVEDOR desconhecido: {provedor!r}. Use {' ou '.join(_PROVEDORES)}.\n" + AJUDA)
    return _PROVEDORES[provedor]()