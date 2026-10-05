#!/usr/bin/env python3
"""Trendtrack Google Ads: texte visible (OCR local) et couverture. macOS."""
import argparse
import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
def configured_url():
    value = os.environ.get('TRENDTRACK_URL', '')
    config = ROOT.parent / '.env'
    if not value and config.exists():
        for line in config.read_text().splitlines():
            if line.startswith('TRENDTRACK_URL='):
                value = line.split('=', 1)[1].strip()
    return value or 'https://app.trendtrack.io'

DEFAULT_URL = configured_url()

# Sélecteurs vérifiés sur les cartes Google de Trendtrack le 5 octobre 2026.
EXTRACT = r'''() => Array.from(document.querySelectorAll('div.group'))
  .filter(e => Array.from(e.querySelectorAll('button')).some(b => b.textContent.trim() === 'Détails'))
  .map(e => {
    const image = e.querySelector('img[src*="medias.trendtrack.io/google/"]');
    return {image: image?.src || '',
      couverture: e.querySelector('svg.lucide-eye')?.parentElement?.textContent?.trim() || ''};
  })'''

SCROLL = r'''() => {
  const e = document.querySelector('.stable-scrollbar-gutter.overflow-auto');
  if (!e) throw Error('Zone de défilement Trendtrack introuvable');
  const before = e.scrollTop;
  e.scrollBy(0, Math.max(400, e.clientHeight * 0.85));
  return {bottom:e.scrollTop + e.clientHeight >= e.scrollHeight - 5, moved:e.scrollTop !== before};
}'''

def safe_cell(value):
    # Empêcher Excel d'interpréter du texte publicitaire comme une formule.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value

