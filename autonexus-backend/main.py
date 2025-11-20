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

# --- IMPORT CONNECTORS ---
from connectors import twitter, notion, gmail

CONNECTORS = {
    "twitter": twitter,
    "notion": notion
}

# --- TRANSLATIONS FOR NOTIFICATIONS ---
TRANSLATIONS = {
    "en": {
        "new": "New Item", "update": "Update", "link": "Open Link",
        "footer": "via", "welcome_title": "🚀 Agent Activated", 
        "welcome_desc": "Surveillance active. I will notify you in English.",
        "source_label": "Source", "query_label": "Query"
    },
    "fr": {
        "new": "Nouvel élément", "update": "Mise à jour", "link": "Ouvrir le lien",
        "footer": "via", "welcome_title": "🚀 Agent Activé", 
        "welcome_desc": "Surveillance active. Je vous notifierai en Français.",
        "source_label": "Source", "query_label": "Recherche"
    },
    "es": {
        "new": "Nuevo elemento", "update": "Actualización", "link": "Abrir enlace",
        "footer": "vía", "welcome_title": "🚀 Agente Activado", 
        "welcome_desc": "Vigilancia activa. Le notificaré en Español.",
        "source_label": "Fuente", "query_label": "Búsqueda"
    }
}

# --- JSON File System ---
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
                print(f"[SYSTEM] DB Loaded: {len(db['workflows'])} agents.")
        except: pass

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except: pass

