# RAG « PV d'AG » — prototype

Un agent lit un PV d'AG (société commerciale), cherche dans la base de documents de l'entreprise les bonnes pratiques pertinentes et produit un rapport d'amélioration avec les sources citées.

## Installation

```bash
pip install -r requirements.txt
export MISTRAL_API_KEY="votre_clé"
```

## Utilisation

1. Rangez les PDF de l'entreprise par catégorie :

```
docs/
  modeles_pv/        # modèles et exemples de PV / actes validés
  guides_internes/   # chartes, guides de rédaction, check-lists
  juridique/         # statuts, extraits de textes applicables
```

2. Vérifiez le découpage (sans API, sans rien écrire) :

```bash
python chunking.py docs/modeles_pv/mon_acte.pdf --full   # un fichier, texte des chunks inclus
python ingest.py docs/ --dry-run                         # tout le dossier, résumé par fichier
```

3. Indexez (à relancer à chaque ajout ou modification : l'ancienne version d'un fichier est remplacée) :

```bash
python ingest.py docs/                 # --reset pour repartir de zéro
python ingest.py docs/ --skip-annexes  # sans les annexes (listes de salariés, bilans détaillés…)
```

4. Analysez un PV :

```bash
python analyze.py mon_pv.pdf -o rapport.md
python analyze.py mon_pv.pdf --categorie modeles_pv   # recherche restreinte
```

## Découpage (chunking.py)

Le découpage suit la structure juridique du document, pas un nombre de caractères fixe.

| Étape | Ce qui est fait |
|---|---|
| Nettoyage | Suppression des pieds de page Docusign, des en-têtes `ACTIVE/…`, des numéros de page et des pages de table des matières (points de suite) |
| Détection du type | Décision du Président / des associés, PV d'AG (titres « PREMIÈRE DÉCISION / RÉSOLUTION »), traité à articles numérotés (« 4. », « 4.2 »), sinon découpage générique par paragraphes |
| Unités | Une décision ou un article = une unité (avec son titre) ; le préambule a la sienne ; les annexes sont repérées (« Annexe 4.2(b) ») et séparées des articles |
| Tailles | Sous-articles de moins de 300 caractères regroupés avec leur article ; unités de plus de 1500 caractères redécoupées sur les limites de paragraphe ou de puce, avec un court chevauchement uniquement dans ce cas |
| Tableaux | Extraits en Markdown, un chunk séparé par tableau avec son texte d'introduction ; cellules fusionnées recollées ; tableaux longs redécoupés par groupes de lignes en répétant l'en-tête |
| Contexte | Chaque chunk est embeddé avec un préfixe : société, type d'acte, date, chemin de section |
| Petit chunk / parent | La recherche se fait sur les petits chunks ; l'agent reçoit l'unité entière (jusqu'à 6000 caractères) |
| Métadonnées | source, catégorie, type de document, société, acte, date (ISO), section, numéro, type de chunk (`texte`, `preambule`, `tableau`, `annexe`), page |

Pour ajouter un type de document, créer une fonction de découpage dans `chunking.py` (voir `split_ordinal` et `split_numbered`) et l'ajouter à `detect_doc_type`.

## Fonctionnement global

| Étape | Fichier | Détail |
|---|---|---|
| Ingestion | `ingest.py`, `chunking.py`, `parents.py` | Découpage structurel, embeddings `mistral-embed`, petits chunks dans ChromaDB, unités entières dans SQLite |
| Décomposition du PV | `analyze.py` | Le LLM découpe le PV en sections (quorum, résolutions, votes, signatures…) et génère pour chacune des questions à poser à la base |
| Recherche | `retrieval.py` | Plusieurs requêtes par section, fusion des chunks d'une même unité, seuil de distance pour écarter le hors-sujet |
| Recommandations | `analyze.py` | Le LLM ne s'appuie que sur les unités retrouvées, cite ses sources et signale quand la base ne couvre pas la section |
| Rapport | `analyze.py` | Markdown : synthèse, tableau de statuts, recommandations par section avec fichier, page et section des sources |

## Le RAG comme outil d'un LLM

`retrieval.py` expose la recherche sous forme d'outil (function calling Mistral / OpenAI), pour qu'un LLM interroge lui-même la base quand il en a besoin.

- `TOOL_SPEC` : la définition de l'outil `search_best_practices` à passer dans `tools=[TOOL_SPEC]`. Paramètres : `query` (obligatoire, une question précise et autonome) et `categorie` (optionnel, nom d'un sous-dossier de `docs/`, par exemple `modeles_pv`).
- `call_tool(name, arguments)` : exécute l'appel renvoyé par le LLM. `arguments` peut être la string JSON du `tool_call` ou un dict. Renvoie toujours une string JSON, à renvoyer au LLM dans un message de rôle `tool`. Ne lève jamais d'exception : une erreur (outil inconnu, JSON invalide, base vide…) revient sous la forme `{"erreur": "..."}` pour que le LLM puisse corriger son appel.
- Résultat : `{"resultats": [{"source", "page", "section", "societe", "date_acte", "type", "pertinence", "texte"}]}`. `texte` est l'unité entière (décision, article, tableau), tronquée à 2500 caractères ; `type` est le type de passage (`texte`, `preambule`, `tableau`, `annexe`) ; `pertinence` vaut `1 - distance cosinus`.

