from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]

# Endpoint do Langflow (API pública no DataStax Langflow)
LANGFLOW_API_URL = "https://api.langflow.astra.datastax.com/lf/252a6775-893d-49c1-bcb7-e25cb3be441a/api/v1/run/f933dc8c-e6fb-4db5-b496-2d23b8770cd9"
LANGFLOW_API_TOKEN = os.environ["LANGFLOW_API_TOKEN"]  # Coloque seu token aqui nas variáveis de ambiente

@app.post("/")
async def slack_events(req: Request):
    payload = await req.json()
    print("Payload recebido do Slack:", payload)

    # 1️⃣ Valida o URL Verification do Slack
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # 2️⃣ Extrai o texto do evento
    event = payload.get("event", {})
    text = event.get("text", "")
    bot_id = payload.get("authed_users", [""])[0]
    text = text.replace(f"<@{bot_id}>", "").strip() or "geral"

    # 3️⃣ Faz requisição real ao Langflow API
    langflow_payload = {
        "input_value": text,
        "output_type": "chat",
        "input_type": "chat",
        "session_id": "user_1"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                LANGFLOW_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LANGFLOW_API_TOKEN}"
                },
                json=langflow_payload
            )
            print("Resposta bruta do Langflow:", resp.text)

            try:
                data = resp.json()
                # Ajuste aqui para o que o Langflow retorna (pode variar!)
                answer = data.get("output", "⚠️ Erro ao consultar Langflow")
            except Exception as e:
                print("Erro ao decodificar JSON:", e)
                answer = "⚠️ Erro ao decodificar resposta do Langflow"

    except Exception as e:
        print("Erro ao consultar Langflow:", e)
        answer = "⚠️ Erro ao consultar Langflow"

    # 4️⃣ Responde de volta no Slack
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://hooks.slack.com/services/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",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
                },
                json={
                    "channel": event.get("channel"),
                    "text": answer,
                    "thread_ts": event.get("thread_ts") or event.get("ts")
                }
            )
    except Exception as e:
        print("Erro ao responder no Slack:", e)

    return {"status": "ok"}
