import os
import hmac
import hashlib
import json

from fastapi import FastAPI, Request, HTTPException
import httpx

app = FastAPI()

# ── Variáveis de ambiente ──────────────────────────────────────────────────────
SLACK_BOT_TOKEN      = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"].encode()
LANGFLOW_API_URL     = os.environ.get(
    "LANGFLOW_API_URL",
    "https://api.langflow.astra.datastax.com/lf/252a6775-893d-49c1-bcb7-e25cb3be441a/api/v1/run/f933dc8c-e6fb-4db5-b496-2d23b8770cd9"
)
LANGFLOW_API_TOKEN   = os.environ["LANGFLOW_API_TOKEN"]

# ── Utilitário de verificação de assinatura do Slack ───────────────────────────
def verify_slack_signature(request: Request, body: bytes) -> None:
    """Lança 401 se a assinatura do Slack não bater."""
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    my_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET, sig_basestring, hashlib.sha256
    ).hexdigest()
    slack_signature = request.headers.get("X-Slack-Signature", "")
    if not hmac.compare_digest(my_signature, slack_signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

# ── Endpoint principal ─────────────────────────────────────────────────────────
@app.post("/slack/events")
async def slack_events(request: Request):
    # ▸ 0. Valida assinatura
    raw_body = await request.body()
    verify_slack_signature(request, raw_body)

    payload = json.loads(raw_body)
    print("Payload recebido do Slack:", payload)

    # ▸ 1. URL Verification
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    # ▸ 2. Extrai texto da mensagem e limpa menção ao bot
    event = payload.get("event", {})
    text = (event.get("text") or "").strip()
    bot_user_id = (payload.get("authorizations") or [{}])[0].get("user_id", "")
    if bot_user_id:
        text = text.replace(f"<@{bot_user_id}>", "").strip() or "geral"

    # ▸ 3. Envia consulta ao Langflow
    langflow_payload = {
        "input_value": text,
        "output_type": "chat",
        "input_type": "chat",
        "session_id": event.get("user"),  # 1 sessão por usuário
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            lf_resp = await client.post(
                LANGFLOW_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LANGFLOW_API_TOKEN}",
                },
                json=langflow_payload,
            )
        print("Resposta bruta do Langflow:", lf_resp.text)
        lf_json = lf_resp.json()
        answer = lf_json.get("output") or "⚠️ Langflow não retornou resposta."
    except Exception as exc:
        print("Erro ao consultar Langflow:", exc)
        answer = "⚠️ Erro ao consultar Langflow."

    # ▸ 4. Posta resposta no Slack (mesmo thread, se existir)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            slack_resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                },
                json={
                    "channel": event.get("channel"),
                    "text": answer,
                    "thread_ts": event.get("thread_ts") or event.get("ts"),
                },
            )
        print("Resposta do Slack:", slack_resp.text)
    except Exception as exc:
        print("Erro ao responder no Slack:", exc)

    return {"status": "ok"}
