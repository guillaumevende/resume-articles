import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from tqdm import tqdm
import ollama
from urllib.parse import urlparse, parse_qs, urlunparse, unquote

import subprocess
import sys

def check_ollama_running():
    try:
        result = subprocess.run(
            ["pgrep", "-x", "ollama"], capture_output=True, text=True
        )
        if result.returncode != 0:
            print("⚠️  Ollama ne semble pas être lancé.")
            print("👉 Lancez-le d'abord avec :  open -a Ollama.app")
            print("   ou démarre le service via :  ollama serve &")
            print()
            input("Appuie sur Entrée quand Ollama est prêt...")
    except Exception as e:
        print(f"Impossible de vérifier l’état d’Ollama : {e}")
        input("Appuie sur Entrée pour continuer...")

check_ollama_running()

# --- Constantes ---
INPUT_DIR = "input"
OUTPUT_HTML = "output.html"
CONCURRENT_REQUESTS = 3
LLM = "gpt-oss:20b"

# --- URLs à exclure ---
EXCLUDED_PATTERNS = [
    "techcafe.fr",          # exemple : bloque tout ce domaine
    "guillaumevende.fr",
]

# --- Nettoyage d'une URL ---
def clean_url(url: str) -> str:
    """Nettoie les URLs Google et supprime les paramètres de tracking."""
    url = unquote(url.strip())

    # Liens Google de redirection
    if "google.com/url" in url:
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "q" in params and params["q"]:
                url = params["q"][0]  # vraie URL contenue dans ?q=
        except Exception:
            pass

    # Supprime les paramètres inutiles
    parsed = urlparse(url)
    blocked = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "sa", "source", "ust", "usg"
    }
    qs = parse_qs(parsed.query)
    cleaned_qs = {k: v for k, v in qs.items() if k not in blocked}
    clean_query = "&".join(f"{k}={v[0]}" for k, v in cleaned_qs.items())
    cleaned = parsed._replace(query=clean_query)
    final = urlunparse(cleaned)

    # Corrige les doubles schémas
    if final.startswith("https://https://") or final.startswith("http://https://"):
        final = final.replace("http://https://", "https://").replace("https://https://", "https://")

    return final


# --- Extraction des URLs ---
def extract_urls_from_html(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    urls = [clean_url(a["href"]) for a in soup.find_all("a", href=True)]
    return urls


# --- Sauvegarde des URLs dans un fichier texte ---
def save_urls_to_file(urls, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")


# --- Résumé avec Ollama ---
async def summarize_with_ai(title, content):
    """Utilise le modèle local pour résumer un texte."""
    try:
        prompt = (
            f"Écris un résumé en français le contenu suivant. Attention, sois vigilant au fait de ne faire qu'une seule phrase et ne pas être trop long. Le format est très important.\n\n"
            f"Ne fais pas tes résumés en commençant par 'cet article traite de...' ou équivalent. Le but est d'avoir un résumé qui adresse directement le contenu.\n\n"
            f"Titre : {title}\n\n"
            f"{content}"
        )

        response = ollama.chat(
            model=LLM,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un assistant qui résume fidèlement le contenu d'un article et tu t'exprimes toujours en français, même si le texte d'origine est en anglais. Tu respectes scrupuleusement les consignes et tu veilles à ne pas trop rédiger car tu sais être concis."
                    )
                },
                {"role": "user", "content": prompt}
            ]
        )
        return response["message"]["content"].strip()
    except Exception as e:
        return f"Résumé indisponible ({e})"


# --- Téléchargement du contenu de chaque article ---
async def fetch_article(session, url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
    }

    try:
        async with session.get(url, headers=headers, ssl=False, timeout=20) as resp:
            if resp.status == 401 or resp.status == 403:
                # Fallback rapide pour sites restreints : log et retourne None
                print(f"🔒 {url} → HTTP {resp.status} (accès restreint)")
                return None
            if resp.status != 200:
                print(f"❌ {url} → HTTP {resp.status}")
                return None
            return await resp.text()
    except Exception as e:
        print(f"⚠️ {url} → {e}")
        return None

