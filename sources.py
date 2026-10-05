# -*- coding: utf-8 -*-
"""
Sources de stickers EN ACCES LIBRE (aucune cle API, aucune inscription) :
- Packs Telegram via l'annuaire public combot.org (HTML + CDN direct)
- Recherche de stickers animes via le site public tenor.com
- Import par URL directe
Les webp/gif telecharges sont convertis en PNG transparent par Pillow.
"""

import os
import sys
import io
import re
import json
import glob
import hashlib
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import langue

DOSSIER_BASE = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
DOSSIER_STICKERS = os.path.join(DOSSIER_BASE, "stickers")
DOSSIER_CACHE = os.path.join(DOSSIER_BASE, ".cache_vignettes")
FICHIER_CONFIG = os.path.join(DOSSIER_BASE, "biblios.json")
TAILLE_VIGNETTE = 384          # px du plus grand cote (cache disque)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

_CACHE_PACKS = {}
_CACHE_PACKS_FILE = os.path.join(DOSSIER_BASE, ".cache_packs.json")

def _sauver_cache_packs():
    try:
        with open(_CACHE_PACKS_FILE, "w", encoding="utf-8") as f:
            json.dump(_CACHE_PACKS, f)
    except Exception:
        pass

def _charger_cache_packs():
    global _CACHE_PACKS
    try:
        if os.path.exists(_CACHE_PACKS_FILE):
            with open(_CACHE_PACKS_FILE, "r", encoding="utf-8") as f:
                _CACHE_PACKS = json.load(f)
    except Exception:
        _CACHE_PACKS = {}

_charger_cache_packs()
_OPENER = urllib.request.build_opener()

# Cache de recherche Tenor
_CACHE_RECHERCHE = {}
_CACHE_RECHERCHE_FILE = os.path.join(DOSSIER_BASE, ".cache_recherche.json")


MAX_CACHE_RECHERCHE = 300     # evite un JSON qui grossit sans fin


def _sauver_cache_recherche():
    try:
        if len(_CACHE_RECHERCHE) > MAX_CACHE_RECHERCHE:
            vieux = sorted(_CACHE_RECHERCHE,
                           key=lambda k: _CACHE_RECHERCHE[k].get("ts", 0))
            for k in vieux[:len(_CACHE_RECHERCHE) - MAX_CACHE_RECHERCHE]:
                del _CACHE_RECHERCHE[k]
        tmp = _CACHE_RECHERCHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_CACHE_RECHERCHE, f, ensure_ascii=False,
                      separators=(",", ":"))
        os.replace(tmp, _CACHE_RECHERCHE_FILE)
    except Exception:
        pass


def _charger_cache_recherche():
    global _CACHE_RECHERCHE
    try:
        if os.path.exists(_CACHE_RECHERCHE_FILE):
            with open(_CACHE_RECHERCHE_FILE, "r", encoding="utf-8") as f:
                _CACHE_RECHERCHE = json.load(f)
    except Exception:
        _CACHE_RECHERCHE = {}


_charger_cache_recherche()


def _cle_cache_recherche(q, hd=False):
    return hashlib.md5(f"multi2:{q}:{hd}".encode()).hexdigest()


