# hygge_traversant ☀️

Surveille les nouvelles annonces de location à Copenhague, les filtre selon nos critères
et prévient sur téléphone via [ntfy](https://ntfy.sh). On garde la main sur l'envoi :
le script ne contacte jamais un propriétaire tout seul.

## Comment ça marche

Toutes les 2 à 4 minutes :

1. récupère la page de résultats BoligPortal (recherche définie dans `config.yaml`) ;
2. écarte les annonces déjà vues (base SQLite dans `data/`) ;
3. ouvre chaque nouvelle annonce et l'analyse (zone, prix total, surface, meublé, étage,
   date d'entrée, domiciliation, signaux d'arnaque, bonus traversant) ;
4. donne un verdict :
   - 🟢 **vert** : dans les critères, canal prioritaire (avec son) ;
   - 🟠 **orange** : à regarder (doute ou critère limite), canal silencieux ;
   - 🔴 **rouge** : bloquant, pas de notification, mais gardé en base pour le récap ;
5. envoie deux notifications : l'**alerte** (résumé et bouton « Annonce »), puis le
   **message** de présentation à copier, dans la langue de l'annonce.

Chaque soir, un **récap** liste les vertes et oranges, les motifs de rejet, les baisses
de prix et le délai de détection. Si la source ne renvoie plus rien ou enchaîne les
erreurs, une **alerte de santé** part sur le canal de test.

## Ce qui n'est pas versionné

Les infos personnelles restent sur la machine, jamais dans git :

| Fichier | Contenu |
|---|---|
| `.env` | noms des canaux ntfy, téléphone, clé API éventuelle (modèle : `.env.example`) |
| `config.yaml` | critères de recherche (modèle : `config.example.yaml`) |
| `private/messages/{fr,da,en}.txt` | vrais messages de présentation (modèles : `messages.example/`) |
| `data/` | base SQLite |

Dans les messages, `{area}` est remplacé par le quartier de l'annonce et `{phone}` par
`CONTACT_PHONE`.

## Installation sur le VPS (Ubuntu, Docker)

```bash
git clone git@github.com:mattcln/hygge_traversant.git && cd hygge_traversant
cp .env.example .env                  # remplir les canaux ntfy et le téléphone
cp config.example.yaml config.yaml    # ajuster budget, dates, recherche
mkdir -p private/messages data        # y copier fr.txt, da.txt, en.txt
docker compose build

# Tester les notifications avec 3 annonces inventées (canal de test)
docker compose run --rm hygge demo

# Lancer en continu
docker compose up -d
docker compose logs -f
```

Générer des noms de canaux impossibles à deviner (ntfy.sh est public : qui connaît le nom
peut lire) :

```bash
python3 -c "import secrets; print('hygge-' + secrets.token_urlsafe(12))"
```

## Téléphones

- Installer **ntfy** (F-Droid sur /e/OS, Play Store sur Pixel) et s'abonner aux canaux.
- Canal **alertes** : les vertes (les deux téléphones).
- Canal **silencieux** : les oranges et le récap du soir.
- Canal **test** : la phase de réglage (`mode: observe`) et les alertes techniques.
- Sur /e/OS : désactiver l'optimisation de batterie pour ntfy.

## Commandes

```bash
hygge demo [--dry-run]     # 3 annonces inventées, pour tester ntfy
hygge once [--dry-run]     # un seul passage
hygge run                  # boucle (ce que fait le conteneur)
hygge recap [--dry-run]    # récap des dernières 24 h tout de suite
hygge stats                # état de la base
hygge save-page URL FICHIER  # sauvegarder une page pour les tests du parser
```

Avec Docker : `docker compose run --rm hygge <commande>`.

## Développement

```bash
pip install -e ".[dev]"
pytest
```

## État

- [x] Config, base SQLite, analyse par mots-clés, verdicts, messages, notifications ntfy,
      récap, alertes de santé, Docker
- [ ] Parser BoligPortal (`sources/boligportal.py`) : à écrire à partir de vraies pages
      dans `tests/fixtures/boligportal/`
- [ ] Analyse par LLM (`analysis/llm.py`), si les mots-clés ne suffisent pas
- [ ] Autres sources (lejebolig.dk)
