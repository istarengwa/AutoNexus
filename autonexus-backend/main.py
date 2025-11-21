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
import time
from datetime import datetime, timezone
from openai import OpenAI 

# --- IMPORT CONNECTORS ---
from connectors import twitter, notion, gmail, discord, github

CONNECTORS = {
    "twitter": twitter,
    "notion": notion,
    "discord": discord,
    "github": github
}

# --- TRANSLATIONS ---
TRANSLATIONS = {
    "en": {
        "new": "New Item", "update": "Update", "link": "Open Link",
        "footer": "via", "ai_report": "🧠 AI Intelligence Report"
    },
    "fr": {
        "new": "Nouveau", "update": "Mise à jour", "link": "Voir",
        "footer": "via", "ai_report": "🧠 Rapport Intelligence IA"
    }
}

# --- DB & HELPERS ---
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

# --- AI PROCESSOR (SMART BATCHING) ---
async def process_data_with_ai(items: list, prompt: str, openai_key: str):
    """
    Découpe les données en morceaux digestes pour respecter le Rate Limit (TPM).
    """
    if not items or not prompt or not openai_key: return None
    
    # 1. Préparation des chunks (morceaux)
    # On vise environ 10 000 caractères par chunk (~2500 tokens) pour rester safe sous les 30k TPM
    # tout en gardant de la place pour la réponse.
    CHUNK_SIZE_LIMIT = 10000 
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    for item in items:
        # On formatte l'item
        item_str = f"--- ITEM {item['fingerprint']} ---\nLINK: {item['link']}\nCONTENT:\n{item['content']}\n"
        item_len = len(item_str)
        
        # Si l'item seul est plus gros que la limite, on le tronque
        if item_len > CHUNK_SIZE_LIMIT:
            item_str = item_str[:CHUNK_SIZE_LIMIT] + "\n...(truncated to fit AI limit)"
            item_len = CHUNK_SIZE_LIMIT

        # Si on dépasse la limite du chunk actuel, on ferme le paquet et on en ouvre un nouveau
        if current_size + item_len > CHUNK_SIZE_LIMIT:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0
        
        current_chunk.append(item_str)
        current_size += item_len
        
    if current_chunk:
        chunks.append(current_chunk)

    print(f"[AI BATCH] Data split into {len(chunks)} batches to respect OpenAI Rate Limits.")

    # 2. Traitement séquentiel
    client = OpenAI(api_key=openai_key)
    aggregated_response = ""

    for i, chunk in enumerate(chunks):
        print(f"[AI BATCH] Processing batch {i+1}/{len(chunks)}...")
        
        chunk_text = "\n".join(chunk)
        
        full_system_prompt = "You are a data processing engine. Extract and format the requested data (e.g. Atoms) from the input chunk."
        full_user_prompt = f"{prompt}\n\nINPUT CHUNK {i+1}/{len(chunks)}:\n{chunk_text}"

        try:
            # On utilise GPT-4o
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": full_system_prompt}, {"role": "user", "content": full_user_prompt}]
            )
            result = res.choices[0].message.content
            aggregated_response += f"\n\n--- BATCH {i+1} RESULTS ---\n{result}"
            
            # Pause de sécurité entre les requêtes pour laisser le quota "refroidir"
            if i < len(chunks) - 1:
                await asyncio.sleep(2) 

        except Exception as e:
            print(f"[AI BATCH ERROR] Batch {i+1} failed: {e}")
            aggregated_response += f"\n[Error on batch {i+1}: {str(e)}]"

    return aggregated_response

