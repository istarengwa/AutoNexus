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
        except Exception as e:
            print(f"[SYSTEM] ❌ Error reading DB: {e}")

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[SYSTEM] ❌ Error saving DB: {e}")

# --- Worker Intelligent (Cycle de vie géré) ---
async def run_infinite_loop(agent_id: str):
    """
    Boucle qui surveille un agent par son ID.
    Vérifie la DB à chaque itération pour voir si l'agent a été mis en pause, modifié ou supprimé.
    """
    print(f"[DAEMON] Thread started for Agent ID: {agent_id}")

    while True:
        # 1. Récupération "Fraîche" de l'agent depuis la DB
        # On cherche l'agent dans la liste en mémoire
        workflow = next((w for w in db["workflows"] if w["id"] == agent_id), None)

        # CAS 1 : Agent supprimé (n'existe plus dans la DB)
        if not workflow:
            print(f"[DAEMON] 🛑 Agent {agent_id} not found (Deleted). Stopping thread.")
            break
        
        # CAS 2 : Agent en pause
        if workflow.get("status") != "active":
            # On attend un peu et on réessaye (mode veille)
            await asyncio.sleep(10)
            continue

        # --- DÉBUT DU SCAN ---
        try:
            source_type = workflow.get("source")
            settings = workflow.get("settings", {})
            connector = CONNECTORS.get(source_type)
            
            webhook = settings.get("webhook")
            recipient_email = settings.get("recipient_email")
            lang = settings.get("agent_language", "en")
            t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

            if not connector:
                print(f"[ERROR] No connector for: {source_type}")
                await asyncio.sleep(60)
                continue

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
                
                # Clé unique isolée par agent
                raw_key = item["unique_key"]
                isolated_key = f"{agent_id}:{raw_key}"
                
                cur_ver = item["fingerprint"]
                last_ver = db["item_states"].get(isolated_key)

                if last_ver is None: 
                    item["is_update"] = False
                    batch.append(item)
                    db["item_states"][isolated_key] = cur_ver
                    changed = True
                elif last_ver != cur_ver:
                    item["is_update"] = True # Notion update detection
                    # Pour Discord/Twitter qui sont des flux, souvent on ignore les updates, mais gardons la logique
                    batch.append(item)
                    db["item_states"][isolated_key] = cur_ver
                    changed = True
            
            # Actions
            if batch and webhook:
                bot_name = settings.get("bot_name", "AutoNexus")
                print(f"[ACTION] 💬 Sending Discord for '{workflow['name']}'")
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

            if batch and recipient_email:
                gmail_creds = db["credentials"].get("gmail")
                if gmail_creds:
                    print(f"[ACTION] 📧 Sending Email for '{workflow['name']}'")
                    await gmail.send_notification(settings, batch, gmail_creds, lang)
            
            if changed: save_db()

        except Exception as e:
            print(f"[LOOP ERROR] Agent {agent_id}: {e}")
        
        # Attente avant prochain scan
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- STARTING AUTONEXUS ---")
    load_db()
    active_count = 0
    for wf in db["workflows"]:
        # On lance TOUS les agents, même en pause (la boucle gérera la pause)
        # pour permettre le "Resume" sans redémarrer le serveur
        asyncio.create_task(run_infinite_loop(wf["id"]))
        active_count += 1
    print(f"[SYSTEM] {active_count} agents loaded.")
    yield
    print("--- STOPPING AUTONEXUS ---")
    save_db()

