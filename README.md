# Script resume-articles
Ce script Python analyse tous les fichiers HTML présents dans le dossier `input/`, extrait les liens vers des articles, télécharge leur contenu, puis génère **un fichier unique `output.html`** contenant :
- le titre de chaque article,
- un résumé automatique (en français, via un modèle local Ollama),
- et un rapport final des traitements réussis ou échoués.
## Contexte
J'ai crréé un podcast, Tech Café, qui constitue une veille sur l'actualité tech. Chaque semaine, des conducteurs d'épisode sont rédigés avec des liens hypertexte qui pointent vers des articles d'information tech. Ils sont souvent en anglais. Pour envoyer une newsletter hebdomadaire qui reprend la liste des articles, avec un résumé en français facilement accessible, j'ai préparé ce script. On remplit un répertoire de fichiers HTML et le script les parcourt, ouvre chaque lien, récupère le titre et le contenu, et ajoute pour chaque article, dans un nouveau document, un titre cliquable et un résumé en français.
## 🚀 Fonctionnalités
- Lecture automatique de tous les fichiers `.html` du dossier `input/`
- Nettoyage des URLs (suppression des paramètres de tracking)
- Téléchargement du contenu des articles (en parallèle)
- Résumé automatique en une phrase avec **Ollama**
- Génération d’un fichier `output.html` propre, daté et stylisé
Le résumé s'appuie sur l'utilisation d'un LLM en local (j'ai utilisé `gpt-oss:20b` avec ollama mais on peut utiliser n'importe quel LLM)
## ⚙️ Développement
⚠️ Afin de me prêter à l'exercice du vibe-coding, j'ai développé 90% de ce script avec des interactions avec ChatGPT (GPT-5). Je suis évidemment largement preneur de feedbacks sur le code délivré.
## 📦 Installation
Sur macOS :
```bash
brew install python
```

Télécharger : https://ollama.com/download

Installer un modèle :
```bash
ollama pull gpt-oss:20b
```

Tester :
```bash
ollama run mistral:instruct "Résume ceci en une phrase : Tech Café est vraiment un super podcast sur la tech !"
```

Ollama doit être lancé avant d'exécuter le script.

```bash
git clone https://github.com/<votre-utilisateur>/resume-articles.git
cd resume-articles
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Arborescence
```
resume-articles/
├─ input/            # placez vos fichiers .html ici
├─ output.html       # fichier généré
├─ resume_articles.py
└─ README.md
```

## ⚙️ Utilisation
1. Créez un dossier input/ au même emplacement que le script et placez un ou plusieurs fichiers .html dans.

2. Lancez le script :
```bash
source .venv/bin/activate
python resume_articles.py
```
Ouvrez output.html à la racine du projet.

## 🔧 Configuration

Ouvrez resume_articles.py et ajustez :

Modèle LLM :
```
LLM = "mistral:instruct"  # ou "gpt-oss:20b" en fonction du modèle téléchargé dans Ollama
```
Exclusions d’URL :
```
EXCLUDED_PATTERNS = [
    "reuters.com", "facebook.com", "linkedin.com", "medium.com", "x.com",
]
```
Concurrence (connexions HTTP simultanées) :
```
CONCURRENT_REQUESTS = 3
```
Filtrage du texte parasite : le script supprime les paragraphes de footer/cookies/newsletters et applique des filtres spécifiques pour certains domaines (TechCrunch, The Verge) afin d’éviter les mentions de « digest ».