def _cle_url_cache(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def charger_image_cache(url):
    """Charge une image PNG convertie depuis le cache disque si presente."""
    try:
        cle = _cle_url_cache(url)
        cache = os.path.join(DOSSIER_CACHE, f"web_{cle}.png")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                data = f.read()
            try:
                os.utime(cache)        # "recemment utilise" pour le nettoyage
            except OSError:
                pass
            return data
    except Exception:
        pass
    return None


def sauver_image_cache(url, png_data):
    """Sauvegarde une image PNG convertie dans le cache disque."""
    if not png_data:
        return
    try:
        os.makedirs(DOSSIER_CACHE, exist_ok=True)
        cle = _cle_url_cache(url)
        cache = os.path.join(DOSSIER_CACHE, f"web_{cle}.png")
        tmp = cache + ".tmp"
        with open(tmp, "wb") as f:
            f.write(png_data)
        os.replace(tmp, cache)
    except Exception:
        pass


def fetch_image_png(url, timeout=8):
    """Recupere une image (depuis le cache disque si dispo, sinon web + cache)."""
    cached = charger_image_cache(url)
    if cached:
        return cached
    try:
        raw = _http(url, timeout=timeout)
        png = convertir_png(raw)
        if png:
            sauver_image_cache(url, png)
        return png
    except Exception:
        return None


CACHE_RECHERCHE_DUREE = 3600
_OPENER.addheaders = list(UA.items())

# (label, mot-cle, nombre de pages de 9 packs)
THEMES = [
    ("Chats populaires", "cat", 3),
    ("Chatons", "kitten", 2),
    ("Minous", "kitty", 2),
    ("Pusheen", "pusheen", 1),
    ("Miaou", "meow", 1),
    ("Neko / manga", "neko", 1),
    ("Mignons", "cute", 1),
]


# Client HTTP haute performance avec pool de connexions persistantes (Keep-Alive)
_SESSION = None
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _SESSION = requests.Session()
    _SESSION.trust_env = False  # Evite les blocages sur proxys Windows obsoletes
    _adapter = HTTPAdapter(
        pool_connections=35,
        pool_maxsize=35,
        max_retries=Retry(total=1, backoff_factor=0.1)
    )
    _SESSION.mount('https://', _adapter)
    _SESSION.mount('http://', _adapter)
    _SESSION.headers.update(UA)
    _SESSION.headers.update({"Accept-Encoding": "gzip, deflate"})
except Exception:
    _SESSION = None

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_OPENER.addheaders = list(UA.items())


# ----------------------------------------------------------------- reseau
# Route automatique (utile en Chine) : pour chaque site on met en
# concurrence la connexion directe et le proxy systeme (Clash, v2rayN...),
# on garde la plus rapide et on la memorise sur disque.
import threading
import time as _time

_PROXY_SYS = {k: v for k, v in urllib.request.getproxies().items()
              if k in ("http", "https")}
_ROUTES_FILE = os.path.join(DOSSIER_BASE, ".routes_reseau.json")
_ROUTES_DUREE = 6 * 3600       # re-test des routes toutes les 6 h
_ROUTES_LOCK = threading.Lock()
try:
    with open(_ROUTES_FILE, "r", encoding="utf-8") as _f:
        _ROUTES = json.load(_f)
except Exception:
    _ROUTES = {}


def _hote(url):
    return urllib.parse.urlparse(url).hostname or ""


def _memoriser_route(hote, route):
    with _ROUTES_LOCK:
        if _ROUTES.get(hote, {}).get("r") == route:
            return
        _ROUTES[hote] = {"r": route, "ts": _time.time()}
        try:
            with open(_ROUTES_FILE, "w", encoding="utf-8") as f:
                json.dump(_ROUTES, f)
        except Exception:
            pass


def _route_connue(hote):
    r = _ROUTES.get(hote)
    if r and _time.time() - r.get("ts", 0) < _ROUTES_DUREE:
        return r.get("r")
    return None


def _requete(url, route, data=None, headers=None, timeout=5):
    """Une requete via la route donnee ('direct' ou 'proxy')."""
    proxies = _proxys_actifs() if route == "proxy" else {}
    if _SESSION is not None:
        h = dict(headers) if headers else None
        if data is not None:
            resp = _SESSION.post(url, data=data, headers=h, timeout=timeout,
                                 proxies=proxies)
        else:
            resp = _SESSION.get(url, headers=h, timeout=timeout,
                                proxies=proxies)
        resp.raise_for_status()
        return resp.content
    opener = _OPENER_PROXY if route == "proxy" else _OPENER
    req = urllib.request.Request(url, data=data, headers=headers or UA)
    with opener.open(req, timeout=timeout) as r:
        return r.read()


_OPENER_PROXY = urllib.request.build_opener(
    urllib.request.ProxyHandler(_PROXY_SYS))
_OPENER_PROXY.addheaders = list(UA.items())


_PROXY_VU_TS = 0.0
_PROXY_LOCK = threading.Lock()


def _maj_proxy_si_besoin(delai=25):
    """Relit les proxys systeme (Clash, Hiddify, v2rayN...).

    Sans ca, _PROXY_SYS est fige au demarrage : si le VPN n'etait pas
    lance a ce moment-la, tenor.com reste injoignable jusqu'au prochain
    redemarrage de l'application."""
    global _PROXY_SYS, _OPENER_PROXY, _PROXY_VU_TS
    if _time.time() - _PROXY_VU_TS < delai:
        return _PROXY_SYS
    with _PROXY_LOCK:
        if _time.time() - _PROXY_VU_TS < delai:
            return _PROXY_SYS
        _PROXY_VU_TS = _time.time()
        try:
            p = {k: v for k, v in urllib.request.getproxies().items()
                 if k in ("http", "https")}
        except Exception:
            p = {}
        if p != _PROXY_SYS:
            _PROXY_SYS = p
            try:
                _OPENER_PROXY = urllib.request.build_opener(
                    urllib.request.ProxyHandler(_PROXY_SYS))
                _OPENER_PROXY.addheaders = list(UA.items())
            except Exception:
                pass
        return _PROXY_SYS



# ------------------------------------------------- proxys locaux automatiques
# Si le proxy systeme de Windows est desactive (Clash/v2rayN en mode "clear"),
# _PROXY_SYS est vide et tenor.com reste injoignable. On cherche donc un proxy
# local deja en ecoute (Clash, v2rayN, Hiddify, sing-box...) et on l'utilise.
_PROXY_AUTO = None
_PROXY_AUTO_OK = 0.0        # date du dernier succes
_PROXY_AUTO_KO = 0.0        # date du dernier echec (evite de sonder sans fin)
_PROXY_CANDIDATS = (10808, 10809, 20808, 20809, 7890, 7897, 7891, 1080,
                    2080, 8889, 20171, 9910, 8090, 1081)
_PROXY_TEST_URL = "https://tenor.com/"


def _port_ouvert(port, delai=0.35):
    import socket
    s = socket.socket()
    s.settimeout(delai)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _essai_proxy(proxy, timeout=6):
    try:
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        op.addheaders = list(UA.items())
        with op.open(_PROXY_TEST_URL, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False


def _chercher_proxy_local(delai_ko=120):
    """Renvoie True si un proxy local joignant tenor.com a ete trouve."""
    global _PROXY_AUTO, _PROXY_AUTO_OK, _PROXY_AUTO_KO
    maintenant = _time.time()
    if _PROXY_AUTO and maintenant - _PROXY_AUTO_OK < 900:
        return True
    if maintenant - _PROXY_AUTO_KO < delai_ko:
        return False
    for port in _PROXY_CANDIDATS:
        if not _port_ouvert(port):
            continue
        proxy = "http://127.0.0.1:%d" % port
        if _essai_proxy(proxy):
            _PROXY_AUTO = proxy
            _PROXY_AUTO_OK = _time.time()
            return True
    _PROXY_AUTO = None
    _PROXY_AUTO_KO = _time.time()
    return False


def _proxys_actifs():
    """Proxys a utiliser : systeme d'abord, sinon proxy local detecte."""
    if _PROXY_SYS:
        return _PROXY_SYS
    if _PROXY_AUTO and _time.time() - _PROXY_AUTO_OK < 900:
        return {"http": _PROXY_AUTO, "https": _PROXY_AUTO}
    return {}

def _course(url, data, headers, timeout):
    """Lance direct + proxy en parallele, renvoie le premier succes."""
    fini = threading.Event()
    res = {}

    def essai(route):
        try:
            contenu = _requete(url, route, data, headers, timeout)
            if not fini.is_set():
                res["ok"] = (route, contenu)
                fini.set()
        except Exception as e:
            res.setdefault("err", []).append(e)
            if len(res["err"]) == 2:
                fini.set()

    for route in ("direct", "proxy"):
        threading.Thread(target=essai, args=(route,), daemon=True).start()
    fini.wait(timeout + 1)
    if "ok" in res:
        route, contenu = res["ok"]
        _memoriser_route(_hote(url), route)
        return contenu
    raise (res.get("err") or [TimeoutError(url)])[0]


def _http(url, data=None, headers=None, timeout=5):
    """Requete HTTP Keep-Alive, par la route (directe/proxy) la plus rapide."""
    _maj_proxy_si_besoin()
    if not _proxys_actifs():
        try:
            return _requete(url, "direct", data, headers, timeout)
        except Exception:
            # direct bloque (tenor.com filtre ?) -> on cherche un proxy local
            if _chercher_proxy_local():
                return _requete(url, "proxy", data, headers, timeout)
            raise
    hote = _hote(url)
    route = _route_connue(hote)
    if route is None:
        return _course(url, data, headers, timeout)
    try:
        return _requete(url, route, data, headers, timeout)
    except Exception:
        autre = "direct" if route == "proxy" else "proxy"
        contenu = _requete(url, autre, data, headers, timeout)
        _memoriser_route(hote, autre)
        return contenu


def prechauffer_reseau(file_q=None):
    """Au demarrage : choisit la route et ouvre les connexions TLS vers
    Tenor (la 1re recherche ne paie plus la poignee de main)."""
    for u in ("https://tenor.com/", "https://media.tenor.com/"):
        try:
            _http(u, timeout=6)
        except Exception:
            pass


def _http_parallel(urls, timeout=6, workers=12):
    def une(u):
        try: return u, _http(u, timeout=timeout)
        except: return u, None
    with ThreadPoolExecutor(workers) as p:
        return list(p.map(une, urls))


def _html(url, timeout=12):
    res = _http(url, timeout=timeout)
    if isinstance(res, bytes):
        return res.decode("utf-8", "ignore")
    return str(res)


def _nettoyer(nom):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in nom)


# ----------------------------------------------------------------- images
def _retirer_fond_blanc(im, seuil=200):
    """Rend transparent le fond clair connecte aux bords (GIF sans alpha).
    Preservation des zones claires INTERNES non connectees (fourrure...)."""
    import numpy as np
    from PIL import Image, ImageDraw
    rgba = im.convert("RGBA")
    arr = np.array(rgba)
    h, w = arr.shape[:2]

    # deja transparent ?
    if (arr[:, :, 3] < 250).mean() > 0.01:
        return im

    rgb = rgba.convert("RGB")
    sentinelle = (255, 0, 255)
    # flood fill natif (C) depuis chaque bord clair non encore atteint
    for x in range(0, w, 6):
        for y in (0, h - 1):
            if rgb.getpixel((x, y)) != sentinelle and \
                    min(rgb.getpixel((x, y))) >= seuil:
                ImageDraw.floodfill(rgb, (x, y), sentinelle, thresh=50)
    for y in range(0, h, 6):
        for x in (0, w - 1):
            if rgb.getpixel((x, y)) != sentinelle and \
                    min(rgb.getpixel((x, y))) >= seuil:
                ImageDraw.floodfill(rgb, (x, y), sentinelle, thresh=50)

    r = np.array(rgb)
    m = (r[:, :, 0] == 255) & (r[:, :, 1] == 0) & (r[:, :, 2] == 255)
    if m.mean() < 0.005:          # pas de fond detectable : on ne touche a rien
        return im
    arr[m, 3] = 0

    # liseré doux sur 1 px pour eviter la bordure dure
    clair = (arr[:, :, :3].astype(np.int16).min(axis=2) >= seuil)
    halo = np.zeros_like(m)
    halo[1:, :] |= m[:-1, :]
    halo[:-1, :] |= m[1:, :]
    halo[:, 1:] |= m[:, :-1]
    halo[:, :-1] |= m[:, 1:]
    liser = halo & ~m & clair
    arr[liser, 3] = 130

    return Image.fromarray(arr, "RGBA")


def convertir_png(data):
    """WebP/GIF -> PNG transparent (1ere image pour les animations).
    Supprime aussi le fond blanc des GIF qui n'ont pas de couche alpha."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data
    try:
        from PIL import Image
        bio = io.BytesIO(data)
        im = Image.open(bio)
        is_gif = (getattr(im, "format", "") == "GIF")
        im = im.convert("RGBA")
        if is_gif and (np_alpha(im) < 250).mean() <= 0.01:
            im = _retirer_fond_blanc(im)
        out = io.BytesIO()
        im.save(out, format="PNG", compress_level=1)
        return out.getvalue()
    except Exception:
        return None


def np_alpha(im):
    import numpy as np
    return np.array(im)[:, :, 3]


def sauver_png(png_data, dossier, nom):
    """Ecrit directement des octets PNG (deja convertis/prepares)."""
    os.makedirs(dossier, exist_ok=True)
    base = _nettoyer(nom)
    chemin = os.path.join(dossier, base + ".png")
    n = 1
    while os.path.exists(chemin):
        chemin = os.path.join(dossier, f"{base}_{n}.png")
        n += 1
    with open(chemin, "wb") as f:
        f.write(png_data)
    return chemin


def sauver_image(data, dossier, nom):
    os.makedirs(dossier, exist_ok=True)
    png = convertir_png(data)
    if png is None:
        raise ValueError("image illisible")
    png = preparer_image(png)      # HD : agrandit les petites sources (512 px)
    base = _nettoyer(nom)
    chemin = os.path.join(dossier, base + ".png")
    n = 1
    while os.path.exists(chemin):
        chemin = os.path.join(dossier, f"{base}_{n}.png")
        n += 1
    with open(chemin, "wb") as f:
        f.write(png)
    return chemin


# ===================================================== PACKS TELEGRAM =====
COMBOT_SEARCH = "https://combot.org/telegram/stickers?q={q}&page={p}"
COMBOT_PACK = "https://combot.org/stickers/{slug}"
COMBOT_CDN_RE = re.compile(r'data-src="(https://cdn\.combot\.online/[^"]+?\.webp)"')
COMBOT_LD_RE = re.compile(
    r'"name":"((?:[^"\\]|\\.)*)","url":"(https://combot\.org/stickers/[^"]+)"')
COMBOT_TITLE_RE = re.compile(r"<title>([^<]+)</title>")


def combot_recherche(requete, page=1):
    """Retourne [(titre, slug)] depuis l'annuaire combot (sans cle)."""
    url = COMBOT_SEARCH.format(q=urllib.parse.quote(requete), p=page)
    h = _html(url)
    out, vus = [], set()
    for bloc in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            h, re.S):
        try:
            data = json.loads(bloc)
        except Exception:
            continue
        graph = data.get("@graph", [data])
        for node in graph:
            if node.get("@type") != "CollectionPage":
                continue
            for el in node.get("mainEntity", {}).get("itemListElement", []):
                u = el.get("url", "")
                slug = u.rsplit("/", 1)[-1]
                if slug and slug not in vus:
                    vus.add(slug)
                    out.append((el.get("name", slug), slug))
    return out


