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

# --- IMPORTS DES CONNECTEURS ---
from connectors import twitter, notion

CONNECTORS = {
    "twitter": twitter,
    "notion": notion
}

# --- Système de Fichier JSON ---
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
                print(f"[SYSTEM] DB Chargée: {len(db['workflows'])} agents.")
        except: pass

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except: pass

# --- Worker Générique ---
async def run_infinite_loop(workflow: dict, webhook: str):
    source_type = workflow.get("source")
    settings = workflow.get("settings", {})
    connector = CONNECTORS.get(source_type)
    
    if not connector:
        print(f"[ERROR] Pas de connecteur trouvé pour : {source_type}")
        return

    print(f"[DAEMON] Start {workflow['name']} via module {source_type}")

    while True:
        try:
            token = db["credentials"].get(source_type)
            items = await connector.fetch(settings, token)
            
            batch = []
            changed = False
            
            for item in items:
                if not item["is_ready"]: continue
                
                key = item["unique_key"]
                cur_ver = item["fingerprint"]
                last_ver = db["item_states"].get(key)

                if last_ver is None:
                    item["is_update"] = False
                    batch.append(item)
                    db["item_states"][key] = cur_ver
                    changed = True
                elif last_ver != cur_ver:
                    item["is_update"] = True
                    batch.append(item)
                    db["item_states"][key] = cur_ver
                    changed = True
            
            if batch and webhook:
                bot_name = settings.get("bot_name", "AutoNexus Agent")
                for v in batch:
                    emoji = "📝" if v["is_update"] else "✅"
                    title = "Mise à jour" if v["is_update"] else "Nouveau"
                    embed = {
                        "title": f"{emoji} {title} : {settings.get('query')}",
                        "description": v['content'],
                        "color": 0xF1C40F if v["is_update"] else 0x3498DB,
                        "fields": [{"name": "Lien", "value": f"[Ouvrir]({v['link']})"}],
                        "footer": {"text": f"via {source_type.capitalize()}"},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    async with httpx.AsyncClient() as client:
                        await client.post(webhook, json={"username": bot_name, "embeds": [embed]})
            
            if changed: save_db()

        except Exception as e:
            print(f"[LOOP ERROR {source_type}] {e}")
        
        await asyncio.sleep(60)

# --- Lifespan & App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for wf in db["workflows"]:
        if wf.get("status") == "active":
            webhook = wf.get("settings", {}).get("webhook")
            if webhook: asyncio.create_task(run_infinite_loop(wf, webhook))
    yield
    save_db()

app = FastAPI(title="AutoNexus API", version="12.1.0 - Fixed AI Schema", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Models ---
class ChatRequest(BaseModel): message: str; history: List[Dict[str, str]]
class CredentialInput(BaseModel): serviceId: str; apiKey: str
class WorkflowConfig(BaseModel): serviceSource: str; serviceDest: str; settings: Dict[str, Any]
class AgentResponse(BaseModel): role: str="agent"; content: str; type: str="text"; formData: Optional[Dict[str, Any]]=None

# --- Logic IA (CORRIGÉE ET RENFORCÉE) ---
def analyze_intent_with_llm(user_input: str):
    openai_key = db["credentials"].get("openai")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            
            # Le prompt est maintenant beaucoup plus strict sur la structure de retour
            prompt = """
            Tu es l'architecte AutoNexus. Tu dois configurer un agent de surveillance.
            
            TES INSTRUCTIONS :
            1. Analyse la demande (ex: "Surveille Notion pour 'Projet A'").
            2. Retourne UNIQUEMENT un objet JSON respectant STRICTEMENT ce schéma.
            
            SCHEMA JSON OBLIGATOIRE :
            {
                "type": "form",
                "content": "Texte court expliquant ce que tu as compris...",
                "formData": {
                    "serviceSource": "notion" OU "twitter",
                    "serviceDest": "discord",
                    "fields": [
                        {"label": "Mot-clé / Query", "key": "query", "type": "text", "placeholder": "Ex: ..."},
                        {"label": "Webhook Discord", "key": "webhook", "type": "password", "placeholder": "https://..."},
                        {"label": "Nom du Bot", "key": "bot_name", "type": "text", "placeholder": "Nom"}
                    ]
                }
            }
            
            IMPORTANT: 
            - La clé "content" est OBLIGATOIRE (sinon ça plante).
            - La clé "type" doit être "form" si tu as détecté une intention, sinon "text".
            """
            
            res = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_input}], 
                response_format={"type": "json_object"}
            )
            
            ai_response = json.loads(res.choices[0].message.content)
            
            # --- SÉCURITÉ ANTI-CRASH ---
            # Si l'IA a oublié le champ content, on le force
            if "content" not in ai_response:
                ai_response["content"] = "Configuration prête (Contenu généré automatiquement)."
            if "role" not in ai_response:
                ai_response["role"] = "agent"
                
            return ai_response
            
        except Exception as e: 
            print(f"[AI ERROR] {e}")
            # En cas d'erreur, on ne plante pas, on renvoie une réponse texte
            return {"type": "text", "content": f"Désolé, mon cerveau IA a eu un hoquet : {e}. Réessayez."}
    
    # Fallback Manuel
    u = user_input.lower()
    if "notion" in u or "doc" in u:
        return {"type": "form", "content": "Config Notion (Mode Manuel).", "formData": {"serviceSource": "notion", "serviceDest": "discord", "fields": [{"label": "Mot-clé", "key": "query", "type": "text"}, {"label": "Webhook", "key": "webhook", "type": "password"}, {"label": "Nom Bot", "key": "bot_name", "type": "text"}]}}
    if "twitter" in u or "x" in u:
        return {"type": "form", "content": "Config Twitter (Mode Manuel).", "formData": {"serviceSource": "twitter", "serviceDest": "discord", "fields": [{"label": "Recherche", "key": "query", "type": "text"}, {"label": "Webhook", "key": "webhook", "type": "password"}, {"label": "Nom Bot", "key": "bot_name", "type": "text"}]}}
    
    return {"type": "text", "content": "Je peux connecter Notion et Twitter. Dites par exemple 'Surveille mes docs Notion'."}

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
    
    # Welcome Message
    wh = c.settings.get("webhook")
    if wh:
        asyncio.create_task(run_infinite_loop(wf, wh))
        async with httpx.AsyncClient() as cl:
            try: await cl.post(wh, json={"username": "AutoNexus", "embeds": [{"title": "🚀 Agent Activé", "description": f"Source: {c.serviceSource} | Query: {c.settings.get('query')}", "color": 0x57F287}]})
            except: pass
            
    return {"status": "success", "message": "Agent déployé."}

@app.get("/api/workflows")
async def get_wfs(): return db["workflows"]
@app.get("/api/system/stats")
async def stats(): return {"cpu": "10%", "active_agents": len(db["workflows"])}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)