# --- WORKER ---
async def run_infinite_loop(workflow: dict):
    source_type = workflow.get("source")
    settings = workflow.get("settings", {})
    connector = CONNECTORS.get(source_type)
    
    webhook = settings.get("webhook")
    recipient_email = settings.get("recipient_email")
    lang = settings.get("agent_language", "en")
    custom_prompt = settings.get("custom_prompt")
    
    t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

    if not connector: return

    print(f"[DAEMON] ✅ Agent '{workflow['name']}' STARTED")

    while True:
        try:
            token = db["credentials"].get(source_type)
            openai_key = db["credentials"].get("openai")
            
            if not token:
                await asyncio.sleep(60)
                continue

            items = await connector.fetch(settings, token)
            
            batch = []
            changed = False
            
            for item in items:
                if not item["is_ready"]: continue
                key = item["unique_key"]
                raw_key = item["unique_key"]
                isolated_key = f"{workflow['id']}:{raw_key}"
                
                cur_ver = item["fingerprint"]
                last_ver = db["item_states"].get(isolated_key)

                if last_ver is None or (source_type == 'notion' and last_ver != cur_ver):
                    item["is_update"] = (last_ver is not None)
                    batch.append(item)
                    db["item_states"][isolated_key] = cur_ver
                    changed = True
            
            # --- AI LAYER ---
            final_message = ""
            is_ai_generated = False

            if batch and custom_prompt and openai_key:
                print(f"[ACTION] 🧠 AI Processing for {len(batch)} items (Smart Batching)...")
                # L'appel AI est maintenant intelligent et découpé
                final_message = await process_data_with_ai(batch, custom_prompt, openai_key)
                is_ai_generated = True
            
            # --- DELIVERY ---
            if batch:
                # DISCORD
                if webhook and webhook.startswith("http"):
                    bot_name = settings.get("bot_name", "AutoNexus")
                    
                    if is_ai_generated:
                        # Découpage pour Discord (max 4096 chars par embed)
                        chunks = [final_message[i:i+4000] for i in range(0, len(final_message), 4000)]
                        for i, chunk in enumerate(chunks):
                            embed = {
                                "title": f"{t['ai_report']} ({i+1}/{len(chunks)})",
                                "description": chunk,
                                "color": 0x9B59B6,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                            async with httpx.AsyncClient() as client:
                                await client.post(webhook, json={"username": bot_name, "embeds": [embed]})
                                await asyncio.sleep(1) # Anti-flood Discord
                    else:
                        # Raw items
                        for v in batch:
                            embed = {
                                "title": f"🔔 {t['new']}: {settings.get('query')}",
                                "description": v['content'][:4000], 
                                "color": 0x7289DA,
                                "fields": [{"name": t["link"], "value": f"[Link]({v['link']})"}],
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                            async with httpx.AsyncClient() as client:
                                await client.post(webhook, json={"username": bot_name, "embeds": [embed]})

                # EMAIL
                if recipient_email:
                    gmail_creds = db["credentials"].get("gmail")
                    if gmail_creds:
                        if is_ai_generated:
                            # On envoie le rapport complet compilé
                            wrapper = [{"content": final_message, "link": "#", "is_update": False}]
                            await gmail.send_notification(settings, wrapper, gmail_creds, lang)
                        else:
                            await gmail.send_notification(settings, batch, gmail_creds, lang)
            
            if changed: save_db()

        except Exception as e:
            print(f"[LOOP ERROR] {e}")
        
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for wf in db["workflows"]:
        if wf.get("status") == "active":
            asyncio.create_task(run_infinite_loop(wf))
    yield
    save_db()

app = FastAPI(title="AutoNexus API", version="30.0.0 - Rate Limit Fix", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel): message: str; history: List[Dict[str, str]]
class CredentialInput(BaseModel): serviceId: str; apiKey: str
class WorkflowConfig(BaseModel): serviceSource: str; serviceDest: str; settings: Dict[str, Any]
class WorkflowUpdate(BaseModel): status: Optional[str] = None; settings: Optional[Dict[str, Any]] = None
class AgentResponse(BaseModel): role: str="agent"; content: str; type: str="text"; formData: Optional[Dict[str, Any]]=None

# --- STRICT ARCHITECT LOGIC ---
def analyze_intent_with_llm(user_input: str):
    openai_key = db["credentials"].get("openai")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            prompt = """
            You are the AutoNexus Architect.
            
            TASK 1: DETECT SOURCE & DESTINATION
            - Source: GitHub, Notion, Discord, Twitter.
            - Destination: Discord OR Email.
            
            TASK 2: GENERATE FORM SCHEMA (STRICT FIELDS)
            
            IF DESTINATION IS DISCORD:
               - Include field: "webhook" (type: password).
               - DO NOT include "recipient_email".
            
            IF DESTINATION IS EMAIL:
               - Include field: "recipient_email" (type: text).
               - DO NOT include "webhook".

            IF USER ASKS FOR ANALYSIS/ATOMS/SUMMARY:
               - Fill 'custom_prompt' with specific instructions.

            JSON OUTPUT:
            {
                "type": "form", 
                "content": "Reply in user language...",
                "formData": {
                    "serviceSource": "...", "serviceDest": "...",
                    "fields": [
                        {"label": "Target (Query/Repo/ID)", "key": "query", "type": "text"},
                        {"label": "AI Instructions", "key": "custom_prompt", "type": "textarea"},
                        {"label": "Bot Name", "key": "bot_name", "type": "text"},
                        {"label": "Lang", "key": "agent_language", "type": "text"}
                    ]
                }
            }
            """
            res = client.chat.completions.create(
                model="gpt-4o", 
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_input}], 
                response_format={"type": "json_object"}
            )
            return json.loads(res.choices[0].message.content)
        except: pass
    
    return {"type": "text", "content": "Please connect OpenAI Key."}

