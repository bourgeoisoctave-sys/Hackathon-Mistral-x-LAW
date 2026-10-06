# RAG « PV d'AG » — prototype

Un agent lit un PV d'AG (société commerciale), cherche dans la base de documents de l'entreprise les bonnes pratiques pertinentes et produit un rapport d'amélioration avec les sources citées.

## Installation

```bash
pip install -r requirements.txt
echo 'MISTRAL_API_KEY=votre_clé' > .env      # lu automatiquement (ou exportez la variable)
```

Tests (hors-ligne, sans clé) : `pytest` · avec l'API réelle : `pytest -m real_api`.

## Utilisation

1. Rangez les PDF de l'entreprise par catégorie :

```
docs/
  modeles_pv/        # modèles et exemples de PV validés
  guides_internes/   # chartes, guides de rédaction, check-lists
  juridique/         # statuts, extraits de textes applicables
```

2. Indexez-les (à relancer à chaque ajout ; les passages déjà indexés ne sont pas dupliqués) :

```bash
python ingest.py docs/            # --reset pour repartir de zéro
```

3. Analysez un PV :

```bash
python analyze.py mon_pv.pdf -o rapport.md
python analyze.py mon_pv.pdf --categorie modeles_pv   # recherche restreinte
```

## Fonctionnement

| Étape | Fichier | Détail |
|---|---|---|
| Ingestion | `ingest.py` | Extraction PDF page par page, découpage en passages de ~1000 caractères avec chevauchement, embeddings `mistral-embed`, stockage dans ChromaDB avec source, page et catégorie |
| Décomposition du PV | `analyze.py` | Le LLM découpe le PV en sections (quorum, résolutions, votes, signatures…) et génère pour chacune des questions à poser à la base |
| Recherche | `analyze.py` | Plusieurs requêtes par section, fusion et dédoublonnage, seuil de distance pour écarter le hors-sujet |
| Recommandations | `analyze.py` | Le LLM ne s'appuie que sur les passages retrouvés, cite ses sources et signale quand la base ne couvre pas la section |
| Rapport | `analyze.py` | Markdown : synthèse, tableau de statuts, recommandations par section avec fichier et page |

Les modèles et paramètres se règlent par variables d'environnement (voir `config.py`) : `CHAT_MODEL`, `EMBED_MODEL`, `CHUNK_SIZE`, `TOP_K_PER_SECTION`, `MAX_DISTANCE`.

## Test sans clé API

`FAKE_EMBEDDINGS=1 python ingest.py docs/` valide l'ingestion et la recherche avec des embeddings factices (qualité de recherche non représentative). L'analyse complète nécessite l'API Mistral.

## Limites connues et pistes d'amélioration

- **PDF scannés** : ignorés pour l'instant (signalés à l'ingestion). Ajouter une étape d'OCR si le corpus en contient.
- **Qualité du retrieval** : à mesurer sur 20 à 30 questions réelles avec la réponse attendue. Pistes si insuffisant : recherche hybride (BM25 + vecteurs), reranking, découpage par titres plutôt que par taille.
- **Versions de documents** : si l'entreprise a plusieurs versions d'un même guide, ajouter une métadonnée de date et filtrer sur la plus récente.
- **Sécurité** : les PV et documents transitent par l'API Mistral. Vérifiez la politique de confidentialité de l'entreprise avant d'indexer des documents sensibles.
- **Valeur juridique** : le rapport applique les pratiques de l'entreprise ; il ne remplace pas la validation du service juridique.
