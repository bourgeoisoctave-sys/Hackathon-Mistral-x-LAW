# Ce que Mistral peut faire dans notre pipeline RAG

> Source : documentation Mistral et Ragas lue via context7, le 04/10/2026. Rien n'a encore été testé.

## Vue d'ensemble

```
PDF ─► Mistral OCR ──────────────► markdown par page
         └─ document_annotation ─► métadonnées {type_acte, date, société, version…}
                                        │
                   découpage par article (à faire nous-mêmes)
                                        │
                                  mistral-embed (1024d) ─► base vectorielle
                                                              │
question ─► mistral-embed ─► retrieval ─► rerank ─► génération (Mistral)
                                 │                       │
                       Ragas : ContextPrecision/Recall   Faithfulness
                       (LLM-juge = Mistral via LiteLLM, référence = juriste)
```

## 1. Parsing des PDFs : Mistral OCR

- Appel : `client.ocr.process(model="mistral-ocr-latest", document=...)`
- Sortie : du **markdown page par page**, avec les tableaux en markdown ou en HTML (`table_format`).
- **`document_annotation_format`** : on donne un schéma JSON, et l'OCR remplit les champs pendant le parsing (type d'acte, date, société, articles…). C'est la piste pour notre **« code PDF »**.
- `bbox_annotation_format` : décrit les images et zones du document (par exemple signatures ou tampons).
- `include_blocks` : position de chaque paragraphe sur la page, pour retrouver l'origine d'un passage.
- `confidence_scores_granularity` : score de confiance de l'OCR, par mot ou par page.
- Options : `pages` (traiter seulement certaines pages), `extract_header` et `extract_footer`.

**Limite :** le découpage se fait par **page**, pas par **article**. Le découpage par article reste à faire, à partir des titres markdown ou avec un LLM.

## 2. Embeddings : `mistral-embed`

| Modèle | Dimensions | Usage |
|---|---|---|
| `mistral-embed` | 1024 | Par défaut, entraîné pour le retrieval |
| `mistral-embed-dim256-2510` | 256 | Plus léger et plus rapide |
| `mistral-embed-dim128-2510` | 128 | Le plus compact |

- Les chunks **et** la requête doivent être embeddés avec le **même** modèle.

## 3. Évaluation : Ragas avec Mistral

- Ragas accepte Mistral comme **LLM-juge** via LiteLLM (`llm_factory`, `embedding_factory`).
- Attention : il faut passer **explicitement** les embeddings Mistral, sinon Ragas cherche une clé OpenAI.
- Chaque cas de test contient : `user_input`, `retrieved_contexts`, `response`, `reference` (écrite par un juriste).

| Couche | Métrique | Question posée |
|---|---|---|
| Retrieval | `ContextPrecision` | Les chunks trouvés sont-ils pertinents ? |
| Retrieval | `ContextRecall` | A-t-on trouvé tout ce qu'il fallait ? |
| Génération | `Faithfulness` | La réponse colle-t-elle aux sources ? |
| Génération | `ResponseRelevancy` | Répond-elle à la question ? |

## 4. Répartition du RAG à 2 personnes

On coupe le pipeline en deux : **A trouve** les bons chunks, **B en tire une réponse** et la vérifie.

**Personne A, « Trouver »**

0. Indexation : PDF → Mistral OCR → découpage par article → `mistral-embed` → base vectorielle, avec la `zone` en métadonnée
1. Vectorisation de la requête
2. Retrieval filtré par zone (top 15-20)
3. Rerank (top 3-5)

**Personne B, « Répondre »**

4. Génération structurée (schéma pydantic)
5. Vérification croisée avec la table de vérité
6. Output JSON → ReAct

```
        PERSONNE A — "Trouver"                     PERSONNE B — "Répondre"
┌──────────────────────────────┐            ┌──────────────────────────────┐
│ 0. Indexation (OCR→chunks→   │            │ 4. Génération pydantic       │
│    embed→base)               │            │ 5. Vérif croisée (table)     │
│ 1. Embed requête             │            │ 6. Output JSON → ReAct       │
│ 2. Retrieval + filtre zone   │            │                              │
│ 3. Rerank → top 3-5          │            │                              │
└──────────────┬───────────────┘            └──────────────▲───────────────┘
               │      CONTRAT (à fixer ensemble en 1er)     │
               └──► [{texte, doc_id, article, zone, page,   ┘
                      score}, ...]  + la question
```

**À faire ensemble, en premier :**
- **Le contrat au milieu** : le format de la liste de chunks que A envoie à B. Une fois ce format fixé, B peut avancer avec 3 chunks écrits à la main, sans attendre A.
- **Le schéma pydantic de sortie** : seuil, article, citation, exceptions, statut.
- **5 à 10 questions test avec leur bonne réponse** : A vérifie qu'il retrouve le bon article, B vérifie qu'il en tire le bon chiffre.