app = FastAPI(title="AutoNexus API", version="19.0.0 - CRUD Actions", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Models ---
class ChatRequest(BaseModel): message: str; history: List[Dict[str, str]]
class CredentialInput(BaseModel): serviceId: str; apiKey: str
class WorkflowConfig(BaseModel): serviceSource: str; serviceDest: str; settings: Dict[str, Any]
class WorkflowUpdate(BaseModel): status: Optional[str] = None; settings: Optional[Dict[str, Any]] = None
class AgentResponse(BaseModel): role: str="agent"; content: str; type: str="text"; formData: Optional[Dict[str, Any]]=None

# --- IA Logic ---
def analyze_intent_with_llm(user_input: str):
    openai_key = db["credentials"].get("openai")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            prompt = """
            AutoNexus Architect.
            RULES:
            - Discord Reader -> source="discord", dest="email"|"discord". Required: 'channel_id', 'query'.
            - Notion Reader -> source="notion".
            - Twitter Reader -> source="twitter".
            JSON SCHEMA:
            {
                "type": "form", "content": "Explanation...",
                "formData": {
                    "serviceSource": "notion" | "twitter" | "discord",
                    "serviceDest": "discord" | "email",
                    "fields": [
                        {"label": "Query/Keyword", "key": "query", "type": "text"},
                        {"label": "Channel ID", "key": "channel_id", "type": "text"},
                        {"label": "Email", "key": "recipient_email", "type": "text"},
                        {"label": "Bot Name", "key": "bot_name", "type": "text"},
                        {"label": "Language (fr/en)", "key": "agent_language", "type": "text", "placeholder": "fr"}
                    ]
                }
            }
            """
            res = client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_input}], response_format={"type": "json_object"}
            )
            return json.loads(res.choices[0].message.content)
        except: pass
    
    u = user_input.lower()
    if "salon" in u or "channel" in u or "discord" in u:
        return {"type": "form", "content": "Manual Discord Config.", "formData": {"serviceSource": "discord", "serviceDest": "email", "fields": [{"label": "Channel ID", "key": "channel_id", "type": "text"}, {"label": "Keyword", "key": "query", "type": "text"}, {"label": "Email", "key": "recipient_email", "type": "text"}, {"label": "Language", "key": "agent_language", "type": "text"}]}}
    return {"type": "text", "content": "I can read Discord, Notion, or Twitter."}

# --- Endpoints CRUD ---

@app.get("/api/workflows")
async def get_wfs(): return db["workflows"]

@app.delete("/api/agent/{agent_id}")
async def delete_agent(agent_id: str):
    # On filtre la liste pour retirer l'agent
    original_len = len(db["workflows"])
    db["workflows"] = [w for w in db["workflows"] if w["id"] != agent_id]
    
    if len(db["workflows"]) < original_len:
        save_db()
        print(f"[SYSTEM] Agent {agent_id} deleted.")
        return {"status": "success", "message": "Agent deleted"}
    raise HTTPException(status_code=404, detail="Agent not found")

@app.patch("/api/agent/{agent_id}")
async def update_agent(agent_id: str, update: WorkflowUpdate):
    workflow = next((w for w in db["workflows"] if w["id"] == agent_id), None)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if update.status:
        workflow["status"] = update.status
        print(f"[SYSTEM] Agent {agent_id} status changed to {update.status}")
    
    if update.settings:
        # Fusion des settings (on garde les anciens si pas écrasés)
        workflow["settings"].update(update.settings)
        # On met aussi à jour le nom racine pour l'affichage
        if "bot_name" in update.settings:
            workflow["name"] = update.settings["bot_name"]
        print(f"[SYSTEM] Agent {agent_id} settings updated")

    save_db()
    return {"status": "success", "workflow": workflow}

@app.post("/api/credentials")
async def save_creds(c: CredentialInput):
    key = c.apiKey.replace(" ", "").strip() if c.serviceId == "gmail" else c.apiKey
    db["credentials"][c.serviceId] = key
    save_db()
    return {"status": "success"}

@app.get("/api/credentials/check/{sid}")
async def check_creds(sid: str): return {"configured": sid in db["credentials"]}

@app.post("/api/agent/chat", response_model=AgentResponse)
async def chat(r: ChatRequest): return analyze_intent_with_llm(r.message)

@app.post("/api/agent/deploy")
async def deploy(c: WorkflowConfig, bg: BackgroundTasks):
    wf_id = str(uuid.uuid4())[:8]
    wf = {
        "id": wf_id, "name": c.settings.get("bot_name", "Agent"), 
        "source": c.serviceSource, "settings": c.settings, "status": "active"
    }
    db["workflows"].append(wf)
    save_db()
    # On lance le thread avec l'ID
    asyncio.create_task(run_infinite_loop(wf_id))
    return {"status": "success", "message": "Agent deployed and active."}

@app.get("/api/system/stats")
async def stats(): return {"cpu": "12%", "active_agents": len([w for w in db["workflows"] if w["status"] == "active"])}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)