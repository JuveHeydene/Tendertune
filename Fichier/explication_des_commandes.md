
(base) juve@kemayou-PC:~$ docker --version
Docker version 29.6.2, build dfc4efb
(base) juve@kemayou-PC:~$ docker --version
docker compose version
ollama --version
ollama list
python3 --version
Docker version 29.6.2, build dfc4efb
Docker Compose version v5.3.1
ollama version is 0.16.2
NAME                       ID              SIZE      MODIFIED     
nomic-embed-text:latest    0a109f422b47    274 MB    6 months ago    
llama3:latest              365c0bd3c000    4.7 GB    6 months ago    
Python 3.13.13
(base) juve@kemayou-PC:~$ uv --version 
uv 0.12.3 (x86_64-unknown-linux-gnu)
(base) juve@kemayou-PC:~$ 

---
Ollama nomic-embed-text)


etape 3 — Créer l’environnement Python
À la racine du projet :

cd /home/juve/Lectures_\&_projects/Projets/BTP_RAG
uv lock
uv sync --all-groups
uv lock écrit uv.lock (versions figées, reproductible).
uv sync crée .venv/ et installe le cœur (FastAPI, LlamaIndex, clients DB, Ollama). Pas Docling, pas Paddle, pas le GPU : extras optionnels dans pyproject.toml.
Vérification :

uv run python -c "from app.config import get_settings; s=get_settings(); print(s.use_gpu, s.device, s.llm_model, s.embed_model)"
Attendu : False cpu <votre llm> <votre embed>.

Étape 4 — Lancer l’infra Docker (sans GPU, sans API)
docker compose up -d postgres qdrant neo4j redis minio
docker compose ps
Attendez que postgres / qdrant / redis / neo4j passent healthy. MinIO n’a pas de healthcheck (image trop minimale) : s’il tourne, c’est bon.

Le schéma SQL est monté dans Postgres (scripts/init_db.sql) uniquement au premier start (volume vide).

---

Apres uv sync 

Resolved 256 packages in 3ms
(base) juve@kemayou-PC:~/Lectures_&_projects/Projets/BTP_RAG$ uv sync --all-groups


Using CPython 3.12.3 interpreter at: /usr/bin/python3.12
Creating virtual environment at: .venv
Resolved 256 packages in 2ms
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          ⠙ Preparing packages... (76/100)                                                                     pytz                             ------------------------------ 439.72 KiB/496.37 KiB                httptools                        ------------------------------ 440.56 KiB/511.57 KiB                langchain-core                   ------------------------------ 452.23 KiB/556.65 KiB                greenlet                         ------------------------------ 444.78 KiB/606.87 KiB                langsmith                        ------------------------------ 444.09 KiB/727.14 KiB                
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          ⠹ Preparing packages... (76/100)                                                                     pytz                             ------------------------------ 439.72 KiB/496.37 KiB                httptools                        ------------------------------ 440.56 KiB/511.57 KiB                langchain-core                   ------------------------------ 452.23 KiB/556.65 KiB                greenlet                         ------------------------------ 444.78 KiB/606.87 KiB                langsmith                        ------------------------------ 444.09 KiB/727.14 KiB                
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          ⠹ Preparing packages... (76/100)                                                                     pytz                             ------------------------------ 439.72 KiB/496.37 KiB                
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          ⠴ Preparing packages... (76/100)                                                                     pytz                             ------------------------------ 439.72 KiB/496.37 KiB                
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          ⠴ Preparing packages... (76/100)                                                                     
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          ⠧ Preparing packages... (76/100)                                                                     
   Building btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          ⠇ Preparing packages... (76/100)                                                                     
      Built btp-rag @ file:///home/juve/Lectures_&_projects/Projets/BTP_RAG                          
