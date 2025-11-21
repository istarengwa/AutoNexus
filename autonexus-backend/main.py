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
    "en": {"new": "New", "update": "Update", "link": "Link", "footer": "via", "ai_report": "🧠 AI Report"},
    "fr": {"new": "Nouveau", "update": "Mise à jour", "link": "Lien", "footer": "via", "ai_report": "🧠 Rapport IA"}
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
                print(f"[SYSTEM] DB Loaded: {len(db['workflows'])} agents.")
        except: pass

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except: pass

# --- AI PROCESSOR (MAP-REDUCE PATTERN) ---
async def process_data_with_ai(items: list, user_prompt: str, openai_key: str):
    """
    1. Découpe les données (Map).
    2. Extrait les infos brutes de chaque morceau.
    3. Synthétise le tout en une seule réponse finale (Reduce).
    """
    if not items or not user_prompt or not openai_key: return None
    
    # 1. DÉCOUPAGE
    SAFE_CHUNK_SIZE = 15000
    chunks = []
    current_chunk = []
    current_size = 0
    
    for item in items:
        item_text = f"SOURCE: {item['link']}\nCONTENT:\n{item['content']}\n---\n"
        if len(item_text) > SAFE_CHUNK_SIZE: item_text = item_text[:SAFE_CHUNK_SIZE] + "\n[...]\n"
        
        if current_size + len(item_text) > SAFE_CHUNK_SIZE:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0
        
        current_chunk.append(item_text)
        current_size += len(item_text)
        
    if current_chunk: chunks.append(current_chunk)
    
    print(f"[AI] Starting Analysis: {len(chunks)} chunks to process.")
    client = OpenAI(api_key=openai_key)
    
    # 2. EXTRACTION (MAP)
    raw_findings = []
    
    for i, chunk in enumerate(chunks):
        print(f"[AI] Analyzing chunk {i+1}/{len(chunks)}...")
        chunk_text = "\n".join(chunk)
        
        # Prompt technique : "Ne réponds pas à la demande finale, contente-toi d'extraire les infos pertinentes"
        extraction_prompt = f"""
        ROLE: Research Assistant.
        USER GOAL: "{user_prompt}"
        
        YOUR JOB: Analyze the code/data below. Extract ALL raw information, concepts, or candidates that are relevant to the User Goal.
        - Do NOT apply limits (e.g. if user wants 5, but you see 20 valid ones here, list 20).
        - Do NOT format the final output yet. Just bullet points of raw findings.
        - If nothing relevant, return "Nothing".
        
        DATA:
        {chunk_text}
        """
        
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": extraction_prompt}]
            )
            result = res.choices[0].message.content
            if "Nothing" not in result:
                raw_findings.append(f"--- FINDINGS PART {i+1} ---\n{result}")
            
            if i < len(chunks)-1: await asyncio.sleep(1) # Pause anti-429
        except Exception as e:
            print(f"[AI ERROR] Chunk {i+1}: {e}")

    # 3. SYNTHÈSE (REDUCE)
    print(f"[AI] Synthesizing final answer...")
    all_findings_text = "\n".join(raw_findings)
    
    # Si on a trop de notes, on tronque pour la synthèse finale (rare si on extrait bien)
    if len(all_findings_text) > 100000: 
        all_findings_text = all_findings_text[:100000] + "\n...(notes truncated)"

    final_system_prompt = "You are the Final Editor. Generate the final response for the user."
    final_user_prompt = f"""
    USER ORIGINAL REQUEST:
    "{user_prompt}"

    RAW MATERIAL COLLECTED FROM FILES:
    {all_findings_text}

    INSTRUCTIONS:
    1. Read the Raw Material.
    2. Select the BEST items to satisfy the User Request.
    3. STRICTLY respect constraints (e.g. "5 atoms" means exactly 5 in total).
    4. Format the output perfectly.
    """

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": final_user_prompt}
            ]
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"Error generating final summary: {e}"

# --- WORKER ---
async def run_infinite_loop(workflow_id: str):
    w_id = workflow_id if isinstance(workflow_id, str) else workflow_id.get("id")
    print(f"[DAEMON] 🚀 Thread {w_id} started")

    while True:
        try:
            current_wf = next((w for w in db["workflows"] if w["id"] == w_id), None)
            if not current_wf: break
            if current_wf.get("status") != "active":
                await asyncio.sleep(10)
                continue

            settings = current_wf.get("settings", {})
            source = current_wf.get("source")
            
            prompt = settings.get("custom_prompt")
            webhook = settings.get("webhook")
            email = settings.get("recipient_email")
            try: refresh = int(settings.get("refresh_interval", 60))
            except: refresh = 60
            lang = settings.get("agent_language", "en")
            t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

            connector = CONNECTORS.get(source)
            token = db["credentials"].get(source)
            openai_key = db["credentials"].get("openai")

            if not connector or not token:
                await asyncio.sleep(60)
                continue

            items = await connector.fetch(settings, token)
            
            batch = []
            changed = False
            for item in items:
                if not item["is_ready"]: continue
                key = f"{w_id}:{item['unique_key']}"
                last_ver = db["item_states"].get(key)
                cur_ver = item["fingerprint"]
                
                if last_ver is None or last_ver != cur_ver:
                    item["is_update"] = (last_ver is not None)
                    batch.append(item)
                    db["item_states"][key] = cur_ver
                    changed = True
            
            ai_result = ""
            is_ai = False
            if batch and prompt and openai_key:
                print(f"[ACTION] AI Processing {len(batch)} items (Map-Reduce)...")
                ai_result = await process_data_with_ai(batch, prompt, openai_key)
                is_ai = True
            
            if batch:
                if webhook and webhook.startswith("http"):
                    bot_name = settings.get("bot_name", "AutoNexus")
                    if is_ai:
                        parts = [ai_result[i:i+4000] for i in range(0, len(ai_result), 4000)]
                        for p in parts:
                            await httpx.AsyncClient().post(webhook, json={"username": bot_name, "embeds": [{"title": f"{t['ai_report']}", "description": p, "color": 0x9B59B6}]})
                    else:
                        for v in batch:
                            await httpx.AsyncClient().post(webhook, json={"username": bot_name, "embeds": [{"title": v['content'][:100], "description": v['content'][:4000], "color": 0x7289DA}]})

                if email:
                    creds = db["credentials"].get("gmail")
                    if creds:
                        if is_ai:
                            # Envoi du rapport final unique
                            wrapper = [{"content": ai_result, "link": "#", "is_update": False}]
                            await gmail.send_notification(settings, wrapper, creds, lang)
                        else:
                            await gmail.send_notification(settings, batch, creds, lang)

            if changed: save_db()

        except Exception as e: print(f"[LOOP ERROR] {e}")
        
        if refresh <= 0:
            if current_wf: 
                current_wf["status"] = "paused"
                save_db()
            print(f"[DAEMON] Agent {w_id} finished (One-shot).")
            break
        else:
            await asyncio.sleep(refresh)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for wf in db["workflows"]:
        if wf.get("status") == "active": asyncio.create_task(run_infinite_loop(wf["id"]))
    yield
    save_db()

