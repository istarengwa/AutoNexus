import httpx
import asyncio
from datetime import datetime, timezone

async def fetch(settings: dict, token: str):
    """
    Récupère les commits (Mode Max Capacity).
    """
    raw_query = settings.get("query", "").strip()
    
    # Mode Deep Code automatique si prompt IA présent
    if settings.get("custom_prompt"):
        mode = "deep_code"
    else:
        mode = "commits_only"

    if not token or not raw_query: return []
    
    repo_name = raw_query.replace("https://github.com/", "").replace("http://github.com/", "")
    if repo_name.endswith("/"): repo_name = repo_name[:-1]
    
    base_url = f"https://api.github.com/repos/{repo_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # NO LIMIT: On demande 100 commits (le max par page autorisé par GitHub)
            # Si vous en voulez plus, il faudrait gérer la pagination, mais 100 couvre déjà "80 atoms"
            limit = 100 
            res = await client.get(f"{base_url}/commits", headers=headers, params={"per_page": limit})
            
            if res.status_code != 200:
                print(f"[GITHUB API ERROR] {res.status_code} - {res.text}")
                return []
            
            data = res.json()
            results = []
            
            for commit in data:
                sha = commit.get("sha")
                html_url = commit.get("html_url")
                commit_msg = commit.get("commit", {}).get("message", "")
                author = commit.get("commit", {}).get("author", {}).get("name", "Unknown")
                
                final_content = f"Commit: {commit_msg}\nAuthor: {author}"

                # --- DEEP SCAN : Lecture TOTALE des fichiers ---
                if mode == 'deep_code':
                    code_changes = ""
                    try:
                        detail_res = await client.get(f"{base_url}/commits/{sha}", headers=headers)
                        if detail_res.status_code == 200:
                            detail = detail_res.json()
                            files = detail.get("files", [])
                            
                            # NO LIMIT: On lit TOUS les fichiers modifiés dans le commit (pas de [:5])
                            for f in files: 
                                filename = f.get("filename")
                                patch = f.get("patch", "[Binary/Large]")
                                
                                # On garde une petite sécurité (10k chars par fichier) pour éviter les crashs réseau
                                # mais c'est très large.
                                if len(patch) > 10000: patch = patch[:10000] + "\n... (truncated)"
                                code_changes += f"\n📄 {filename}\n```diff\n{patch}\n```\n"
                            
                            final_content += f"\n\nCODE CHANGES:\n{code_changes}"
                    except: pass
                
                results.append({
                    "unique_key": f"github:{sha}",
                    "fingerprint": sha, 
                    "content": final_content,
                    "link": html_url,
                    "is_ready": True,
                    "is_update": False 
                })
                
                # Délai minimal pour éviter le ban IP GitHub
                if mode == 'deep_code': await asyncio.sleep(0.1)
                
            return results

    except Exception as e:
        print(f"[GITHUB ERROR] {e}")
        return []