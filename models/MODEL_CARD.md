# Model card: Agenclave triage classifier

## What it does

Labels a software issue report with a coarse type so the app can filter before
spending on agents, and so the code-fix harness knows the category. Not a
substitute for human triage on anything that matters.

The model predicts issue type only: `bug`, `feature_request`, `documentation`,
`question_other` (NLBSE'23 labels). I wanted a severity head too, but the only
severity dataset I could download at a useful size has no licence beyond "cite the
paper", so I left it out. The training path still exists behind
`scripts/prepare_data.py --with-severity` and `scripts/train_classifier.py
--with-severity` for local experiments; nothing it produces is shipped.

## Model

- Features compared: TF-IDF (word 1-2 grams, sublinear tf, English stop-words,
  vocab up to 50k) and sentence-transformer embeddings (`all-MiniLM-L6-v2`, CPU).
- Estimators: logistic regression and random forest, so four configs in total.
- Selection by validation macro-F1. The served model is TF-IDF + logistic
  regression, which also means the API imports no torch and can show the top
  tokens per class.

## Training data

See [`../data/README.md`](../data/README.md). 11,947 issues after exact-text dedup
(four balanced classes), stratified 70/15/15 train/val/test, seed 42. Dedup happens
before the split, and `tests/test_features.py` asserts the splits are disjoint by
row and by text.

## Metrics (held-out test set, n = 1,793)

Served model, TF-IDF + logistic regression: macro-F1 0.675, accuracy 0.674.

Per class:

| class            | precision | recall | f1    | support |
| ---------------- | --------- | ------ | ----- | ------- |
| bug              | 0.654     | 0.690  | 0.672 | 449     |
| feature_request  | 0.660     | 0.696  | 0.678 | 448     |
| documentation    | 0.773     | 0.686  | 0.727 | 446     |
| question_other   | 0.624     | 0.624  | 0.624 | 450     |

All four configs (test macro-F1 / accuracy):

| config                | macro-F1 | accuracy |
| --------------------- | -------- | -------- |
| tfidf + logreg        | 0.675    | 0.674    |
| tfidf + randomforest  | 0.653    | 0.655    |
| minilm + logreg       | 0.628    | 0.628    |
| minilm + randomforest | 0.569    | 0.578    |

MiniLM embeddings didn't help: best MiniLM config 0.628 vs 0.675 for TF-IDF. Issue
titles and bodies are short and the vocabulary is narrow, which suits a bag-of-words
model. `documentation` is the easiest class (f1 0.73); the `question_other`
catch-all is the hardest (f1 0.62) and is most often confused with `bug`, which is
intuitive: "is this a bug or am I doing it wrong?" Confusion matrix:
[`../results/cm_type.png`](../results/cm_type.png); full numbers:
[`../results/classifier_metrics.json`](../results/classifier_metrics.json).

## Limitations

- The label set is coarse and comes from one dataset.
- Trained on open-source GitHub issues; may not transfer to other domains.
- No `performance` class (no public dataset labels one) and no severity head (see
  above).
- The "top tokens" shown in the UI are the highest-weighted vocabulary for the
  predicted class, not the tokens from the specific issue.