def combot_pack(slug):
    """Ouvre une page pack : {'titre', 'slug', 'urls': [...webp...]}."""
    h = _html(COMBOT_PACK.format(slug=urllib.parse.quote(slug)))
    urls = list(dict.fromkeys(COMBOT_CDN_RE.findall(h)))
    m = COMBOT_TITLE_RE.search(h)
    titre = m.group(1).replace("— Telegram stickers", "").strip() \
        if m else slug
    titre = titre.replace("&amp;", "&")
    return {"titre": titre, "slug": slug, "urls": urls}


# -- operations en arriere-plan (recoivent une queue vers l'UI) -----------
def combot_catalogue(file_q):
    """Catalogue construit en parallele a partir des recherches thematiques."""
    taches = []
    for theme, mot, pages in THEMES:
        for p in range(1, pages + 1):
            taches.append((theme, mot, p))

    def fetch(t):
        theme, mot, p = t
        try:
            return theme, combot_recherche(mot, p)
        except Exception:
            return theme, []

    catalogue = []
    vus = set()
    with ThreadPoolExecutor(8) as pool:
        for theme, res in pool.map(fetch, taches):
            for titre, slug in res:
                if slug in vus:
                    continue
                vus.add(slug)
                catalogue.append({"theme": theme, "titre": titre,
                                  "slug": slug})
            file_q.put(("tg_catalog", list(catalogue)))
            file_q.put(("status", langue.T("Catalogue : {n} packs").format(n=len(catalogue))))
    file_q.put(("tg_catalog_done", True))
    file_q.put(("status", langue.T("{n} packs Telegram prets").format(n=len(catalogue))))


def combot_chercher_pack(requete, file_q):
    """Mots-cles -> liste de packs (repli mot par mot)."""
    file_q.put(("status", langue.T("Recherche de packs : {q}").format(q=requete)))
    try:
        mots = [m for m in re.split(r"[^a-zA-Z0-9]+", requete) if len(m) > 1]
        resultat, vus = [], set()
        for mot in mots or [requete]:
            for p in range(1, 3):
                for titre, slug in combot_recherche(mot, p):
                    if slug not in vus:
                        vus.add(slug)
                        resultat.append({"theme": "Resultats",
                                         "titre": titre, "slug": slug})
        file_q.put(("tg_search", resultat))
        file_q.put(("status", langue.T("{n} packs trouves").format(n=len(resultat))))
    except Exception as e:
        if not _PROXY_SYS:
            file_q.put(("error", langue.T(
                "Tenor injoignable : active ton VPN/proxy "
                "(Clash, Hiddify) puis relance la recherche.")))
        else:
            file_q.put(("error", str(e)))


def combot_ouvrir(slug, file_q):
    """Ouvre un pack et envoie les vignettes (18 premieres), (url, png).
    Telechargement en parallele, resolution d'origine (affichage net)."""
    file_q.put(("status", langue.T("Ouverture {slug}...").format(slug=slug)))
    try:
        pack = combot_pack(slug)
        file_q.put(("tg_pack", pack))

        def une(u):
            png = fetch_image_png(u, timeout=10)
            return (u, png) if png else None

        vign = []
        with ThreadPoolExecutor(8) as pool:
            futurs = [pool.submit(une, u) for u in pack["urls"][:18]]
            for fut in as_completed(futurs):
                res = fut.result()
                if res:
                    vign.append(res)
                    file_q.put(("tg_thumbs", list(vign)))
        file_q.put(("status", f"{pack['titre']} : {len(pack['urls'])} stickers"))
    except Exception as e:
        file_q.put(("error", f"Pack introuvable ({e})"))


def combot_telecharger(slug, file_q):
    """Telecharge tout le pack (20 stickers max cote combot)."""
    try:
        pack = combot_pack(slug)
    except Exception as e:
        file_q.put(("error", str(e)))
        return
    dossier = os.path.join(DOSSIER_STICKERS, "tg_" + _nettoyer(slug))
    deja = {os.path.basename(p)
            for p in glob.glob(os.path.join(dossier, "*.png"))}
    nb = 0
    for i, u in enumerate(pack["urls"]):
        nom = f"{i+1:03d}"
        if nom + ".png" in deja:
            continue
        try:
            sauver_image(_http(u, timeout=10), dossier, nom)
            nb += 1
            if (i + 1) % 5 == 0:
                file_q.put(("status", f"{pack['titre']} : {i+1}/"
                                      f"{len(pack['urls'])}"))
        except Exception as e:
            file_q.put(("status", f"sticker {i+1} ignore"))
    file_q.put(("downloaded", dossier))
    file_q.put(("status", f"Pack '{pack['titre']}' ajoute ({nb} nouveaux)"))


# ============================================================ TENOR ======
TENOR_SEARCH = "https://tenor.com/search/{q}-stickers"
TENOR_WEBP_RE = re.compile(
    r"(https://media(?:[0-9]+)?\.tenor\.com/[A-Za-z0-9_\-/]+?\.webp)")


# ------------------------------------------------ recherche multi-sources
GIPHY_SEARCH = "https://giphy.com/search/{q}-stickers"
GIPHY_ID_RE = re.compile(
    r"giphy\.com/media/(?:v1\.[A-Za-z0-9]+/)?([A-Za-z0-9]{8,24})/(?:200|giphy)")
STICKERLY_SEARCH = "https://sticker.ly/s/search?keyword={q}"
STICKERLY_RE = re.compile(
    r"https://stickerly\.pstatic\.net/sticker_pack/[^\"'\s]+?\.(?:png|webp)")


def _urls_tenor(slug, n):
    h = _html(TENOR_SEARCH.format(q=urllib.parse.quote(slug)), timeout=10)
    return list(dict.fromkeys(TENOR_WEBP_RE.findall(h)))[:n]


GIPHY_RES_RE = re.compile(
    r"https://giphy\.com/stickers/[a-z0-9-]*?-?([A-Za-z0-9]{8,24})[\"/?]")


def _urls_giphy(slug, n):
    """Resultats reels uniquement (la page contient aussi des tendances)."""
    h = _html(GIPHY_SEARCH.format(q=urllib.parse.quote(slug)), timeout=10)
    ids = list(dict.fromkeys(GIPHY_RES_RE.findall(h)))[:n]
    return [f"https://media.giphy.com/media/{i}/200.gif" for i in ids]


STICKERLY_API = "https://api.sticker.ly/v4/stickerPack/smartSearch"
STICKERLY_UA = "androidapp.stickerly/3.17.0 (M2012K11AG; U; Android 29; en-US; us;)"


def _urls_stickerly(slug, n, par_pack=3):
    """Packs dont le nom contient le mot cherche (sinon les 2 premiers),
    quelques stickers par pack pour varier."""
    mot = slug.replace("-", " ")
    corps = json.dumps({"keyword": mot, "enabledKeywordSearch": True,
                        "filter": {"extendSearchResult": False,
                                   "sortBy": "RECOMMENDED",
                                   "languages": ["ALL"], "minStickerCount": 5,
                                   "searchBy": "ALL", "stickerType": "ALL"}})
    data = json.loads(_http(STICKERLY_API, data=corps.encode(), timeout=10,
                            headers={"Content-Type": "application/json",
                                     "User-Agent": STICKERLY_UA}))
    packs = data.get("result", {}).get("stickerPacks", []) or []
    termes = [t for t in mot.lower().split() if t]
    bons = [pk for pk in packs
            if any(t in (pk.get("name") or "").lower() for t in termes)]
    urls = []
    for pk in (bons or packs[:2]):
        base = pk.get("resourceUrlPrefix", "")
        for f in (pk.get("resourceFiles") or [])[:par_pack]:
            urls.append(base + f)
        if len(urls) >= n:
            break
    return urls[:n]


