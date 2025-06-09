from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
ASTRA_URL = os.environ["ASTRA_URL"]
ASTRA_TOKEN = os.environ["ASTRA_TOKEN"]

@app.post("/")
async def slack_events(req: Request):
    payload = await req.json()
    print("Payload:", payload)

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    event = payload.get("event", {})
    text = event.get("text", "")
    bot_id = payload.get("authed_users", [""])[0]
    text = text.replace(f"<@{bot_id}>", "").strip() or "geral"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                ASTRA_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ASTRA_TOKEN}"
                },
                json={
                    "input_value": text,
                    "input_type": "text",
                    "output_type": "text"
                }
            )
            data = resp.json()
            answer = data.get("response", "⚠️ erro ao consultar Langflow")
    except Exception as e:
        print("Erro ao consultar Langflow:", e)
        answer = "⚠️ erro ao consultar Langflow"

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
