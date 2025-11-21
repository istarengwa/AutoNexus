import httpx
import asyncio
import base64

# Fichiers à ignorer pour ne pas polluer l'IA avec du bruit
IGNORED_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.lock', '.pdf', '.zip', '.tar', '.gz', '.mp4', '.exe', '.bin']
IGNORED_DIRS = ['.git', 'node_modules', 'vendor', 'dist', 'build', '__pycache__']

async def get_file_content(client, url, headers):
    """Télécharge et décode un fichier depuis GitHub API"""
    try:
        res = await client.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            # GitHub renvoie souvent en base64
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"]).decode('utf-8', errors='ignore')
                return content
            return data.get("content", "") # Cas rare brut
    except:
        return ""
    return ""

async def fetch(settings: dict, token: str):
    """
    Mode Hybride :
    - Si 'custom_prompt' présent : Scan des FICHIERS (Snapshot du code actuel).
    - Sinon : Scan des COMMITS (Surveillance d'activité).
    """
    raw_query = settings.get("query", "").strip()
    has_prompt = bool(settings.get("custom_prompt"))
    
    if not token or not raw_query: return []
    
    # Nettoyage URL
    repo_name = raw_query.replace("https://github.com/", "").replace("http://github.com/", "")
    if repo_name.endswith("/"): repo_name = repo_name[:-1]
    
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    
    results = []

    try:
        async with httpx.AsyncClient() as client:
            
            # --- MODE 1 : ANALYSE DU CODE (SNAPSHOT) ---
            if has_prompt:
                print(f"[GITHUB] Mode Analyse de Code activé pour {repo_name}")
                
                # 1. Récupérer l'arbre des fichiers (Recursive)
                tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/main?recursive=1"
                # Fallback sur 'master' si 'main' n'existe pas (gestion d'erreur basique)
                res = await client.get(tree_url, headers=headers)
                if res.status_code == 404:
                    tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/master?recursive=1"
                    res = await client.get(tree_url, headers=headers)
                
                if res.status_code != 200:
                    print(f"[GITHUB ERROR] Impossible de lire l'arborescence: {res.status_code}")
                    return []

                tree = res.json().get("tree", [])
                
                # 2. Filtrer les fichiers pertinents
                files_to_scan = []
                for item in tree:
                    if item["type"] == "blob": # C'est un fichier
                        path = item["path"]
                        # Filtre extensions et dossiers inutiles
                        if any(path.endswith(ext) for ext in IGNORED_EXTS): continue
                        if any(bad_dir in path for bad_dir in IGNORED_DIRS): continue
                        
                        files_to_scan.append(item)

                # Limite de sécurité : on ne lit que les 60 premiers fichiers pour l'instant
                # (suffisant pour votre cas "Semaine 1")
                files_to_scan = files_to_scan[:60]
                
                print(f"[GITHUB] {len(files_to_scan)} fichiers pertinents identifiés. Téléchargement...")

                # 3. Télécharger le contenu
                for f in files_to_scan:
                    content = await get_file_content(client, f["url"], headers)
                    if not content: continue
                    
                    # On crée un item "Code"
                    results.append({
                        "unique_key": f"github_file:{f['sha']}", # Le SHA change si le fichier change
                        "fingerprint": f["sha"], 
                        "content": f"📄 FICHIER: {f['path']}\n\n{content}",
                        "link": f"https://github.com/{repo_name}/blob/main/{f['path']}",
                        "is_ready": True,
                        "is_update": False 
                    })
                    # Petite pause
                    await asyncio.sleep(0.1)

            # --- MODE 2 : SURVEILLANCE COMMITS (Classique) ---
            else:
                print(f"[GITHUB] Mode Surveillance Commits pour {repo_name}")
                url = f"https://api.github.com/repos/{repo_name}/commits"
                res = await client.get(url, headers=headers, params={"per_page": 20})
                if res.status_code == 200:
                    for commit in res.json():
                        msg = commit.get("commit", {}).get("message", "")
                        author = commit.get("commit", {}).get("author", {}).get("name", "")
                        results.append({
                            "unique_key": f"github:{commit['sha']}",
                            "fingerprint": commit['sha'],
                            "content": f"Commit: {msg} (par {author})",
                            "link": commit.get("html_url"),
                            "is_ready": True,
                            "is_update": False
                        })

            return results

    except Exception as e:
        print(f"[GITHUB CRITICAL ERROR] {e}")
        return []