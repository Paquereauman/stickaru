# -*- coding: utf-8 -*-
"""
Chat volant - widget de bureau (Windows)
Fenetre transparente sans bord, toujours au premier plan.

Commandes :
  Glisser        deplacer le chat
  Clic gauche    sticker suivant
  Clic droit     sticker precedent
  Molette        changer de sticker
  B ou bouton +  ouvrir la bibliotheque en ligne (Telegram, GIPHY, URL)
  R              recharger les stickers du dossier
  Double-clic    quitter
  Echap / Q      quitter

Depose tes propres stickers PNG dans le dossier  stickers/
(images sur fond transparent, grandes -> elles sont reduites automatiquement).
"""

import os
import sys
import io
import glob
import hashlib
import ctypes
from ctypes import wintypes, byref, c_void_p, c_int, c_uint, c_ulong, sizeof

import pygame

# ---------------------------------------------------------------- config
TAILLE = 240               # taille de base (pixels), ajustee selon DPI
TAILLE_BASE = 240
DOSSIER = os.path.join((os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))), "stickers")

# ---------------------------------------------------------------- win32
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WS_POPUP        = 0x80000000
WS_EX_LAYERED   = 0x00080000
WS_EX_TOPMOST   = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

ULW_ALPHA       = 0x00000002
AC_SRC_OVER     = 0x00
AC_SRC_ALPHA    = 0x01
DIB_RGB_COLORS  = 0
BI_RGB          = 0