def _urls_risibank(slug, n):
    return risibank_recherche(slug.replace("-", " "), max_urls=n)


SOURCES_RECHERCHE = (_urls_tenor, _urls_risibank, _urls_giphy,
                     _urls_stickerly)


def urls_multi_sources(slug, n=36):
    """Tenor + Giphy + Sticker.ly en parallele, resultats entrelaces."""
    listes = []
    with ThreadPoolExecutor(len(SOURCES_RECHERCHE)) as pool:
        futurs = [pool.submit(f, slug, n) for f in SOURCES_RECHERCHE]
        for fut in futurs:
            try:
                listes.append(fut.result())
            except Exception:
                listes.append([])
    urls = []
    for groupe in zip(*[l + [None] * (n - len(l)) for l in listes]):
        urls.extend(u for u in groupe if u)
    return list(dict.fromkeys(urls))[:n]


_CJK_RE = re.compile(r"[぀-ヿ一-鿿]")


def _plan_sources(q_trad, q_orig, avec_risibank=True):
    """(fonction, requete) par source : Risibank (FR) recoit le texte
    d'origine, les sources anglophones la traduction ; en chinois on
    evite Risibank (0 resultat) et on passe Sticker.ly en premier."""
    slug = lambda t: re.sub(r"[\W_]+", "-", t.lower()).strip("-")
    en, orig = slug(q_trad), slug(q_orig or q_trad)
    if _CJK_RE.search(q_orig or q_trad):
        return [(_urls_stickerly, orig), (_urls_tenor, orig),
                (_urls_giphy, orig)]
    # Sticker.ly cherche par nom de pack ("Barbie Cool" pour "cool") :
    # trop imprecis hors chinois, on ne le garde que pour le CJK.
    plan = [(_urls_tenor, en), (_urls_giphy, en)]
    if avec_risibank:
        plan.append((_urls_risibank, orig))
    return plan


def recherche_multi(q_trad, q_orig, avec_risibank, file_q, n=12):
    """Recherche en flux : chaque source s'affiche des qu'elle repond
    (la plus lente ne bloque plus les autres)."""
    import time
    cle = _cle_cache_recherche(f"flux3:{q_trad}|{q_orig}|{int(bool(avec_risibank))}", False)
    cached = _CACHE_RECHERCHE.get(cle)
    file_q.put(("status", f"Recherche : {q_orig or q_trad}"))
    if cached and cached.get("urls"):
        lots = [cached["urls"]]
    else:
        lots = None
    items_tous, vus = [], set()
    envoye = [False]

    def publier(urls):
        nouv = [u for u in urls if u not in vus]
        vus.update(nouv)
        if not nouv:
            return
        base = len(items_tous)
        items = [{"id": str(base + k), "mini": u, "url": u, "titre": "",
                  "png": charger_image_cache(u)} for k, u in enumerate(nouv)]
        items_tous.extend(items)
        if not envoye[0]:
            envoye[0] = True
            file_q.put(("giphy_results", items))
        else:
            file_q.put(("giphy_append", items))
        for k, it in enumerate(items):
            dl.submit(une_vignette, base + k, it["url"])

    empreintes = set()
    verrou = threading.Lock()

    def une_vignette(idx, u):
        png = fetch_image_png(u, timeout=5)
        if not png:
            file_q.put(("giphy_retirer", u))      # pas de case vide
            return
        try:                                      # meme image, autre source
            from PIL import Image
            im = Image.open(io.BytesIO(png)).convert("L").resize((8, 8))
            px = list(im.getdata())
            moy = sum(px) / 64
            emp = sum(1 << k for k, v in enumerate(px) if v > moy)
            with verrou:
                if emp in empreintes:
                    file_q.put(("giphy_retirer", u))
                    return
                empreintes.add(emp)
        except Exception:
            pass
        file_q.put(("giphy_item", (u, png)))

    dl = ThreadPoolExecutor(16)      # vignettes : pool partage, non bloquant
    if lots:
        publier(lots[0])
    else:
        plan = _plan_sources(q_trad, q_orig, avec_risibank)
        with ThreadPoolExecutor(len(plan)) as pool:
            futurs = [pool.submit(f, q, n) for f, q in plan]
            for fut in as_completed(futurs):
                try:
                    publier(fut.result())
                except Exception:
                    pass
        if items_tous:
            _CACHE_RECHERCHE[cle] = {"urls": [it["url"] for it in items_tous],
                                     "ts": time.time()}
            _sauver_cache_recherche()
    dl.shutdown(wait=True)
    if not envoye[0]:
        file_q.put(("giphy_results", []))
        file_q.put(("status", "Aucun resultat"))
        return
    file_q.put(("giphy_done", True))
    file_q.put(("status", f"{len(items_tous)} stickers trouves"))


def tenor_recherche(requete, file_q):
    """Recherche des stickers animes sur tenor.com avec cache memoire et cache disque."""
    slug = re.sub(r"[\W_]+", "-", requete.lower()).strip("-")
    q = urllib.parse.quote(slug)
    cle = _cle_cache_recherche(q, False)
    cached = _CACHE_RECHERCHE.get(cle)
    urls = []
    if cached and cached.get("urls") and len(cached.get("urls", [])) > 0:
        urls = cached["urls"]
        file_q.put(("status", langue.T("Recherche : {q} (cache)").format(q=requete)))
    else:
        url = TENOR_SEARCH.format(q=q)
        file_q.put(("status", langue.T("Recherche : {q}").format(q=requete)))
        try:
            urls = urls_multi_sources(slug, 36)
            if urls:
                _CACHE_RECHERCHE[cle] = {"urls": urls, "ts": __import__("time").time()}
                _sauver_cache_recherche()
        except Exception as e:
            if not _PROXY_SYS:
                file_q.put(("error", langue.T(
                    "Tenor injoignable : active ton VPN/proxy "
                    "(Clash, Hiddify) puis relance la recherche.")))
            else:
                file_q.put(("error", str(e)))
            return

    if not urls:
        file_q.put(("giphy_results", []))
        file_q.put(("status", langue.T("Aucun resultat trouve sur Tenor")))
        return

    # Preparer la liste avec les images deja en cache disque si disponibles
    items = [{"id": str(i), "mini": u, "url": u, "titre": "",
              "png": charger_image_cache(u)} for i, u in enumerate(urls)]
    file_q.put(("giphy_results", items))

    # Envoyer instantanement les images deja pretes depuis le cache disque
    for i, item in enumerate(items):
        if item.get("png"):
            file_q.put(("giphy_item", (i, item["png"])))

    # Telecharger le reste en parallele (as_completed pour affichage immediat)
    a_charger = [(i, it["url"]) for i, it in enumerate(items) if not it.get("png")]
    if a_charger:
        def une(t):
            idx, u = t
            png = fetch_image_png(u, timeout=5)
            return idx, png

        with ThreadPoolExecutor(18) as pool:
            futurs = [pool.submit(une, t) for t in a_charger]
            for fut in as_completed(futurs):
                try:
                    idx, png = fut.result()
                    if png:
                        file_q.put(("giphy_item", (idx, png)))
                except Exception:
                    pass

    file_q.put(("giphy_done", True))
    file_q.put(("status", langue.T("{n} stickers trouves").format(n=len(items))))


def tenor_url_hd(url_mini):
    """Miniature AAAA m -> source originale AAAAC (jusqu'a ~498 px)."""
    m = GIPHY_ID_RE.search(url_mini)
    if m:
        return f"https://i.giphy.com/{m.group(1)}.webp"
    if "tenor.com" not in url_mini:
        return url_mini
    parties = url_mini.split("/")
    if len(parties) >= 2 and len(parties[-2]) >= 15:
        parties[-2] = parties[-2][:-5] + "AAAAC"
        return "/".join(parties)
    return url_mini