Prepared 100 packages in 3m 27s
Installed 131 packages in 92ms
 + aiohappyeyeballs==2.7.1
 + aiohttp==3.14.3
 + aiosignal==1.4.0
 + aiosqlite==0.22.1
 + annotated-doc==0.0.5
 + annotated-types==0.8.0
 + anyio==4.14.2
 + argon2-cffi==25.1.0
 + argon2-cffi-bindings==26.1.0
 + arq==0.28.0
 + asyncpg==0.31.0
 + attrs==26.1.0
 + banks==2.5.0
 + btp-rag==0.1.0 (from file:///home/juve/Lectures_&_projects/Projets/BTP_RAG)
 + certifi==2026.7.22
 + cffi==2.1.1
 + charset-normalizer==3.5.1
 + click==8.4.2
 + colorama==0.4.6
 + dataclasses-json==0.6.7
 + defusedxml==0.7.1
 + deprecated==1.3.1
 + dirtyjson==1.0.8
 + distro==1.9.0
 + et-xmlfile==2.0.0
 + fastapi==0.141.1
 + filetype==1.2.0
 + frozenlist==1.8.0
 + fsspec==2026.7.0
 + greenlet==3.5.5
 + griffe==2.2.0
 + griffecli==2.2.0
 + griffelib==2.2.0
 + grpcio==1.83.0
 + h11==0.16.0
 + h2==4.4.1
 + hiredis==3.4.1
 + hpack==4.2.0
 + httpcore==1.0.9
 + httptools==0.8.0
 + httpx==0.28.1
 + hyperframe==6.1.0
 + idna==3.19
 + iniconfig==2.3.0
 + jinja2==3.1.6
 + jiter==0.16.0
 + joblib==1.5.3
 + jsonpatch==1.33
 + jsonpointer==3.1.1
 + langchain==1.3.16
 + langchain-core==1.6.0
 + langchain-protocol==0.0.18
 + langgraph==1.2.11
 + langgraph-checkpoint==4.2.0
 + langgraph-prebuilt==1.1.0
 + langgraph-sdk==0.4.3
 + langsmith==0.11.1
 + llama-index==0.14.24
 + llama-index-core==0.14.24
 + llama-index-embeddings-ollama==0.9.0
 + llama-index-embeddings-openai==0.6.0
 + llama-index-instrumentation==0.5.0
 + llama-index-llms-ollama==0.10.1
 + llama-index-llms-openai==0.7.10
 + llama-index-vector-stores-qdrant==0.10.3
 + llama-index-workflows==2.23.3
 + lxml==6.1.2
 + markdown==3.10.3
 + markupsafe==3.0.3
 + marshmallow==3.26.2
 + minio==7.2.20
 + multidict==6.7.1
 + mypy-extensions==1.1.0
 + neo4j==6.2.0
 + nest-asyncio==1.6.0
 + networkx==3.6.1
 + nltk==3.10.3
 + numpy==2.3.5
 + ollama==0.6.2
 + openai==2.54.0
 + openpyxl==3.1.5
 + orjson==3.12.0
 + ormsgpack==1.12.2
 + packaging==26.3
 + pgvector==0.5.0
 + pillow==12.3.0
 + platformdirs==4.11.3
 + pluggy==1.6.0
 + portalocker==3.2.0
 + propcache==0.5.2
 + protobuf==3.20.2
 + pycparser==3.0
 + pycryptodome==3.23.0
 + pydantic==2.13.4
 + pydantic-core==2.46.4
 + pydantic-settings==2.15.0
 + pygments==2.21.0
 + pyjwt==2.13.0
 + pytest==9.1.1
 + pytest-asyncio==1.4.0
 + python-docx==1.2.0
 + python-dotenv==1.2.3
 + python-multipart==0.0.32
 + pytz==2026.3.post1
 + pyyaml==6.0.2
 + qdrant-client==1.19.0
 + redis==5.3.1
 + regex==2026.7.19
 + requests==2.34.2
 + requests-toolbelt==1.0.0
 + setuptools==84.0.0
 + sniffio==1.3.1
 + sqlalchemy==2.0.52
 + starlette==1.6.0
 + tenacity==9.1.4
 + tiktoken==0.14.0
 + tinytag==2.3.0
 + tqdm==4.70.0
 + typing-extensions==4.16.0
 + typing-inspect==0.9.0
 + typing-inspection==0.4.4
 + urllib3==2.7.0
 + uuid-utils==0.17.0
 + uvicorn==0.52.4
 + uvloop==0.22.1
 + watchfiles==1.2.0
 + websockets==16.1.1
 + wrapt==2.3.0
 + xxhash==4.0.1
 + yarl==1.24.5
 + zstandard==0.25.0


 --- 

 Service	Avant (hôte)	Maintenant (hôte)
MinIO API
9000
9010
MinIO console
9001
9011
Redis
6379
6380
API
8000
8001



---

Le plus simple : **psql dans le conteneur** (pas besoin de client Postgres sur l’hôte).

```bash
docker compose exec postgres psql -U ao_user -d ao_db
```

Mot de passe : tu es déjà authentifié via le socket interne, en général **aucun prompt**.

Dans `psql` :

```sql
\dt
```

Tu dois voir notamment : `tenants`, `users`, `sessions`, `refresh_tokens`, `audit_logs`, `documents`, `dossiers`, `chunks`, `exigences`, `outline_items`, `generations`, `reviews`, `conversations`, `messages`, `exports`.

Pour quitter : `\q`

Sans session interactive :

```bash
docker compose exec postgres psql -U ao_user -d ao_db -c '\dt'
```

Seed du tenant :

```bash
docker compose exec postgres psql -U ao_user -d ao_db -c "SELECT id, slug, name FROM tenants;"
```

Depuis l’hôte, si `psql` est installé :

```bash
psql postgresql://ao_user:ao_pass@localhost:5432/ao_db -c '\dt'
```

`init_db.sql` ne s’exécute **que** au premier remplissage du volume. Si `\dt` est vide, le volume existait déjà avant le script : il faudrait recréer le volume (`docker compose down -v` efface les données Postgres).


---

`scripts/init_db.sql` ne se relance **pas** si le volume Postgres existe déjà. Docker ne l’exécute que la **première** fois (dossier data vide). Il faut donc un `ALTER` à la main.

## 1. Vérifier que Postgres tourne

```bash
cd ~/Lectures_\&_projects/Projets/BTP_RAG
docker compose ps postgres
```

## 2. Voir si la colonne existe déjà

```bash
docker compose exec postgres psql -U ao_user -d ao_db -c "\d documents"
```

Si tu vois `graph_extracted`, tu as fini.

## 3. Ajouter la colonne (sans tout casser)

```bash
docker compose exec postgres psql -U ao_user -d ao_db -c "
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS graph_extracted BOOLEAN NOT NULL DEFAULT FALSE;
"
```

- `IF NOT EXISTS` : pas d’erreur si tu relances.
- `DEFAULT FALSE` : les documents déjà là restent « graphe pas extrait » (normal).
- Les données (chunks, tenants, etc.) **ne sont pas** effacées.

Revérifie :

```bash
docker compose exec postgres psql -U ao_user -d ao_db -c "\d documents"
```

## Ce qu’il ne faut **pas** faire (sauf reset volontaire)

```bash
docker compose down -v
```

Le `-v` **supprime le volume** → base recréée depuis `init_db.sql`, **toutes les données perdues**. Utile seulement si tu acceptes de repartir de zéro.

## Plus tard

Quand le schéma bougera souvent, un outil du type Alembic gérera ces `ALTER`. Pour **une** colonne maintenant, `psql` + `ALTER` suffit.


---

---

# LANCER L'app

À la racine du projet :

**Tout** (bases + API + worker + front) :

```bash
docker compose --profile dev up -d
```

Front : http://localhost:5174  
API : http://localhost:8001/health

**Bases seulement** (Postgres, Qdrant, Neo4j, Redis, MinIO) :

```bash
docker compose up -d
```

---

Non. **Ollama n’a pas besoin du mode GPU.** `USE_GPU=true` concerne Paddle / CUDA dans *cette* stack, pas Ollama.

L’erreur est un **refus de connexion** : depuis le container, rien n’écoute sur `host.docker.internal:11434`. Ce n’est pas « pas de GPU », c’est « Ollama n’est pas joignable ».

**À vérifier sur l’hôte :**

```bash
ollama serve          # s’il n’est pas déjà lancé (souvent un service systemd)
ollama list           # nomic-embed-text et llama3 doivent apparaître
ollama pull nomic-embed-text
curl -s http://127.0.0.1:11434/api/tags
```

Si `curl` sur l’hôte échoue, le worker Docker échouera aussi.

**Si `curl` marche sur l’hôte mais pas depuis Docker :** Ollama n’écoute que `127.0.0.1`. Il faut qu’il écoute toutes les interfaces, par exemple :

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

(ou la même variable dans le service systemd / l’appli Ollama.)

Le GPU **accélère** Ollama s’il est installé avec le bon backend, mais le CPU suffit pour `nomic-embed-text`. Tant que le port 11434 n’accepte pas les connexions depuis le container, l’ingest restera `failed` à l’étape embeddings.




Tu n’as **pas** à relancer `ollama serve` : le service systemd **tourne déjà**. D’où `address already in use`.

Le vrai problème : il n’écoute que **`127.0.0.1:11434`**. Les modèles sont là (`nomic-embed-text`, `llama3`). Le worker Docker arrive via `host.docker.internal`, donc **pas** via loopback → `Connection refused`.

Toujours **pas** besoin du GPU.

Ouvre Ollama à toutes les interfaces (une fois) :

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/host.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Vérif : `ss -ltnp | grep 11434` doit montrer `0.0.0.0:11434` (plus seulement `127.0.0.1`).

Puis relance un upload (ou le même fichier s’il n’est pas en doublon SHA). Le worker pourra appeler les embeddings.

---



Oui : il y a **deux variantes de Paddle**, et Docling est **indépendant** du GPU.

---

## 1. Où sont les paquets ?

**Toujours sur l’hôte**, dans :

`backend_ao/.venv/`

Docker **ne les a pas**.  
Si tu n’as jamais fait `uv sync --extra …` sur la machine, ils n’existent nulle part.

---

## 2. Les 3 “packs” optionnels (noms dans `pyproject.toml`)

| Extra | Ce que ça installe | GPU ? |
|-------|--------------------|-------|
| `ingest` | **Docling** | Non (Docling n’est pas “le pack GPU”) |
| `ocr` | **PaddleOCR + paddlepaddle (CPU)** + pymupdf | Non |
| `ocr-gpu` | **PaddleOCR + paddlepaddle-gpu** + pymupdf + cuDNN | Oui (tente le GPU) |

Donc :
- **Paddle CPU** = extra `ocr`
- **Paddle GPU** = extra `ocr-gpu`
- **Docling** = extra `ingest` (ni CPU ni GPU dans le nom ; c’est un autre outil)

Tu ne dois **pas** installer `ocr` et `ocr-gpu` en même temps (conflit).

---

## 3. Deux choses différentes : *installé* vs *mode d’exécution*

### A) Ce qui est **installé** (une fois, avec `uv sync`)

Exemple actuel chez toi :

```bash
uv sync --extra ingest --extra ocr-gpu
```

→ dans le venv : **Docling + Paddle (version GPU)**

Sans GPU, sur une autre machine :

```bash
uv sync --extra ingest --extra ocr
```

→ **Docling + Paddle (version CPU)**

Si tu fais seulement `uv sync` (sans extras) → **ni Docling ni Paddle**.

### B) Ce qui est **utilisé à l’exécution** (`.env`)

```bash
USE_GPU=true   # ou false
```

Ça ne réinstalle rien. Ça dit à Paddle : « essaie le GPU ou reste en CPU ».

| `USE_GPU` | Si Paddle est installé (`ocr` ou `ocr-gpu`) |
|-----------|---------------------------------------------|
| `false` | OCR uniquement en **CPU** |
| `true` | Essaie **GPU**, sinon **repli CPU** (chez toi : souvent repli) |

Docling, lui, n’écoute pas vraiment ce flag comme Paddle : s’il est installé, le code l’essaie ; s’il plante, repli vers pypdf / Paddle.

---

## 4. Réponses directes à tes questions

**Il y a un Paddle CPU et un Paddle GPU ?**  
Oui. Deux packages Python différents : `paddlepaddle` (CPU) vs `paddlepaddle-gpu` (GPU). Même librairie OCR (`paddleocr`) au-dessus.

**Sans mode GPU, j’ai toujours Docling et Paddle ?**  
- **Oui**, si tu les as installés avec les extras (`ingest` + `ocr` ou `ocr-gpu`).  
- `USE_GPU=false` ne les désinstalle pas. Ça force juste Paddle en CPU.  
- Docling reste disponible s’il a été installé avec `--extra ingest`.

**Ils sont sur l’hôte ?**  
Oui. Uniquement dans `backend_ao/.venv`. Pas dans l’image Docker actuelle.

---

## 5. Schéma ultra simple

```text
INSTALLATION (une fois)
  uv sync --extra ingest          → Docling dans backend_ao/.venv
  uv sync --extra ocr             → Paddle CPU dans le même .venv
  uv sync --extra ocr-gpu         → Paddle GPU dans le même .venv

EXÉCUTION
  Docker worker     → PAS de Docling/Paddle (image sans extras)
  run_worker_hybrid → OUI (utilise backend_ao/.venv)

  USE_GPU=false → Paddle en CPU
  USE_GPU=true  → Paddle tente GPU, sinon CPU
```

---

## 6. Chez toi, concrètement aujourd’hui

1. Installé sur l’hôte : **Docling + Paddle GPU** (`ingest` + `ocr-gpu`).
2. Worker Docker : **arrêté** (sinon pas d’OCR avancé).
3. Worker hybride : lit ce `.venv` → peut utiliser Docling / Paddle.
4. `USE_GPU=true` : Paddle **tente** le GPU, mais chez toi il **rebascule souvent en CPU** (problème cuDNN). Docling peut aussi échouer → le PDF texte passe quand même par **pypdf**.

---

## 7. Les 3 setups possibles (pour toi ou un collègue)

| Besoin | Commande install | `.env` | Lancement |
|--------|------------------|--------|-----------|
| OCR + Docling, avec GPU | `uv sync --extra ingest --extra ocr-gpu` | `USE_GPU=true` | stop worker Docker + `run_worker_hybrid.sh` |
| OCR + Docling, sans GPU | `uv sync --extra ingest --extra ocr` | `USE_GPU=false` | idem hybride |
| Pas d’OCR avancé | `uv sync` seul (ou image Docker) | peu importe | worker Docker suffit (PDF texte seulement) |

En une phrase : **Docling et Paddle s’installent sur l’hôte via des extras nommés ; Paddle existe en variante CPU ou GPU ; sans GPU tu peux quand même avoir les deux si tu as sync avec `ingest` + `ocr` ; Docker seul ne les a pas.**


## `nohup` c’est quoi ?

**nohup** = *no hang up* (« ne pas raccrocher »).

Sans `nohup`, si tu lances un programme dans un terminal puis tu **fermes le terminal**, le système envoie un signal `SIGHUP` et le programme **s’arrête**.

Avec `nohup`, le programme **continue** même après fermeture du terminal / déconnexion SSH.

---

## Les deux façons de lancer le worker hybride

### 1. Terminal dédié (logs visibles tout de suite)

```bash
./backend_ao/scripts/run_worker_hybrid.sh
```

- Le worker tourne **dans ce terminal**
- Les logs s’affichent **directement** à l’écran
- Tu fermes le terminal → le worker s’arrête
- Tu n’as **pas besoin** de `tail -f`

### 2. Avec `nohup` (arrière-plan + fichier)

```bash
nohup ./backend_ao/scripts/run_worker_hybrid.sh > /tmp/btp-worker-hybrid.log 2>&1 &
```

Décortiqué :

| Morceau | Rôle |
|---------|------|
| `nohup` | Le worker survit à la fermeture du terminal |
| `./backend_ao/scripts/run_worker_hybrid.sh` | Le script à lancer |
| `> /tmp/btp-worker-hybrid.log` | Redirige la **sortie normale** (stdout) vers ce fichier |
| `2>&1` | Redirige aussi les **erreurs** (stderr) vers le même fichier |
| `&` | Lance en **arrière-plan** (le terminal se libère tout de suite) |

Dans ce cas, **oui** : tu ne vois plus les logs dans le terminal, parce qu’ils partent dans le fichier.

---

## `tail -f /tmp/btp-worker-hybrid.log`

| Morceau | Rôle |
|---------|------|
| `tail` | Affiche la fin d’un fichier |
| `-f` | *follow* : reste ouvert et montre les **nouvelles lignes** en direct |

C’est l’équivalent de « regarder les logs en live », mais **en lisant le fichier** créé par `nohup`.

```text
Lancement nohup  →  logs écrits dans /tmp/btp-worker-hybrid.log
                         ↑
tail -f ─────────────── lit ce fichier et l’affiche
```

Sans `nohup` (script lancé dans le terminal), les logs sont déjà à l’écran → `tail -f` n’est **pas** nécessaire (sauf si tu as aussi redirigé vers un fichier autrement).

---

## En résumé

| Lancement | Où sont les logs ? | Comment les voir ? |
|-----------|--------------------|--------------------|
| `./…/run_worker_hybrid.sh` | Dans le terminal | Rien à faire, tu les vois |
| `nohup … > /tmp/….log 2>&1 &` | Dans le fichier | `tail -f /tmp/btp-worker-hybrid.log` |

**Oui :** avec `nohup` + redirection, tu ne vois pas les logs dans le terminal ; tu les suis avec `tail -f` sur le fichier.


---

Tu as un **diagnostic très clair** dans tes logs :

- `PDF pypdf densité=0.0` → c’est bien un scan
- Paddle essaie le GPU (`GPU ID: 0`)
- puis échoue : `Cannot load cudnn shared library ...`
- et fait un **repli CPU** → ingestion `ready` (donc pipeline fonctionne)

## Pourquoi Docling “refuse”

Ce n’est pas un bug métier, c’est un **conflit runtime GPU** :

1. Ton stack Paddle actuelle est calée sur **cuDNN 8** (pour `paddlepaddle-gpu 2.6.x`)
2. Docling (via `torch`) essaie de charger **cuDNN 9** (`libcudnn.so.9`)
3. Dans le même env, tu n’as pas cette lib dispo pour torch → Docling GPU plante

En plus, le log Docling disait aussi : **“No OCR engine found”** (rapidocr/onnxruntime non dispo), donc même sans le souci cuDNN, Docling OCR n’était pas prêt.

---

## A faire : TENTATIVE POUR GPU FONCTIONNELE AVEC PADDLE

### Option A (pragmatique, recommandée tout de suite)
- **Scans**: garder Paddle (CPU fallback si GPU KO)
- **PDF texte**: pypdf/Docling fallback actuel
- Avantage : stable maintenant, pas de blocage

### Option B (propre et robuste)
Séparer en **2 environnements workers** :

- Env 1: Paddle OCR (GPU, cuDNN 8)
- Env 2: Docling (CPU torch ou stack cuDNN 9 propre)

C’est la meilleure approche si tu veux les deux sans conflit.

### Option C (forcer Docling en CPU)
Installer torch CPU / désactiver GPU côté Docling pour éviter la dépendance `libcudnn.so.9`.  
Tu gardes Paddle séparément pour OCR scans.

---

## Mon avis concret

Pour des **PDF scans**, Docling n’est pas ton urgence : Paddle fait déjà le job (et chez toi il retombe CPU proprement).  
La vraie décision à prendre : veux-tu investir dans Docling OCR maintenant ?  
- si oui → fais Option B (deux envs/workers)  
- sinon → continue avec Paddle pour scans, Docling seulement quand stack GPU dédiée est prête.

Si tu veux, je peux te proposer un plan exact en 5 commandes pour mettre en place l’Option B proprement.





Oui : **horloge A = ingestion** (écrire la mémoire).  
**Horloge B = RAG / chat** (lire cette mémoire au moment d’une question).

---

## Horloge A vs Horloge B

| | Horloge A (ingestion) | Horloge B (RAG / chat) |
|--|------------------------|-------------------------|
| Quand | Upload document | Message conversation |
| But | Parse → chunks → embeddings → Qdrant → Neo4j | Question → retrieve → LLM |
| Déclencheur | `POST /documents` (ou upload en conversation) | `POST .../messages/stream` |
| Async | Worker ARQ | API synchrone + stream SSE |

Le **RAG n’est pas pendant l’ingestion**.  
À l’ingestion on **prépare** les vecteurs (Qdrant) et le graphe.  
Le RAG, c’est quand on **interroge** ces vecteurs (horloge B).

---

## Ordre de lecture — Horloge A (ingestion)

Lis dans cet ordre :

### 1. Entrée HTTP (upload)

1. `backend_ao/app/api/documents.py`  
   - `POST /documents` → lit le fichier, appelle `store_document`  
   - (optionnel) `backend_ao/app/api/conversations.py` → `POST .../documents` (même upload depuis le chat)

### 2. MinIO + Postgres + file

2. `backend_ao/app/services/document_upload.py`  
   - SHA doublon  
   - PUT MinIO `ao-raw`  
   - INSERT `documents` status=`pending`  
   - `enqueue_ingest`

3. `backend_ao/app/services/queue.py`  
   - `enqueue_ingest` → job Redis ARQ `ingest_document`

4. `backend_ao/app/services/minio_client.py`  
   - client MinIO (buckets)

### 3. Worker ARQ

5. `backend_ao/app/worker_settings.py`  
   - enregistre `ingest_document` + `extract_graph`

6. **`backend_ao/app/workers/ingest.py`** ← **cœur de l’horloge A**  
   Enchaînement :  
   MinIO GET → parse → chunk → Postgres chunks → embed Ollama → Qdrant → `ready` → enqueue graphe

### 4. Étapes appelées par le worker

7. `backend_ao/app/ingest/parse.py`  
   - Docling / Paddle / pypdf / docx / xlsx

8. `backend_ao/app/ingest/chunk.py`  
   - découpe parent / fenêtres

9. `backend_ao/app/ingest/index_qdrant.py`  
   - `embed_texts` (Ollama)  
   - `ensure_collection` + `upsert_chunks` (Qdrant)

10. Modèle SQL (schéma)  
    - `backend_ao/app/models/sql.py` (`Document`, `ChunkRow`)  
    - ou `backend_ao/scripts/init_db.sql` (tables `documents`, `chunks`)

### 5. Après `ready` — graphe (toujours horloge A, job 2)

11. `backend_ao/app/graph/extract.py`  
    - `extract_graph` : chunks → Ollama JSON → MERGE Neo4j  
    - met `graph_extracted=true`

### Doc de synthèse (optionnel)

12. `Mise_en_place/ingestion_horloge_A.md` — schéma global déjà rédigé

---

## Flux condensé (horloge A)

```text
POST /documents
  → document_upload.store_document
       → MinIO ao-raw
       → Postgres documents (pending)
       → Redis ARQ ingest_document
  → HTTP 200 immédiat

Worker ingest_document
  → MinIO GET
  → parse.py
  → chunk.py
  → Postgres chunks
  → Ollama embeddings
  → Qdrant ao_chunks
  → status = ready
  → enqueue extract_graph

Worker extract_graph
  → Ollama + Neo4j
  → graph_extracted = true
```

---

## Horloge B — où est le RAG (ordre de lecture)

Le RAG commence **ici**, quand l’utilisateur pose une question :

1. `backend_ao/app/api/conversations.py` — `POST .../messages/stream`
2. `backend_ao/app/services/chat_pipeline.py` — `stream_message` / route
3. `backend_ao/app/workflow/nodes/route.py` — intent (`hybrid_rag`, `run_section`, …)
4. `backend_ao/app/workflow/nodes/retrieve.py` — appelle le retriever
5. **`backend_ao/app/rag/hybrid_retriever.py`** ← **RAG V1 (dense Qdrant)**
6. `backend_ao/app/workflow/nodes/generate.py` + `chat_pipeline` — prompt + stream Ollama

À ce moment-là on **lit** ce que l’horloge A a écrit (Qdrant + éventuellement Neo4j plus tard).

---

## Mini règle mentale

- **Horloge 1 / A** = *écrire* le patrimoine (fichier → texte → vecteurs → graphe)  
- **Horloge 2 / B** = *lire* le patrimoine pour répondre (retrieve + LLM)

Commence par `documents.py` → `document_upload.py` → `workers/ingest.py`, puis descends dans `parse` / `chunk` / `index_qdrant` / `graph/extract`.


