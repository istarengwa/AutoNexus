import httpx
from datetime import datetime, timezone

async def fetch(settings: dict, token: str):
    """
    Récupère les tweets récents.
    Args:
        settings: dict contenant la 'query'
        token: Le Bearer Token Twitter
    """
    query = settings.get("query")
    if not token or not query:
        return []
    
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {"query": query, "max_results": 10}
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, params=params, headers=headers)
            
            if res.status_code != 200:
                print(f"[TWITTER API ERROR] {res.text}")
                return []
            
            data = res.json()
            results = []
            
            if "data" in data:
                for t in data["data"]:
                    results.append({
                        "unique_key": f"twitter:{t['id']}", 
                        "fingerprint": t.get("created_at", ""), 
                        "content": t["text"],
                        "link": f"https://twitter.com/user/status/{t['id']}",
                        "is_ready": True
                    })
            return results
    except Exception as e:
        print(f"[TWITTER ERROR] {e}")
        return []