def preparer_image(png_data, cible=512):
    """RGBA -> PNG. Agrandit en HD (LANCZOS par paliers + netteté) si la
    source est petite. L'agrandissement en plusieurs paliers (max 2x) puis
    une legere accentuation donnent un rendu bien plus net qu'un seul saut."""
    from PIL import Image, ImageFilter
    im = Image.open(io.BytesIO(png_data)).convert("RGBA")
    w, h = im.size
    m = max(w, h)
    if m < int(cible * 0.8):       # seulement si la source est vraiment petite
        while max(im.size) < cible:
            nw, nh = im.size
            k = min(2.0, cible / max(nw, nh))
            im = im.resize((max(1, int(nw * k)), max(1, int(nh * k))),
                           Image.LANCZOS)
        # accentuation douce pour compenser l'interpolation
        try:
            alpha = im.getchannel("A")
            rgb = im.convert("RGB").filter(
                ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
            im = Image.merge("RGBA", (*rgb.split(), alpha))
        except Exception:
            pass
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def tenor_version_hd(item, file_q):
    """Recupere la source originale d'un sticker Tenor (au clic)."""
    url = item["url"]
    hd_url = tenor_url_hd(url)
    cached = charger_image_cache(hd_url)
    if cached:
        file_q.put(("hd_prete", (url, cached)))
        return
    try:
        data = _http(hd_url, timeout=10)
        png = convertir_png(data)
        if png:
            sauver_image_cache(hd_url, png)
            file_q.put(("hd_prete", (url, png)))
        else:
            file_q.put(("hd_prete", (url, item.get("png"))))
    except Exception:
        file_q.put(("hd_prete", (url, item.get("png"))))


def tenor_precharger_hd(items, file_q, limite=8):
    """Recupere en douceur les sources originales des premieres vignettes."""
    def une(item):
        try:
            u = item["url"]
            hd_url = tenor_url_hd(u)
            png = fetch_image_png(hd_url, timeout=10)
            return u, png
        except Exception:
            return item["url"], None

    with ThreadPoolExecutor(6) as pool:
        futurs = [pool.submit(une, it) for it in items[:limite]]
        for fut in as_completed(futurs):
            try:
                u, png = fut.result()
                if png:
                    file_q.put(("hd_prete", (u, png)))
            except Exception:
                pass


SEUIL_HD = 400          # px du plus grand cote pour qualifier "haute resolution"


def _mesurer_png(png):
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    return max(im.size)


def tenor_recherche_hd(requete, file_q):
    """Recherche exigeante : ne conserve que les sources originales dont la
    taille reelle depasse SEUIL_HD px. Resultats envoyes au fur et a mesure."""
    slug = re.sub(r"[\W_]+", "-", requete.lower()).strip("-")
    q = urllib.parse.quote(slug)
    url = TENOR_SEARCH.format(q=q)
    file_q.put(("status", langue.T("Recherche HD : {q}").format(q=requete)))
    try:
        urls = urls_multi_sources(slug, 48)
        file_q.put(("hd_debut", True))

        def une(u):
            try:
                hd_url = tenor_url_hd(u)
                png = fetch_image_png(hd_url, timeout=10)
                if png and _mesurer_png(png) >= SEUIL_HD:
                    return u, png
            except Exception:
                pass
            return u, None

        gardes, testes = 0, 0
        with ThreadPoolExecutor(12) as pool:
            futurs = [pool.submit(une, u) for u in urls]
            for fut in as_completed(futurs):
                u, png = fut.result()
                testes += 1
                if png:
                    item = {"id": str(gardes), "mini": u, "url": u,
                            "titre": "", "png": png, "png_hd": png}
                    file_q.put(("hd_result", item))
                    gardes += 1
                if testes % 4 == 0:
                    file_q.put(("status",
                                f"HD : {gardes} stickers trouves sur "
                                f"{testes} testes..."))
                if gardes >= 24:
                    break
        file_q.put(("hd_fin", True))
        file_q.put(("status",
                    f"{gardes} stickers haute resolution" if gardes else
                    "Aucune source HD pour cette recherche"))
    except Exception as e:
        file_q.put(("error", str(e)))


def _nom_depuis_url(url, prefixe="sticker"):
    base = os.path.basename(urllib.parse.urlparse(url).path).rsplit(".", 1)[0]
    return prefixe + "_" + _nettoyer(base)[:36]


def tenor_telecharger(item, file_q):
    """Clic droit : enregistre la meilleure version (HD si possible)."""
    try:
        dossier = os.path.join(DOSSIER_STICKERS, "web")
        png = item.get("png_hd")
        if png is None:
            try:
                png = convertir_png(_http(tenor_url_hd(item["url"]),
                                          timeout=12))
            except Exception:
                png = item.get("png")
        if not png:
            raise ValueError("image indisponible")
        png = preparer_image(png)
        chemin = sauver_png(png, dossier, _nom_depuis_url(item["url"]))
        file_q.put(("downloaded", dossier))
        file_q.put(("saved_web", (item["url"], chemin)))
        file_q.put(("status", langue.T("Enregistre en HD : {nom}").format(nom=os.path.basename(chemin))))
    except Exception as e:
        file_q.put(("error", str(e)))


def sauver_sticker_url(url, file_q, nom=None, sous_dossier="web"):
    """Telecharge une seule image (ex: vignette d'un pack Telegram), HD."""
    try:
        data = _http(url, timeout=12)
        png = convertir_png(data)
        if png is None:
            raise ValueError("image illisible")
        png = preparer_image(png)
        dossier = os.path.join(DOSSIER_STICKERS, sous_dossier)
        chemin = sauver_png(png, dossier, nom or _nom_depuis_url(url))
        file_q.put(("downloaded", dossier))
        file_q.put(("saved_web", (url, chemin)))
        file_q.put(("status", langue.T("Enregistre en HD : {nom}").format(nom=os.path.basename(chemin))))
    except Exception as e:
        file_q.put(("error", str(e)))


# ============================================================= URL =======
def telecharger_url(url, file_q):
    url = url.strip()
    file_q.put(("status", langue.T("Telechargement URL...")))
    try:
        data = _http(url, timeout=30)
        nom = os.path.splitext(
            os.path.basename(urllib.parse.urlparse(url).path))[0] or "image"
        dossier = os.path.join(DOSSIER_STICKERS, "imports")
        chemin = sauver_image(data, dossier, nom[:40])
        file_q.put(("downloaded", dossier))
        file_q.put(("saved_web", (url, chemin)))
        file_q.put(("status", langue.T("Importe : {nom}").format(nom=os.path.basename(chemin))))
    except Exception as e:
        file_q.put(("error", str(e)))


# ============================================================ LOCAL ======
def compter_stickers_locaux():
    os.makedirs(DOSSIER_STICKERS, exist_ok=True)
    total = 0
    dossiers = {}
    for racine, _dirs, fichiers in os.walk(DOSSIER_STICKERS):
        pngs = [f for f in fichiers if f.lower().endswith(".png")]
        if pngs:
            dossiers[os.path.relpath(racine, DOSSIER_STICKERS)] = len(pngs)
            total += len(pngs)
    return total, dossiers


def lister_stickers_locaux(dossier=None):
    """Chemins PNG enregistres. dossier=None = tout, sinon relpath
    d'un sous-dossier (ex: 'web', 'tg_xxx')."""
    os.makedirs(DOSSIER_STICKERS, exist_ok=True)
    base = (DOSSIER_STICKERS if not dossier
            else os.path.join(DOSSIER_STICKERS, dossier))
    return lister_dossier(base)


def lister_dossier(base):
    """Tous les PNG d'un dossier absolu quelconque (sous-dossiers inclus),
    sauf le cache interne."""
    if not base or not os.path.isdir(base):
        return []
    out = []
    for racine, dirs, fichiers in os.walk(base):
        dirs[:] = [d for d in dirs if d != os.path.basename(DOSSIER_CACHE)]
        for f in fichiers:
            if f.lower().endswith(".png"):
                chemin = os.path.join(racine, f)
                if os.path.exists(chemin):
                    out.append(chemin)
    return sorted(out)


def compter_dossier(base):
    return len(lister_dossier(base))


# ====================================================== VIGNETTES CACHE ==
def _cle_vignette(chemin, cible):
    st = os.stat(chemin)
    brut = f"{os.path.abspath(chemin).lower()}|{int(st.st_mtime)}|" \
           f"{st.st_size}|{cible}".encode("utf-8")
    return hashlib.md5(brut).hexdigest()


def vignette_locale(chemin, cible=TAILLE_VIGNETTE):
    """Petit PNG (octets) genere en cache disque. Tres rapide au second
    appel, meme entre deux lancements. None si image illisible."""
    try:
        os.makedirs(DOSSIER_CACHE, exist_ok=True)
        cle = _cle_vignette(chemin, cible)
        cache = os.path.join(DOSSIER_CACHE, cle + ".png")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()
        from PIL import Image
        im = Image.open(chemin).convert("RGBA")
        im.thumbnail((cible, cible), Image.LANCZOS)
        out = io.BytesIO()
        # compression rapide : les vignettes sont petites et cachees
        im.save(out, format="PNG", optimize=False, compress_level=1)
        data = out.getvalue()
        # ecriture atomique
        tmp = cache + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, cache)
        return data
    except Exception:
        return None


