# Guide local moviebox-api

Ce guide explique comment utiliser ce clone local en CLI, comment le brancher ensuite a un bot Telegram, et comment le reconstruire en image Docker.

Note importante : utilise cet outil uniquement pour des contenus que tu as le droit de consulter, telecharger ou automatiser.

## 1. Etat actuel

Le depot GitHub `Simatwa/moviebox-api` est clone dans :

```powershell
D:\KANDRA\moviebox-api
```

Un environnement virtuel local a ete cree dans `.venv`, puis le package a ete installe avec l'extra CLI :

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[cli]"
```

Validation faite :

```powershell
.\.venv\Scripts\python.exe -c "import moviebox_api; print(moviebox_api.__version__)"
.\.venv\Scripts\moviebox.exe --help
.\.venv\Scripts\moviebox-v3.exe item-details "Avatar" -Y -J
.\.venv\Scripts\moviebox-v3.exe download-movie "Avatar" -Y -T
```

Resultat : la version installee est `0.5.3`, le CLI demarre, et `moviebox-v3` repond correctement. Pendant le test du 05/06/2026, `moviebox-v2` retournait une erreur `400 Bad Request` sur son host par defaut; pars donc sur `v3`.

## 2. Utilisation CLI pas a pas

Ouvre PowerShell puis place-toi dans le projet :

```powershell
cd D:\KANDRA\moviebox-api
```

Active le venv :

```powershell
.\.venv\Scripts\activate
```

Verifie les commandes disponibles :

```powershell
moviebox --help
moviebox v3 --help
moviebox-v3 --help
```

Rechercher les details d'un film :

```powershell
moviebox v3 item-details "Avatar" -Y
```

Sortie JSON, plus facile a parser pour un bot :

```powershell
moviebox v3 item-details "Avatar" -Y -J
```

Rechercher une serie :

```powershell
moviebox v3 item-details "Merlin" -s tv_series -Y
```

Tester un telechargement sans telecharger le fichier :

```powershell
moviebox v3 download-movie "Avatar" -Y -T
moviebox v3 download-series "Merlin" -s 1 -e 1 -l 1 -Y -T
```

Telecharger dans un dossier dedie :

```powershell
New-Item -ItemType Directory -Force -Path .\downloads
moviebox v3 download-movie "Avatar" -Y -q 720p -d .\downloads -D .\downloads
```

Telecharger un episode precis :

```powershell
moviebox v3 download-series "Merlin" -s 1 -e 1 -l 1 -Y -q 720p -d .\downloads -D .\downloads
```

Options utiles :

```powershell
-Y                  # accepte le premier resultat sans question interactive
-J                  # sortie JSON pour certaines commandes
-T                  # test sans telechargement reel
-q 720p             # qualite: best, worst, 360p, 480p, 720p, 1080p
-x English          # langue des sous-titres, repetable
-u Original         # piste audio/dub, selon disponibilite
--no-caption        # ne pas telecharger les sous-titres
```

## 3. Branchement Telegram

Pour ton bot Telegram, le plus simple est de faire une premiere integration qui appelle le CLI et renvoie le resume texte/JSON.

Mapping conseille :

```text
/film Avatar
  -> moviebox-v3 item-details "Avatar" -Y -J

/testfilm Avatar
  -> moviebox-v3 download-movie "Avatar" -Y -T

/serie Merlin
  -> moviebox-v3 item-details "Merlin" -s tv_series -Y -J

/testserie Merlin 1 1
  -> moviebox-v3 download-series "Merlin" -s 1 -e 1 -l 1 -Y -T
```

Regles pratiques pour le bot :

- Mets un timeout sur chaque commande CLI, par exemple 60 a 120 secondes.
- Parse la sortie JSON quand tu utilises `-J`.
- Evite d'envoyer directement de gros fichiers dans Telegram; garde les fichiers dans `downloads` et renvoie plutot un chemin, un statut ou un lien interne.
- Garde une liste de commandes autorisees cote bot; ne passe jamais une commande shell libre venant d'un message Telegram.

Exemple de logique Python pour le bot :

```python
import json
import subprocess


