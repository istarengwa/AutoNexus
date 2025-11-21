import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import httpx 
import asyncio
import json
import os
from datetime import datetime, timezone
from openai import OpenAI 

from connectors import twitter, notion, gmail, discord

CONNECTORS = {
    "twitter": twitter,
    "notion": notion,
    "discord": discord
}

TRANSLATIONS = {
    "en": {
        "new": "New Item", "update": "Update", "link": "Open Link",
        "footer": "via", "welcome_title": "🚀 Agent Activated", 
        "welcome_desc": "Surveillance active. I will notify you in English.",
        "source_label": "Source", "query_label": "Query"
    },
    "fr": {
        "new": "Nouveau Message", "update": "Modifié", "link": "Voir le message",
        "footer": "via", "welcome_title": "🚀 Agent Activé", 
        "welcome_desc": "Je surveille le salon Discord. Je vous notifierai des discussions.",
        "source_label": "Source", "query_label": "Filtre"
    }
}

DB_FILE = "autonexus_data.json"
db = {"workflows": [], "credentials": {}, "item_states": {}}

def load_db():
    global db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                db["workflows"] = data.get("workflows", [])
                db["credentials"] = data.get("credentials", {})
                s = data.get("item_states", {})
                db["item_states"] = {} if isinstance(s, list) else s
                print(f"[SYSTEM] 📂 DB Loaded.")
                print(f"[SYSTEM] 🔑 Keys found: {list(db['credentials'].keys())}")
        except Exception as e:
            print(f"[SYSTEM] ❌ Error reading DB: {e}")
    else:
        print("[SYSTEM] ⚠️ No save file found (First run?)")

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[SYSTEM] ❌ Error saving DB: {e}")