def vignette_cachee(chemin, cible=TAILLE_VIGNETTE):
    """Octets du cache disque si deja genere, sinon None (jamais de calcul)."""
    try:
        cache = os.path.join(DOSSIER_CACHE,
                             _cle_vignette(chemin, cible) + ".png")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()
    except Exception:
        return None
    return None


def mes_vignettes(chemins, file_q, cible=TAILLE_VIGNETTE):
    """Genere les vignettes d'un lot en parallele (arriere-plan)."""
    def une(c):
        return c, vignette_locale(c, cible)
    with ThreadPoolExecutor(8) as pool:
        for chemin, data in pool.map(une, chemins):
            file_q.put(("mes_thumb", (chemin, data)))
    file_q.put(("mes_fin", True))


# ====================================================== BIBLIOTHEQUES ====
def charger_biblios():
    """Categories locales ajoutees par l'utilisateur : {nom: chemin}."""
    try:
        with open(FICHIER_CONFIG, "r", encoding="utf-8") as f:
            data = json.load(f)
        biblios = data.get("biblios", {})
        return {n: c for n, c in biblios.items()
                if isinstance(n, str) and isinstance(c, str)
                and os.path.isdir(c)}
    except Exception:
        return {}


def sauver_biblios(biblios):
    with open(FICHIER_CONFIG, "w", encoding="utf-8") as f:
        json.dump({"biblios": biblios}, f, ensure_ascii=False, indent=1)


def ajouter_bibli(nom, chemin):
    biblios = charger_biblios()
    base = nom.strip() or os.path.basename(chemin) or "Bibliotheque"
    nom = base
    n = 2
    while nom in biblios:
        nom = f"{base} {n}"
        n += 1
    biblios[nom] = os.path.abspath(chemin)
    sauver_biblios(biblios)
    return nom


def retirer_bibli(nom):
    biblios = charger_biblios()
    if nom in biblios:
        del biblios[nom]
        sauver_biblios(biblios)
        return True
    return False


def choisir_dossier_natif():
    """Boite de dialogue Windows (tkinter, fourni avec Python)."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        dossier = tk.filedialog.askdirectory(title="Choisir un dossier de stickers")
    except Exception:
        dossier = ""
    root.destroy()
    return dossier or None


# ============================================================== FAVORIS ==
FICHIER_FAVORIS = os.path.join(DOSSIER_BASE, "favoris.json")


def charger_favoris():
    """Chemins explicitement enregistres par l'utilisateur (etoile ou
    sauvegarde manuelle)."""
    try:
        with open(FICHIER_FAVORIS, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [p for p in data
                    if isinstance(p, str) and os.path.isfile(p)]
    except Exception:
        pass
    return []


def sauver_favoris(favoris):
    with open(FICHIER_FAVORIS, "w", encoding="utf-8") as f:
        json.dump(favoris, f, ensure_ascii=False, indent=1)


def ajouter_favori(chemin):
    favoris = charger_favoris()
    p = os.path.abspath(chemin)
    if p not in favoris:
        favoris.insert(0, p)
        sauver_favoris(favoris)
    return p


def retirer_favori(chemin):
    favoris = charger_favoris()
    p = os.path.abspath(chemin)
    if p in favoris:
        favoris.remove(p)
        sauver_favoris(favoris)
        return True
    return False


def est_sticker_explicite(chemin):
    """True sauf stickers issus de packs téléchargés (tg_*, marketplace_*, theme_*)."""
    p = os.path.abspath(chemin).lower()
    base = os.path.abspath(DOSSIER_STICKERS).lower() + os.sep
    if p.startswith(base):
        tete = p[len(base):].split(os.sep)[0]
        if tete.startswith("tg_") or tete.startswith("marketplace_") or tete.startswith("theme_"):
            return False
    return True


def supprimer_dossier_pack(nom_dossier):
    """Supprime un pack/dossier de stickers téléchargé."""
    dossier = os.path.join(DOSSIER_STICKERS, nom_dossier)
    if os.path.isdir(dossier):
        import shutil
        shutil.rmtree(dossier, ignore_errors=True)
        return True
    return False


# ====================================================== DOUBLONS ==========
def empreinte_fichier(chemin):
    """SHA-256 du contenu : doublons exacts (memes octets)."""
    h = hashlib.sha256()
    try:
        with open(chemin, "rb") as f:
            for bloc in iter(lambda: f.read(1 << 16), b""):
                h.update(bloc)
    except Exception:
        return None
    return h.hexdigest()


def empreinte_perceptuelle(chemin, taille=8):
    """dHash 64 bits : doublons visuels (redimensionnes / re-encodes)."""
    from PIL import Image
    im = Image.open(chemin).convert("L")
    im = im.resize((taille + 1, taille), Image.LANCZOS)
    px = list(im.getdata())
    bits = 0
    for i in range(taille):
        for j in range(taille):
            bits = (bits << 1) | (px[i * (taille + 1) + j] >
                                  px[i * (taille + 1) + j + 1])
    return bits


def distance_hamming(a, b):
    return bin(a ^ b).count("1")


def detecter_doublons(chemins, seuil=6, progress=None):
    """Groupes de doublons : [{'garde', 'doublons', 'type'}].
    'garde' = plus ancien (a conserver), 'doublons' = a supprimer.
    Passe 1 : hash SHA-256 exact. Passe 2 : dHash perceptuel (seuil)."""
    par_hash = {}
    for i, c in enumerate(chemins):
        h = empreinte_fichier(c)
        if h:
            par_hash.setdefault(h, []).append(c)
        if progress and i % 20 == 0:
            progress(i, len(chemins))
    groupes, vus = [], set()
    for h, liste in par_hash.items():
        if len(liste) > 1:
            liste.sort(key=lambda p: os.path.getmtime(p))
            groupes.append({"garde": liste[0], "doublons": liste[1:],
                            "type": "exact"})
            vus.update(liste)
    # doublons perceptuels parmi les restants (index par morceaux 16 bits)
    restants = [c for c in chemins if c not in vus]
    empreintes = {}
    for c in restants:
        try:
            empreintes[c] = empreinte_perceptuelle(c)
        except Exception:
            pass
    index = {}
    for c, h in empreintes.items():
        for k in range(4):
            index.setdefault((h >> (16 * k)) & 0xFFFF, set()).add(c)
    for c, h in empreintes.items():
        if c in vus:
            continue
        candidats = set()
        for k in range(4):
            candidats |= index.get((h >> (16 * k)) & 0xFFFF, set())
        groupe = [c]
        for d in candidats:
            if d == c or d in vus:
                continue
            if distance_hamming(h, empreintes[d]) <= seuil:
                groupe.append(d)
        if len(groupe) > 1:
            groupe.sort(key=lambda p: os.path.getmtime(p))
            vus.update(groupe)
            groupes.append({"garde": groupe[0], "doublons": groupe[1:],
                            "type": "proche"})
    return groupes


def supprimer_fichier(chemin):
    try:
        os.remove(chemin)
        return True
    except Exception:
        return False


def detecter_doublons_worker(chemins, file_q, seuil=6):
    """Arriere-plan : progression puis resultat des groupes de doublons."""
    def progress(i, n):
        file_q.put(("doublons_progress", (i, n)))
    try:
        groupes = detecter_doublons(chemins, seuil, progress)
        file_q.put(("doublons_result", groupes))
        file_q.put(("status", langue.T("{n} groupes de doublons trouves").format(n=len(groupes))))
    except Exception as e:
        file_q.put(("error", str(e)))


def nettoyer_doublons_auto(file_q, seuil=6):
    """Supprime automatiquement les doublons (garde le plus ancien).
    Lance en arriere-plan au demarrage et apres chaque installation."""
    chemins = _tous_chemins_locaux()
    file_q.put(("doublons_auto_progress", (0, len(chemins))))

    def progress(i, n):
        if i % 20 == 0:
            file_q.put(("doublons_auto_progress", (i, n)))
    try:
        groupes = detecter_doublons(chemins, seuil, progress)
    except Exception as e:
        file_q.put(("error", str(e)))
        return
    supprimes = 0
    for grp in groupes:
        for chemin in grp["doublons"]:
            if supprimer_fichier(chemin):
                supprimes += 1
    file_q.put(("doublons_auto_result", supprimes))
    file_q.put(("status", f"Nettoyage auto : {supprimes} doublon(s) "
                          f"supprime(s)"))


# ====================================================== SUPPRESSION FLOUS =
def _est_flou(chemin, seuil=200):
    """True si le sticker est flou/pixelise :
    - resolution trop petite (< seuil px), ou
    - issu d'un pack combot (tg_* / marketplace_*) : sources 128 px
      agrandies en 512 px -> rendu pixelise."""
    try:
        rel = os.path.relpath(chemin, DOSSIER_STICKERS)
        tete = rel.split(os.sep)[0]
        if tete.startswith("tg_") or tete.startswith("marketplace_"):
            return True
        from PIL import Image
        im = Image.open(chemin)
        return max(im.size) < seuil
    except Exception:
        return False


def supprimer_flous(seuil=200, progress=None):
    """Supprime les stickers flous/pixelises. Renvoie le nombre de fichiers
    supprimes."""
    chemins = _tous_chemins_locaux()
    nb = 0
    for i, c in enumerate(chemins):
        if _est_flou(c, seuil):
            if supprimer_fichier(c):
                nb += 1
        if progress and i % 20 == 0:
            progress(i, len(chemins))
    return nb


def supprimer_flous_worker(file_q, seuil=200):
    """Arriere-plan : supprime les stickers flous puis vide le cache de
    vignettes pour liberer l'espace."""
    def progress(i, n):
        if i % 20 == 0:
            file_q.put(("flous_progress", (i, n)))
    try:
        nb = supprimer_flous(seuil, progress)
        if nb:
            try:
                for f in os.listdir(DOSSIER_CACHE):
                    os.remove(os.path.join(DOSSIER_CACHE, f))
            except Exception:
                pass
        file_q.put(("flous_result", nb))
        file_q.put(("status", langue.T("{n} sticker(s) flou(s) supprime(s)").format(n=nb)))
    except Exception as e:
        file_q.put(("error", str(e)))


