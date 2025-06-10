import os
import hmac
import hashlib
import json

from fastapi import FastAPI, Request, HTTPException
import httpx

app = FastAPI()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"].encode()
LANGFLOW_API_URL = os.environ.get(
    "LANGFLOW_API_URL",
    "https://api.langflow.astra.datastax.com/lf/252a6775-893d-49c1-bcb7-e25cb3be441a/api/v1/run/f933dc8c-e6fb-4db5-b496-2d23b8770cd9?stream=false"
)
LANGFLOW_API_TOKEN = os.environ["LANGFLOW_API_TOKEN"]

def verify_slack_signature(request: Request, body: bytes) -> None:
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    my_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET, sig_basestring, hashlib.sha256
    ).hexdigest()
    slack_signature = request.headers.get("X-Slack-Signature", "")
    if not hmac.compare_digest(my_signature, slack_signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

@app.post("/slack/events")
async def slack_events(request: Request):
    raw_body = await request.body()
    verify_slack_signature(request, raw_body)

    # Ignora replays automáticos do Slack
    if request.headers.get("X-Slack-Retry-Num"):
        return {"ok": True}

    payload = json.loads(raw_body)
    print("Payload recebido do Slack:", payload)

    # URL verification
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event = payload.get("event", {})
    bot_user_id = (payload.get("authorizations") or [{}])[0].get("user_id", "")

    # ▸ 1. Ignora tudo que não for app_mention
    if event.get("type") != "app_mention":
        return {"ok": True}

    # ▸ 2. Ignora mensagens do próprio bot
    if (
        event.get("bot_id")
        or event.get("subtype") == "bot_message"
        or event.get("user") == bot_user_id
    ):
        return {"ok": True}

    # ▸ 3. Limpa texto da menção ao bot
    text = (event.get("text") or "").strip()
    if bot_user_id:
        text = text.replace(f"<@{bot_user_id}>", "").strip() or "geral"

    # ▸ 4. Consulta Langflow
    langflow_payload = {
        "input_value": text,
        "output_type": "chat",
        "input_type": "chat",
        "session_id": event.get("user"),
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:  # aumentei timeout
            lf_resp = await client.post(
                LANGFLOW_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LANGFLOW_API_TOKEN}",
                    "Accept": "application/json",
                },
                json=langflow_payload,
            )
        print("Resposta bruta do Langflow:", lf_resp.text)
        lf_resp.raise_for_status()
        answer = lf_resp.json().get("output") or "⚠️ Langflow não retornou resposta."
    except Exception as exc:
        import traceback, sys
        traceback.print_exception(exc, file=sys.stderr)
        answer = f"⚠️ Erro ao consultar Langflow: {exc}"

    # ▸ 5. Posta a resposta no Slack
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

@app.get("/")
async def root():
    return {"status": "running"}