async def run_infinite_loop(workflow: dict):
    source_type = workflow.get("source")
    workflow_id = workflow.get("id") # ID unique de l'agent
    settings = workflow.get("settings", {})
    connector = CONNECTORS.get(source_type)
    
    webhook = settings.get("webhook")
    recipient_email = settings.get("recipient_email")
    lang = settings.get("agent_language", "en")
    
    t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

    if not connector:
        print(f"[ERROR] ❌ No connector for: {source_type}")
        return

    print(f"[DAEMON] ✅ Agent '{workflow['name']}' STARTED (Scan: {source_type})")

    while True:
        try:
            token = db["credentials"].get(source_type)
            if not token:
                print(f"[DAEMON] ⚠️ Agent '{workflow['name']}' paused: Missing {source_type} key.")
                await asyncio.sleep(60)
                continue

            items = await connector.fetch(settings, token)
            
            batch = []
            changed = False
            
            for item in items:
                if not item["is_ready"]: continue
                
                # --- ISOLATION DE LA MÉMOIRE ---
                # Avant : key = item["unique_key"]  (ex: notion:123) -> Partagé par tout le monde
                # Après : On préfixe avec l'ID de l'agent pour que chacun ait sa mémoire
                raw_key = item["unique_key"]
                isolated_key = f"{workflow_id}:{raw_key}"
                
                cur_ver = item["fingerprint"]
                last_ver = db["item_states"].get(isolated_key)

                if last_ver is None: 
                    item["is_update"] = False
                    batch.append(item)
                    db["item_states"][isolated_key] = cur_ver
                    changed = True
                elif last_ver != cur_ver:
                    item["is_update"] = True
                    batch.append(item)
                    db["item_states"][isolated_key] = cur_ver
                    changed = True
            
            # --- ACTION 1: DISCORD ---
            if batch and webhook:
                bot_name = settings.get("bot_name", "AutoNexus")
                print(f"[ACTION] 💬 Sending Discord for '{workflow['name']}' ({len(batch)} items)")
                for v in batch:
                    embed = {
                        "title": f"💬 {t['new']}: {settings.get('query')}",
                        "description": v['content'],
                        "color": 0x7289DA,
                        "fields": [{"name": t["link"], "value": f"[Go]({v['link']})"}],
                        "footer": {"text": f"{t['footer']} {source_type.capitalize()}"},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    async with httpx.AsyncClient() as client:
                        await client.post(webhook, json={"username": bot_name, "embeds": [embed]})

            # --- ACTION 2: EMAIL ---
            if batch and recipient_email:
                gmail_creds = db["credentials"].get("gmail")
                if gmail_creds:
                    print(f"[ACTION] 📧 Sending Email for '{workflow['name']}' to {recipient_email}")
                    await gmail.send_notification(settings, batch, gmail_creds, lang)
                else:
                    print(f"[ACTION] ❌ EMAIL FAILED: No 'gmail' key found in Connections!")
            
            if changed: save_db()

        except Exception as e:
            print(f"[LOOP ERROR] Agent '{workflow['name']}': {e}")
        
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- STARTING AUTONEXUS ---")
    load_db()
    active_count = 0
    for wf in db["workflows"]:
        if wf.get("status") == "active":
            asyncio.create_task(run_infinite_loop(wf))
            active_count += 1
    print(f"[SYSTEM] {active_count} agents relaunched.")
    print("--------------------------")
    yield
    print("--- STOPPING AUTONEXUS ---")
    save_db()

app = FastAPI(title="AutoNexus API", version="18.0.0 - Isolated Memory", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel): message: str; history: List[Dict[str, str]]
class CredentialInput(BaseModel): serviceId: str; apiKey: str
class WorkflowConfig(BaseModel): serviceSource: str; serviceDest: str; settings: Dict[str, Any]
class AgentResponse(BaseModel): role: str="agent"; content: str; type: str="text"; formData: Optional[Dict[str, Any]]=None

def analyze_intent_with_llm(user_input: str):
    openai_key = db["credentials"].get("openai")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            prompt = """
            You are the AutoNexus Architect.
            RULES:
            - READ/LISTEN Discord -> serviceSource="discord". REQUIRED: 'channel_id', 'query'.
            - READ Notion -> serviceSource="notion".
            - READ Twitter -> serviceSource="twitter".
            - Destination Email -> serviceDest="email". Field: 'recipient_email'.
            JSON SCHEMA:
            {
                "type": "form", "content": "Explanation...",
                "formData": {
                    "serviceSource": "notion" | "twitter" | "discord",
                    "serviceDest": "discord" | "email",
                    "fields": [
                        {"label": "Keyword/Query", "key": "query", "type": "text"},
                        {"label": "Channel ID (Numbers)", "key": "channel_id", "type": "text"},
                        {"label": "Email", "key": "recipient_email", "type": "text"},
                        {"label": "Bot Name", "key": "bot_name", "type": "text"},
                        {"label": "Language (fr/en)", "key": "agent_language", "type": "text", "placeholder": "fr"}
                    ]
                }
            }
            """
            res = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_input}], 
                response_format={"type": "json_object"}
            )
            return json.loads(res.choices[0].message.content)
        except: pass
    
    u = user_input.lower()
    if "salon" in u or "channel" in u or "discord" in u:
        return {"type": "form", "content": "Manual Discord Config.", "formData": {"serviceSource": "discord", "serviceDest": "email", "fields": [{"label": "Channel ID", "key": "channel_id", "type": "text"}, {"label": "Keyword", "key": "query", "type": "text"}, {"label": "Email", "key": "recipient_email", "type": "text"}, {"label": "Language", "key": "agent_language", "type": "text"}]}}
    return {"type": "text", "content": "I can read Discord, Notion, or Twitter."}

@app.post("/api/credentials")
async def save_creds(c: CredentialInput):
    final_key = c.apiKey
    if c.serviceId == "gmail":
        final_key = c.apiKey.replace(" ", "").strip()
    db["credentials"][c.serviceId] = final_key
    save_db()
    print(f"[SECURITY] Key saved for: {c.serviceId}")
    return {"status": "success"}

@app.get("/api/credentials/check/{sid}")
async def check_creds(sid: str): return {"configured": sid in db["credentials"]}

@app.post("/api/agent/chat", response_model=AgentResponse)
async def chat(r: ChatRequest): return analyze_intent_with_llm(r.message)

@app.post("/api/agent/deploy")
async def deploy(c: WorkflowConfig, bg: BackgroundTasks):
    wf = {
        "id": str(uuid.uuid4())[:8], "name": c.settings.get("bot_name", "Agent"), 
        "source": c.serviceSource, "settings": c.settings, "status": "active"
    }
    db["workflows"].append(wf)
    save_db()
    asyncio.create_task(run_infinite_loop(wf))
    return {"status": "success", "message": "Agent deployed and active."}

@app.get("/api/workflows")
async def get_wfs(): return db["workflows"]
@app.get("/api/system/stats")
async def stats(): return {"cpu": "12%", "active_agents": len(db["workflows"])}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)