# -*- coding: utf-8 -*-
"""Bibliotheque de stickers - application autonome (pygame, theme clair).

Recherche de stickers (tenor.com) et de packs Telegram (combot.org),
aucune cle API. Clic sur une image = copier dans le presse-papiers,
clic droit = enregistrer dans 'Mes stickers', etoile = favori.
"""

import os
import sys
import io
import re
import json
import ctypes
from ctypes import wintypes
import pygame
from concurrent.futures import ThreadPoolExecutor

import sources
import langue

CF_DIB = 8
GMEM_MOVEABLE = 2
BI_BITFIELDS = 3
LCS_WINDOWS_COLOR_SPACE = 0x57696E20   # "Win "


# ------------------------------------------------------------ DPI / echelle
def dpi_awareness():
    """Per-monitor v2 avant creation de la fenetre (rendu net, pas de flou)."""
    u = ctypes.windll.user32
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            u.SetProcessDPIAware()
        except Exception:
            pass


def app_user_model_id(aumid="Bpaquereau.Stickaru"):
    """Identifie l'appli aupres de Windows : sans ca, une appli lancee par
    pythonw.exe affiche l'icone de Python dans la barre des taches."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(aumid)
        return True
    except Exception:
        return False


def dpi_systeme():
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


class BITMAPV5HEADER(ctypes.Structure):
    _fields_ = [
        ("bV5Size", wintypes.DWORD), ("bV5Width", wintypes.LONG),
        ("bV5Height", wintypes.LONG), ("bV5Planes", wintypes.WORD),
        ("bV5BitCount", wintypes.WORD), ("bV5Compression", wintypes.DWORD),
        ("bV5SizeImage", wintypes.DWORD), ("bV5XPelsPerMeter", wintypes.LONG),
        ("bV5YPelsPerMeter", wintypes.LONG), ("bV5ClrUsed", wintypes.DWORD),
        ("bV5ClrImportant", wintypes.DWORD), ("bV5RedMask", wintypes.DWORD),
        ("bV5GreenMask", wintypes.DWORD), ("bV5BlueMask", wintypes.DWORD),
        ("bV5AlphaMask", wintypes.DWORD), ("bV5CSType", wintypes.DWORD),
        ("bV5Endpoints", ctypes.c_byte * 36), ("bV5GammaRed", wintypes.DWORD),
        ("bV5GammaGreen", wintypes.DWORD), ("bV5GammaBlue", wintypes.DWORD),
        ("bV5Intent", wintypes.DWORD), ("bV5ProfileData", wintypes.DWORD),
        ("bV5ProfileSize", wintypes.DWORD), ("bV5Reserved", wintypes.DWORD)]


def copier_image_presse_papiers(png_data):
    """Copie une image dans le presse-papiers Windows.
    Deux formats : PNG (Telegram/Discord/WhatsApp/web) + CF_DIB alpha
    (Paint, Office, Pillow). Transparence conservee, image agrandie en HD."""
    import numpy as np
    from PIL import Image
    png_data = sources.preparer_image(png_data)
    im = Image.open(io.BytesIO(png_data)).convert("RGBA")
    w, h = im.size
    arr = np.frombuffer(im.tobytes(), np.uint8).reshape(h, w, 4)
    bgra = arr[:, :, [2, 1, 0, 3]][::-1]        # BGRA, lignes bottom-up
    pixels = bgra.tobytes()

    entete = BITMAPV5HEADER()
    entete.bV5Size = ctypes.sizeof(BITMAPV5HEADER)
    entete.bV5Width = w
    entete.bV5Height = h          # positif = bottom-up
    entete.bV5Planes = 1
    entete.bV5BitCount = 32
    entete.bV5Compression = BI_BITFIELDS
    entete.bV5SizeImage = len(pixels)
    entete.bV5RedMask = 0x00FF0000
    entete.bV5GreenMask = 0x0000FF00
    entete.bV5BlueMask = 0x000000FF
    entete.bV5AlphaMask = 0xFF000000
    entete.bV5CSType = LCS_WINDOWS_COLOR_SPACE

    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HGLOBAL]
    u32.RegisterClipboardFormatW.restype = wintypes.UINT
    u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]

    def allouer(octets):
        hm = k32.GlobalAlloc(GMEM_MOVEABLE, len(octets))
        if not hm:
            raise MemoryError("GlobalAlloc")
        pt = k32.GlobalLock(hm)
        ctypes.memmove(pt, octets, len(octets))
        k32.GlobalUnlock(hm)
        return hm

    dib = bytes(entete) + pixels
    h_dib = allouer(dib)
    h_png = allouer(png_data)
    if not u32.OpenClipboard(None):
        k32.GlobalFree(h_dib)
        k32.GlobalFree(h_png)
        raise OSError("presse-papiers indisponible")
    try:
        u32.EmptyClipboard()
        if not u32.SetClipboardData(CF_DIB, h_dib):
            raise OSError("SetClipboardData refuse (DIB)")
        cf_png = u32.RegisterClipboardFormatW("PNG")
        if cf_png and not u32.SetClipboardData(cf_png, h_png):
            raise OSError("SetClipboardData refuse (PNG)")
    finally:
        u32.CloseClipboard()
    # la memoire appartient desormais au presse-papiers

# --------------------------------------------------------------- palette
L, H = 1000, 660          # dimensions logiques de base (x echelle DPI)
L_MIN, H_MIN = 620, 460   # tailles minimales
SB = 205                  # largeur sidebar etendue
SB_COMPACT = 64           # largeur sidebar en mode etroit
SEUIL_COMPACT = 880       # largeur logique sous laquelle la sidebar se replie

FOND      = (244, 245, 248)
BLANC     = (255, 255, 255)
BORD      = (226, 229, 235)
TEXTE     = (31, 34, 42)
SOUS      = (118, 124, 138)
PIST      = (233, 235, 240)    # piste / skeleton
ACCENT    = (245, 166, 35)
ACCENT_D  = (224, 144, 18)
ACCENT_F  = (255, 245, 226)
VERT      = (34, 178, 108)
VERT_F    = (232, 250, 240)
ROUGE     = (224, 86, 76)

NAV = [("recherche", "Recherche"),
       ("boutique", "Boutique"),
       ("importer", "Importer URL"),
       ("mes", langue.T("Mes stickers"))]

# libelles affiches -> requetes en anglais (meilleurs resultats)
CHIPS = [("Tous", ""), ("Chats", "cat"), ("Chiens", "cute dog"),
         ("WhatsApp", "whatsapp sticker"), ("Bubu & Dudu", "bubu dudu"),
         ("Pusheen", "pusheen"), ("Manga", "anime chibi"),
         ("Memes", "meme"), ("Droles", "funny"), ("Amour", "love")]

BOUTIQUE_CHIPS = [
    ("Tous", ""),
    ("WhatsApp", "whatsapp"),
    ("Bubu & Dudu", "bubu"),
    ("Peach & Goma", "peach"),
    ("Chiens", "dog"),
    ("Chats Mignons", "mignon"),
    ("Pusheen", "pusheen"),
    ("Memes & Droles", "meme"),
    ("Anime & Manga", "anime"),
    ("Gaming", "gaming"),
    ("Animaux", "animaux"),
    ("Amour", "amour"),
    ("Dodo", "dodo"),
]

TRAD = {
    "chat": "cat", "chats": "cat", "chaton": "kitten", "chatons": "kitten",
    "mignon": "cute", "mignons": "cute", "drole": "funny", "drôles": "funny",
    "amour": "love", "noel": "christmas", "nourriture": "food", "dort": "sleep",
    "chien": "dog", "chiens": "dog", "chiot": "puppy", "chiots": "puppy",
    "ours": "bear", "grenouille": "frog", "lapin": "bunny", "coeur": "heart",
    "colere": "angry", "colère": "angry", "triste": "sad", "joie": "happy",
    "bisou": "kiss", "bisous": "kiss", "danse": "dance"
}

GRILLE_COLS = 6
CELL = 112
GAP = 12


def traduire(texte):
    mots = texte.lower().split()
    return " ".join(TRAD.get(m.strip(",."), m) for m in mots) or texte


class Bibliotheque:
    def __init__(self):
        dpi_awareness()
        app_user_model_id()
        langue.charger()
        self.echelle = max(1.0, min(2.0, dpi_systeme()))
        self.k = self.echelle
        try:
            icone = os.path.join((os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))),
                                 "chat.ico")
            # pygame ne lit pas ce .ico (PNG embarques) : on passe par PIL
            # et on prend la plus grande taille (256 px, nette partout)
            from PIL import Image
            im = Image.open(icone)
            im.size = max(im.info.get("sizes", [im.size]))
            im = im.convert("RGBA")
            pygame.display.set_icon(
                pygame.image.fromstring(im.tobytes(), im.size, "RGBA"))
        except Exception:
            pass

        # taille initiale : logique x DPI, bornee a l'ecran
        try:
            u0 = ctypes.windll.user32
            sw, sh = u0.GetSystemMetrics(0), u0.GetSystemMetrics(1)
        except Exception:
            sw = sh = 100000
        # mini physique = taille logique mini x plus petite echelle UI (0.8)
        self.lmin = round(L_MIN * self.echelle * 0.80)
        self.hmin = round(H_MIN * self.echelle * 0.80)
        self.larg = max(self.lmin, min(round(L * self.echelle),
                                       int(sw * 0.92)))
        self.haut = max(self.hmin, min(round(H * self.echelle),
                                       int(sh * 0.92)))
        self.sb_cachee = False        # sidebar manuellement masquee
        self._recalquer_echelle(self.larg, self.haut)
        self._creer_polices()
        self._maj_sidebar()
        self.zone_sb_toggle = pygame.Rect(0, 0, 1, 1)
        self.zones_bib_retrait = []
        self.ecran = pygame.display.set_mode((self.larg, self.haut),
                                             pygame.RESIZABLE)
        pygame.display.set_caption("Stickaru v" + sources.VERSION)
        pygame.key.set_repeat(350, 35)   # maintien de Retour arriere, fleches
        self._centrer()
        self._forcer_icone_fenetre()
        self._masquer_titre()

        self.horloge = pygame.time.Clock()
        self._anims = {}              # url -> (box, [(surface, fin_ms)], total_ms) | None
        self._anims_attente = {}      # url -> future de decodage
        self._anim_pool = ThreadPoolExecutor(2)
        self._anim_visible = False

        self.vue = "recherche"
        self.actif = True
        self.need_reload = False
        self.status = ""
        self.souris = (0, 0)
        self.toast = None             # (texte, ticks)
        self.t0 = pygame.time.get_ticks()
        self._rid = 0                 # id de la recherche courante

        # recherche
        self.rq = ""
        self.rq_focus = False
        self._rq_derniere = ""
        self._debounce_rq = 0
        self.items = []
        self.r_chargement = False
        self.mode_hd = False
        self.avec_risibank = sources.lire_pref("risibank", True)
        self.hd_encours = False
        self.r_scroll = 0
        self.ajoutes = set()
        self.attente_copie = set()   # ids dont la version HD arrive (copie auto)
        self.chargement_hd = set()
        self.hd_prelances = False
        # cache de surfaces (evite re-decodage des PNG a chaque frame)
        self._surfs_web = {}         # cle url(+hd) -> (box, surface)
        self._surfs_pack = {}        # url vignette pack -> (box, surface)
        # favoris
        self.favoris_attente = set() # urls en cours d'enregistrement favori
        self.url_fichier = {}        # url recherche -> chemin sauvegarde
        self.zones_favoris = []
        self.favoris = set()

        self.pq = ""
        self.pq_focus = False
        self.catalogue = []
        self.liste = []
        self.p_chargement = False
        self.slug_sel = None
        self.pack_info = None
        self.thumbs = []
        self.scroll_liste = 0
        self.scroll_apercu = 0
        self.col_liste = 300
        self.pack_ajoutes = set()

        # import url
        self.url = ""
        self.url_focus = False

        # mes stickers (grille des PNG enregistres)
        self.mes_dossier = "mes"      # "mes" = explicites, "fav" = etoiles,
                                      # None = tous, ("d",nom) / ("b",nom)
        self.mes_fichiers = []
        self.mes_scroll = 0
        self._mes_data = {}           # chemin -> octets PNG vignette
        self._mes_thumbs = {}         # chemin -> surface (taille courante)
        self._mes_cell = 0            # taille pour laquelle le cache est fait
        self._mes_attente = set()     # vignettes en cours de generation
        self._mes_job = False         # un worker vignette a la fois
        self.biblios = sources.charger_biblios()
        self._comptes_bib = {}
        self.n_mes = 0
        self.n_fav = 0

        # recherche instantanee (Mes stickers) : index + debounce
        self.mes_recherche = ""
        self.mes_recherche_focus = False
        self.mes_filtre = None
        self._debounce = 0
        self._mes_recherche_derniere = ""
        self._index = {}
        self._inverse = {}
        self._index_charge = False

        # nettoyage automatique des doublons (aucune page dediee)
        self.d_auto_actif = True    # nettoyage automatique active
        self.d_auto = False         # un nettoyage auto est en cours
        self.d_auto_fait = False    # deja nettoye au demarrage
        self._auto_ticks = pygame.time.get_ticks() + 2500
        # suppression automatique des stickers flous (une fois au demarrage)
        self._flous_fait = False
        self._flous_ticks = pygame.time.get_ticks() + 6000

        # boutique de packs
        self.boutique = sources.charger_catalogue_packs()
        self.bq = ""
        self.bq_focus = False
        self._bq_derniere = ""
        self._debounce_bq = 0
        self.b_chargement = False
        self.b_sel = self.boutique[0] if self.boutique else None
        self.b_apercu = []
        self.b_apercu_info = None
        self.b_scroll = 0
        self.b_scroll_ap = 0
        self.col_boutique = 300
        self.b_installe = set()
        self._maj_installe()

        self._actualiser_mes()

        self.files = []
        # Index de recherche local (chargement disque instantane)
        self._index, self._inverse = sources.charger_index()
        self._index_charge = bool(self._index)
        self._lancer(sources.construire_index_worker)
        self._lancer(sources.charger_catalogue_packs_worker)
        self._lancer(sources.prechauffer_reseau)
        self._lancer(sources.nettoyer_caches)

    # ---------------------------------------------------------------- noyau
    def px(self, v):
        """Pixels physiques pour une valeur logique (echelle UI courante)."""
        return round(v * self.k)

    def _recalquer_echelle(self, w, h):
        """k = DPI x facteur d'ajustement a la taille de fenetre.
        wl/hl = dimensions de reference (style px CSS) pour les breakpoints."""
        fit = min((w / self.echelle) / float(L),
                  (h / self.echelle) / float(H))
        fit = max(0.80, min(fit, 1.25))
        self.k = self.echelle * fit
        self.wl = w / self.k     # largeur logique effective
        self.hl = h / self.k     # hauteur logique effective
        self.petit_h = self.hl < 560
        self.minuscule_h = self.hl < 480

    def _creer_polices(self):
        # En chinois : police CJK (SysFont ne fait pas de repli glyphe par
        # glyphe, les ideogrammes sortiraient en carres).
        cjk = None
        if getattr(langue, "LANGUE", "fr") == "zh":
            for _c in ("C:/Windows/Fonts/msyh.ttc",
                       "C:/Windows/Fonts/simhei.ttf",
                       "C:/Windows/Fonts/NotoSansSC-VF.ttf"):
                if os.path.exists(_c):
                    cjk = _c
                    break

        self._cjk_ttf = next((c for c in ("C:/Windows/Fonts/msyh.ttc",
                                          "C:/Windows/Fonts/simhei.ttf")
                              if os.path.exists(c)), None)

        def police(taille, bold=False):
            t = max(9, round(taille * self.k))
            if cjk:
                try:
                    f = pygame.font.Font(cjk, t)
                    f.set_bold(bool(bold))
                    return f
                except Exception:
                    pass
            return pygame.font.SysFont("segoeui,arial", t, bold=bold)
        self.f_titre = police(22, True)
        self.f_nav = police(15, True)
        self.f = police(14)
        self.fm = police(15, True)
        self.fg = police(19, True)
        self.f_big = police(34, True)
        self.fp = police(12)
        self.f_compact = police(10, True)

    def _masquer_titre(self):
        """Barre de titre sans logo ni nom (la barre des taches les garde)."""
        try:
            class WTA(ctypes.Structure):
                _fields_ = [("flags", ctypes.c_uint), ("mask", ctypes.c_uint)]
            hwnd = pygame.display.get_wm_info().get("window")
            opts = WTA(0x3, 0x3)   # WTNCA_NODRAWCAPTION | WTNCA_NODRAWICON
            ctypes.windll.uxtheme.SetWindowThemeAttribute(
                ctypes.c_void_p(hwnd), 1, ctypes.byref(opts),
                ctypes.sizeof(opts))
        except Exception:
            pass

    def _forcer_icone_fenetre(self):
        """SDL ne suffit pas toujours sous Windows : on pose l'icone
        directement sur la fenetre (barre de titre + barre des taches)."""
        try:
            from ctypes import wintypes
            chemin = os.path.join(
                (os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))), "chat.ico")
            if not os.path.exists(chemin):
                return False
            hwnd = pygame.display.get_wm_info().get("window")
            if not hwnd:
                return False
            u = ctypes.windll.user32
            u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                     wintypes.UINT, ctypes.c_int,
                                     ctypes.c_int, wintypes.UINT]
            u.LoadImageW.restype = wintypes.HANDLE
            u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                       wintypes.WPARAM, wintypes.LPARAM]
            u.SendMessageW.restype = wintypes.LPARAM
            WM_SETICON, IMAGE_ICON, LR_LOADFROMFILE = 0x80, 1, 0x10
            ok = False
            # tailles systeme reelles (DPI) : petite = titre, grande = barre
            petite = u.GetSystemMetrics(49) or 16     # SM_CXSMICON
            grande = max(u.GetSystemMetrics(11) or 32, 48)   # SM_CXICON
            # barre des taches : le logo en grand
            h = u.LoadImageW(None, chemin, IMAGE_ICON, grande, grande,
                             LR_LOADFROMFILE)
            if h:
                u.SendMessageW(wintypes.HWND(hwnd), WM_SETICON,
                               wintypes.WPARAM(1), wintypes.LPARAM(h))
                ok = True
            # barre de titre : aucune icone (petite icone nulle, y compris
            # celle de la classe SDL, + cadre "dialogue" sans icone)
            # (WM_SETICON : tout wParam non nul = grande icone, donc 0 seul)
            # (icone nulle => Windows reduit la grande : on pose une vide)
            vide = os.path.join(os.environ.get("TEMP", "."), "stickaru_vide.ico")
            if not os.path.exists(vide):
                from PIL import Image
                Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(vide)
            hv = u.LoadImageW(None, vide, IMAGE_ICON, petite, petite,
                              LR_LOADFROMFILE)
            u.SendMessageW(wintypes.HWND(hwnd), WM_SETICON,
                           wintypes.WPARAM(0), wintypes.LPARAM(hv or 0))
            u.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int,
                                           ctypes.c_void_p]
            u.SetClassLongPtrW(hwnd, -34, None)          # GCLP_HICONSM
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            ex = u.GetWindowLongPtrW(wintypes.HWND(hwnd), -20)  # GWL_EXSTYLE
            u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int,
                                            ctypes.c_ssize_t]
            u.SetWindowLongPtrW(hwnd, -20, ex | 0x0001)  # WS_EX_DLGMODALFRAME
            u.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                           0x0001 | 0x0002 | 0x0004 | 0x0020)  # FRAMECHANGED
            return ok
        except Exception:
            return False

    def _centrer(self):
        try:
            u = ctypes.windll.user32
            w, h = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
            info = pygame.display.get_wm_info()
            u.SetWindowPos(info["window"], 0,
                           (w - self.larg) // 2, (h - self.haut) // 2,
                           0, 0, 0x0001 | 0x0004 | 0x0040)
        except Exception:
            pass

    def _lancer(self, fn, *args, liee=False):
        import queue, threading
        rid = self._rid if liee else -1
        q = queue.Queue()

        def poster(m):
            q.put((rid, m[0], m[1]))

        class FileTaggee:
            put = staticmethod(poster)

        threading.Thread(target=self._cible, args=(fn, args, FileTaggee()),
                         daemon=True).start()
        self.files.append(q)

    @staticmethod
    def _cible(fn, args, q):
        try:
            fn(*args, q)
        except Exception as e:
            q.put(("error", str(e)))

    GENRES_LIES = {"local_thumb", "giphy_results", "giphy_append", "giphy_retirer", "giphy_item", "giphy_done",
                   "hd_debut", "hd_result", "hd_fin", "hd_prete"}

    def _poll(self):
        reste = []
        for q in self.files:
            vide = True
            while not q.empty():
                vide = False
                try:
                    rid, genre, val = q.get_nowait()
                except Exception:
                    break
                # ignore les reponses d'une recherche deja remplacee
                if genre in self.GENRES_LIES and rid != -1 \
                        and rid != self._rid:
                    continue
                self._recevoir(genre, val)
            reste.append(q)
        self.files = reste

    def _recevoir(self, genre, val):
        if genre == "status":
            self.status = val
        elif genre == "error":
            self.status = str(val)
            self.toast = (str(val)[:60], pygame.time.get_ticks())
            self.r_chargement = self.p_chargement = False
            self.hd_encours = False
        elif genre == "tg_catalog":
            self.catalogue = val
            self.liste = val
        elif genre == "tg_search":
            self.liste = val
            self.p_chargement = False
            self.scroll_liste = 0
        elif genre == "tg_pack":
            self.pack_info = val
            self.thumbs = []
        elif genre == "tg_thumbs":
            self.thumbs = val
        elif genre == "giphy_results":
            locaux = [it for it in self.items if it.get("local")]
            self.items = locaux + val
            self.r_chargement = False
            if not self.mode_hd:
                self.hd_prelances = False
        elif genre == "giphy_append":
            self.items.extend(val)
        elif genre == "hd_debut":
            locaux = [it for it in self.items if it.get("local")]
            self.items = locaux
            self.hd_encours = True
            self.r_scroll = 0
        elif genre == "hd_result":
            self.items.append(val)
            self.r_chargement = False
        elif genre == "hd_fin":
            self.hd_encours = False
        elif genre == "giphy_item":
            i, png = val
            if isinstance(i, str):            # recherche multi : par URL
                cible = next((it for it in self.items
                              if it.get("url") == i), None)
                if cible is not None and png:
                    cible["png"] = png
            else:
                web_items = [it for it in self.items if not it.get("local")]
                if 0 <= i < len(web_items) and png:
                    web_items[i]["png"] = png
        elif genre == "local_thumb":
            chemin, data = val
            for it in self.items:
                if it.get("local") and it.get("chemin") == chemin:
                    it["png"] = data
        elif genre == "giphy_retirer":
            self.items = [it for it in self.items if it.get("url") != val]
        elif genre == "giphy_done":
            if not self.hd_prelances:
                self.hd_prelances = True
                self._precharger_hd()
        elif genre == "hd_prete":
            url, png = val
            self.chargement_hd.discard(url)
            cible = next((it for it in self.items if it["url"] == url), None)
            if cible is not None and png:
                cible["png_hd"] = png
            if url in self.attente_copie:
                self.attente_copie.discard(url)
                if png:
                    try:
                        copier_image_presse_papiers(png)
                        self.toast = (langue.T("Image HD copiee - colle-la (Ctrl+V)"),
                                      pygame.time.get_ticks())
                    except Exception as ex:
                        self.toast = (str(ex)[:50], pygame.time.get_ticks())
        elif genre == "saved_web":
            url, chemin = val
            chemin = os.path.abspath(chemin)
            self.url_fichier[url] = chemin
            if url in self.favoris_attente:
                self.favoris_attente.discard(url)
                sources.ajouter_favori(chemin)
                self.favoris.add(chemin)
                self._actualiser_mes()
                self.toast = (langue.T("Ajoute aux favoris"),
                              pygame.time.get_ticks())
        elif genre == "downloaded":
            self.need_reload = True
            if os.path.isdir(val):
                # pack installe : on l'ouvre directement (sinon il est
                # masque dans le filtre langue.T("Mes stickers"))
                self.toast = (langue.T("Pack installe - ouvert dans Mes stickers"),
                              pygame.time.get_ticks())
                self.vue = "mes"
                self._choisir_dossier(("d", os.path.basename(val)))
            else:
                self.toast = (langue.T("Enregistre dans Mes stickers"),
                              pygame.time.get_ticks())
            self._actualiser_mes()
        elif genre == "mes_thumb":
            chemin, data = val
            self._mes_attente.discard(chemin)
            if data:
                self._mes_data[chemin] = data
                self._mes_thumbs.pop(chemin, None)
        elif genre == "mes_fin":
            self._mes_job = False
        elif genre == "doublons_auto_progress":
            i, n = val
            self.status = f"Nettoyage auto des doublons : {i}/{n}..."
        elif genre == "doublons_auto_result":
            self.d_auto = False
            self.d_auto_fait = True
            if val:
                self._actualiser_mes()
                self.toast = (langue.T(
                    "{n} doublon(s) supprime(s) automatiquement").format(n=val),
                    pygame.time.get_ticks())
        elif genre == "flous_progress":
            i, n = val
            self.status = langue.T(
                "Suppression des stickers flous : {i}/{n}...").format(i=i, n=n)
        elif genre == "flous_result":
            if val:
                self._actualiser_mes()
                self.toast = (langue.T(
                    "{n} sticker(s) flou(s) supprime(s)").format(n=val),
                              pygame.time.get_ticks())
        elif genre == "index_progress":
            i, n = val
            self.status = langue.T("Index de recherche : {i}/{n}...").format(
                i=i, n=n)
        elif genre == "index_ready":
            self._index, self._inverse = val
            self._index_charge = True
            self._appliquer_recherche_mes()
        elif genre == "boutique_catalogue":
            self.boutique = val
            self.b_chargement = False
        elif genre == "boutique_apercu_info":
            self.b_apercu_info = val
            self.b_apercu = []
        elif genre == "boutique_apercu":
            self.b_apercu = val
        elif genre == "boutique_installe":
            self.b_installe.add(val)
            self._actualiser_mes()
            # un pack installe peut contenir des doublons : re-nettoyage
            if self.d_auto_actif and not self.d_auto:
                self.d_auto = True
                self._lancer(sources.nettoyer_doublons_auto)

    # ---------------------------------------------------------------- events
    def gerer(self):
        evenements = pygame.event.get()
        if evenements or any(not q.empty() for q in self.files):
            self._dernier_actif = pygame.time.get_ticks()
        for e in evenements:
            if e.type == pygame.QUIT:
                self.actif = False
            elif e.type == pygame.MOUSEMOTION:
                self.souris = e.pos
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.actif = False
                else:
                    self._clavier(e)
            elif e.type == pygame.TEXTEDITING:
                self._ime = e.text          # composition IME (pinyin...)
            elif e.type == pygame.TEXTINPUT:
                self._ime = ""
                if e.text.isprintable():
                    self._ecrire_champ(self._lire_champ() + e.text)
            elif e.type == pygame.MOUSEBUTTONDOWN:
                self._clic(e.pos, e.button)
            elif e.type == pygame.VIDEORESIZE:
                self.redimensionner(e.w, e.h)
        # Vue Recherche : la recherche web part uniquement sur Entree / OK
        # debounce de la recherche instantanee (Mes stickers)
        if self.vue == "mes":
            if self.mes_recherche != self._mes_recherche_derniere:
                self._mes_recherche_derniere = self.mes_recherche
                self._debounce = pygame.time.get_ticks()
            if self._debounce and \
                    pygame.time.get_ticks() - self._debounce > 180:
                self._debounce = 0
                self._appliquer_recherche_mes()
        # debounce de la recherche thematique (Boutique)
        if self.vue == "boutique":
            if self.bq != self._bq_derniere:
                self._bq_derniere = self.bq
                self._debounce_bq = pygame.time.get_ticks()
            if self._debounce_bq and \
                    pygame.time.get_ticks() - self._debounce_bq > 200:
                self._debounce_bq = 0
                affiches = self.boutique_affiches
                if affiches and (not self.b_sel or self.b_sel not in affiches):
                    self.ouvrir_boutique(0)
        # nettoyage automatique des doublons (apres le demarrage)
        if self.d_auto_actif and not self.d_auto and not self.d_auto_fait \
                and pygame.time.get_ticks() > self._auto_ticks:
            self.d_auto = True
            self.status = "Nettoyage automatique des doublons..."
            self._lancer(sources.nettoyer_doublons_auto)
        # suppression automatique des stickers flous (apres le nettoyage)
        if not self._flous_fait and not self.d_auto and \
                pygame.time.get_ticks() > self._flous_ticks:
            self._flous_fait = True
            self.status = "Suppression des stickers flous..."
            self._lancer(sources.supprimer_flous_worker)
        self._poll()
        self._anim_visible = False
        self._dessiner()
        pygame.display.flip()
        inactif = pygame.time.get_ticks() - getattr(self, "_dernier_actif", 0)
        self.horloge.tick(60 if inactif < 1500 else
                          30 if self._anim_visible else 20)

    def _maj_sidebar(self):
        self.compact = self.wl < SEUIL_COMPACT
        self.sb = 0 if self.sb_cachee else \
            self.px(SB_COMPACT if self.compact else SB)

    def _bascule_sidebar(self):
        self.sb_cachee = not self.sb_cachee
        self._maj_sidebar()

    def redimensionner(self, w, h):
        w = max(self.lmin, min(w, 4000))
        h = max(self.hmin, min(h, 4000))
        if (w, h) == (self.larg, self.haut):
            if (w, h) != self.ecran.get_size():
                self.ecran = pygame.display.set_mode(
                    (w, h), pygame.RESIZABLE)
            return
        ancien_k = self.k
        self.larg, self.haut = w, h
        self._recalquer_echelle(w, h)
        # recreer les polices seulement si le rendu change vraiment
        if abs(self.k - ancien_k) >= 0.04:
            self._creer_polices()
        self.ecran = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        self._forcer_icone_fenetre()      # SDL remet son icone apres set_mode
        self._maj_sidebar()
        # bornage des scrolls
        self.r_scroll = max(0, self.r_scroll)
        self.scroll_liste = max(0, self.scroll_liste)
        self.scroll_apercu = max(0, self.scroll_apercu)

    def _maj_installe(self):
        try:
            deja = set()
            for d in os.listdir(sources.DOSSIER_STICKERS):
                full = os.path.join(sources.DOSSIER_STICKERS, d)
                if os.path.isdir(full) and len(os.listdir(full)) > 0:
                    clean = d
                    for pref in ("marketplace_", "theme_", "tg_"):
                        if clean.startswith(pref):
                            clean = clean[len(pref):]
                    deja.add(clean)
                    deja.add(d)
            self.b_installe = deja
        except Exception:
            pass

    def _champ_actif(self):
        if self.rq_focus:
            return "rq"
        if self.bq_focus:
            return "bq"
        if self.pq_focus:
            return "pq"
        if self.url_focus:
            return "url"
        if self.mes_recherche_focus:
            return "mes"
        return None

    def _lire_champ(self):
        return {"rq": self.rq, "bq": self.bq, "pq": self.pq, "url": self.url,
                "mes": self.mes_recherche}.get(self._champ_actif(), "")

    def _ecrire_champ(self, v):
        c = self._champ_actif()
        if c == "rq":
            self.rq = v
        elif c == "bq":
            self.bq = v
        elif c == "pq":
            self.pq = v
        elif c == "url":
            self.url = v
        elif c == "mes":
            self.mes_recherche = v

    def _set_focus(self, c):
        self.rq_focus = (c == "rq")
        self.bq_focus = (c == "bq")
        self.pq_focus = (c == "pq")
        self.url_focus = (c == "url")
        self.mes_recherche_focus = (c == "mes")

    def _clavier(self, e):
        c = self._champ_actif()
        if c and e.key == pygame.K_BACKSPACE:
            self._ecrire_champ(self._lire_champ()[:-1])
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if c == "rq":
                self.lancer_recherche(self.rq)
            elif c == "bq":
                self._lancer_recherche_boutique()
            elif c == "url":
                self.importer_url()
            elif c == "mes":
                self._appliquer_recherche_mes()

    # ---------------------------------------------------------------- actions
    def lancer_recherche(self, texte):
        q = traduire(texte.strip() or "cat")
        # ne pas retoucher le champ pendant la frappe (l'espace final
        # disparaissait) ; seulement si la recherche vient d'ailleurs (chip)
        if texte.strip() != self.rq.strip():
            self.rq = texte.strip()
        # Afficher les stickers locaux correspondant a la recherche (instantané)
        self.items = []
        if len(self._surfs_web) > 500:
            self._surfs_web.clear()
        self.r_chargement = True
        self.hd_encours = self.mode_hd
        self.ajoutes.clear()
        self.attente_copie.clear()
        self.chargement_hd.clear()
        self._rid += 1
        # Afficher stickers locaux instantanement avant Tenor (connexion lente/VPN)
        self._afficher_locaux_par_recherche(texte.strip() or "cat")
        if self.mode_hd:
            self.status = langue.T("Recherche HD : ") + q
            self._lancer(sources.tenor_recherche_hd, q, liee=True)
        else:
            self.status = langue.T("Recherche : ") + q
            self._lancer(sources.recherche_multi, q, texte.strip() or "cat",
                         self.avec_risibank, liee=True)

    def _afficher_locaux_par_recherche(self, texte):
        """Stickers locaux correspondant a la recherche (instantané, hors-ligne).
        Utilise l'index deja charge au demarrage (self._index, self._inverse)."""
        q = texte.strip()
        if not q or not hasattr(self, "_inverse") or self._inverse is None:
            return
        try:
            q_en = traduire(q)
            fichiers = list(dict.fromkeys(
                sources.rechercher_index(self._index, self._inverse, q) +
                sources.rechercher_index(self._index, self._inverse, q_en)
            ))
            if not fichiers:
                return
            # vignettes en cache seulement ici ; les manquantes sont
            # generees en arriere-plan (la saisie ne se fige plus)
            items, manquantes = [], []
            for i, f in enumerate(fichiers[:48]):
                vign = sources.vignette_cachee(f)
                if not vign:
                    manquantes.append(f)
                items.append({"id": f"local_{i}", "mini": f, "url": f,
                              "titre": os.path.basename(f), "png": vign,
                              "local": True, "chemin": f})
            if manquantes:
                self._lancer(sources.vignettes_locales_worker, manquantes,
                             liee=True)
            if items:
                self.items = items
                self._surfs_web.clear()
                self.status = langue.T(
                    "{n} stickers locaux trouves (recherche web en cours...)").format(
                        n=len(items))
        except Exception:
            pass

    def basculer_risibank(self):
        self.avec_risibank = not self.avec_risibank
        sources.ecrire_pref("risibank", self.avec_risibank)
        self.lancer_recherche(self.rq or "cat")

    def basculer_hd(self):
        self.mode_hd = not self.mode_hd
        self.lancer_recherche(self.rq or "cat")

    # ---- favoris --------------------------------------------------------
    def _item_favori(self, item):
        url = item["url"]
        if url in self.favoris_attente:
            return True
        chemin = item.get("chemin") or self.url_fichier.get(url)
        return bool(chemin and chemin in self.favoris)

    def basculer_favori(self, i):
        """Etoile d'un resultat de recherche : enregistre si besoin puis
        ajoute/retire des favoris (vue Mes stickers)."""
        if i >= len(self.items):
            return
        item = self.items[i]
        url = item["url"]
        chemin = item.get("chemin") or self.url_fichier.get(url)
        if chemin and os.path.exists(chemin):
            if chemin in self.favoris:
                sources.retirer_favori(chemin)
                self.favoris.discard(chemin)
                self.toast = (langue.T("Retire des favoris"),
                              pygame.time.get_ticks())
            else:
                sources.ajouter_favori(chemin)
                self.favoris.add(chemin)
                self.toast = (langue.T("Ajoute aux favoris"),
                              pygame.time.get_ticks())
            self._actualiser_mes()
            return
        if not item.get("png") and not item.get("png_hd"):
            self.status = "Image encore indisponible..."
            return
        if url in self.favoris_attente:
            return
        self.favoris_attente.add(url)
        if i not in self.ajoutes:
            self.ajoutes.add(i)
            self._lancer(sources.tenor_telecharger, item)
        self.toast = (langue.T("Enregistrement du favori..."),
                      pygame.time.get_ticks())

    def _surf_de(self, cache, cle, src, box):
        """Surface mise a l'echelle une seule fois par (image, taille).
        Jamais d'agrandissement au-dela de la resolution d'origine
        (evite le flou sur les petites images)."""
        entree = cache.get(cle)
        if entree and entree[0] == box:
            return entree[1]
        try:
            img = pygame.image.load(io.BytesIO(src)).convert_alpha()
        except Exception:
            return None
        iw, ih = img.get_size()
        kk = min(box / iw, box / ih, 1.0)
        surf = pygame.transform.smoothscale(
            img, (max(1, int(iw * kk)), max(1, int(ih * kk))))
        if len(cache) > 400:
            cache.clear()
        cache[cle] = (box, surf)
        return surf

    def _anim_surf(self, url, box):
        """Image courante de l'animation de `url` (None si pas animee ou pas
        encore decodee). Le decodage se fait en tache de fond."""
        entree = self._anims.get(url, False)
        if entree is False:
            fut = self._anims_attente.get(url)
            if fut is None:
                self._anims_attente[url] = self._anim_pool.submit(
                    sources.decoder_anim, url)
                return None
            if not fut.done():
                return None
            del self._anims_attente[url]
            res = fut.result()
            if len(self._anims) > 60:
                self._anims.clear()
            if not res:
                self._anims[url] = None
                return None
            frames = []
            fin = 0
            for data, taille, duree in res[0]:
                fin += duree
                frames.append((pygame.image.frombuffer(
                    data, taille, "RGBA").convert_alpha(), fin))
            entree = self._anims[url] = [None, frames, fin]
        if entree is None:
            return None
        if entree[0] != box:              # remise a l'echelle une fois par taille
            mises = []
            for surf, fin in entree[1]:
                iw, ih = surf.get_size()
                kk = min(box / iw, box / ih, 1.0)
                if kk < 1.0:
                    surf = pygame.transform.smoothscale(
                        surf, (max(1, int(iw * kk)), max(1, int(ih * kk))))
                mises.append((surf, fin))
            entree[0], entree[1] = box, mises
        self._anim_visible = True
        t = pygame.time.get_ticks() % max(1, entree[2])
        for surf, fin in entree[1]:
            if t < fin:
                break
        return surf

    def _precharger_hd(self):
        prets = [it for it in self.items if not it.get("local")][:8]
        if prets:
            self._lancer(sources.tenor_precharger_hd, prets, liee=True)

    def dl_sticker_web(self, i):
        if i >= len(self.items):
            return
        item = self.items[i]
        if item.get("local") or item.get("chemin"):
            self.toast = (langue.T("Sticker deja dans vos stickers"), pygame.time.get_ticks())
            return
        if not item.get("png") or i in self.ajoutes:
            return
        self.ajoutes.add(i)
        self._lancer(sources.tenor_telecharger, item)

    def copier_sticker_web(self, i):
        if i >= len(self.items):
            return
        item = self.items[i]
        if item.get("local") or item.get("chemin"):
            chemin = item.get("chemin")
            try:
                with open(chemin, "rb") as f:
                    self._copier(f.read())
            except Exception:
                if item.get("png"):
                    self._copier(item["png"])
            return
        url = item["url"]
        hd = item.get("png_hd")
        if hd:
            self._copier(hd)
            return
        mini = item.get("png")
        if not mini:
            return
        if url in self.chargement_hd:
            return                      # deja en cours
        # fetch de la source originale, puis copie automatique
        self.chargement_hd.add(url)
        self.attente_copie.add(url)
        self.toast = (langue.T("Recuperation HD..."), pygame.time.get_ticks())
        self._lancer(sources.tenor_version_hd, item, liee=True)

    def _copier(self, png):
        try:
            copier_image_presse_papiers(png)
            self.toast = (langue.T("Image HD copiee - colle-la (Ctrl+V)"),
                          pygame.time.get_ticks())
        except Exception as ex:
            self.toast = (str(ex)[:50], pygame.time.get_ticks())

    def importer_url(self):
        if self.url.strip().startswith("http"):
            u = self.url.strip()
            self._lancer(sources.telecharger_url, u)
            self.url = ""
        else:
            self.status = "URL invalide (doit commencer par http)"

    def _clic(self, pos, bouton):
        x, y = pos
        # molette
        if bouton in (4, 5):
            d = -self.px(48) if bouton == 4 else self.px(48)
            if x < self.sb:
                return
            if self.vue == "recherche":
                self.r_scroll = max(0, self.r_scroll + d)
                if self.wl < 740:
                    # une seule zone visible selon qu'un pack est ouvert
                    if self.slug_sel:
                        self.scroll_apercu = max(0, self.scroll_apercu + d)
                    else:
                        self.scroll_liste = max(0, self.scroll_liste + d)
                else:
                    front = self.sb + self.px(26) + self.col_liste + self.px(9)
                    if x < front:
                        self.scroll_liste = max(0, self.scroll_liste + d)
                    else:
                        self.scroll_apercu = max(0, self.scroll_apercu + d)
            elif self.vue == "boutique":
                if self.wl < 740:
                    if self.b_sel:
                        self.b_scroll_ap = max(0, self.b_scroll_ap + d)
                    else:
                        self.b_scroll = max(0, self.b_scroll + d)
                else:
                    front = self.sb + self.px(26) + self.col_boutique \
                        + self.px(9)
                    if x < front:
                        self.b_scroll = max(0, self.b_scroll + d)
                    else:
                        self.b_scroll_ap = max(0, self.b_scroll_ap + d)
            elif self.vue == "mes":
                self.mes_scroll = max(0, self.mes_scroll + d)
            return
        if bouton not in (1, 3):
            return

        # languette masquer/afficher la sidebar (prioritaire sur la limite x)
        if bouton == 1 and self.zone_sb_toggle.collidepoint(pos):
            self._bascule_sidebar()
            return

        # clic droit sur une categorie ajoutee = la retirer
        if bouton == 3 and self.vue == "mes":
            for r, nom in self.zones_bib_retrait:
                if r.collidepoint(pos):
                    self._retirer_bibli(nom)
                    return

        if x < self.sb:
            if bouton == 1:
                if self.zone_github.collidepoint(pos):
                    os.startfile(sources.URL_GITHUB)
                    return
                for code, r in self.zones_langue:
                    if r.collidepoint(pos):
                        if code == "cycle":
                            i = langue.CODES.index(langue.LANGUE)
                            langue.definir(
                                langue.CODES[(i + 1) % len(langue.CODES)])
                        else:
                            langue.definir(code)
                        self._creer_polices()
                        self.toast = (langue.NOMS.get(langue.LANGUE, ""),
                                      pygame.time.get_ticks())
                        return
                for cle, r in self.zones_nav:
                    if r.collidepoint(pos):
                        self.vue = cle
            return
        if bouton == 1:
            for action, r in self.zones_btn:
                if r.collidepoint(pos):
                    action()
                    return
            for c, r in self.zones_input:
                self._set_focus(c if r.collidepoint(pos) else None)
                if r.collidepoint(pos):
                    return
            self._set_focus(None)

        if self.vue == "recherche":
            if bouton == 1:
                for i, r in self.zones_favoris:
                    if r.collidepoint(pos):
                        self.basculer_favori(i)
                        return
            for i, r in self.zones_grille:
                if r.collidepoint(pos):
                    if bouton == 3:
                        self.dl_sticker_web(i)
                    else:
                        self.copier_sticker_web(i)
        elif self.vue == "mes":
            if bouton == 1:
                for i, r in self.zones_mes:
                    if r.collidepoint(pos):
                        self.copier_sticker_local(i)
            elif bouton == 3 and self.mes_dossier == "fav":
                # clic droit en vue Favoris = retirer des favoris
                for i, r in self.zones_mes:
                    if r.collidepoint(pos) and i < len(self.mes_affiches):
                        chemin = self.mes_affiches[i]
                        if sources.retirer_favori(chemin):
                            self.favoris.discard(os.path.abspath(chemin))
                            self._actualiser_mes()
                            self.toast = (langue.T("Retire des favoris"),
                                          pygame.time.get_ticks())
                        break
        elif self.vue == "boutique":
            if bouton == 1:
                for idx, r in self.zones_boutique:
                    if r.collidepoint(pos):
                        self.ouvrir_boutique(idx)
                        return
                for i, r in self.zones_b_apercu:
                    if r.collidepoint(pos):
                        self.copier_boutique(i)
                        return

    # ---------------------------------------------------------------- dessin
    def _dessiner(self):
        e = self.ecran
        e.fill(FOND)
        self.zones_nav = []
        self.zones_btn = []
        self.zones_langue = []
        self.zone_github = pygame.Rect(0, 0, 0, 0)
        self.zones_input = []
        self.zones_grille = []
        self.zones_liste = []
        self.zones_thumbs = []
        self.zones_mes = []
        self.zones_favoris = []
        self.zones_bib_retrait = []
        self.zones_d_check = []
        self.zones_boutique = []
        self.zones_b_apercu = []

        self._sidebar(e)
        if self.vue == "recherche":
            self._vue_recherche(e)
        elif self.vue == "boutique":
            self._vue_boutique(e)
        elif self.vue == "importer":
            self._vue_importer(e)
        else:
            self._vue_mes(e)
        self._footer(e)
        self._dessiner_bascule_sb(e)

    def _rond(self, e, couleur, rect, survol=False):
        pygame.draw.rect(e, couleur, rect, border_radius=10)

    def _btn(self, e, rect, label, base, texte_col, action,
             police=None, grand=False):
        survol = rect.collidepoint(self.souris)
        col = tuple(max(0, c - 12) for c in base) if survol else base
        pygame.draw.rect(e, col, rect, border_radius=8)
        f = police or (self.fm if grand else self.f)
        t = f.render(label, True, texte_col)
        e.blit(t, t.get_rect(center=rect.center))
        self.zones_btn.append((action, rect))

    def _police_texte(self, texte, base=None):
        """Police CJK (meme taille que `base`) si le texte contient des
        ideogrammes, sinon `base` (les ideogrammes sortiraient en carres)."""
        base = base or self.f
        if not (self._cjk_ttf and any(ord(c) > 0x2E7F for c in texte)):
            return base
        cache = self.__dict__.setdefault("_f_cjk", {})
        h = base.get_height()
        if h not in cache:
            try:
                cache[h] = pygame.font.Font(self._cjk_ttf, max(9, round(h * 0.75)))
            except Exception:
                cache[h] = base
        return cache[h]

    def _champ(self, e, rect, texte, focus, placeholder=""):
        pygame.draw.rect(e, BLANC, rect, border_radius=self.px(10))
        pygame.draw.rect(e, ACCENT if focus else BORD, rect,
                         self.px(2) if focus else 1,
                         border_radius=self.px(10))
        ime = getattr(self, "_ime", "") if focus else ""
        aff = texte + ime + ("|" if focus else "")
        if focus:
            try:
                pygame.key.set_text_input_rect(rect)   # fenetre IME placee ici
            except Exception:
                pass
        if aff:
            t = self._police_texte(aff).render(aff, True, TEXTE)
        else:
            t = self.f.render(placeholder, True, SOUS)
        e.blit(t, (rect.x + self.px(14),
                   rect.centery - t.get_height() // 2))

    def _logo_chat(self, e, cx, cy, taille):
        """Tete de chat blanche dans un carre orange (taille = cote)."""
        lr = pygame.Rect(0, 0, taille, taille)
        lr.center = (cx, cy)
        pygame.draw.rect(e, ACCENT, lr, border_radius=max(6, taille // 3))
        k = taille / 40.0
        pygame.draw.polygon(e, BLANC,
                            [(cx - 11 * k, cy - 2 * k),
                             (cx - 9 * k, cy - 12 * k),
                             (cx - 3 * k, cy - 7 * k)])
        pygame.draw.polygon(e, BLANC,
                            [(cx + 11 * k, cy - 2 * k),
                             (cx + 9 * k, cy - 12 * k),
                             (cx + 3 * k, cy - 7 * k)])
        pygame.draw.circle(e, BLANC, (cx, cy + 2 * k), int(12 * k))
        pygame.draw.circle(e, (60, 45, 20),
                           (cx - int(4 * k), cy), max(1, int(1.8 * k)))
        pygame.draw.circle(e, (60, 45, 20),
                           (cx + int(4 * k), cy), max(1, int(1.8 * k)))
        # nez + moustaches
        pygame.draw.polygon(e, (240, 140, 120),
                            [(cx - 1.5 * k, cy + 3 * k), (cx + 1.5 * k, cy + 3 * k),
                             (cx, cy + 4.5 * k)])
        for sgn in (-1, 1):
            for dy in (-1, 0.5, 2):
                pygame.draw.aaline(e, (60, 45, 20),
                                   (cx + sgn * 2.5 * k, cy + (4 + dy / 2) * k),
                                   (cx + sgn * 11 * k, cy + (4 + dy * 1.4) * k))

    def _icone_nav(self, e, cle, cx, cy, coul):
        """Pictogrammes simples pour la sidebar compacte."""
        s = self.echelle
        ep = max(2, int(2.2 * s))
        if cle == "recherche":                 # loupe
            pygame.draw.circle(e, coul, (cx - int(3 * s), cy - int(3 * s)),
                               int(6 * s), ep)
            pygame.draw.line(e, coul,
                             (cx + int(2 * s), cy + int(2 * s)),
                             (cx + int(7 * s), cy + int(7 * s)), ep)

        elif cle == "importer":                # fleche vers le bas
            pygame.draw.line(e, coul, (cx, cy - int(8 * s)),
                             (cx, cy + int(4 * s)), ep)
            pygame.draw.lines(e, coul, False,
                              [(cx - int(5 * s), cy),
                               (cx, cy + int(6 * s)),
                               (cx + int(5 * s), cy)], ep)
            pygame.draw.line(e, coul,
                             (cx - int(8 * s), cy + int(8 * s)),
                             (cx + int(8 * s), cy + int(8 * s)), ep)
        elif cle == "mes":                     # dossier
            pygame.draw.lines(e, coul, False,
                              [(cx - int(9 * s), cy + int(6 * s)),
                               (cx - int(9 * s), cy - int(5 * s)),
                               (cx - int(3 * s), cy - int(5 * s)),
                               (cx - int(1 * s), cy - int(2 * s)),
                               (cx + int(9 * s), cy - int(2 * s)),
                               (cx + int(9 * s), cy + int(6 * s))], ep)
            pygame.draw.line(e, coul,
                             (cx - int(9 * s), cy + int(2 * s)),
                             (cx + int(9 * s), cy + int(2 * s)), ep)
        elif cle == "boutique":                # sac de courses
            pygame.draw.rect(e, coul, (cx - int(7 * s), cy - int(6 * s),
                                       int(14 * s), int(12 * s)), ep)
            pygame.draw.lines(e, coul, False,
                              [(cx - int(4 * s), cy - int(6 * s)),
                               (cx, cy - int(10 * s)),
                               (cx + int(4 * s), cy - int(6 * s))], ep)

    def _sidebar(self, e):
        if self.sb_cachee:
            return
        s = self.echelle
        pygame.draw.rect(e, BLANC, (0, 0, self.sb, self.haut))
        pygame.draw.line(e, BORD, (self.sb - 1, 0),
                         (self.sb - 1, self.haut))

        p = self.px
        if self.compact:
            self._logo_chat(e, self.sb // 2, p(36), p(30))
            y = p(74)
            haut_lig = p(44)
            for cle, label in NAV:
                r = pygame.Rect(p(8), y, self.sb - p(16), p(36))
                actif = (self.vue == cle)
                survol = r.collidepoint(self.souris)
                if actif:
                    pygame.draw.rect(e, ACCENT_F, r, border_radius=p(8))
                    pygame.draw.rect(
                        e, ACCENT,
                        (p(8), y + p(6), max(2, p(3)), p(24)), border_radius=2)
                elif survol:
                    pygame.draw.rect(e, FOND, r, border_radius=p(8))
                self._icone_nav(e, cle, r.centerx, r.centery,
                                ACCENT_D if actif else TEXTE)
                # etiquette bulle au survol
                if survol:
                    t = self.f_nav.render(langue.T(label), True, TEXTE)
                    bulle = pygame.Rect(self.sb + p(6),
                                        r.centery - p(15),
                                        t.get_width() + p(20),
                                        p(30))
                    pygame.draw.rect(e, BLANC, bulle, border_radius=p(8))
                    pygame.draw.rect(e, BORD, bulle, 1, border_radius=p(8))
                    e.blit(t, (bulle.x + p(10),
                               bulle.centery - t.get_height() // 2))
                self.zones_nav.append((cle, r))
                y += haut_lig
            # selecteur de langue (mode compact : un bouton qui fait defiler)
            rl = pygame.Rect(p(6), self.haut - p(72), self.sb - p(12), p(24))
            sv = rl.collidepoint(self.souris)
            pygame.draw.rect(e, ACCENT_F if sv else BLANC, rl,
                             border_radius=p(7))
            pygame.draw.rect(e, ACCENT, rl, 1, border_radius=p(7))
            tl = self.fp.render(langue.ETIQUETTES[langue.LANGUE], True, ACCENT_D)
            e.blit(tl, tl.get_rect(center=rl.center))
            self.zones_langue.append(("cycle", rl))
            # compteur en pastille
            t = self.f_compact.render(str(self.total_local), True, BLANC)
            rd = max(t.get_width(), t.get_height()) + p(8)
            cx = self.sb // 2
            cy = self.haut - p(28)
            pygame.draw.circle(e, ACCENT, (cx, cy), rd // 2)
            e.blit(t, (cx - t.get_width() // 2,
                       cy - t.get_height() // 2))
            return

        # logo et titre responsive
        logo_rad = p(17)
        logo_cx = p(26)
        logo_cy = p(36)
        self._logo_chat(e, logo_cx, logo_cy, logo_rad * 2)

        tx = logo_cx + logo_rad + p(8)
        w_titre_max = max(p(60), self.sb - tx - p(8))
        self._texte_lim(self.f_titre if not self.petit_h else self.fm,
                        "Stickaru", TEXTE, tx, p(18) if not self.petit_h else p(20), w_titre_max)
        self._texte_lim(self.fp, langue.T("bibliotheque"), SOUS,
                        tx, p(42) if not self.petit_h else p(40), w_titre_max)

        y = p(80 if not self.petit_h else 68)
        pas_nav = p(44 if not self.petit_h else 38)
        for cle, label in NAV:
            r = pygame.Rect(p(10), y, self.sb - p(20), p(36 if not self.petit_h else 32))
            actif = (self.vue == cle)
            if actif:
                pygame.draw.rect(e, ACCENT_F, r, border_radius=p(8))
                pygame.draw.rect(e, ACCENT,
                                 (r.x, r.y + p(6),
                                  max(2, p(3)), r.h - p(12)),
                                 border_radius=2)
            elif r.collidepoint(self.souris):
                pygame.draw.rect(e, FOND, r, border_radius=p(8))
            t = self.f_nav.render(langue.T(label), True,
                                  ACCENT_D if actif else TEXTE)
            e.blit(t, (r.x + p(16), r.centery - t.get_height() // 2))
            self.zones_nav.append((cle, r))
            y += pas_nav

        # selecteur de langue (FR / EN / 中文)
        h_lang = p(24)
        w_lang = max(p(30), (self.sb - p(20) - p(8)) // 3)
        y_lang = self.haut - p(64)
        x_lang = p(10)
        for code in langue.CODES:
            rl = pygame.Rect(x_lang, y_lang, w_lang, h_lang)
            actif_l = (langue.LANGUE == code)
            sv = rl.collidepoint(self.souris)
            pygame.draw.rect(e, ACCENT if actif_l else
                             (ACCENT_F if sv else BLANC),
                             rl, border_radius=p(7))
            pygame.draw.rect(e, ACCENT if actif_l else BORD, rl, 1,
                             border_radius=p(7))
            etiq = langue.ETIQUETTES[code]
            tl = self._police_texte(etiq, self.fp).render(etiq, True,
                                BLANC if actif_l else TEXTE)
            e.blit(tl, tl.get_rect(center=rl.center))
            self.zones_langue.append((code, rl))
            x_lang += w_lang + p(4)

        n = self.fp.render(langue.T("{n} stickers").format(n=self.total_local),
                           True, SOUS)
        e.blit(n, (p(18), self.haut - p(36)))
        tg = self.fp.render("GitHub v" + sources.VERSION, True, ACCENT_D)
        self.zone_github = tg.get_rect(topleft=(p(18), self.haut - p(20)))
        e.blit(tg, self.zone_github)
        pygame.draw.line(e, ACCENT_D, self.zone_github.bottomleft,
                         self.zone_github.bottomright)

    def _dessiner_bascule_sb(self, e):
        """Languette sur le bord gauche : masque/affiche la sidebar."""
        p = self.px
        cy = self.haut // 2
        larg_t, haut_t = p(20), p(62)
        if self.sb_cachee:
            r = pygame.Rect(0, cy - haut_t // 2, larg_t, haut_t)
        else:
            r = pygame.Rect(self.sb - larg_t // 2, cy - haut_t // 2,
                            larg_t, haut_t)
        survol = r.collidepoint(self.souris)
        pygame.draw.rect(e, ACCENT_F if survol else BLANC, r,
                         border_radius=larg_t // 2)
        pygame.draw.rect(e, ACCENT if survol else BORD, r,
                         max(1, p(1)), border_radius=larg_t // 2)
        # chevron : > si sidebar masquee, < si visible
        col = ACCENT_D if survol else SOUS
        sens = 1 if self.sb_cachee else -1
        kx, ky = p(4), p(8)
        pygame.draw.lines(
            e, col, False,
            [(r.centerx - sens * kx, cy - ky),
             (r.centerx + sens * kx, cy),
             (r.centerx - sens * kx, cy + ky)], max(2, p(2)))
        self.zone_sb_toggle = r

    def _chips(self, e, y, callback, compact=False):
        """Boutons rapides avec retour a la ligne automatique.
        Renvoie la hauteur occupee."""
        x0 = self.sb + self.px(26)
        x = x0
        x_max = self.larg - self.px(20)
        h_chip = self.px(22 if compact else 28)
        ligne = self.px(28 if compact else 36)
        pas = self.px(8)
        fonte = self.fp if compact else self.f
        pad = self.px(16 if compact else 22)
        hauteur = h_chip
        for _label, query in CHIPS:
            label = langue.T(_label)
            w = fonte.size(label)[0] + pad
            if x + w > x_max and x > x0:
                x = x0
                y += ligne
                hauteur += ligne
            r = pygame.Rect(x, y, w, h_chip)
            survol = r.collidepoint(self.souris)
            pygame.draw.rect(e, ACCENT_F if survol else BLANC, r,
                             border_radius=h_chip // 2)
            pygame.draw.rect(e, ACCENT if survol else BORD, r,
                             max(1, self.px(1)), border_radius=h_chip // 2)
            t = fonte.render(label, True, ACCENT_D if survol else TEXTE)
            e.blit(t, (x + pad // 2,
                       y + (h_chip - t.get_height()) // 2))
            self.zones_btn.append(((lambda q=query: callback(q)), r))
            x += w + pas
        return hauteur

    def _spinner(self, e, rect):
        import math
        t = (pygame.time.get_ticks() - self.t0) / 400.0
        for i in range(8):
            a = t + i * math.pi / 4
            alpha = 40 + i * 25
            col = (200, 200, 208)
            x = rect.centerx + math.cos(a) * 12
            y = rect.centery + math.sin(a) * 12
            pygame.draw.circle(e, col, (int(x), int(y)), 2.5)

    def _skeleton(self, e, r):
        col = PIST if (pygame.time.get_ticks() // 300 + r.x) % 2 else (238, 240, 244)
        pygame.draw.rect(e, col, r, border_radius=self.px(10))

    def _badge_ajoute(self, e, r):
        d = self.px(22)
        br = pygame.Rect(r.right - d - self.px(4),
                         r.bottom - d - self.px(4), d, d)
        pygame.draw.circle(e, VERT, br.center, d // 2)
        k = d / 22.0
        pygame.draw.lines(e, BLANC, False,
                          [(br.centerx - 5 * k, br.centery),
                           (br.centerx - 1 * k, br.centery + 4 * k),
                           (br.centerx + 5 * k, br.centery - 4 * k)],
                          max(2, int(2 * k)))

    @staticmethod
    def _etoile_pts(r):
        import math
        cx, cy = r.centerx, r.centery
        R, ri = r.w * 0.42, r.w * 0.17
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            rad = R if k % 2 == 0 else ri
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
        return pts

    def _dessiner_etoile(self, e, r, actif):
        survol = r.collidepoint(self.souris)
        pygame.draw.circle(e, BLANC, r.center, r.w // 2)
        pygame.draw.circle(e, ACCENT if (actif or survol) else BORD,
                           r.center, r.w // 2 - 1, max(1, self.px(1)))
        pts = self._etoile_pts(r)
        if actif:
            pygame.draw.polygon(e, ACCENT_D, pts)
        else:
            pygame.draw.polygon(e, SOUS if survol else (196, 200, 208),
                                pts, max(1, self.px(1)))

    # ---- vue recherche --------------------------------------------------
    def _vue_recherche(self, e):
        p = self.px
        x0 = self.sb + p(26)
        # en-tete responsive : masque sous-titre/chips sur fenetre basse
        if self.minuscule_h:
            y_titre, h_champ, y_champ = p(10), p(34), p(40)
        elif self.petit_h:
            y_titre, h_champ, y_champ = p(14), p(36), p(46)
        else:
            y_titre, h_champ, y_champ = p(22), p(40), p(78)
        fonte_titre = self.fm if self.minuscule_h else self.fg
        e.blit(fonte_titre.render(langue.T("Rechercher un sticker"), True, TEXTE),
               (x0, y_titre))
        if not self.petit_h:
            if self.mode_hd:
                e.blit(self.f.render(langue.T("Mode HAUTE RESOLUTION (>= 400 px)."),
                                     True, ACCENT_D), (x0, p(50)))
            else:
                e.blit(self.f.render(
                    langue.T("Clic = copier · clic droit = enregistrer · etoile = favori."), True, SOUS), (x0, p(50)))

        # ligne de champ : le champ prend toute la largeur restante
        w_hd, w_ok, w_rb = p(86), p(54), p(112)
        champ_w = max(p(120),
                      self.larg - x0 - p(26) - w_hd - w_ok - w_rb - p(26))
        ri = pygame.Rect(x0, y_champ, champ_w, h_champ)
        self._champ(e, ri, self.rq, self.rq_focus,
                    langue.T("chat, mignon, anime, dormeur..."))
        self.zones_input.append(("rq", ri))
        rhd = pygame.Rect(ri.right + p(10), y_champ, w_hd, h_champ)
        if self.mode_hd:
            pygame.draw.rect(e, ACCENT, rhd, border_radius=p(10))
            tcol = BLANC
        else:
            pygame.draw.rect(e, BLANC, rhd, border_radius=p(10))
            pygame.draw.rect(e, BORD, rhd, 1, border_radius=p(10))
            tcol = TEXTE
        t = self.fm.render("HD 400+", True, tcol)
        e.blit(t, t.get_rect(center=rhd.center))
        self.zones_btn.append((self.basculer_hd, rhd))
        # case a cocher : inclure Risibank dans la recherche
        rrb = pygame.Rect(rhd.right + p(8), y_champ, w_rb, h_champ)
        pygame.draw.rect(e, BLANC, rrb, border_radius=p(10))
        pygame.draw.rect(e, ACCENT if rrb.collidepoint(self.souris) else BORD,
                         rrb, 1, border_radius=p(10))
        cb = pygame.Rect(rrb.x + p(10), rrb.centery - p(8), p(16), p(16))
        if self.avec_risibank:
            pygame.draw.rect(e, ACCENT, cb, border_radius=p(4))
            pygame.draw.lines(e, BLANC, False,
                              [(cb.x + p(3), cb.centery),
                               (cb.x + p(7), cb.bottom - p(4)),
                               (cb.right - p(3), cb.y + p(4))], max(2, p(2)))
        else:
            pygame.draw.rect(e, BORD, cb, max(1, p(2)), border_radius=p(4))
        t = self.fp.render("Risibank", True, TEXTE)
        e.blit(t, (cb.right + p(7), rrb.centery - t.get_height() // 2))
        self.zones_btn.append((self.basculer_risibank, rrb))
        rb = pygame.Rect(rrb.right + p(8), y_champ, w_ok, h_champ)
        self._btn(e, rb, "OK", ACCENT, BLANC,
                  lambda: self.lancer_recherche(self.rq), grand=True)

        h_chips = 0
        if not self.minuscule_h:
            y_chips = y_champ + h_champ + p(10)
            h_chips = self._chips(e, y_chips, self.lancer_recherche,
                                  compact=self.petit_h)
            top = y_chips + h_chips + p(12 if self.petit_h else 16)
        else:
            top = y_champ + h_champ + p(10)
        zone = pygame.Rect(self.sb, top,
                           self.larg - self.sb, self.haut - top - p(38))
        pygame.draw.rect(e, FOND, zone)
        prev = e.get_clip()
        e.set_clip(zone)

        self.zones_grille = []
        gap = p(GAP)
        dispo = zone.width - p(52)
        # colonnes selon la place, puis cellules etirees pour remplir
        cible = 92 if self.wl < 740 else CELL
        cols = max(1, dispo // (p(cible) + gap))
        cell = (dispo - (cols - 1) * gap) // cols
        largeur_grille = cols * cell + (cols - 1) * gap
        gx0 = self.sb + (zone.width - largeur_grille) // 2
        pas = cell + gap

        if not self.items and (self.r_chargement or self.hd_encours):
            for i in range(cols * 3):
                c, li = i % cols, i // cols
                r = pygame.Rect(gx0 + c * pas,
                                zone.y + p(14) + li * pas - self.r_scroll,
                                cell, cell)
                self._skeleton(e, r)
            if self.hd_encours:
                t = self.fm.render(
                    langue.T("Analyse des sources originales (>= 400 px)..."),
                    True, ACCENT_D)
                e.blit(t, (zone.centerx - t.get_width() // 2,
                           zone.bottom - p(60)))
        elif not self.items:
            if not self.rq.strip():
                t = self.f.render(
                    langue.T("Tapez un mot-cle ci-dessus ou choisissez une thematique pour rechercher."), True, SOUS)
            else:
                t = self.f.render(
                    langue.T("Aucune source HD pour cette recherche.") if self.mode_hd
                    else langue.T("Aucun resultat."), True, SOUS)
            e.blit(t, (zone.centerx - t.get_width() // 2, zone.y + p(50)))

        for i, item in enumerate(self.items):
            c, li = i % cols, i // cols
            r = pygame.Rect(gx0 + c * pas,
                            zone.y + p(14) + li * pas - self.r_scroll,
                            cell, cell)
            if r.bottom < zone.y or r.y > zone.bottom:
                continue
            survol = r.collidepoint(self.souris)
            pygame.draw.rect(e, BLANC, r, border_radius=p(10))
            pygame.draw.rect(e,
                             ACCENT if (survol and item.get("png")) else BORD,
                             r, p(2) if survol else 1, border_radius=p(10))
            if item.get("png_hd") or item.get("png"):
                src = item.get("png_hd") or item.get("png")
                cle = item["url"] + ("/hd" if item.get("png_hd") else "")
                img = None
                if not item.get("local"):
                    img = self._anim_surf(item["url"], cell - p(14))
                if img is None:
                    img = self._surf_de(self._surfs_web, cle, src, cell - p(14))
                if img is not None:
                    e.blit(img, img.get_rect(center=r.center))
                else:
                    self._skeleton(e, r)
            else:
                self._skeleton(e, pygame.Rect(r.x + p(8), r.y + p(8),
                                              r.w - p(16), r.h - p(16)))
            if item.get("png_hd"):
                hd = self.fp.render("HD", True, ACCENT_D)
                br = pygame.Rect(r.x + p(5), r.y + p(5),
                                 hd.get_width() + p(8), p(16))
                pygame.draw.rect(e, ACCENT_F, br, border_radius=p(8))
                e.blit(hd, (br.x + p(4), br.y + p(2)))
            elif item["url"] in self.chargement_hd:
                self._spinner(e, pygame.Rect(r.x + p(4), r.y + p(4),
                                             p(24), p(24)))
            if i in self.ajoutes:
                self._badge_ajoute(e, r)
            # etoile favori (haut droite)
            sr = pygame.Rect(r.right - p(26), r.y + p(4), p(22), p(22))
            self._dessiner_etoile(e, sr, self._item_favori(item))
            self.zones_favoris.append((i, sr))
            self.zones_grille.append((i, r))
        e.set_clip(prev)

        # scrollbar
        nb_lignes = max(1, (len(self.items) + cols - 1) // cols)
        contenu_h = nb_lignes * pas + p(14)
        self.r_scroll = min(self.r_scroll,
                            max(0, contenu_h - zone.height))
        if contenu_h > zone.height:
            self._scrollbar(e, zone, self.r_scroll, contenu_h)

    def _texte_lim(self, f, texte, couleur, x, y, w_max):
        """Dessine un texte en le tronquant avec '...' si trop large."""
        if f.size(texte)[0] <= w_max:
            t = f.render(texte, True, couleur)
        else:
            t = f.render(texte + "...", True, couleur)
            while t.get_width() > w_max and len(texte) > 1:
                texte = texte[:-1]
                t = f.render(texte + "...", True, couleur)
        self.ecran.blit(t, (x, y))

    def _scrollbar(self, e, zone, scroll, contenu_h):
        p = pygame.Rect(zone.right - 8, zone.y + 6, 4, zone.height - 12)
        pygame.draw.rect(e, PIST, p, border_radius=2)
        h = max(30, int(p.height * zone.height / contenu_h))
        y = p.y + int((p.height - h) * min(1, scroll / max(1, contenu_h - zone.height)))
        pygame.draw.rect(e, (190, 195, 205), (p.x, y, 4, h), border_radius=2)

    # ---- vue importer ---------------------------------------------------
    def _vue_importer(self, e):
        p = self.px
        x0 = self.sb + p(26)
        if self.minuscule_h:
            y_titre, y_carte = p(8), p(48)
        elif self.petit_h:
            y_titre, y_carte = p(12), p(58)
        else:
            y_titre, y_carte = p(22), p(96)
        fonte_titre = self.fm if self.minuscule_h else self.fg
        e.blit(fonte_titre.render(langue.T("Importer une image"), True, TEXTE),
               (x0, y_titre))

        ligne = self.wl >= 560           # champ + bouton sur la meme ligne
        h_carte = min(p(220) if ligne else p(256),
                      self.haut - y_carte - p(20))
        carte = pygame.Rect(x0, y_carte, self.larg - x0 - p(26), h_carte)
        pygame.draw.rect(e, BLANC, carte, border_radius=p(14))
        e.blit(self.fm.render(langue.T("Adresse directe d'un sticker (PNG, WebP ou GIF)"),
                              True, TEXTE),
               (carte.x + p(24), carte.y + p(24)))
        w_bouton, h_champ = p(138), p(42)
        if ligne:
            champ_w = carte.w - p(48) - w_bouton - p(12)
            pos_champ = (carte.x + p(24), carte.y + p(68))
            pos_btn = (pos_champ[0] + champ_w + p(12), pos_champ[1])
            y_aide = carte.y + p(128)
        else:
            champ_w = carte.w - p(48)
            pos_champ = (carte.x + p(24), carte.y + p(64))
            pos_btn = (carte.x + p(24), pos_champ[1] + h_champ + p(10))
            y_aide = pos_btn[1] + h_champ + p(18)
        ri = pygame.Rect(pos_champ[0], pos_champ[1],
                         max(p(120), champ_w), h_champ)
        self._champ(e, ri, self.url, self.url_focus,
                    "https://exemple.com/chat.png")
        self.zones_input.append(("url", ri))
        self._btn(e, pygame.Rect(pos_btn[0], pos_btn[1],
                                 w_bouton, h_champ),
                  langue.T("Telecharger"), VERT, BLANC, self.importer_url, grand=True)
        lignes = [langue.T("Fonctionne avec les CDN, StickPNG, HiClipart, etc."),
                  langue.T("Le WebP/GIF est converti automatiquement en PNG transparent.")]
        for i, ln in enumerate(lignes):
            if y_aide + i * p(24) < carte.bottom - p(12):
                e.blit(self.f.render(ln, True, SOUS),
                       (carte.x + p(24), y_aide + i * p(24)))

    # ---- vue mes stickers ----------------------------------------------
    def _lib_dossier(self, nom):
        """Nom propre affiché pour chaque catégorie/dossier."""
        if nom.startswith("theme_"):
            return "✨ " + nom[6:].replace("_", " ").title()
        if nom.startswith("marketplace_"):
            return "🛍️ " + nom[12:].replace("_", " ").title()
        if nom.startswith("tg_"):
            return "✈️ " + nom[3:].replace("_", " ").title()
        if nom.startswith("wa_"):
            return "💬 " + nom[3:].replace("_", " ").title()
        return nom.replace("_", " ").title()

    def _supprimer_dossier_actuel(self):
        if self.mes_dossier and isinstance(self.mes_dossier, tuple) and self.mes_dossier[0] == "d":
            nom = self.mes_dossier[1]
            if sources.supprimer_dossier_pack(nom):
                self._choisir_dossier(None)
                self._actualiser_mes()
                self._maj_installe()
                self.toast = (langue.T("Pack '{nom}' supprime").format(
                    nom=self._lib_dossier(nom)), pygame.time.get_ticks())

    def _recalc_total_locaux(self):
        self._comptes_bib = {n: sources.compter_dossier(c)
                             for n, c in self.biblios.items()}
        self.total_local = (sum(self.dossiers_locaux.values())
                            + sum(self._comptes_bib.values()))

    def _fichiers_mes(self, cle):
        if cle == "mes":
            # uniquement les stickers explicitement enregistres par
            # l'utilisateur (hors packs Telegram telecharges)
            fs = [p for p in sources.lister_stickers_locaux()
                  if sources.est_sticker_explicite(p)]
            vus = set(fs)
            for p in self.favoris:
                if p not in vus and os.path.exists(p):
                    vus.add(p)
                    fs.append(p)
            return sorted(fs)
        if cle == "fav":
            return sorted(p for p in self.favoris if os.path.exists(p))
        if cle is None:
            fs = sources.lister_stickers_locaux()
            pour = set(fs)
            for ch in self.biblios.values():
                for f in sources.lister_dossier(ch):
                    if f not in pour:
                        pour.add(f)
                        fs.append(f)
            return sorted(fs)
        typ, val = cle
        if typ == "d":
            return sources.lister_stickers_locaux(val)
        return sources.lister_dossier(self.biblios.get(val, ""))

    def _actualiser_mes(self):
        self.favoris = {os.path.abspath(p)
                        for p in sources.charger_favoris()}
        self.biblios = sources.charger_biblios()
        self.total_local, self.dossiers_locaux = \
            sources.compter_stickers_locaux()
        self._recalc_total_locaux()
        self.n_fav = len([p for p in self.favoris if os.path.exists(p)])
        self.n_mes = len(self._fichiers_mes("mes"))
        if self.mes_dossier is not None and \
                self.mes_dossier not in ("mes", "fav"):
            typ, val = self.mes_dossier
            if (typ == "d" and val not in self.dossiers_locaux) or \
               (typ == "b" and val not in self.biblios):
                self.mes_dossier = "mes"
        self.mes_fichiers = self._fichiers_mes(self.mes_dossier)
        self._appliquer_recherche_mes()
        self.mes_scroll = 0

    def _choisir_dossier(self, cle):
        if cle == self.mes_dossier:
            return
        self.mes_dossier = cle
        self.mes_fichiers = self._fichiers_mes(cle)
        self._appliquer_recherche_mes()
        self.mes_scroll = 0

    # ---- recherche instantanee (Mes stickers) ---------------------------
    @property
    def mes_affiches(self):
        """Fichiers visibles apres filtrage par la recherche instantanee."""
        if self.mes_filtre is None:
            return self.mes_fichiers
        cle = (id(self.mes_fichiers), len(self.mes_fichiers),
               id(self.mes_filtre))
        memo = getattr(self, "_memo_affiches", None)
        if memo is None or memo[0] != cle:
            memo = (cle, [c for c in self.mes_fichiers
                          if c in self.mes_filtre])
            self._memo_affiches = memo
        return memo[1]

    def _appliquer_recherche_mes(self):
        q = self.mes_recherche.strip()
        if not q:
            self.mes_filtre = None
        elif self._index_charge:
            self.mes_filtre = set(sources.rechercher_index(
                self._index, self._inverse, q))
        else:
            ql = q.lower()
            self.mes_filtre = {c for c in self.mes_fichiers
                               if ql in os.path.basename(c).lower()}
        self.mes_scroll = 0

    def _effacer_recherche_mes(self):
        self.mes_recherche = ""
        self.mes_filtre = None
        self.mes_scroll = 0

    def _ajouter_bibli(self):
        """Boite de dialogue : ajoute un dossier disque comme categorie."""
        dossier = sources.choisir_dossier_natif()
        if not dossier:
            return
        nom_fichier = os.path.basename(os.path.normpath(dossier))
        try:
            nom = sources.ajouter_bibli(nom_fichier, dossier)
        except Exception as ex:
            self.toast = (str(ex)[:50], pygame.time.get_ticks())
            return
        self.biblios = sources.charger_biblios()
        self.total_local, self.dossiers_locaux = \
            sources.compter_stickers_locaux()
        self._recalc_total_locaux()
        self._choisir_dossier(("b", nom))
        self.toast = (langue.T("Categorie '{nom}' ajoutee").format(nom=nom),
                      pygame.time.get_ticks())

    def _retirer_bibli(self, nom):
        if sources.retirer_bibli(nom):
            self.biblios = sources.charger_biblios()
            self._recalc_total_locaux()
            if self.mes_dossier == ("b", nom):
                self._choisir_dossier(None)
            else:
                self.mes_fichiers = self._fichiers_mes(self.mes_dossier)
            self.toast = (langue.T("Categorie '{nom}' retiree").format(nom=nom),
                          pygame.time.get_ticks())

    def _maj_vignettes(self, visibles):
        """Lance la generation des vignettes visibles d'abord, puis le
        reste en arriere-plan (cache disque persistant)."""
        if self._mes_job:
            return
        manquantes = [c for c in visibles
                      if c not in self._mes_data
                      and c not in self._mes_attente]
        if not manquantes:
            manquantes = [c for c in self.mes_fichiers
                          if c not in self._mes_data
                          and c not in self._mes_attente][:24]
        if manquantes:
            lot = manquantes[:20]
            self._mes_attente.update(lot)
            self._mes_job = True
            self._lancer(sources.mes_vignettes, lot)

    def _thumb_mes(self, chemin, box):
        """Vignette (octets en cache) -> surface. None si pas prete.
        Jamais d'agrandissement : les petites images restent nettes."""
        data = self._mes_data.get(chemin)
        if data is None:
            return None
        if self._mes_cell != box:
            self._mes_thumbs.clear()
            self._mes_cell = box
        surf = self._mes_thumbs.get(chemin)
        if surf is None:
            img = pygame.image.load(io.BytesIO(data)).convert_alpha()
            iw, ih = img.get_size()
            k = min(box / iw, box / ih, 1.0)
            surf = pygame.transform.smoothscale(
                img, (max(1, int(iw * k)), max(1, int(ih * k))))
            self._mes_thumbs[chemin] = surf
        return surf

    def copier_sticker_local(self, i):
        affiches = self.mes_affiches
        if 0 <= i < len(affiches):
            try:
                with open(affiches[i], "rb") as f:
                    self._copier(f.read())
            except Exception as ex:
                self.toast = (str(ex)[:50], pygame.time.get_ticks())

    def _chips_dossiers(self, e, x, y, x_max):
        """Filtres Mes stickers / Favoris / Tous / dossiers integres /
        bibliotheques ajoutees / bouton Ajouter. Renvoie la hauteur."""
        p = self.px
        choix = [("mes", langue.T("Mes stickers ({n})").format(n=self.n_mes), False),
                 ("fav", langue.T("Etoiles ({n})").format(n=self.n_fav), False),
                 (None, langue.T("Tous"), False)]
        for nom in sorted(self.dossiers_locaux):
            lib = self._lib_dossier(nom)
            if len(lib) > 20:
                lib = lib[:19] + "..."
            choix.append((("d", nom),
                          f"{lib} ({self.dossiers_locaux[nom]})", False))
        for nom in sorted(self.biblios):
            lib = nom if len(nom) <= 20 else nom[:19] + "..."
            choix.append((("b", nom),
                          f"{lib} ({self._comptes_bib.get(nom, 0)})", True))
        fonte = self.fp
        h_chip, ligne, pas = p(26), p(32), p(8)
        ligne0 = y
        for cle, label, retirable in choix:
            w = fonte.size(label)[0] + p(22)
            if x + w > x_max and x > self.sb + p(26):
                x = self.sb + p(26)
                y += ligne
            sel = (cle == self.mes_dossier)
            r = pygame.Rect(x, y, w, h_chip)
            survol = r.collidepoint(self.souris)
            if sel:
                pygame.draw.rect(e, ACCENT, r, border_radius=h_chip // 2)
                tcol = BLANC
            else:
                pygame.draw.rect(e, ACCENT_F if survol else BLANC, r,
                                 border_radius=h_chip // 2)
                pygame.draw.rect(e, ACCENT if survol else BORD, r,
                                 max(1, p(1)), border_radius=h_chip // 2)
                tcol = ACCENT_D if survol else TEXTE
            t = fonte.render(label, True, tcol)
            e.blit(t, (x + p(11), y + (h_chip - t.get_height()) // 2))
            self.zones_btn.append(
                ((lambda c=cle: self._choisir_dossier(c)), r))
            if retirable:
                self.zones_bib_retrait.append((r, cle[1]))
            x += w + pas
        # bouton "+ Ajouter"
        label = langue.T("+ Ajouter une categorie")
        w = fonte.size(label)[0] + p(22)
        if x + w > x_max and x > self.sb + p(26):
            x = self.sb + p(26)
            y += ligne
        r = pygame.Rect(x, y, w, h_chip)
        survol = r.collidepoint(self.souris)
        pygame.draw.rect(e, VERT_F if survol else BLANC, r,
                         border_radius=h_chip // 2)
        pygame.draw.rect(e, VERT if survol else BORD, r,
                         max(1, p(1)), border_radius=h_chip // 2)
        t = fonte.render(label, True, VERT if not survol else (20, 130, 80))
        e.blit(t, (x + p(11), y + (h_chip - t.get_height()) // 2))
        self.zones_btn.append((self._ajouter_bibli, r))
        return y + h_chip - ligne0

    def _vue_mes(self, e):
        p = self.px
        x0 = self.sb + p(26)
        fonte_titre = self.fm if self.minuscule_h else self.fg
        y_titre = p(8) if self.minuscule_h else p(20)
        e.blit(fonte_titre.render(langue.T("Mes stickers"), True, TEXTE),
               (x0, y_titre))

        # compteur en sous-titre (sauf fenetre tres basse)
        if not self.minuscule_h:
            sous = langue.T("{n} stickers - clic = copier").format(
                n=len(self.mes_affiches))
            if self.mes_recherche.strip():
                sous += langue.T(" (filtre : {q})").format(
                    q=self.mes_recherche.strip())
            if self.mes_dossier == "fav":
                sous += langue.T(" - clic droit = retirer des favoris")
            e.blit(self.fp.render(sous, True, SOUS),
                   (x0, y_titre + p(28)))

        # boutons en haut a droite
        h_btn = p(30) if self.petit_h else p(34)
        x_btn = self.larg - p(130)
        self._btn(e, pygame.Rect(x_btn, y_titre - p(2), p(104), h_btn),
                  langue.T("Actualiser"), BLANC, TEXTE, self._actualiser_mes)
        if self.mes_dossier and isinstance(self.mes_dossier, tuple) and self.mes_dossier[0] == "d" and not self.mes_dossier[1].startswith("web"):
            self._btn(e, pygame.Rect(x_btn - p(140), y_titre - p(2), p(130), h_btn),
                      langue.T("🗑️ Supprimer"), BLANC, ROUGE if hasattr(self, 'ROUGE') else (220, 60, 60),
                      self._supprimer_dossier_actuel)

        # champ de recherche instantanee (debounce 180 ms)
        h_champ = p(30) if self.minuscule_h else p(34)
        y_champ = y_titre + (p(34) if self.minuscule_h else p(62))
        w_champ = self.larg - x0 - p(26) - p(120)
        ri = pygame.Rect(x0, y_champ, max(p(120), w_champ), h_champ)
        self._champ(e, ri, self.mes_recherche, self.mes_recherche_focus,
                    langue.T("Recherche instantanee (nom, dossier, tags)..."))
        self.zones_input.append(("mes", ri))
        if self.mes_recherche:
            self._btn(e, pygame.Rect(ri.right + p(8), y_champ,
                                     p(104), h_champ),
                      langue.T("Effacer"), BLANC, TEXTE, self._effacer_recherche_mes)

        # filtres par dossier
        y_chips = y_champ + h_champ + p(8)
        h_chips = self._chips_dossiers(e, x0, y_chips,
                                       self.larg - p(20))
        top = y_chips + h_chips + p(12)
        zone = pygame.Rect(self.sb, top,
                           self.larg - self.sb, self.haut - top - p(38))
        prev = e.get_clip()
        e.set_clip(zone)

        gap = p(GAP)
        cible = 92 if self.wl < 740 else CELL
        cols = max(1, (zone.width - p(52)) // (p(cible) + gap))
        cell = (zone.width - p(52) - (cols - 1) * gap) // cols
        largeur_grille = cols * cell + (cols - 1) * gap
        gx0 = self.sb + (zone.width - largeur_grille) // 2
        pas = cell + gap

        if not self.mes_affiches:
            if self.mes_recherche.strip():
                msg = langue.T("Aucun sticker ne correspond a la recherche.")
                t2 = None
            elif self.mes_dossier == "mes":
                msg = langue.T("Aucun sticker enregistre.")
                t2 = self.fp.render(
                    langue.T("Etoile ou clic droit dans Recherche pour en ajouter."),
                    True, SOUS)
            elif self.mes_dossier == "fav":
                msg = langue.T("Aucun favori : cliquez l'etoile d'un sticker.")
                t2 = None
            else:
                msg = langue.T("Aucun sticker dans ce dossier.")
                t2 = None
            t = self.f.render(msg, True, SOUS)
            e.blit(t, (zone.centerx - t.get_width() // 2, zone.y + p(50)))
            if t2:
                e.blit(t2, (zone.centerx - t2.get_width() // 2,
                            zone.y + p(80)))

        visibles = []
        affiches = self.mes_affiches
        y0 = zone.y + p(10) - self.mes_scroll
        li_min = max(0, (zone.y - y0 - cell) // pas)
        li_max = (zone.bottom - y0) // pas + 1
        for i in range(li_min * cols, min(len(affiches), (li_max + 1) * cols)):
            chemin = affiches[i]
            c, li = i % cols, i // cols
            r = pygame.Rect(gx0 + c * pas,
                            zone.y + p(10) + li * pas - self.mes_scroll,
                            cell, cell)
            if r.bottom < zone.y or r.y > zone.bottom:
                continue
            visibles.append(chemin)
            survol = r.collidepoint(self.souris)
            pygame.draw.rect(e, BLANC, r, border_radius=p(10))
            pygame.draw.rect(e, ACCENT if survol else BORD, r,
                             p(2) if survol else 1, border_radius=p(10))
            img = self._thumb_mes(chemin, cell - p(14))
            if img is not None:
                e.blit(img, img.get_rect(center=r.center))
            else:
                self._skeleton(e, pygame.Rect(r.x + p(8), r.y + p(8),
                                              r.w - p(16), r.h - p(16)))
            self.zones_mes.append((i, r))
        e.set_clip(prev)
        # generation en arriere-plan : visibles d'abord, puis le reste
        self._maj_vignettes(visibles)

        nb_lignes = max(1, (len(self.mes_affiches) + cols - 1) // cols)
        contenu_h = nb_lignes * pas + p(10)
        self.mes_scroll = min(self.mes_scroll,
                              max(0, contenu_h - zone.height))
        if contenu_h > zone.height:
            self._scrollbar(e, zone, self.mes_scroll, contenu_h)


    # ---- vue boutique ---------------------------------------------------
    @property
    def boutique_affiches(self):
        """Liste des packs et collections thématiques filtrés selon la recherche."""
        q = self.bq.strip().lower()
        if not q:
            return self.boutique
        res = []
        # Pack thématique dynamique Tenor
        slug = re.sub(r"[\W_]+", "_", q).strip("_")
        dynamic_pack = {
            "id": f"tenor_{slug}",
            "nom": f"Collection : {self.bq.capitalize()}",
            "description": langue.T(
                "Bibliotheque '{q}' (36 stickers HD Tenor)").format(q=self.bq),
            "source": "tenor_theme",
            "theme_query": self.bq,
            "nb": 36,
            "tags": [q]
        }
        res.append(dynamic_pack)
        # Pack thematique dynamique Risibank (memes FR : Soral, Zemmour...)
        res.append({
            "id": f"risibank_{slug}",
            "nom": f"Risibank : {self.bq.strip()}",
            "description": langue.T("Memes FR de Risibank : {q}").format(
                q=self.bq.strip()),
            "source": "risibank_theme",
            "theme_query": self.bq.strip(),
            "nb": 60,
            "tags": [q, "risibank"],
        })
        for p in self.boutique:
            tags = " ".join(p.get("tags", [])).lower()
            nom = p.get("nom", "").lower()
            desc = p.get("description", "").lower()
            if q in tags or q in nom or q in desc:
                res.append(p)
        return res

    def ouvrir_boutique(self, idx):
        affiches = self.boutique_affiches
        if idx >= len(affiches):
            return
        pack = affiches[idx]
        self.b_sel = pack
        self.b_apercu = []
        self.b_apercu_info = None
        self.b_scroll_ap = 0
        self._lancer(sources.apercu_pack_worker, pack)

    def installer_boutique(self, pack):
        pid = pack.get("id") or pack.get("slug") or "pack"
        if pid in self.b_installe:
            self.toast = (langue.T("Deja installe"), pygame.time.get_ticks())
            return
        self.status = f"Installation de {pack.get('nom', pid)}..."
        self._lancer(sources.installer_pack_worker, pack)

    def copier_boutique(self, i):
        if 0 <= i < len(self.b_apercu):
            _u, png = self.b_apercu[i]
            self._copier(sources.preparer_image(png))   # HD au collage

    def _chips_boutique(self, e, y):
        x0 = self.sb + self.px(26)
        x = x0
        x_max = self.larg - self.px(20)
        h_chip = self.px(22 if self.petit_h else 26)
        ligne = self.px(28 if self.petit_h else 32)
        pas = self.px(8)
        fonte = self.fp if self.petit_h else self.f
        pad = self.px(16 if self.petit_h else 20)
        hauteur = h_chip
        for _label, query in BOUTIQUE_CHIPS:
            label = langue.T(_label)
            w = fonte.size(label)[0] + pad
            if x + w > x_max and x > x0:
                x = x0
                y += ligne
                hauteur += ligne
            r = pygame.Rect(x, y, w, h_chip)
            actif = (self.bq == query) or (not self.bq and not query)
            survol = r.collidepoint(self.souris)
            pygame.draw.rect(e, ACCENT_F if (actif or survol) else BLANC, r,
                             border_radius=h_chip // 2)
            pygame.draw.rect(e, ACCENT if (actif or survol) else BORD, r,
                             max(1, self.px(1)), border_radius=h_chip // 2)
            t = fonte.render(label, True, ACCENT_D if (actif or survol) else TEXTE)
            e.blit(t, (x + pad // 2, y + (h_chip - t.get_height()) // 2))

            def _click_chip(q_val=query):
                self.bq = q_val
                affiches = self.boutique_affiches
                if affiches:
                    self.ouvrir_boutique(0)

            self.zones_btn.append((_click_chip, r))
            x += w + pas
        return hauteur

    def _lancer_recherche_boutique(self):
        affiches = self.boutique_affiches
        if affiches:
            self.ouvrir_boutique(0)

    def _vue_boutique(self, e):
        p = self.px
        x0 = self.sb + p(26)
        etroit = self.wl < 740
        fonte_titre = self.fm if self.minuscule_h else self.fg
        y_titre = p(8) if self.minuscule_h else p(16)
        e.blit(fonte_titre.render(langue.T("Boutique de packs & Thèmes"), True, TEXTE),
               (x0, y_titre))
        if not self.minuscule_h:
            e.blit(self.fp.render(
                langue.T("Téléchargez des collections entières de stickers (Telegram, WhatsApp, Tenor)."),
                True, SOUS), (x0, y_titre + p(26)))

        # Champ de recherche thématique & boutons
        y_champ = y_titre + (p(32) if self.minuscule_h else p(50))
        h_champ = p(34)
        w_btn_rech = p(105)
        w_btn_act = p(95)
        champ_w = max(p(120), self.larg - x0 - w_btn_rech - w_btn_act - p(36))
        ri = pygame.Rect(x0, y_champ, champ_w, h_champ)
        self._champ(e, ri, self.bq, self.bq_focus,
                    langue.T("Rechercher un thème (WhatsApp, Pusheen, Manga, Mignon...)"))
        self.zones_input.append(("bq", ri))

        # Bouton Rechercher
        self._btn(e, pygame.Rect(ri.right + p(8), y_champ, w_btn_rech, h_champ),
                  langue.T("Rechercher"), ACCENT_D, BLANC,
                  lambda: self._lancer_recherche_boutique())

        # Bouton Actualiser
        self._btn(e, pygame.Rect(ri.right + w_btn_rech + p(16), y_champ, w_btn_act, h_champ),
                  langue.T("Actualiser"), BLANC, TEXTE,
                  lambda: (setattr(self, "b_chargement", True),
                           self._lancer(sources.charger_catalogue_packs_worker)))

        # Chips de filtrage thématique
        y_chips = y_champ + h_champ + p(8)
        h_chips = self._chips_boutique(e, y_chips) if not self.minuscule_h else 0

        top = y_chips + h_chips + (p(10) if not self.minuscule_h else p(8))
        zfull = pygame.Rect(x0, top, self.larg - x0 - p(20),
                            self.haut - top - p(38))
        if etroit:
            if self.b_sel:
                self._dessiner_apercu_boutique(e, zfull, "etroit")
            else:
                self._dessiner_liste_boutique(e, zfull)
            return
        zone_w = self.larg - self.sb - p(64)
        col_liste = int(max(p(250), min(p(380), zone_w * 0.42)))
        self.col_boutique = col_liste
        zl = pygame.Rect(x0, top, col_liste, zfull.height)
        self._dessiner_liste_boutique(e, zl)
        za = pygame.Rect(zl.right + p(18), top,
                         self.larg - zl.right - p(18) - p(20), zfull.height)
        self._dessiner_apercu_boutique(e, za, "large")

    def _dessiner_liste_boutique(self, e, zl):
        p = self.px
        prev = e.get_clip()
        e.set_clip(zl)
        pygame.draw.rect(e, BLANC, zl, border_radius=p(12))
        self.zones_boutique = []
        affiches = self.boutique_affiches
        if not affiches:
            if self.b_chargement:
                self._spinner(e, zl)
            else:
                t = self.f.render(langue.T("Aucun pack trouvé."), True, SOUS)
                e.blit(t, (zl.centerx - t.get_width() // 2, zl.y + p(40)))
            e.set_clip(prev)
            return
        pas_l = p(66)
        for i, pack in enumerate(affiches):
            r = pygame.Rect(zl.x + p(8), zl.y + p(8) + i * pas_l
                            - self.b_scroll, zl.w - p(16), p(60))
            if r.bottom < zl.y or r.y > zl.bottom:
                continue
            sel = (pack is self.b_sel) or (self.b_sel and pack.get("id") == self.b_sel.get("id"))
            survol = r.collidepoint(self.souris)
            is_theme = (pack.get("source") == "tenor_theme")
            if sel:
                col_fond = ACCENT_F
            elif is_theme:
                col_fond = (250, 246, 255) if not survol else (244, 238, 255)
            else:
                col_fond = (247, 248, 251) if survol else BLANC
            pygame.draw.rect(e, col_fond, r, border_radius=p(8))
            if is_theme and not sel:
                pygame.draw.rect(e, (215, 195, 245), r, 1, border_radius=p(8))

            pid = pack.get("id") or pack.get("slug") or "pack"
            installe = (pid in self.b_installe) or (pack.get("slug") in self.b_installe)
            rb = pygame.Rect(r.right - p(56), r.centery - p(14),
                             p(48), p(28))
            surv_b = rb.collidepoint(self.souris)
            if installe:
                pygame.draw.rect(e, VERT_F, rb, border_radius=p(8))
                pygame.draw.rect(e, VERT, rb, max(1, p(1)),
                                 border_radius=p(8))
                t = self.fm.render("OK", True, VERT)
                e.blit(t, t.get_rect(center=rb.center))
            else:
                pygame.draw.rect(e, VERT_F if surv_b else (240, 248, 243),
                                 rb, border_radius=p(8))
                pygame.draw.rect(e, VERT if surv_b else (185, 212, 199),
                                 rb, max(1, p(1)), border_radius=p(8))
                t = self.fm.render("+", True, VERT if not surv_b
                                   else (20, 130, 80))
                e.blit(t, t.get_rect(center=rb.center))
            self.zones_btn.append(
                ((lambda pk=pack: self.installer_boutique(pk)), rb))
            w_txt = rb.x - r.x - p(16)
            titre = ("✨ " if is_theme else "") + pack.get("nom", pid)
            self._texte_lim(self.fm, titre, TEXTE if not is_theme else (110, 50, 180),
                            r.x + p(10), r.y + p(4), w_txt)
            desc = pack.get("description", "")
            if len(desc) > 46:
                desc = desc[:45] + "..."
            self._texte_lim(self.fp, desc, SOUS,
                            r.x + p(10), r.y + p(26), w_txt)
            self._texte_lim(self.fp, f"{pack.get('nb', '?')} stickers",
                            ACCENT_D if is_theme else SOUS, r.x + p(10), r.y + p(42), w_txt)
            self.zones_boutique.append((i, r))
        e.set_clip(prev)
        cont_liste = len(affiches) * pas_l + p(16)
        self.b_scroll = min(self.b_scroll, max(0, cont_liste - zl.height))
        if cont_liste > zl.height:
            self._scrollbar(e, zl, self.b_scroll, cont_liste)

    def _dessiner_apercu_boutique(self, e, za, entete):
        p = self.px
        prev = e.get_clip()
        e.set_clip(za)
        pygame.draw.rect(e, BLANC, za, border_radius=p(12))
        self.zones_b_apercu = []
        if not self.b_sel:
            if entete == "etroit":
                e.set_clip(prev)
                return
            msg = ["Sélectionne un pack à gauche",
                   "pour le prévisualiser.", "",
                   langue.T("Clic sur une vignette = copier l'image"),
                   "Bouton + = installer tout le pack."]
            for i, ln in enumerate(msg):
                t = self.fm if i == 0 else self.f
                self._texte_lim(t, ln, TEXTE if i == 0 else SOUS,
                                za.x + p(24), za.y + p(90) + i * p(26),
                                za.w - p(48))
            e.set_clip(prev)
            return
        pack = self.b_sel
        pid = pack.get("id") or pack.get("slug") or "pack"
        installe = (pid in self.b_installe) or (pack.get("slug") in self.b_installe)
        is_theme = (pack.get("source") == "tenor_theme")
        if entete == "etroit":
            rb0 = pygame.Rect(za.x + p(12), za.y + p(12), p(96), p(32))
            self._btn(e, rb0, langue.T("< Retour"), BLANC, TEXTE,
                      lambda: setattr(self, "b_sel", None))
            self._texte_lim(self.fm, pack.get("nom", pid), TEXTE,
                            rb0.right + p(10),
                            rb0.centery - self.fm.get_height() // 2,
                            za.right - rb0.right - p(22))
            ligne2_y = rb0.bottom + p(8)
            nb = self.b_apercu_info[1] if self.b_apercu_info else pack.get("nb", "?")
            self._texte_lim(self.fp, f"{nb} stickers", SOUS,
                            za.x + p(16), ligne2_y, za.w - p(190))
            self._btn(e, pygame.Rect(za.right - p(180), ligne2_y - p(4),
                                     p(168), p(32)),
                      langue.T("Déjà installé") if installe else langue.T("Installer tout le pack"),
                      VERT if not installe else PIST,
                      BLANC if not installe else SOUS,
                      (lambda: None) if installe else
                      (lambda: self.installer_boutique(pack)))
            gy = ligne2_y + p(42)
            h_grille = za.bottom - gy - p(8)
        else:
            self._texte_lim(self.fg, ("✨ " if is_theme else "") + pack.get("nom", pid), TEXTE,
                            za.x + p(18), za.y + p(16), za.w - p(230))
            desc = pack.get("description", "")
            self._texte_lim(self.f, desc, SOUS,
                            za.x + p(18), za.y + p(44), za.w - p(230))
            nb = self.b_apercu_info[1] if self.b_apercu_info else pack.get("nb", "?")
            self._texte_lim(self.fp, langue.T(
                "{n} stickers HD - clic = copier · bouton = installer").format(n=nb),
                            SOUS, za.x + p(18), za.y + p(70), za.w - p(36))
            self._btn(e, pygame.Rect(za.right - p(210), za.y + p(18),
                                     p(190), p(36)),
                      langue.T("Déjà installé") if installe else langue.T("Installer tout le pack"),
                      VERT if not installe else PIST,
                      BLANC if not installe else SOUS,
                      (lambda: None) if installe else
                      (lambda: self.installer_boutique(pack)),
                      grand=True)
            gy = za.y + p(96)
            h_grille = za.height - p(110)
        cell = p(88)                # Format net, net et sans flou
        gap_a = p(8)
        cols_a = max(1, (za.w - p(36)) // (cell + gap_a))
        cont_a = ((len(self.b_apercu) + cols_a - 1) // cols_a or 1) \
            * (cell + gap_a)
        self.b_scroll_ap = min(self.b_scroll_ap, max(0, cont_a - h_grille))
        for i, (_u, png) in enumerate(self.b_apercu):
            c, li = i % cols_a, i // cols_a
            r = pygame.Rect(za.x + p(18) + c * (cell + gap_a),
                            gy + li * (cell + gap_a) - self.b_scroll_ap,
                            cell, cell)
            if r.bottom < za.y or r.y > za.bottom:
                continue
            survol = r.collidepoint(self.souris)
            pygame.draw.rect(e, FOND, r, border_radius=p(8))
            pygame.draw.rect(e, ACCENT if survol else BORD, r,
                             p(2) if survol else 1, border_radius=p(8))
            try:
                img = self._surf_de(self._surfs_pack, _u, png, cell - p(12))
                if img is not None:
                    e.blit(img, img.get_rect(center=r.center))
            except Exception:
                pass
            self.zones_b_apercu.append((i, r))
        if not self.b_apercu:
            self._spinner(e, pygame.Rect(za.x, gy, za.w, p(60)))
        e.set_clip(prev)
        if cont_a > h_grille:
            zs = pygame.Rect(za.x, gy, za.w, h_grille)
            self._scrollbar(e, zs, self.b_scroll_ap, cont_a)

    # ---- footer ---------------------------------------------------------
    def _footer(self, e):
        if self.status:
            t = self.fp.render(self.status, True, SOUS)
            zone = pygame.Rect(self.sb + 12, 0,
                               self.larg - self.sb - 24, self.haut)
            prev = e.get_clip()
            e.set_clip(zone)
            e.blit(t, (self.sb + 12, self.haut - 26))
            e.set_clip(prev)
        if self.toast:
            texte, t0 = self.toast
            age = pygame.time.get_ticks() - t0
            if age > 2200:
                self.toast = None
            else:
                t = self.fm.render("  " + texte + "  ", True, BLANC)
                w = t.get_width() + 24
                r = pygame.Rect(self.larg - w - 20, self.haut - 58, w, 36)
                pygame.draw.rect(e, VERT, r, border_radius=18)
                e.blit(t, (r.x + 12, r.y + 9))


# lancement autonome (sans fenetre flottante)
if __name__ == "__main__":
    os.chdir((os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))))
    pygame.init()
    bib = Bibliotheque()
    try:
        while bib.actif:
            bib.gerer()
    finally:
        pygame.quit()