# --- ENDPOINTS ---
@app.post("/api/credentials")
async def save_creds(c: CredentialInput):
    key = c.apiKey.replace(" ", "").strip() if c.serviceId == "gmail" else c.apiKey
    db["credentials"][c.serviceId] = key
    save_db()
    return {"status": "success"}

@app.get("/api/credentials/check/{sid}")
async def check_creds(sid: str): return {"configured": sid in db["credentials"]}

@app.get("/api/workflows")
async def get_wfs(): return db["workflows"]

@app.delete("/api/agent/{agent_id}")
async def delete_agent(agent_id: str):
    db["workflows"] = [w for w in db["workflows"] if w["id"] != agent_id]
    save_db()
    return {"status": "success"}

@app.patch("/api/agent/{agent_id}")
async def update_agent(agent_id: str, update: WorkflowUpdate):
    wf = next((w for w in db["workflows"] if w["id"] == agent_id), None)
    if wf:
        if update.status: 
            wf["status"] = update.status
        
        if update.settings: 
            wf["settings"].update(update.settings)
            
            # RESET MEMORY on Edit
            prefix = f"{agent_id}:"
            keys_to_delete = [k for k in db["item_states"].keys() if k.startswith(prefix)]
            for k in keys_to_delete:
                del db["item_states"][k]
            
            print(f"[SYSTEM] Agent {agent_id} updated & memory cleared ({len(keys_to_delete)} items forgotten). Rescanning...")

        save_db()
    return {"status": "success"}

@app.post("/api/agent/chat", response_model=AgentResponse)
async def chat(r: ChatRequest): return analyze_intent_with_llm(r.message)

@app.post("/api/agent/deploy")
async def deploy(c: WorkflowConfig, bg: BackgroundTasks):
    wf = {
        "id": str(uuid.uuid4())[:8], "name": c.settings.get("bot_name", "Agent"), 
        "source": c.serviceSource.lower(), "settings": c.settings, "status": "active"
    }
    db["workflows"].append(wf)
    save_db()
    asyncio.create_task(run_infinite_loop(wf))
    return {"status": "success", "message": f"Agent '{c.settings.get('bot_name')}' deployed successfully!"}

@app.get("/api/system/stats")
async def stats(): return {"cpu": "12%", "active_agents": len(db["workflows"])}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)