# --- Polyvalent Worker (Discord & Email) ---
async def run_infinite_loop(workflow: dict):
    source_type = workflow.get("source")
    settings = workflow.get("settings", {})
    connector = CONNECTORS.get(source_type)
    
    # Destination Settings
    webhook = settings.get("webhook")
    recipient_email = settings.get("recipient_email")
    lang = settings.get("agent_language", "en") # Default to English
    
    # Get translation dict
    t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

    if not connector:
        print(f"[ERROR] No connector found for: {source_type}")
        return

    print(f"[DAEMON] Start {workflow['name']} (Lang: {lang})")

    while True:
        try:
            token = db["credentials"].get(source_type)
            # Pass language settings to connector (for internal formatting like Notion)
            items = await connector.fetch(settings, token)
            
            batch = []
            changed = False
            
            for item in items:
                if not item["is_ready"]: continue
                key = item["unique_key"]
                cur_ver = item["fingerprint"]
                last_ver = db["item_states"].get(key)

                if last_ver is None or last_ver != cur_ver:
                    item["is_update"] = (last_ver is not None)
                    batch.append(item)
                    db["item_states"][key] = cur_ver
                    changed = True
            
            # --- ACTION 1: DISCORD ---
            if batch and webhook:
                bot_name = settings.get("bot_name", "AutoNexus")
                for v in batch:
                    emoji = "📝" if v["is_update"] else "✅"
                    title_prefix = t["update"] if v["is_update"] else t["new"]
                    
                    embed = {
                        "title": f"{emoji} {title_prefix}: {settings.get('query')}",
                        "description": v['content'],
                        "color": 0xF1C40F if v["is_update"] else 0x3498DB,
                        "fields": [{"name": t["link"], "value": f"[{t['link']}]({v['link']})"}],
                        "footer": {"text": f"{t['footer']} {source_type.capitalize()}"},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    async with httpx.AsyncClient() as client:
                        await client.post(webhook, json={"username": bot_name, "embeds": [embed]})

            # --- ACTION 2: EMAIL ---
            if batch and recipient_email:
                gmail_creds = db["credentials"].get("gmail")
                if gmail_creds:
                    # We pass the language to the Gmail connector
                    await gmail.send_notification(settings, batch, gmail_creds, lang)
                else:
                    print("[DAEMON] Cannot send email: Missing Gmail credentials.")
            
            if changed: save_db()

        except Exception as e:
            print(f"[LOOP ERROR] {e}")
        
        await asyncio.sleep(60)

# --- Lifespan & App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for wf in db["workflows"]:
        if wf.get("status") == "active":
            asyncio.create_task(run_infinite_loop(wf))
    yield
    save_db()

app = FastAPI(title="AutoNexus API", version="15.0.0 - Polyglot AI", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Models ---
class ChatRequest(BaseModel): message: str; history: List[Dict[str, str]]
class CredentialInput(BaseModel): serviceId: str; apiKey: str
class WorkflowConfig(BaseModel): serviceSource: str; serviceDest: str; settings: Dict[str, Any]
class AgentResponse(BaseModel): role: str="agent"; content: str; type: str="text"; formData: Optional[Dict[str, Any]]=None

# --- Logic IA (Polyglot) ---
def analyze_intent_with_llm(user_input: str):
    openai_key = db["credentials"].get("openai")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            
            prompt = """
            You are the AutoNexus Architect.
            
            INSTRUCTIONS:
            1. DETECT the language of the user's input (French, English, Spanish, etc.).
            2. REPLY in the SAME language as the user.
            3. Configure the agent based on the request.
            4. ALWAYS include a field 'agent_language' in the form so the user can choose the notification language (e.g. 'fr', 'en', 'es').
            
            JSON SCHEMA:
            {
                "type": "form", 
                "content": "Reply text in User's Language...",
                "formData": {
                    "serviceSource": "notion" | "twitter",
                    "serviceDest": "discord" | "email",
                    "fields": [
                        {"label": "Translated Label...", "key": "query", "type": "text"},
                        // Add conditionally webhook OR recipient_email
                        {"label": "Email...", "key": "recipient_email", "type": "text"},
                        {"label": "Bot Name...", "key": "bot_name", "type": "text"},
                        
                        // MANDATORY LANGUAGE FIELD
                        {"label": "Notification Language (fr/en)", "key": "agent_language", "type": "text", "placeholder": "fr"}
                    ]
                }
            }
            """
            res = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_input}], 
                response_format={"type": "json_object"}
            )
            ai_resp = json.loads(res.choices[0].message.content)
            if "content" not in ai_resp: ai_resp["content"] = "Config ready."
            return ai_resp
            
        except Exception as e: return {"type": "text", "content": f"AI Error: {e}"}
    
    # Fallback Manual (Default English but hints at AI)
    return {"type": "text", "content": "Please connect OpenAI Key to enable multi-language support and dynamic analysis."}

# --- Welcome Message (Localized) ---
async def send_discord_welcome(workflow: dict):
    settings = workflow.get("settings", {})
    webhook = settings.get("webhook")
    lang = settings.get("agent_language", "en")
    t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    
    if not webhook: return
    
    embed = {
        "title": f"{t['welcome_title']} : {settings.get('bot_name')}",
        "description": t['welcome_desc'],
        "color": 0x57F287,
        "fields": [
            {"name": t['source_label'], "value": workflow['source'], "inline": True}, 
            {"name": t['query_label'], "value": settings.get('query'), "inline": True}
        ],
        "footer": {"text": f"ID: {workflow['id']}"}
    }
    async with httpx.AsyncClient() as client:
        try: await client.post(webhook, json={"username": "AutoNexus", "embeds": [embed]})
        except: pass

# --- Endpoints ---
@app.post("/api/credentials")
async def save_creds(c: CredentialInput):
    db["credentials"][c.serviceId] = c.apiKey
    save_db()
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
    
    if c.settings.get("webhook"):
        bg.add_task(send_discord_welcome, wf)

    asyncio.create_task(run_infinite_loop(wf))
    return {"status": "success", "message": "Agent deployed."}

@app.get("/api/workflows")
async def get_wfs(): return db["workflows"]
@app.get("/api/system/stats")
async def stats(): return {"cpu": "11%", "active_agents": len(db["workflows"])}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)