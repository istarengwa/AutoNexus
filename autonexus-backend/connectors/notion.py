import httpx
import asyncio
from datetime import datetime, timedelta, timezone

async def get_page_content(page_id: str, token: str) -> str:
    """
    Récupère le contenu texte d'une page.
    Supporte plus de types de blocs pour ne rien rater.
    """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"}
    
    try:
        async with httpx.AsyncClient() as client:
            # On récupère jusqu'à 100 blocs (paragraphes) par page
            res = await client.get(url, headers=headers, params={"page_size": 100})
            if res.status_code != 200: return ""
            
            data = res.json()
            text_content = []
            
            # Liste des types de blocs contenant du texte riche
            text_blocks = [
                "paragraph", "heading_1", "heading_2", "heading_3", 
                "bulleted_list_item", "numbered_list_item", "to_do", 
                "toggle", "quote", "callout"
            ]
            
            for block in data.get("results", []):
                b_type = block.get("type")
                if b_type in text_blocks:
                    # Extraction du texte brut
                    rich_text = block.get(b_type, {}).get("rich_text", [])
                    for rt in rich_text:
                        text_content.append(rt.get("plain_text", ""))
            
            return " ".join(text_content)
    except Exception as e:
        print(f"[NOTION READ ERROR] Page {page_id}: {e}")
        return ""

async def fetch(settings: dict, token: str):
    """
    Scan Notion Profond (Titre + Contenu)
    Scan les 50 dernières pages modifiées.
    """
    query = settings.get("query", "").strip().lower()
    if not token or not query: return []
    
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    
    # AUGMENTATION DE LA PROFONDEUR DE RECHERCHE (10 -> 50)
    payload = {
        "page_size": 50, 
        "sort": {"direction": "descending", "timestamp": "last_edited_time"}
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. Récupérer les dernières pages modifiées (Globalement)
            res = await client.post("https://api.notion.com/v1/search", json=payload, headers=headers)
            
            if res.status_code != 200:
                print(f"[NOTION API ERROR] {res.status_code} - {res.text}")
                return []
            
            data = res.json()
            results = []
            now = datetime.now(timezone.utc)
            
            # 2. Analyse Profonde
            for item in data.get("results", []):
                page_id = item["id"]
                
                # Extraction Titre
                title = "Document sans titre"
                if item["object"] == "page" and "properties" in item:
                    for prop in item["properties"].values():
                        if prop["id"] == "title" and prop["title"]: 
                            title = prop["title"][0]["plain_text"]
                elif item["object"] == "database" and "title" in item:
                    if item["title"]: title = item["title"][0]["plain_text"]
                
                # --- LOGIQUE DE RECHERCHE ---
                match_found = False
                snippet = ""
                
                # A. Check Titre (Rapide)
                if query in title.lower():
                    match_found = True
                    snippet = "📍 Trouvé dans le titre"
                else:
                    # B. Check Contenu (Lent mais nécessaire)
                    # On ne le fait que si le titre ne match pas
                    content = await get_page_content(page_id, token)
                    if query in content.lower():
                        match_found = True
                        # Création d'un extrait de texte autour du mot clé
                        idx = content.lower().find(query)
                        start = max(0, idx - 30)
                        end = min(len(content), idx + 60)
                        snippet = f"...{content[start:end]}..."
                
                if not match_found: continue

                # --- FILTRE DE STABILITÉ (Debounce) ---
                # On ignore les pages modifiées il y a moins de 1 minute (édition en cours)
                last_edited_str = item["last_edited_time"]
                last_edited = datetime.fromisoformat(last_edited_str.replace('Z', '+00:00'))
                
                # Si la page a été modifiée il y a moins de 60 secondes, on considère qu'elle n'est pas prête
                is_stable = (now - last_edited) > timedelta(seconds=60)
                
                results.append({
                    "unique_key": f"notion:{page_id}", 
                    "fingerprint": last_edited_str, # C'est la date qui sert de versioning
                    "content": f"📄 **{title}**\n🔎 *{snippet}*",
                    "link": item.get("url"),
                    "is_ready": is_stable,
                    "is_update": False 
                })
                
                # Petite pause pour éviter le rate-limit si on scanne beaucoup de contenu
                await asyncio.sleep(0.1)

            return results
            
    except Exception as e:
        print(f"[NOTION GLOBAL ERROR] {e}")
        return []