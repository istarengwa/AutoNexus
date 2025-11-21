import httpx
from datetime import datetime, timedelta, timezone

async def fetch(settings: dict, token: str):
    channel_id = settings.get("channel_id")
    query = settings.get("query", "").strip().lower()
    
    if not token or not channel_id: 
        return []
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    
    params = {"limit": 50}
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, params=params)
            
            if res.status_code == 403:
                print(f"[DISCORD ERROR] Error 403: Bot lacks access to this channel. Verify it's invited to the server.")
                return []
            if res.status_code != 200:
                print(f"[DISCORD API ERROR] {res.status_code} - {res.text}")
                return []
            
            messages = res.json()
            results = []
            now = datetime.now(timezone.utc)
            
            for msg in messages:
                if msg.get("author", {}).get("bot"):
                    continue
                
                content = msg.get("content", "")
                
                if query and query not in content.lower():
                    continue
                
                msg_date_str = msg["timestamp"]
                msg_date = datetime.fromisoformat(msg_date_str)
                
                link = f"https://discord.com/channels/@me/{channel_id}/{msg['id']}"
                
                author = msg.get("author", {}).get("username", "Unknown")
                
                results.append({
                    "unique_key": f"discord:{msg['id']}",
                    "fingerprint": msg_date_str,
                    "content": f"💬 **{author} said:**\n{content}",
                    "link": link,
                    "is_ready": True,
                    "is_update": False 
                })
                
            return results

    except Exception as e:
        print(f"[DISCORD READ ERROR] {e}")
        return []