```python
from retrieval import TOOL_SPEC, call_tool

res = client.chat.complete(model=..., messages=messages, tools=[TOOL_SPEC])
for tc in res.choices[0].message.tool_calls or []:
    messages.append({"role": "tool", "name": tc.function.name, "tool_call_id": tc.id,
                     "content": call_tool(tc.function.name, tc.function.arguments)})
```

`analyze.py` utilise les mêmes fonctions `retrieve` et `passage_label`, importées depuis `retrieval.py`.

## Réglages (config.py, par variables d'environnement)

`CHAT_MODEL`, `EMBED_MODEL`, `UNIT_MIN_CHARS` (300), `UNIT_MAX_CHARS` (1500), `PARENT_MAX_CHARS` (6000), `CHUNK_OVERLAP` (100), `TOP_K_PER_QUERY`, `TOP_K_PER_SECTION`, `MAX_DISTANCE`.

## Test sans clé API

`FAKE_EMBEDDINGS=1 python ingest.py docs/` valide le découpage, l'ingestion et la recherche avec des embeddings factices (la qualité de recherche n'est pas représentative). L'analyse complète nécessite l'API Mistral.

## Limites connues et pistes d'amélioration

- **PDF scannés** : ignorés pour l'instant (signalés à l'ingestion). Ajouter une étape d'OCR si le corpus en contient.
- **Tableaux** : l'extraction repose sur la détection de PyMuPDF et des règles de nettoyage. Elle est fiable sur les tableaux financiers testés, moins sur des mises en page très inhabituelles. Relire l'aperçu (`chunking.py --full`) sur quelques tableaux avant d'indexer un gros corpus.
- **Données personnelles** : certains actes contiennent en annexe des listes nominatives (salariés, bénéficiaires). `--skip-annexes` permet de ne pas les indexer ; à décider selon la politique de l'entreprise.
- **Détection de structure** : testée sur 5 actes (décisions du Président, traité de scission). Les PV d'AG classiques (« résolutions ») et les guides internes utilisent des motifs prévus mais non testés sur de vrais documents.
- **Qualité du retrieval** : à mesurer sur 20 à 30 questions réelles avec la réponse attendue. Pistes : recherche hybride (BM25 + vecteurs), reranking, comparaison de modèles d'embedding.
- **Versions de documents** : si l'entreprise a plusieurs versions d'un même guide, ajouter une métadonnée de date et filtrer sur la plus récente.
- **Sécurité** : les PV et documents transitent par l'API Mistral. Vérifiez la politique de confidentialité de l'entreprise avant d'indexer des documents sensibles.
- **Valeur juridique** : le rapport applique les pratiques de l'entreprise ; il ne remplace pas la validation du service juridique.