def manual_login(url, local):
    """Authentification humaine dans Chrome standard, sans Playwright/CDP."""
    chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    if not chrome.exists():
        raise RuntimeError('Google Chrome doit être installé dans Applications.')
    profile = local / 'profil'
    if os.path.lexists(profile / 'SingletonLock'):
        raise RuntimeError('Le navigateur dédié est déjà ouvert. Arrête le scraper (Ctrl+C), puis quitte son Chrome et réessaie. Aucun profil ne sera supprimé.')
    print('\nChrome va démarrer normalement, sans automatisation.', flush=True)
    print('1. Connecte-toi à Trendtrack avec Google dans cette fenêtre.')
    print('2. Vérifie que les annonces sont accessibles.')
    print('3. Dans CE Chrome dédié, utilise Chrome > Quitter Google Chrome (⌘Q).')
    print('4. Lance ensuite Lancer.command pour choisir les filtres et extraire.\n', flush=True)
    with (local / 'connexion-chrome.log').open('a') as log:
        result = subprocess.run([str(chrome), '--user-data-dir=' + str(profile), url], stdout=log, stderr=log)
    if result.returncode:
        raise RuntimeError('Chrome a quitté avec une erreur. Voir .local/connexion-chrome.log.')
    print('Chrome fermé. Si la connexion Trendtrack a réussi, tu peux lancer Lancer.command.')
    return 0

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=DEFAULT_URL)
    parser.add_argument('--max', type=int, default=0, help='Nombre maximal à traiter ; 0 = sans limite')
    parser.add_argument('--connexion', action='store_true', help='Ouvrir Chrome normalement pour se connecter, sans automatisation')
    args = parser.parse_args()
    if args.max < 0:
        parser.error('--max doit être positif ou nul')
    if urlparse(args.url).hostname != 'app.trendtrack.io' or urlparse(args.url).scheme != 'https':
        parser.error('Utilisez une URL https://app.trendtrack.io/...')
    os.umask(0o077)
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    if args.connexion:
        return manual_login(args.url, local)
    if os.path.lexists(local / 'profil' / 'SingletonLock'):
        raise RuntimeError('Quitte le Chrome dédié à la connexion (⌘Q) avant de lancer le scraper.')
    from playwright.sync_api import sync_playwright
    from rapidocr_onnxruntime import RapidOCR
    print('Préparation de la reconnaissance de texte locale…', flush=True)
    ocr = RapidOCR()
    out = ROOT / 'exports' / datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')
    out.mkdir(parents=True)
    (out / 'images').mkdir()
    csv_path = out / 'annonces.csv'
    seen = set()
    errors = []
    reason = 'interrompu'
    count = 0
    with sync_playwright() as p:
        # Chrome normal chiffre sa session avec le trousseau macOS réel.
        # Garder le même stockage lors du passage à Playwright.
        context = p.chromium.launch_persistent_context(
            str(local / 'profil'), channel='chrome', headless=False,
            ignore_default_args=['--use-mock-keychain', '--password-store=basic'],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(args.url, wait_until='domcontentloaded', timeout=60000)
            try:
                page.get_by_role('button', name='Détails', exact=True).first.wait_for(timeout=30000)
            except Exception:
                raise RuntimeError(
                    'La liste des annonces n’est pas accessible. Si la connexion est demandée, '
                    'utilise Se-connecter.command, vérifie que les annonces sont visibles, '
                    'puis quitte ce Chrome avec ⌘Q et relance Lancer.command. '
                    'Ne tente pas de connexion Google dans cette fenêtre automatisée. '
                    'Une recherche sans résultats peut également provoquer cet arrêt.'
                ) from None
            print('\nRègle tes filtres Google Ads dans la fenêtre Chrome dédiée.')
            print('Si tu es déconnecté : arrête avec Ctrl+C, puis lance Se-connecter.command avant de réessayer.')
            input('Quand les annonces sont affichées, appuie sur Entrée ici : ')
            selected_url = page.url
            if urlparse(selected_url).hostname != 'app.trendtrack.io' or parse_qs(urlparse(selected_url).query).get('platform') != ['google']:
                raise RuntimeError('Ouvre la liste Google Ads avant de lancer l’extraction.')
            (out / 'recherche.txt').write_text(selected_url, encoding='utf-8')
            page.get_by_role('button', name='Détails', exact=True).first.wait_for(timeout=30000)
            if page.get_by_role('dialog', name='Ad details').count():
                page.get_by_role('button', name='Fermer le panneau').click()
            page.locator('.stable-scrollbar-gutter.overflow-auto').evaluate('(e) => {e.scrollTop = 0}')
            print('Extraction en cours. Ne change pas les filtres dans cette fenêtre. Ctrl+C pour arrêter.')
            idle_bottom = 0
            with csv_path.open('x', newline='', encoding='utf-8-sig') as f, (out / 'annonces.jsonl').open('x', encoding='utf-8') as feed:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['texte_annonce', 'couverture'])
                while True:
                    if page.url != selected_url:
                        raise RuntimeError('La recherche a changé ou la session a expiré. Export partiel conservé.')
                    cards = page.evaluate(EXTRACT)
                    if not cards:
                        raise RuntimeError('Cartes absentes : session, chargement ou interface à vérifier.')
                    added = 0
                    for card in cards:
                        image_url = card['image']
                        if not image_url:
                            continue
                        if image_url in seen:
                            continue
                        seen.add(image_url)
                        added += 1
                        text = ''
                        saved_image = ''
                        temp = local / 'image-ocr'
                        try:
                            if urlparse(image_url).hostname != 'medias.trendtrack.io':
                                raise RuntimeError('Domaine de média inattendu')
                            response = context.request.get(image_url, timeout=30000)
                            if not response.ok:
                                raise RuntimeError(f'Image HTTP {response.status}')
                            image_bytes = response.body()
                            temp.write_bytes(image_bytes)
                            saved_image = 'images/' + hashlib.sha256(image_url.encode()).hexdigest() + '.png'
                            (out / saved_image).write_bytes(image_bytes)
                            response.dispose()
                            result, _ = ocr(str(temp))
                            text = '\n'.join(line[1] for line in (result or []))
                            if not text:
                                errors.append({'image': image_url, 'raison': 'Aucun texte détecté'})
                        except Exception as exc:
                            errors.append({'image': image_url, 'raison': str(exc)})
                        finally:
                            temp.unlink(missing_ok=True)
                        writer.writerow([safe_cell(text), card['couverture']])
                        f.flush()
                        feed.write(json.dumps({'texte_annonce': text, 'couverture': card['couverture'],
                            'image_url': image_url, 'image_path': saved_image}, ensure_ascii=False) + '\n')
                        feed.flush()
                        count += 1
                        print(f'\r{count} annonces enregistrées — {len(errors)} textes à vérifier', end='', flush=True)
                        if args.max and count >= args.max:
                            reason = 'Limite demandée atteinte ; export partiel'
                            break
                    if args.max and count >= args.max:
                        break
                    state = page.evaluate(SCROLL)
                    idle_bottom = idle_bottom + 1 if state['bottom'] and not added else 0
                    if idle_bottom >= 10:
                        reason = 'Bas de liste stable pendant environ 30 secondes ; exhaustivité non garantie'
                        break
                    page.wait_for_timeout(3000 if state['bottom'] else 500)
        except KeyboardInterrupt:
            reason = 'Arrêt demandé ; export partiel'
        except Exception as exc:
            reason = f'Arrêt sur erreur ; export partiel : {exc}'
        finally:
            (out / 'rapport.json').write_text(json.dumps({'annonces': count, 'fin': reason, 'textes_a_verifier': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
            context.close()
        print(f'\n\n{reason}\n{count} annonces. Fichier : {csv_path}')
        return 1 if 'erreur' in reason or count == 0 else 0

if __name__ == '__main__':
    sys.exit(main())
