# Front — dossiers d’appels d’offres

## Hybride (hôte)

```bash
# racine : docker compose up -d
cd frontend_ao
npm run dev -- --port 5174
```

Vite proxifie vers `http://localhost:8000`.

## Docker (un seul service `frontend`)

```bash
docker compose --profile dev up -d
```

`--profile app` lance la même stack. UI : http://localhost:5174
