# Ad Pipeline

MVP local pour suivre les annonces Google collectées dans Trendtrack.
Python 3.9+ pour l’interface, sans dépendance externe. Chrome et les dépendances
du dossier `scraper` sont nécessaires uniquement pour collecter de nouvelles annonces.

## Démarrer

Double-cliquer sur `Ouvrir.command` sur macOS, ou exécuter :

```sh
python3 server.py
```

Ouvrir http://127.0.0.1:8765. Le serveur écoute uniquement sur la machine locale.
Laisser le terminal ouvert pendant l’utilisation. Ctrl+C arrête l’application.

Copier `.env.example` vers `.env` pour personnaliser les chemins. La clé Mistral
peut être renseignée directement dans **Réglages**. Une valeur exportée dans
l’environnement du processus prend priorité sur le fichier `.env`.

## Parcours

1. Renseigner `TRENDTRACK_URL` dans `.env` avec l’URL de sa page d’annonces, puis se connecter avec `scraper/Se-connecter.command` et quitter ce Chrome.
2. Lancer `scraper/Lancer.command`, régler ses filtres et démarrer la collecte.
3. Les nouvelles annonces apparaissent dans **À analyser** pendant que le pipeline est ouvert.
4. Dans le pipeline, enregistrer une clé Mistral, choisir 1, 10, 25 ou 100 annonces puis cliquer sur **Analyser avec Mistral**.
5. Les analyses abouties passent dans **À examiner**. Ouvrir une fiche pour corriger les champs.
6. Déplacer les cartes vers **Retenue** ou **Écartée**, par glisser-déposer ou par le menu d’étape.

Seul le texte OCR est transmis à l’API officielle Mistral. Aucun appel n’est
effectué lors d’un import ou de l’enregistrement de la clé. Les analyses sont
facturées sur le compte Mistral. L’arrêt d’un lot prend effet après l’appel en cours.
Une erreur de connexion, d’accès ou de quota interrompt le lot. Le relancer
reprend les annonces encore sans analyse. Les résultats déjà acquis sont conservés.

## Données et continuité

- SQLite : `data/pipeline.sqlite3`.
- Clé API : `.env`, permissions limitées au compte utilisateur. Jamais retournée au navigateur.
- Import du dossier `SCRAPER_EXPORT_DIR` toutes les 10 secondes tant que le serveur est lancé.
- Sur cette installation, `.env` pointe vers le scraper existant dans `../trendtrack/exports`. Pour utiliser la copie fournie dans ce projet, remettre `SCRAPER_EXPORT_DIR=scraper/exports`.
- Chaque nouveau scraping crée `annonces.csv`, `annonces.jsonl` et `images/`.
- Les visuels sont téléchargés par le scraper puis servis depuis le disque.
- Les anciens CSV, dépourvus d’images, sont importés avec un emplacement vide explicite.
- Une annonce retrouvée ultérieurement avec le même texte peut recevoir son image sans perdre sa décision.
- Les nouvelles annonces sont dédupliquées par URL de visuel. Les anciens CSV sont rapprochés par texte OCR normalisé : deux créations avec exactement le même texte peuvent alors être regroupées.
- Les imports ne remplacent ni l’analyse, ni une correction, ni une décision.
- `SEED_CSV` permet de reprendre une seule fois le CSV des 100 annonces déjà enrichies.
- L’export CSV du pipeline contient toutes les annonces et leur statut.
- Le classement « potentiel e-commerce » est **oui** si consommable=non, service=non et micro-niche claire. Ce n’est pas un score de rentabilité.

Si le scraper est déjà en cours lors d’une mise à jour du code, il utilise encore
son ancienne version. Relancer la collecte pour conserver les images.
Les données persistent après fermeture. Sauvegarder `data/` et les exports du scraper
pour transférer l’application sur une autre machine.

## GitHub

Le dépôt inclut le serveur, l’interface, les tests, la configuration d’exemple et
le scraper. `.gitignore` exclut clé, base de données, images, exports et profils
Chrome. Aucun compte GitHub n’est requis pour l’exécution locale.

```sh
python3 -m unittest discover -s tests -v
```

Les tests Mistral utilisent une réponse simulée : le test réel requiert une clé valide.
Documentation API : https://docs.mistral.ai/api/endpoint/chat

## Limites du MVP

L’outil est monoposte. Pas d’authentification multi-utilisateur, pas de déploiement
public, pas d’analyse d’image par Mistral. La liste charge progressivement 25 cartes
par colonne. L’OCR et les classifications demandent une vérification humaine.
Le scraping reste lancé manuellement avec sélection des filtres ; le pipeline importe
automatiquement ses résultats, sans lancer ni planifier de navigateur en arrière-plan.
