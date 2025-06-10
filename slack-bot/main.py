from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
# ⚠️ Ajustamos para o novo endpoint do Langflow
LANGFLOW_API_URL = "https://langflow-api-v2.onrender.com/v1/run-flow"

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

    # 3️⃣ Faz requisição pro Langflow
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                LANGFLOW_API_URL,
                headers={"Content-Type": "application/json"},
                json={"input": text}  # ⚠️ Mudamos de "query" para "input"
            )
            print("Resposta bruta do Langflow:", resp.text)

            # ⚠️ Ajustamos para "output" no JSON de resposta
            try:
                data = resp.json()
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
                "https://slack.com/api/chat.postMessage",
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