app = FastAPI(title="AutoNexus API", version="38.0.0 - Map Reduce", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel): message: str; history: List[Dict[str, str]]
class CredentialInput(BaseModel): serviceId: str; apiKey: str
class WorkflowConfig(BaseModel): serviceSource: str; serviceDest: str; settings: Dict[str, Any]
class WorkflowUpdate(BaseModel): status: Optional[str] = None; settings: Optional[Dict[str, Any]] = None
class AgentResponse(BaseModel): role: str="agent"; content: str; type: str="text"; formData: Optional[Dict[str, Any]]=None

def analyze_intent_with_llm(user_input: str):
    openai_key = db["credentials"].get("openai")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            prompt = """
            AutoNexus Architect.
            RULES:
            - Source: GitHub, Notion, Discord, Twitter.
            - Destination: Discord OR Email.
            - IF "Atom", "Intuition", "Analysis" -> fill custom_prompt.
            JSON:
            {
                "type": "form", "content": "...",
                "formData": {
                    "serviceSource": "...", "serviceDest": "...",
                    "fields": [
                        {"label": "Target", "key": "query", "type": "text"},
                        {"label": "AI Instructions", "key": "custom_prompt", "type": "textarea"},
                        {"label": "Timer (0=Once)", "key": "refresh_interval", "type": "number"},
                        {"label": "Bot Name", "key": "bot_name", "type": "text"},
                        {"label": "Lang", "key": "agent_language", "type": "text"},
                        {"label": "Email", "key": "recipient_email", "type": "text"},
                        {"label": "Webhook", "key": "webhook", "type": "password"}
                    ]
                }
            }
            """
            res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_input}], response_format={"type": "json_object"})
            return json.loads(res.choices[0].message.content)
        except: pass
    return {"type": "text", "content": "Connect OpenAI."}

@app.post("/api/credentials")
async def save_creds(c: CredentialInput):
    k = c.apiKey.replace(" ", "").strip() if c.serviceId == "gmail" else c.apiKey
    db["credentials"][c.serviceId] = k
    save_db()
    return {"status": "success"}

@app.get("/api/credentials/check/{sid}")
async def check_creds(sid: str): return {"configured": sid in db["credentials"]}
@app.get("/api/workflows")
async def get_wfs(): return db["workflows"]
@app.delete("/api/agent/{aid}")
async def delete_agent(aid: str):
    db["workflows"] = [w for w in db["workflows"] if w["id"] != aid]
    save_db()
    return {"status": "success"}
@app.patch("/api/agent/{aid}")
async def update_agent(aid: str, u: WorkflowUpdate):
    w = next((x for x in db["workflows"] if x["id"] == aid), None)
    if w:
        if u.status: 
            w["status"] = u.status
            if u.status == "active": asyncio.create_task(run_infinite_loop(aid))
        if u.settings: 
            w["settings"].update(u.settings)
            prefix = f"{aid}:"
            keys = [k for k in db["item_states"].keys() if k.startswith(prefix)]
            for k in keys: del db["item_states"][k]
            print(f"[SYSTEM] Agent {aid} reset. Relaunching...")
            asyncio.create_task(run_infinite_loop(aid))
        save_db()
    return {"status": "success"}
@app.post("/api/agent/chat", response_model=AgentResponse)
async def chat(r: ChatRequest): return analyze_intent_with_llm(r.message)
@app.post("/api/agent/deploy")
async def deploy(c: WorkflowConfig, bg: BackgroundTasks):
    wf = {"id": str(uuid.uuid4())[:8], "name": c.settings.get("bot_name"), "source": c.serviceSource.lower(), "settings": c.settings, "status": "active"}
    db["workflows"].append(wf)
    save_db()
    asyncio.create_task(run_infinite_loop(wf["id"]))
    return {"status": "success", "message": f"Agent deployed!"}
@app.get("/api/system/stats")
async def stats(): return {"cpu": "12%", "active_agents": len(db["workflows"])}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)