# ====================================================== INDEX RECHERCHE ==
FICHIER_INDEX = os.path.join(DOSSIER_BASE, ".index_recherche.json")


def _mots_cle(chemin):
    """Mots-cles depuis le nom de fichier et les dossiers parents."""
    parties = os.path.normpath(chemin).replace("\\", "/").split("/")
    nom = os.path.splitext(parties[-1])[0]
    mots = set()
    for p in parties[-3:] + [nom]:
        p = p.lower()
        if p.startswith("tg_"):
            p = p[3:]
        for m in re.split(r"[^a-z0-9\u00e0-\u00ff\u3040-\u30ff\u4e00-\u9fff]+", p):
            if (len(m) >= 2 or m[0] >= "぀") and not m.isdigit():
                mots.add(m)
    return " ".join(sorted(mots))


def _tous_chemins_locaux():
    """Tous les stickers locaux : dossier stickers + bibliotheques ajoutees."""
    fs = lister_stickers_locaux()
    pour = set(fs)
    for ch in charger_biblios().values():
        for f in lister_dossier(ch):
            if f not in pour:
                pour.add(f)
                fs.append(f)
    return fs


def construire_index(chemins=None, progress=None):
    """Index {chemin: meta} + inverse {mot: [chemins]} pour une recherche
    instantanee (sous-chaine)."""
    if chemins is None:
        chemins = _tous_chemins_locaux()
    index, inverse = {}, {}
    for i, c in enumerate(chemins):
        try:
            st = os.stat(c)
            mots = _mots_cle(c)
            index[c] = {"mots": mots, "taille": st.st_size,
                        "mtime": int(st.st_mtime)}
            for m in mots.split():
                inverse.setdefault(m, set()).add(c)
        except Exception:
            continue
        if progress and i % 25 == 0:
            progress(i, len(chemins))
    return index, {m: sorted(s) for m, s in inverse.items()}


def sauver_index(index, inverse):
    try:
        with open(FICHIER_INDEX, "w", encoding="utf-8") as f:
            json.dump({"index": index, "inverse": inverse}, f,
                      ensure_ascii=False, separators=(",", ":"))
    except Exception:
        pass


def charger_index():
    """Index disque si a jour (mtime/taille), sinon ({}, {})."""
    try:
        with open(FICHIER_INDEX, "r", encoding="utf-8") as f:
            data = json.load(f)
        index, inverse = data.get("index", {}), data.get("inverse", {})
        for c in list(index):
            try:
                st = os.stat(c)
            except Exception:
                del index[c]
                continue
            if int(st.st_mtime) != index[c].get("mtime") or \
                    st.st_size != index[c].get("taille"):
                del index[c]
        return index, inverse
    except Exception:
        return {}, {}


def rechercher_index(index, inverse, requete):
    """Filtre instantane : chaque mot doit matcher (sous-chaine) un
    mot-cle de l'index. O(mots x entrees de l'inverse)."""
    mots = [m.lower() for m in re.split(r"[^a-z0-9\u00e0-\u00ff\u3040-\u30ff\u4e00-\u9fff]+", requete)
            if len(m) >= 2 or m[0] >= "぀"]
    if not mots:
        return list(index)
    ensembles = []
    for m in mots:
        s = set()
        for cle, chemins in inverse.items():
            if m in cle:
                s.update(chemins)
        ensembles.append(s)
    commun = set.intersection(*ensembles) if ensembles else set()
    return sorted(commun)


def construire_index_worker(file_q):
    """Arriere-plan : reconstruit l'index complet puis le sauvegarde."""
    def progress(i, n):
        if i % 50 == 0:
            file_q.put(("index_progress", (i, n)))
    try:
        index, inverse = construire_index(progress=progress)
        sauver_index(index, inverse)
        file_q.put(("index_ready", (index, inverse)))
        file_q.put(("status", langue.T("Index de recherche : {n} stickers").format(n=len(index))))
    except Exception as e:
        file_q.put(("error", str(e)))


# ====================================================== BOUTIQUE PACKS ==
# Index distant (JSON) : remplacez par votre URL si vous hebergez le votre.
# --------------------------------------------------------------- RISIBANK
# Banque de medias humoristiques francophone (memes, stickers FR).
# Recherche par tag via l'API publique : les espaces valent "ET",
# les accents sont normalises par le site, une page = 80 medias.
RISIBANK_SEARCH = ("https://risibank.fr/api/v1/medias/search"
                   "?query={q}&page={p}")
RISIBANK_TRENDING = "https://risibank.fr/api/v1/medias/trending"


def _risibank_urls(donnees):
    """Extrait les URLs d'images d'une reponse Risibank."""
    medias = donnees if isinstance(donnees, list) else (donnees or {}).get("medias", [])
    urls = []
    for m in medias or []:
        if isinstance(m, dict):
            if m.get("nsfw_category") or m.get("is_deleted"):
                continue                 # pas de contenu sexuel / supprime
            u = m.get("cache_url") or m.get("url")
            if u:
                urls.append(u)
    return urls


RISIBANK_HD = 400      # px du plus grand cote : on ne garde que la HD


def _filtrer_hd(urls, n):
    """Garde les images >= RISIBANK_HD px (ordre conserve). Les images
    testees restent en cache disque : pas de double telechargement."""
    def hd(u):
        try:
            png = fetch_image_png(u, timeout=4)
            return u if png and _mesurer_png(png) >= RISIBANK_HD else None
        except Exception:
            return None
    with ThreadPoolExecutor(16) as pool:
        return [u for u in pool.map(hd, urls) if u][:n]


def risibank_recherche(requete, max_urls=60, max_pages=2):
    """Medias Risibank correspondant a une requete (tag(s))."""
    q = " ".join((requete or "").strip().lower().split())
    if not q:
        return []
    cle = _cle_cache_recherche("risibank-hd:" + q, False)
    cached = _CACHE_RECHERCHE.get(cle)
    if cached and cached.get("urls"):
        return cached["urls"]
    urls, vus = [], set()
    for page in range(1, max_pages + 1):
        if len(urls) >= max_urls * 2:
            break
        try:
            url = RISIBANK_SEARCH.format(q=urllib.parse.quote(q), p=page)
            data = json.loads(_http(url, timeout=15).decode("utf-8"))
        except Exception:
            break
        trouves = _risibank_urls(data)
        if not trouves:
            break
        for u in trouves:
            if u not in vus:
                vus.add(u)
                urls.append(u)
                if len(urls) >= max_urls * 2:
                    break
    urls = _filtrer_hd(urls[:max(24, max_urls * 2)], max_urls)
    if urls:
        _CACHE_RECHERCHE[cle] = {"urls": urls, "ts": __import__("time").time()}
        _sauver_cache_recherche()
    return urls


def risibank_trending(max_urls=80):
    """Selection du moment sur Risibank."""
    cle = _cle_cache_recherche("risibank-hd:trending", False)
    cached = _CACHE_RECHERCHE.get(cle)
    if cached and cached.get("urls"):
        return cached["urls"][:max_urls]
    try:
        data = json.loads(_http(RISIBANK_TRENDING, timeout=15).decode("utf-8"))
        urls = _filtrer_hd(_risibank_urls(data), max_urls)
    except Exception:
        return []
    if urls:
        _CACHE_RECHERCHE[cle] = {"urls": urls, "ts": __import__("time").time()}
        _sauver_cache_recherche()
    return urls


VERSION = "1.1.0"
URL_GITHUB = "https://github.com/Paquereauman/stickaru"

