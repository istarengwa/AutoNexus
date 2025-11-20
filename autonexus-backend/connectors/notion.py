import httpx
import asyncio
from datetime import datetime, timedelta, timezone

# Snippets translation
SNIPPETS = {
    "en": {"title_found": "📍 Found in Title"},
    "fr": {"title_found": "📍 Trouvé dans le titre"},
    "es": {"title_found": "📍 Encontrado en el título"}
}

async def get_page_content(page_id: str, token: str) -> str:
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, params={"page_size": 100})
            if res.status_code != 200: return ""
            data = res.json()
            text_content = []
            text_blocks = ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "to_do", "toggle", "quote", "callout"]
            for block in data.get("results", []):
                b_type = block.get("type")
                if b_type in text_blocks:
                    rich_text = block.get(b_type, {}).get("rich_text", [])
                    for rt in rich_text: text_content.append(rt.get("plain_text", ""))
            return " ".join(text_content)
    except: return ""

async def fetch(settings: dict, token: str):
    query = settings.get("query", "").strip().lower()
    lang = settings.get("agent_language", "en")
    t = SNIPPETS.get(lang, SNIPPETS["en"])

    if not token or not query: return []
    
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    payload = {"page_size": 50, "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.notion.com/v1/search", json=payload, headers=headers)
            if res.status_code != 200: return []
            data = res.json()
            results = []
            now = datetime.now(timezone.utc)
            
            for item in data.get("results", []):
                page_id = item["id"]
                title = "Untitled"
                if item["object"] == "page" and "properties" in item:
                    for prop in item["properties"].values():
                        if prop["id"] == "title" and prop["title"]: title = prop["title"][0]["plain_text"]
                elif item["object"] == "database" and "title" in item:
                    if item["title"]: title = item["title"][0]["plain_text"]
                
                match_found = False
                snippet = ""
                
                if query in title.lower():
                    match_found = True
                    snippet = t["title_found"]
                else:
                    content = await get_page_content(page_id, token)
                    if query in content.lower():
                        match_found = True
                        idx = content.lower().find(query)
                        start = max(0, idx - 30)
                        end = min(len(content), idx + 60)
                        snippet = f"...{content[start:end]}..."
                
                if not match_found: continue

                last_edited = datetime.fromisoformat(item["last_edited_time"].replace('Z', '+00:00'))
                is_stable = (now - last_edited) > timedelta(seconds=60)
                
                results.append({
                    "unique_key": f"notion:{page_id}", 
                    "fingerprint": item["last_edited_time"], 
                    "content": f"📄 **{title}**\n🔎 *{snippet}*",
                    "link": item.get("url"),
                    "is_ready": is_stable,
                    "is_update": False 
                })
                await asyncio.sleep(0.1)

            return results
    except: return []