HTTRANSPARENT   = -1
HTCAPTION       = 2
WM_DESTROY      = 0x0002
WM_NCHITTEST    = 0x0084
WM_LBUTTONDOWN  = 0x0201
WM_LBUTTONUP    = 0x0202
WM_RBUTTONUP    = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_MOUSEMOVE    = 0x0200
WM_MOUSEWHEEL   = 0x020A
WM_KEYDOWN      = 0x0100
VK_ESCAPE       = 0x1B
VK_Q            = 0x51
VK_B            = 0x42
VK_R            = 0x52
VK_LEFT         = 0x25
VK_RIGHT        = 0x27
PM_REMOVE       = 0x0001


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte),
                ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte),
                ("AlphaFormat", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", POINT)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", c_int), ("cbWndExtra", c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


def _proto(lib, nom, restype, *argtypes):
    f = getattr(lib, nom)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


L = ctypes.c_long
P = ctypes.c_void_p

_proto(user32, "GetSystemMetrics", L, ctypes.c_int)
_proto(kernel32, "GetModuleHandleW", P, wintypes.LPCWSTR)
_proto(user32, "LoadCursorW", P, wintypes.HINSTANCE, ctypes.c_void_p)
_proto(user32, "RegisterClassW", wintypes.ATOM, ctypes.POINTER(WNDCLASS))
_proto(user32, "CreateWindowExW", wintypes.HWND, wintypes.DWORD,
       wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p)
_proto(user32, "DefWindowProcW", ctypes.c_ssize_t, wintypes.HWND,
       wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_proto(user32, "GetDC", wintypes.HDC, wintypes.HWND)
_proto(user32, "ReleaseDC", ctypes.c_int, wintypes.HWND, wintypes.HDC)
_proto(user32, "ShowWindow", wintypes.BOOL, wintypes.HWND, ctypes.c_int)
_proto(user32, "DestroyWindow", wintypes.BOOL, wintypes.HWND)
_proto(user32, "SetForegroundWindow", wintypes.BOOL, wintypes.HWND)
_proto(user32, "GetCursorPos", wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
_proto(user32, "PostQuitMessage", None, ctypes.c_int)
_proto(user32, "GetMessageW", wintypes.BOOL, ctypes.POINTER(MSG),
       wintypes.HWND, wintypes.UINT, wintypes.UINT)
_proto(user32, "PeekMessageW", wintypes.BOOL, ctypes.POINTER(MSG),
       wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
_proto(user32, "TranslateMessage", wintypes.BOOL, ctypes.POINTER(MSG))
_proto(user32, "DispatchMessageW", ctypes.c_ssize_t, ctypes.POINTER(MSG))
_proto(user32, "GetWindowRect", wintypes.BOOL, wintypes.HWND,
       ctypes.POINTER(wintypes.RECT))
_proto(user32, "SetWindowPos", wintypes.BOOL, wintypes.HWND, wintypes.HWND,
       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
       wintypes.UINT)
_proto(user32, "SetCapture", wintypes.HWND, wintypes.HWND)
_proto(user32, "ReleaseCapture", wintypes.BOOL)
_proto(user32, "GetCapture", wintypes.HWND)
_proto(user32, "SetTimer", ctypes.c_void_p, wintypes.HWND, ctypes.c_void_p,
       wintypes.UINT, ctypes.c_void_p)
_proto(user32, "KillTimer", wintypes.BOOL, wintypes.HWND, ctypes.c_void_p)
_proto(user32, "IsWindowVisible", wintypes.BOOL, wintypes.HWND)
_proto(user32, "SetProcessDpiAwarenessContext", wintypes.BOOL, ctypes.c_void_p)
_proto(user32, "SetProcessDPIAware", wintypes.BOOL)
_proto(user32, "GetDpiForSystem", wintypes.UINT)
shcore = ctypes.windll.shcore
_proto(shcore, "SetProcessDpiAwareness", ctypes.c_long, ctypes.c_int)
_proto(gdi32, "CreateCompatibleDC", wintypes.HDC, wintypes.HDC)
_proto(gdi32, "CreateDIBSection", wintypes.HBITMAP, wintypes.HDC,
       ctypes.POINTER(BITMAPINFO), wintypes.UINT,
       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
_proto(gdi32, "SelectObject", wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
_proto(gdi32, "DeleteObject", wintypes.BOOL, wintypes.HGDIOBJ)
_proto(gdi32, "DeleteDC", wintypes.BOOL, wintypes.HDC)
_proto(user32, "UpdateLayeredWindow", wintypes.BOOL,
       wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT),
       ctypes.POINTER(SIZE), wintypes.HDC, ctypes.POINTER(POINT),
       wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)


# ---------------------------------------------------------------- stickers
CACHE_PRE = os.path.join((os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))), ".cache_premult")


def _cle_cache_premult(chemin):
    st = os.stat(chemin)
    brut = f"{os.path.abspath(chemin).lower()}|{int(st.st_mtime)}|{st.st_size}|{TAILLE}".encode("utf-8")
    return hashlib.md5(brut).hexdigest()


def _sauver_cache_premult(chemin, pixels, masque):
    os.makedirs(CACHE_PRE, exist_ok=True)
    cle = _cle_cache_premult(chemin)
    with open(os.path.join(CACHE_PRE, cle), "wb") as f:
        f.write(len(masque).to_bytes(4, "little"))
        f.write(pixels)
        f.write(masque)


def _charger_cache_premult(chemin):
    try:
        cle = _cle_cache_premult(chemin)
        p = os.path.join(CACHE_PRE, cle)
        if not os.path.exists(p):
            return None
        try:
            os.utime(p)            # garde les rendus utilises au nettoyage
        except OSError:
            pass
        with open(p, "rb") as f:
            lm = int.from_bytes(f.read(4), "little")
            pixels = f.read(lm * 4)
            masque = f.read(lm)
        return pixels, masque
    except Exception:
        return None


def _generer_premult(chemin):
    """Charge un PNG, redimensionne, centre, badge, convertit en BGRA premultiplie + masque."""
    try:
        import sources
        data = sources.vignette_cachee(chemin, TAILLE)
        if data:
            surface = pygame.image.load(io.BytesIO(data)).convert_alpha()
        else:
            surface = pygame.image.load(chemin).convert_alpha()
        taille = adapter_taille(surface.get_size())
        if taille != surface.get_size():
            surface = pygame.transform.smoothscale(surface, taille)
        cadre = pygame.Surface((TAILLE, TAILLE), pygame.SRCALPHA)
        cadre.fill((0, 0, 0, 0))
        cadre.blit(surface, ((TAILLE - surface.get_width()) // 2, (TAILLE - surface.get_height()) // 2))
        dessiner_badge(cadre)
        bruts = pygame.image.tostring(cadre, "RGBA", False)
        import numpy as np
        arr = np.frombuffer(bruts, np.uint8).reshape(-1, 4)
        a = arr[:, 3].astype(np.uint16)
        out = np.empty((arr.shape[0], 4), np.uint8)
        out[:, 0] = arr[:, 2].astype(np.uint16) * a // 255
        out[:, 1] = arr[:, 1].astype(np.uint16) * a // 255
        out[:, 2] = arr[:, 0].astype(np.uint16) * a // 255
        out[:, 3] = a
        pixels = out.tobytes()
        masque = arr[:, 3].tobytes()
        _sauver_cache_premult(chemin, pixels, masque)
        return pixels, masque
    except Exception as e:
        print("Erreur sticker :", chemin, e)
        return None


def _scanner_stickers():
    """Retourne la liste triee des chemins PNG recursifs."""
    fichiers = []
    for racine, _dirs, fs in os.walk(DOSSIER):
        for f in fs:
            if f.lower().endswith(".png"):
                fichiers.append(os.path.join(racine, f))
    fichiers.sort()
    return fichiers


def _generer_chats_secours():
    """4 stickers chats integres."""
    chats = [((245, 166, 35, 255), (255, 150, 175, 255)),
             ((184, 188, 196, 255), (255, 150, 175, 255)),
             ((58, 58, 63, 255), (214, 130, 255, 255)),
             ((245, 235, 220, 255), (255, 140, 160, 255))]
    resultats = {}
    for i, (coul, acc) in enumerate(chats):
        base = pygame.Surface((TAILLE, TAILLE), pygame.SRCALPHA)
        dessiner_chat_integre(base, coul, acc)
        cadre = pygame.Surface((TAILLE, TAILLE), pygame.SRCALPHA)
        cadre.fill((0, 0, 0, 0))
        cadre.blit(base, (0, 0))
        dessiner_badge(cadre)
        bruts = pygame.image.tostring(cadre, "RGBA", False)
        import numpy as np
        arr = np.frombuffer(bruts, np.uint8).reshape(-1, 4)
        a = arr[:, 3].astype(np.uint16)
        out = np.empty((arr.shape[0], 4), np.uint8)
        out[:, 0] = arr[:, 2].astype(np.uint16) * a // 255
        out[:, 1] = arr[:, 1].astype(np.uint16) * a // 255
        out[:, 2] = arr[:, 0].astype(np.uint16) * a // 255
        out[:, 3] = a
        resultats[f"_secours_{i}"] = (out.tobytes(), arr[:, 3].tobytes())
    print("Aucun PNG dans", DOSSIER, "-> chats integres utilises.")
    return resultats


def _charger_stickers_optimise(limite_initiale=0):
    """Charge stickers avec cache disque + parallele.
    limite_initiale>0 = N stickers d'abord.
    Retourne (chemins, dict_cache)."""
    os.makedirs(DOSSIER, exist_ok=True)
    fichiers = _scanner_stickers()
    if not fichiers:
        return [], {}

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    cache = {}
    lock = Lock()
    limite = limite_initiale if limite_initiale > 0 else len(fichiers)

    def travail(chemin):
        premult = _charger_cache_premult(chemin) or _generer_premult(chemin)
        return (chemin, premult) if premult else (chemin, None)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futurs = {pool.submit(travail, f): f for f in fichiers[:limite]}
        for futur in as_completed(futurs):
            chemin, premult = futur.result()
            if premult:
                with lock:
                    cache[chemin] = premult

    return fichiers, cache
    try:
        cle = _cle_cache_premult(chemin)
        p = os.path.join(CACHE_PRE, cle)
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            lm = int.from_bytes(f.read(4), "little")
            pixels = f.read(lm * 4)
            masque = f.read(lm)
        return pixels, masque
    except Exception:
        return None


def dessiner_chat_integre(surface, couleur, accent):
    """Dessine une tete de chat mignonne (secours si aucun PNG)."""
    w, h = surface.get_size()
    cx = w // 2
    # contour blanc facon sticker
    blanc = (255, 255, 255, 255)
    # oreilles
    pygame.draw.polygon(surface, blanc,
                        [(44, 96), (70, 30), (110, 78)])
    pygame.draw.polygon(surface, blanc,
                        [(196, 96), (170, 30), (130, 78)])
    pygame.draw.circle(surface, blanc, (cx, 148), 88)
    # tete + oreilles couleur
    pygame.draw.polygon(surface, couleur, [(58, 92), (78, 46), (106, 80)])
    pygame.draw.polygon(surface, couleur, [(182, 92), (162, 46), (134, 80)])
    pygame.draw.circle(surface, couleur, (cx, 148), 78)
    # interieur des oreilles
    pygame.draw.polygon(surface, accent, [(70, 80), (80, 56), (96, 76)])
    pygame.draw.polygon(surface, accent, [(170, 80), (160, 56), (144, 76)])
    # rayures
    ray = tuple(max(0, c - 45) for c in couleur[:3]) + (255,)
    for dx in (-34, 0, 34):
        pygame.draw.line(surface, ray, (cx + dx, 74), (cx + dx, 96), 6)
    # yeux
    for ex in (cx - 30, cx + 30):
        pygame.draw.ellipse(surface, (255, 255, 255, 255), (ex - 15, 126, 30, 38))
        pygame.draw.ellipse(surface, (40, 35, 45, 255), (ex - 9, 132, 18, 28))
        pygame.draw.circle(surface, (255, 255, 255, 255), (ex + 2, 138), 4)
    # nez + bouche
    pygame.draw.polygon(surface, accent, [(cx - 8, 168), (cx + 8, 168), (cx, 178)])
    pygame.draw.arc(surface, (80, 60, 60, 255), (cx - 14, 172, 14, 14), 0, 3.2, 3)
    pygame.draw.arc(surface, (80, 60, 60, 255), (cx, 172, 14, 14), 0, 3.2, 3)
    # moustaches
    for dy in (-4, 4):
        pygame.draw.line(surface, (90, 80, 80, 220),
                         (cx - 30, 172 + dy), (cx - 74, 166 + dy), 2)
        pygame.draw.line(surface, (90, 80, 80, 220),
                         (cx + 30, 172 + dy), (cx + 74, 166 + dy), 2)


def _charger_image(chemin, taille):
    """PNG via cache de vignettes disque a la taille exacte (demarrage
    rapide, sans redimensionnement), sinon chargement direct du fichier."""
    try:
        import sources
        data = sources.vignette_cachee(chemin, taille)
        if data:
            return pygame.image.load(io.BytesIO(data)).convert_alpha()
    except Exception:
        pass
    return pygame.image.load(chemin).convert_alpha()


def charger_stickers():
    """Retourne les surfaces PNG du dossier (sous-dossiers inclus)
    ou 4 chats integres si rien."""
    os.makedirs(DOSSIER, exist_ok=True)
    fichiers = []
    for racine, _dirs, fs in os.walk(DOSSIER):
        for f in fs:
            if f.lower().endswith(".png"):
                fichiers.append(os.path.join(racine, f))
    fichiers.sort()
    stickers = []
    for f in fichiers:
        try:
            img = _charger_image(f, TAILLE)
            taille = adapter_taille(img.get_size())
            if taille != img.get_size():
                img = pygame.transform.smoothscale(img, taille)
            stickers.append(img)
        except Exception as e:
            print("Image ignoree :", f, e)
    if not stickers:
        chats = [((245, 166, 35, 255), (255, 150, 175, 255)),   # orange
                 ((184, 188, 196, 255), (255, 150, 175, 255)),  # gris
                 ((58, 58, 63, 255), (214, 130, 255, 255)),     # noir
                 ((245, 235, 220, 255), (255, 140, 160, 255))]  # crème
        for coul, acc in chats:
            base = pygame.Surface((TAILLE_BASE, TAILLE_BASE), pygame.SRCALPHA)
            dessiner_chat_integre(base, coul, acc)
            if TAILLE != TAILLE_BASE:
                base = pygame.transform.smoothscale(base, (TAILLE, TAILLE))
            stickers.append(base)
        print("Aucun PNG dans", DOSSIER, "-> chats integres utilises.")
    return stickers


def adapter_taille(taille_img):
    iw, ih = taille_img
    echelle = min(TAILLE / iw, TAILLE / ih)
    return (max(1, int(iw * echelle)), max(1, int(ih * echelle)))


def badge_rect():
    """Zone du bouton '+' (coordonnees locales TAILLE)."""
    s = TAILLE / 240.0
    cote = int(52 * s)
    return pygame.Rect(TAILLE - cote - int(6 * s),
                       TAILLE - cote - int(6 * s), cote, cote)


def dessiner_badge(cadre):
    r = badge_rect()
    s = TAILLE / 240.0
    pygame.draw.circle(cadre, (38, 38, 46, 235), r.center, r.width // 2)
    pygame.draw.circle(cadre, (255, 255, 255, 255), r.center,
                       r.width // 2, max(2, int(3 * s)))
    ep = max(3, int(6 * s))
    ex = int(14 * s)
    pygame.draw.line(cadre, (255, 255, 255, 255),
                     (r.centerx - ex, r.centery),
                     (r.centerx + ex, r.centery), ep)
    pygame.draw.line(cadre, (255, 255, 255, 255),
                     (r.centerx, r.centery - ex),
                     (r.centerx, r.centery + ex), ep)


def vers_premultiplie(surface):
    """RGBA -> (BGRA premultiplie, masque alpha) pour UpdateLayeredWindow.
    On ne garde que des octets en memoire (pas de Surface pygame)."""
    surface = surface.convert_alpha()
    cadre = pygame.Surface((TAILLE, TAILLE), pygame.SRCALPHA)
    cadre.fill((0, 0, 0, 0))
    cadre.blit(surface, ((TAILLE - surface.get_width()) // 2,
                         (TAILLE - surface.get_height()) // 2))
    dessiner_badge(cadre)
    bruts = pygame.image.tostring(cadre, "RGBA", False)
    try:
        import numpy as np
        arr = np.frombuffer(bruts, np.uint8).reshape(-1, 4)
        a = arr[:, 3].astype(np.uint16)
        out = np.empty((arr.shape[0], 4), np.uint8)
        out[:, 0] = arr[:, 2].astype(np.uint16) * a // 255   # B premultiplie
        out[:, 1] = arr[:, 1].astype(np.uint16) * a // 255   # G premultiplie
        out[:, 2] = arr[:, 0].astype(np.uint16) * a // 255   # R premultiplie
        out[:, 3] = a                                        # A
        return out.tobytes(), arr[:, 3].tobytes()
    except ImportError:
        taille = len(bruts) // 4
        sortie = bytearray(len(bruts))
        alpha = bytearray(taille)
        for i in range(taille):
            r, g, b, al = bruts[4 * i], bruts[4 * i + 1], bruts[4 * i + 2], bruts[4 * i + 3]
            sortie[4 * i] = b * al // 255
            sortie[4 * i + 1] = g * al // 255
            sortie[4 * i + 2] = r * al // 255
            sortie[4 * i + 3] = al
            alpha[i] = al
        return bytes(sortie), bytes(alpha)


# ---------------------------------------------------------------- fenetre
def _get_cache_item(cache_dict, index):
    items = list(cache_dict.values())
    return items[index] if index < len(items) else (None, None)


def liberer_ram():
    """Demande a Windows de paginer la memoire non utilisee (working set)."""
    try:
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        ctypes.windll.psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        ctypes.windll.psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
    except Exception:
        pass


class FenetreFlottante:
    def __init__(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # pygame sans fenetre
        # DPI reels (evite le flou/le decalage sur ecran mise a l'echelle)
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                user32.SetProcessDPIAware()
        pygame.init()
        pygame.display.set_mode((1, 1))
        # adapte la taille aux ecrans haute densite (ex: 150 %)
        try:
            dpi = user32.GetDpiForSystem()
        except AttributeError:
            dpi = 96
        globals()["TAILLE"] = int(round(TAILLE * dpi / 96))
        fichiers, self.cache = _charger_stickers_optimise(limite_initiale=8)
        if not self.cache:
            self.cache = _generer_chats_secours()
            fichiers = []
        self.fichiers = fichiers
        self.nb_stickers = len(self.cache)
        self._precharge_fond = None
        self.index = 0
        self.pixels, self.masque = _get_cache_item(self.cache, 0)

        self.hinst = kernel32.GetModuleHandleW(None)
        self.classe = "ChatVolantPy"
        self.wndproc_ref = WNDPROC(self.gerer_message)  # garde la ref alive

        wc = WNDCLASS()
        wc.style = 0x0008  # CS_DBLCLKS
        wc.lpfnWndProc = self.wndproc_ref
        wc.hInstance = self.hinst
        wc.lpszClassName = self.classe
        wc.hCursor = user32.LoadCursorW(None, 32512)  # fleche
        atom = user32.RegisterClassW(byref(wc))
        if not atom:
            raise ctypes.WinError()

        sx, sy = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        self.x, self.y = (sx - TAILLE) // 2, (sy - TAILLE) // 2

        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            self.classe, "Chat volant", WS_POPUP,
            self.x, self.y, TAILLE, TAILLE, None, None, self.hinst, None)

        self._creer_dib()
        self.dessiner()
        user32.ShowWindow(self.hwnd, 1)
        liberer_ram()
        self.pression_pos = None
        self.pos_depart = (0, 0)
        self.en_drag = False
        self.vivant = True
        self.demande_biblio = False
        self._warm_pret = False
        self._warm_actif = False
        self._lancer_rechauffage()

    def _lancer_rechauffage(self):
        """Genere en tache de fond les vignettes manquantes a taille
        exacte. Ne signale le rechargement que si quelque chose a ete
        cree (pas de boucle si tout est deja cache)."""
        import threading
        import sources
        if self._warm_actif:
            return
        self._warm_actif = True

        def travail():
            nouveau = False
            try:
                for f in sources.lister_stickers_locaux():
                    if sources.vignette_cachee(f, TAILLE) is None:
                        if sources.vignette_locale(f, TAILLE):
                            nouveau = True
                self._warm_pret = nouveau
            except Exception:
                pass
            finally:
                self._warm_actif = False
        threading.Thread(target=travail, daemon=True).start()

    def _creer_dib(self):
        self.screen_dc = user32.GetDC(0)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        bmi = BITMAPINFO()
        h = bmi.bmiHeader
        h.biSize = sizeof(BITMAPINFOHEADER)
        h.biWidth = TAILLE
        h.biHeight = -TAILLE   # top-down
        h.biPlanes = 1
        h.biBitCount = 32
        h.biCompression = BI_RGB
        self.bits = c_void_p()
        self.hbm = gdi32.CreateDIBSection(self.mem_dc, byref(bmi),
                                          DIB_RGB_COLORS, byref(self.bits),
                                          None, 0)
        gdi32.SelectObject(self.mem_dc, self.hbm)

    def dessiner(self):
        ctypes.memmove(self.bits, self.pixels, TAILLE * TAILLE * 4)
        pos = POINT(self.x, self.y)
        src = POINT(0, 0)
        taille = SIZE(TAILLE, TAILLE)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.hwnd, self.screen_dc, byref(pos),
                                   byref(taille), self.mem_dc, byref(src),
                                   0, byref(blend), ULW_ALPHA)

    def changer(self, delta):
        self.index = (self.index + delta) % self.nb_stickers
        self.pixels, self.masque = _get_cache_item(self.cache, self.index)
        self.dessiner()

    def alpha_sous(self, x, y):
        if 0 <= x < TAILLE and 0 <= y < TAILLE:
            return self.masque[y * TAILLE + x]
        return 0

    def gerer_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_NCHITTEST:
            p = wintypes.POINT()
            user32.GetCursorPos(byref(p))
            x, y = p.x - self.x, p.y - self.y
            if self.alpha_sous(x, y) < 10:
                return HTTRANSPARENT          # laisse cliquer sur le bureau
            return 1                          # HTCLIENT : on gere tout

        if msg == WM_LBUTTONDOWN:
            p = wintypes.POINT()
            user32.GetCursorPos(byref(p))
            user32.SetCapture(hwnd)
            user32.SetForegroundWindow(hwnd)
            self.pression_pos = (p.x, p.y)
            self.pos_depart = (p.x, p.y)
            self.en_drag = False
            return 0

        if msg == WM_MOUSEMOVE:
            if self.pression_pos is not None:
                p = wintypes.POINT()
                user32.GetCursorPos(byref(p))
                dx0 = p.x - self.pos_depart[0]
                dy0 = p.y - self.pos_depart[1]
                if abs(dx0) > 4 or abs(dy0) > 4:
                    self.en_drag = True
                    user32.SetWindowPos(hwnd, None,
                                        self.x + dx0, self.y + dy0,
                                        0, 0, 0x0001 | 0x0004)  # NOSIZE|NOZORDER
                    self.pos_depart = (p.x, p.y)
            return 0

        if msg == WM_LBUTTONUP:
            p = wintypes.POINT()
            user32.GetCursorPos(byref(p))
            user32.ReleaseCapture()
            if self.pression_pos is not None and not self.en_drag:
                dx = abs(p.x - self.pression_pos[0])
                dy = abs(p.y - self.pression_pos[1])
                if dx < 5 and dy < 5:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(self.hwnd, byref(rect))
                    local = (p.x - rect.left, p.y - rect.top)
                    if badge_rect().collidepoint(local):
                        self.demande_biblio = True
                    else:
                        self.changer(1)       # clic corps = sticker suivant
            self.pression_pos = None
            self.en_drag = False
            return 0
        if msg == WM_LBUTTONDBLCLK:
            self.vivant = False
            return 0
        if msg == WM_RBUTTONUP:
            self.changer(-1)
            return 0
        if msg == WM_MOUSEWHEEL:
            delta = ctypes.c_short(wparam >> 16).value
            self.changer(1 if delta > 0 else -1)
            return 0
        if msg == WM_KEYDOWN:
            if wparam in (VK_ESCAPE, VK_Q):
                self.vivant = False
            elif wparam == VK_B:
                self.demande_biblio = True
            elif wparam == VK_R:
                self.recharger()
            elif wparam == VK_RIGHT:
                self.changer(1)
            elif wparam == VK_LEFT:
                self.changer(-1)
            return 0
        if msg == WM_DESTROY:
            self.vivant = False
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _pomper(self):
        """Traite les messages de la fenetre du chat (sans bloquer)."""
        m = MSG()
        while user32.PeekMessageW(byref(m), self.hwnd, 0, 0, PM_REMOVE):
            user32.TranslateMessage(byref(m))
            user32.DispatchMessageW(byref(m))

    def _lancer_precharge_voisins(self):
        """Precharge les stickers voisins en tache de fond."""
        import threading
        if self.nb_stickers < 3 or not hasattr(self, 'fichiers'):
            return
        voisins = []
        for delta in (1, -1, 2, -2):
            idx = (self.index + delta) % self.nb_stickers
            if idx < len(self.fichiers):
                voisins.append(self.fichiers[idx])
        if not voisins:
            return

        def fond():
            for chemin in voisins:
                if chemin not in self.cache:
                    premult = _charger_cache_premult(chemin)
                    if not premult:
                        premult = _generer_premult(chemin)
                    if premult:
                        self.cache[chemin] = premult
        t = threading.Thread(target=fond, daemon=True)
        t.start()
        self._precharge_fond = t

    def _suivre_position(self):
        rect = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, byref(rect))
        if (rect.left, rect.top) != (self.x, self.y):
            self.x, self.y = rect.left, rect.top
            self.dessiner()

    def _ouvrir_bibliotheque(self):
        import bibliotheque
        # le module bibliotheque veut un affichage reel (pas 'dummy')
        pygame.display.quit()
        os.environ.pop("SDL_VIDEODRIVER", None)
        pygame.display.init()
        bib = bibliotheque.Bibliotheque()
        while bib.actif and self.vivant:
            self._pomper()
            bib.gerer()
            self._suivre_position()
        # retour en mode sans fenetre pygame (la fenetre Win32 reste)
        pygame.display.quit()
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        if bib.need_reload:
            self.recharger()
        self.demande_biblio = False

    def recharger(self):
        fichiers, cache = _charger_stickers_optimise()
        if not cache:
            cache = _generer_chats_secours()
            fichiers = []
        self.fichiers = fichiers
        self.cache = cache
        self.nb_stickers = len(self.cache)
        self.index = self.index % self.nb_stickers if self.nb_stickers else 0
        if self.nb_stickers:
            self.pixels, self.masque = _get_cache_item(self.cache, self.index)
        self.dessiner()
        self._lancer_rechauffage()

    def boucle(self):
        horloge = pygame.time.Clock()
        tour = 0
        while self.vivant:
            self._pomper()
            if self._warm_pret:
                self._warm_pret = False
                self.recharger()          # bascule sur les vignettes exactes
            if self.demande_biblio:
                self._ouvrir_bibliotheque()
            self._suivre_position()
            # 60 fps pendant un glisser (fluidite), 10 fps sinon (CPU ~0)
            horloge.tick(60 if getattr(self, "en_drag", False) else 10)
            tour += 1
            if tour % 300 == 0:
                liberer_ram()
        user32.DestroyWindow(self.hwnd)

    def quitter(self):
        try:
            gdi32.DeleteObject(self.hbm)
            gdi32.DeleteDC(self.mem_dc)
            user32.ReleaseDC(0, self.screen_dc)
        except Exception:
            pass
        pygame.quit()


if __name__ == "__main__":
    try:
        app = FenetreFlottante()
        app.boucle()
        app.quitter()
    except Exception:
        import traceback
        traceback.print_exc()
        input("Entree pour fermer...")
        sys.exit(1)
