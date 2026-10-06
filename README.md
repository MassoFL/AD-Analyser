# Ad Pipeline

MVP local pour suivre les annonces Google collectées dans Trendtrack.
Python 3.9+ pour l’interface. PostgreSQL/Supabase via Psycopg, SQLite disponible en mode local. Chrome et les dépendances
du dossier `scraper` sont nécessaires uniquement pour collecter de nouvelles annonces.

## Démarrer

Double-cliquer sur `Ouvrir.command` sur macOS, ou exécuter :

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
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

- Base active : Supabase lorsque `SUPABASE_DB_URL` est renseignée ; sinon SQLite dans `data/pipeline.sqlite3`. Aucun repli silencieux vers SQLite en cas de panne réseau.
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
Les données persistent après fermeture. Les images restent locales : conserver les exports du scraper et leurs chemins pour les afficher sur une autre machine. Supabase contient leurs références, pas les fichiers. La connexion Supabase exige un accès Internet.

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

## Configuration Supabase

1. Dans le SQL Editor du projet, exécuter les fichiers de `supabase/migrations/` dans l’ordre (001, puis 002).
   Ce script idempotent crée le schéma privé `ad_pipeline`, les tables et le rôle
   `ad_pipeline_app`. Les tables ne sont pas exposées par la Data API ; RLS est activé,
   sans accès pour `anon` ou `authenticated`.
2. Activer le rôle avec un mot de passe aléatoire fort, dans une requête non sauvegardée :
   `ALTER ROLE ad_pipeline_app LOGIN PASSWORD 'REMPLACER_PAR_UN_SECRET';`
   Le compte dispose uniquement des droits de lecture, insertion et mise à jour nécessaires.
3. Dans **Connect → Direct → Session pooler**, relever l’hôte. Dans `.env`, définir :
   `SUPABASE_DB_URL=postgresql://ad_pipeline_app.PROJECT_REF:MOT_DE_PASSE@HOTE:5432/postgres`
   Encoder les caractères spéciaux du mot de passe dans l’URL. Ce secret reste exclusivement côté serveur.
4. Télécharger le certificat officiel dans **Database → Settings → SSL configuration**,
   le placer dans `supabase/certs/supabase-ca.crt`, puis définir
   `SUPABASE_SSLROOTCERT=supabase/certs/supabase-ca.crt`. La connexion vérifie le certificat et le nom du serveur.
5. Arrêter l’ancienne interface pour figer les modifications, puis reprendre ses données :
   `.venv/bin/python migrate_supabase.py`
   Une sauvegarde SQLite cohérente est créée dans `data/backups/` avant la copie.
   La migration est transactionnelle et vérifie les lignes insérées. Une nouvelle exécution
   conserve les lignes déjà présentes dans Supabase, y compris leurs corrections.
6. Relancer `Ouvrir.command`. Les imports, analyses, statuts et exports utilisent alors Supabase.

Les images et la clé Mistral restent locales. Le serveur reste monoposte et accessible
uniquement depuis ce Mac ; Supabase ne constitue pas un déploiement public de l’interface.
Ne jamais publier `.env`, les certificats propres à l’installation ou les sauvegardes.

Tests locaux : `.venv/bin/python -m unittest discover -s tests -v`.
Tests PostgreSQL optionnels : `RUN_SUPABASE_TESTS=1 .venv/bin/python -m unittest discover -s tests -v`.
Ces derniers créent uniquement des tables temporaires isolées, annulées à la fin : ils ne changent aucune annonce réelle.

Référence : [connexion PostgreSQL Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

## Déployer sur Vercel

Importer ce dépôt avec **Framework Preset: Other**, **Root Directory: ./**.
Le fichier `vercel.json` fournit la configuration ; ne pas ajouter de commande de build.
Python 3.12 est défini dans `.python-version`. Activer Fluid Compute si le projet utilise
encore les anciennes limites d’exécution. Une requête d’analyse dispose de 120 secondes.

Dans **Settings → Environment Variables**, renseigner côté serveur :

| Variable | Valeur |
| --- | --- |
| `SUPABASE_DB_URL` | L’URL privée du compte `ad_pipeline_app` ; utiliser le Transaction pooler, port **6543**, sur Vercel. |
| `MISTRAL_API_KEY` | La clé Mistral. |
| `MISTRAL_MODEL` | `mistral-small-latest` (facultatif). |

Ne pas définir de variable `NEXT_PUBLIC_*` pour ces secrets. Le certificat public
Supabase est inclus dans `certs/`, donc **ne pas copier le chemin local
`SUPABASE_SSLROOTCERT` dans Vercel**. Redéployer après une modification des variables.
Le site s’ouvre sans identifiant ni mot de passe. Toute personne ayant son URL peut
consulter les annonces, les modifier, exporter les données et lancer des appels Mistral
facturés au compte configuré. Les anciennes variables PIPELINE_USER et PIPELINE_PASSWORD
ne sont plus utilisées et peuvent être retirées de Vercel.

Le scraper reste sur le Mac. Lancer `Synchroniser.command` en plus du scraper pour
alimenter Supabase (ou garder l’interface locale ouverte : elle réalise déjà cet import).
Vercel consulte directement la même base. La collecte s’arrête lorsque le Mac ou le
collecteur est arrêté ; le site conserve l’accès aux données déjà importées.

Sur le site, les lots Mistral sont une suite de requêtes, une annonce par requête :
**garder l’onglet ouvert jusqu’à la fin**. Fermer l’onglet interrompt la suite du lot ;
l’annonce en cours peut encore terminer. Les résultats aboutis restent dans Supabase.
Un verrou PostgreSQL empêche d’analyser simultanément la même annonce depuis deux sites.
Après un échec réseau, aucune nouvelle tentative facturée n’est lancée automatiquement.
Les réglages Mistral sur Vercel se font dans les variables d’environnement, jamais dans `.env`.

Les nouvelles annonces avec une URL de visuel Trendtrack affichent ce visuel directement
sur le site. Les anciens exports sans URL restent sans image. Les fichiers locaux ne sont
pas téléchargés dans Vercel ; les visuels restent tributaires de leur disponibilité chez
Trendtrack. Le stockage permanent des images dans Supabase Storage n’est pas inclus ici.
L’export CSV est téléchargé par pages pour respecter les limites de réponse Vercel.

Documentation : [runtime Python Vercel](https://vercel.com/docs/functions/runtimes/python).

## Mots-clés de recherche (préparation)

Le champ `ads.search_keywords` conserve jusqu’à trois expressions (100 caractères chacune),
indépendamment de l’analyse Mistral et du statut. Elles apparaissent sur les cartes retenues
lorsqu’elles existent et dans les exports CSV. L’API de modification accepte
`search_keywords: ["expression 1", "expression 2", "expression 3"]` avec la révision habituelle.
Les imports et les changements d’étape ne les remplacent pas.

Appliquer `supabase/migrations/002_search_keywords.sql` avant d’enregistrer des mots-clés.
Sans cette migration, le pipeline existant continue de fonctionner avec des listes vides.
Aucune saisie manuelle ni génération Mistral n’est activée : cette étape prépare seulement
le stockage, la validation, l’API et l’affichage pour une future génération.