def search_movie(title: str) -> dict:
    result = subprocess.run(
        ["moviebox-v3", "item-details", title, "-Y", "-J"],
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    return json.loads(result.stdout)
```

Quand tu voudras brancher ton bot existant, il faudra me donner son code ou son framework (`python-telegram-bot`, `aiogram`, bot Node.js, etc.) et je connecterai ces commandes proprement.

## 4. Image Docker

Construire l'image :

```powershell
docker build -t moviebox-api:local .
```

### Mode service HTTP

L'image demarre maintenant en mode API par defaut, ce qui permet de l'utiliser comme un service par ton futur orchestrator ARR.

Lancer le service :

```powershell
New-Item -ItemType Directory -Force -Path .\downloads
docker run --rm -p 8095:8095 -v "${PWD}\downloads:/downloads" --name moviebox-api moviebox-api:local
```

Verifier la sante du service :

```powershell
curl.exe http://127.0.0.1:8095/health
```

Rechercher un film :

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8095/movies/details -Method Post -ContentType 'application/json' -Body '{"title":"Avatar"}'
```

Tester un telechargement sans telecharger :

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8095/movies/download -Method Post -ContentType 'application/json' -Body '{"title":"Avatar","quality":"720p","test":true,"background":false}'
```

Lancer un vrai telechargement en job de fond :

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8095/movies/download -Method Post -ContentType 'application/json' -Body '{"title":"Avatar","quality":"720p","background":true}'
```

Lister les jobs :

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8095/jobs
```

Rechercher une serie :

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8095/series/details -Method Post -ContentType 'application/json' -Body '{"title":"Merlin"}'
```

Tester un episode :

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8095/series/download -Method Post -ContentType 'application/json' -Body '{"title":"Merlin","season":1,"episode":1,"limit":1,"test":true,"background":false}'
```

Dans un `docker-compose.yml` de ton media server, le service ressemblera a ca :

```yaml
moviebox-api:
  image: moviebox-api:local
  container_name: moviebox-api
  restart: unless-stopped
  environment:
    PORT: "8095"
    MOVIEBOX_MAX_WORKERS: "2"
    MOVIEBOX_DOWNLOAD_ROOT: /downloads
  volumes:
    - ./downloads/moviebox:/downloads
  ports:
    - "8095:8095"
```

Depuis un orchestrator dans le meme compose, tu appelleras plutot :

```text
http://moviebox-api:8095/health
http://moviebox-api:8095/movies/details
http://moviebox-api:8095/movies/download
http://moviebox-api:8095/series/details
http://moviebox-api:8095/series/download
http://moviebox-api:8095/jobs
```

### Mode CLI dans Docker

Le mode CLI reste disponible en passant directement les arguments `moviebox` :

```powershell
docker run --rm moviebox-api:local --help
docker run --rm moviebox-api:local v3 item-details "Avatar" -Y
docker run --rm moviebox-api:local v3 download-movie "Avatar" -Y -T
```

Utiliser un dossier `downloads` persistant depuis Windows :

```powershell
New-Item -ItemType Directory -Force -Path .\downloads
docker run --rm -v "${PWD}\downloads:/downloads" moviebox-api:local v3 download-movie "Avatar" -Y -T
```

Pour un vrai telechargement dans le volume :

```powershell
docker run --rm -v "${PWD}\downloads:/downloads" moviebox-api:local v3 download-movie "Avatar" -Y -q 720p -d /downloads -D /downloads
```

## 5. Commandes de maintenance

Mettre a jour le depot :

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -e ".[cli]"
```

Reconstruire Docker apres mise a jour :

```powershell
docker build -t moviebox-api:local .
```