PACKS_INDEX_URL = ("https://raw.githubusercontent.com/Paquereauman/"
                   "stickaru/main/packs_index.json")
FICHIER_PACKS_LOCAL = os.path.join(DOSSIER_BASE, "packs_index.json")


def charger_catalogue_packs():
    """Index des packs : chargement local immediat (0 ms, 0 reseau)."""
    try:
        with open(FICHIER_PACKS_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f).get("packs", [])
    except Exception:
        pass
    return []


def charger_catalogue_packs_worker(file_q):
    """Actualise le catalogue en arriere-plan si besoin."""
    try:
        packs = charger_catalogue_packs()
        if not packs:
            try:
                data = json.loads(_http(PACKS_INDEX_URL, timeout=4).decode("utf-8"))
                packs = data.get("packs", [])
            except Exception:
                pass
        file_q.put(("boutique_catalogue", packs))
        file_q.put(("status", langue.T("{n} packs disponibles").format(n=len(packs))))
    except Exception as e:
        file_q.put(("error", str(e)))


def _urls_pack(pack):
    """URLs des stickers d'un pack (source combot, tenor_theme ou liste directe)."""
    if pack.get("source") == "tenor_theme":
        q_theme = pack.get("theme_query") or pack.get("id", "")
        slug = re.sub(r"[\W_]+", "-", q_theme.lower()).strip("-") or "stickers"
        cle = _cle_cache_recherche(slug, False)
        cached = _CACHE_RECHERCHE.get(cle)
        if cached and cached.get("urls"):
            return cached["urls"]
        try:
            url = TENOR_SEARCH.format(q=urllib.parse.quote(slug))
            urls = urls_multi_sources(slug, 36)
            if urls:
                _CACHE_RECHERCHE[cle] = {"urls": urls, "ts": __import__("time").time()}
                _sauver_cache_recherche()
                return urls
        except Exception:
            return []
    if pack.get("source") == "risibank_theme":
        q = pack.get("theme_query") or pack.get("id", "")
        return risibank_recherche(q, max_urls=pack.get("nb", 60) or 60)
    if pack.get("source") == "risibank_trending":
        return risibank_trending(max_urls=pack.get("nb", 80) or 80)
    if pack.get("source") == "combot" and pack.get("slug"):
        return combot_pack(pack["slug"]).get("urls", [])
    return pack.get("urls", [])


def apercu_pack_worker(pack, file_q, limite=18):
    """Vignettes d'apercu d'un pack : [(url, png)] en resolution d'origine
    (affichage net) et telechargees en parallele (rapide)."""
    try:
        urls = _urls_pack(pack)
        file_q.put(("boutique_apercu_info", (pack, len(urls))))

        def une(u):
            png = fetch_image_png(u, timeout=10)
            return (u, png) if png else None

        vign = []
        with ThreadPoolExecutor(10) as pool:
            futurs = [pool.submit(une, u) for u in urls[:limite]]
            for fut in as_completed(futurs):
                res = fut.result()
                if res:
                    vign.append(res)
                    file_q.put(("boutique_apercu", list(vign)))
        file_q.put(("status", f"{pack.get('nom', pack.get('id', ''))} : "
                              f"{len(urls)} stickers"))
    except Exception as e:
        file_q.put(("error", str(e)))


def installer_pack_worker(pack, file_q):
    """Installe tout le pack ou la collection thematique dans stickers/."""
    pid = _nettoyer(pack.get("id") or pack.get("slug") or "pack")
    prefix = "theme_" if pack.get("source") in (
        "tenor_theme", "risibank_theme", "risibank_trending") \
        else "marketplace_"
    dossier = os.path.join(DOSSIER_STICKERS, prefix + pid)
    os.makedirs(dossier, exist_ok=True)
    try:
        urls = _urls_pack(pack)
    except Exception as e:
        file_q.put(("error", str(e)))
        return
    if not urls:
        file_q.put(("error", langue.T("Aucun sticker trouve a installer")))
        return

    deja = {os.path.basename(p)
            for p in glob.glob(os.path.join(dossier, "*.png"))}
    nb = 0

    def dl_une(t):
        i, u = t
        nom = f"{i+1:03d}"
        if nom + ".png" in deja:
            return False
        hd_u = tenor_url_hd(u) if "tenor.com" in u else u
        try:
            raw = _http(hd_u, timeout=10)
            sauver_image(raw, dossier, nom)
            return True
        except Exception:
            try:
                raw = _http(u, timeout=10)
                sauver_image(raw, dossier, nom)
                return True
            except Exception:
                return False

    with ThreadPoolExecutor(12) as pool:
        futurs = [pool.submit(dl_une, (i, u)) for i, u in enumerate(urls)]
        for fut in as_completed(futurs):
            if fut.result():
                nb += 1
                if nb % 4 == 0:
                    file_q.put(("status", f"{pack.get('nom', pid)} : {nb}/{len(urls)} installes"))

    file_q.put(("boutique_installe", pid))
    file_q.put(("downloaded", dossier))
    file_q.put(("status", f"Pack '{pack.get('nom', pid)}' installe ({nb} nouveaux stickers) !"))


def precharger_populaires_worker(file_q=None):
    """Prefetch discret en fond des recherches les plus frequentes pour affichage instantane."""
    mots = ["cat", "kitten", "cute cat", "pusheen", "funny cat", "love cat", "anime cat", "sleep cat"]
    for mot in mots:
        slug = re.sub(r"[\W_]+", "-", mot.lower()).strip("-")
        q = urllib.parse.quote(slug)
        cle = _cle_cache_recherche(q, False)
        if cle not in _CACHE_RECHERCHE:
            try:
                url = TENOR_SEARCH.format(q=q)
                urls = urls_multi_sources(slug, 24)
                if urls:
                    _CACHE_RECHERCHE[cle] = {"urls": urls, "ts": __import__("time").time()}
                    _sauver_cache_recherche()
            except Exception:
                continue


# ====================================================== NETTOYAGE CACHES ==
MAX_CACHE_WEB = 200 * 1024 * 1024      # images web telechargees (octets)
AGE_MAX_PREMULT = 30 * 86400           # rendus pre-multiplies (secondes)
_FICHIER_NETTOYAGE = os.path.join(DOSSIER_BASE, ".dernier_nettoyage")


def nettoyer_caches(file_q=None):
    """Une fois par jour : limite le cache d'images web (les moins
    recemment utilisees partent d'abord) et supprime les vieux rendus
    de l'affichage. Tout est regenerable a la demande."""
    import time
    try:
        if time.time() - os.path.getmtime(_FICHIER_NETTOYAGE) < 86400:
            return
    except OSError:
        pass
    libere = 0
    try:
        web = []
        for e in os.scandir(DOSSIER_CACHE):
            if e.name.startswith("web_") and e.is_file():
                st = e.stat()
                web.append((st.st_mtime, st.st_size, e.path))
        total = sum(t for _, t, _ in web)
        for _, taille, chemin in sorted(web):
            if total <= MAX_CACHE_WEB:
                break
            try:
                os.remove(chemin)
                total -= taille
                libere += taille
            except OSError:
                pass
    except OSError:
        pass
    premult = os.path.join(DOSSIER_BASE, ".cache_premult")
    limite = time.time() - AGE_MAX_PREMULT
    try:
        for e in os.scandir(premult):
            st = e.stat()
            if e.is_file() and st.st_mtime < limite:
                try:
                    os.remove(e.path)
                    libere += st.st_size
                except OSError:
                    pass
    except OSError:
        pass
    try:
        with open(_FICHIER_NETTOYAGE, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass
    if file_q is not None and libere > 1024 * 1024:
        file_q.put(("status", langue.T("Cache nettoye : {n} Mo liberes").format(n=libere // (1024 * 1024))))


# ============================================================ PREFERENCES ==
_FICHIER_PREFS = os.path.join(DOSSIER_BASE, ".prefs.json")


def lire_pref(cle, defaut=None):
    try:
        with open(_FICHIER_PREFS, "r", encoding="utf-8") as f:
            return json.load(f).get(cle, defaut)
    except Exception:
        return defaut


def ecrire_pref(cle, valeur):
    try:
        with open(_FICHIER_PREFS, "r", encoding="utf-8") as f:
            prefs = json.load(f)
    except Exception:
        prefs = {}
    prefs[cle] = valeur
    try:
        with open(_FICHIER_PREFS, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception:
        pass


def vignettes_locales_worker(chemins, file_q):
    """Vignettes des stickers locaux trouves par la recherche."""
    def une(c):
        try:
            return c, vignette_locale(c)
        except Exception:
            return c, None
    with ThreadPoolExecutor(6) as pool:
        for c, data in pool.map(une, chemins):
            if data:
                file_q.put(("local_thumb", (c, data)))