# --- Traitement complet d'une URL ---
async def process_url(session, url, semaphore):
    """
    Télécharge l'article et génère un résumé.
    Retourne toujours (title, summary), même en cas d'erreur.
    """

    async with semaphore:
        try:
            html = await fetch_article(session, url)

            # Si rien n'a été récupéré
            if not html:
                return "Erreur de chargement", "Résumé indisponible (contenu inaccessible)"

            # Extrait le titre
            soup = BeautifulSoup(html, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.text.strip() if title_tag else "Titre non trouvé"

            # Récupère le texte
            # --- Extraction et nettoyage des paragraphes pertinents ---
            paragraphs = []
            for p in soup.find_all("p"):
                t = p.get_text(strip=True)
                if not t:
                    continue

                # Exclusion de textes parasites génériques
                if any(x in t.lower() for x in [
                    "cookie", "newsletter", "subscribe", "sign up", "digest",
                    "privacy policy", "advertisement", "adblock", "accept cookies",
                    "breaking bad", "comment", "related article", "get the verge",
                    "connect with", "daily digest", "follow", "open in app"
                ]):
                    continue

                paragraphs.append(t)

            # --- Nettoyage spécifique selon le domaine ---
            domain = urlparse(url).netloc.lower()

            if "techcrunch.com" in domain:
                paragraphs = [p for p in paragraphs if not any(
                    x in p.lower()
                    for x in [
                        "latest news", "artificial intelligence", "amazon apps",
                        "biotech", "climate", "cryptocurrency", "enterprise",
                        "apps", "health", "tc+", "privacy", "advertising"
                    ]
                )]

            elif "theverge.com" in domain:
                paragraphs = [p for p in paragraphs if not any(
                    x in p.lower()
                    for x in [
                        "digest quotidien", "flux d’accueil", "daily digest",
                        "articles de ce sujet", "articles de cet auteur",
                        "s’abonner", "newsletter", "inscrivez-vous", "follow us"
                    ]
                )]

            text = " ".join(paragraphs[:10])

            # Nettoyage spécifique selon le domaine
            domain = urlparse(url).netloc.lower()

            # --- TechCrunch : supprimer les phrases de navigation
            if "techcrunch.com" in domain:
                paragraphs = [p for p in paragraphs if not any(
                    x in p.lower()
                    for x in [
                        "latest news", "artificial intelligence", "amazon apps",
                        "biotech", "climate", "cryptocurrency", "enterprise",
                        "apps", "health", "tc+", "privacy", "advertising"
                    ]
                )]
                text = " ".join(paragraphs[:10])

            # --- The Verge : supprimer les bas de page génériques
            elif "theverge.com" in domain:
                paragraphs = [p for p in paragraphs if not any(
                    x in p.lower()
                    for x in [
                        "daily digest", "subscribe", "newsletter", "follow us",
                        "sign up", "cookie", "privacy policy", "advertisement"
                    ]
                )]
                text = " ".join(paragraphs[:10])

            # Si texte vide
            if not text:
                return title, "Résumé indisponible (aucun texte détecté)"

            # Appel au modèle local pour résumé
            try:
                response = ollama.chat(
                    model=LLM,
                    messages=[{"role": "user", "content": f"Résume ce texte en une phrase en français : {text}"}],
                )
                summary = response["message"]["content"].strip()
            except Exception as e:
                summary = f"Résumé indisponible ({e})"

            return title, summary

        except Exception as e:
            return "Erreur de chargement", f"Résumé indisponible ({e})"

# --- Génération du fichier HTML de sortie ---
from datetime import datetime

async def generate_output_html(urls, output_file):
    """
    Génère un fichier HTML unique compilant les résumés de toutes les URLs.
    Ajoute un en-tête avec titre et date, et écrit les résultats au fur et à mesure.
    """

    import aiohttp
    import asyncio

    total = len(urls)
    success_count = 0
    error_count = 0

    # Création de l'en-tête HTML
    header = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Résumés d’articles - {datetime.now().strftime("%d/%m/%Y")}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      margin: 40px auto;
      max-width: 900px;
      line-height: 1.6;
      color: #212529;
    }}
    h1 {{
      text-align: center;
      color: #004085;
      border-bottom: 2px solid #004085;
      padding-bottom: 10px;
    }}
    .meta {{
      text-align: center;
      font-size: 0.9em;
      color: #666;
      margin-bottom: 40px;
    }}
    .article {{
      margin-bottom: 20px;
      padding: 12px;
      border-left: 4px solid #004085;
      background: #f8f9fa;
      border-radius: 6px;
    }}
    .error {{
      border-left-color: #d9534f;
      background: #fdf2f2;
    }}
    a {{
      font-weight: bold;
      color: #004085;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <h1>Résumés d’articles</h1>
  <div class="meta">Généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")}</div>
"""
    footer = "\n</body>\n</html>"

    # Écrit l'en-tête dans le fichier
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(header)

    semaphore = asyncio.Semaphore(5)  # limite de connexions simultanées

    async with aiohttp.ClientSession() as session:
        for i, url in enumerate(urls, start=1):
            print(f"🔄 ({i}/{total}) Traitement de : {url}")
            title, summary = await process_url(session, url, semaphore)

            with open(output_file, "a", encoding="utf-8") as f:
                if "Erreur" in title or "Résumé indisponible" in summary:
                    error_count += 1
                    f.write(f'''
<div class="article error">
  <a href="{url}">⚠️ Erreur de chargement</a><br />
  <span>{summary}</span>
</div>
''')
                else:
                    success_count += 1
                    f.write(f'''
<div class="article">
  <a href="{url}">{title}</a><br />
  <span>{summary}</span>
</div>
''')

    # Ajoute le pied de page
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"""
<hr />
<p><strong>Synthèse du traitement</strong><br />
✅ Articles traités avec succès : {success_count}<br />
⚠️ Erreurs de chargement ou résumé : {error_count}<br />
📄 Total d’articles analysés : {total}
</p>
{footer}
""")

    print("\n--- Synthèse du traitement ---")
    print(f"✅ Articles traités avec succès : {success_count}")
    print(f"⚠️ Erreurs de chargement ou résumé : {error_count}")
    print(f"📄 Total d’articles analysés : {total}")
    print(f"🗂️  Fichier généré : {output_file}")


def collect_urls_from_directory(input_dir):
    """Parcourt tous les fichiers HTML du dossier input et extrait toutes les URLs."""
    all_urls = []

    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".html"):
            continue

        path = os.path.join(input_dir, filename)
        urls = extract_urls_from_html(path)
        all_urls.extend(urls)
        print(f"✅ {len(urls)} URL(s) extraites depuis {filename}")

    # Supprime les doublons
    all_urls = list(dict.fromkeys(all_urls))
    print(f"\n🌐 Total unique : {len(all_urls)} URL(s) collectées dans '{input_dir}'\n")

    return all_urls

# --- Programme principal ---
async def main():
    # Récupère toutes les URLs de tous les fichiers du dossier input/
    urls = collect_urls_from_directory(INPUT_DIR)

    if not urls:
        print("Aucune URL trouvée. Vérifie que le dossier 'input/' contient des fichiers HTML.")
        return

    # Applique le filtre d’exclusion s’il existe
    urls = [u for u in urls if not any(p in u for p in EXCLUDED_PATTERNS)]

    print(f"{len(urls)} URL(s) à traiter après filtrage.\n")

    await generate_output_html(urls, OUTPUT_HTML)


if __name__ == "__main__":
    asyncio.run(main())