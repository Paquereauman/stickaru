# -*- coding: utf-8 -*-
"""Choix de la langue de l'interface : francais (fr), anglais (en), chinois (zh).

Module volontairement autonome et sans dependance : il ne peut jamais faire
planter l'application. Si une traduction manque, le texte francais d'origine
est renvoye tel quel.

Ajouter une chaine = ajouter une ligne dans TABLE, rien d'autre a faire.
"""

import os
import sys
import json

DOSSIER = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
FICHIER = os.path.join(os.environ.get("STICKARU_DATA") or DOSSIER, "langue.json")

CODES = ("fr", "en", "zh")
ETIQUETTES = {"fr": "FR", "en": "EN", "zh": "中文"}
NOMS = {"fr": "Francais", "en": "English", "zh": "中文"}

LANGUE = "fr"

# --------------------------------------------------------------------------
# (texte francais d'origine, anglais, chinois)
# --------------------------------------------------------------------------
TABLE = [
    # --- barre laterale / navigation ---
    ("Recherche", "Search", "搜索"),
    ("Boutique", "Shop", "商店"),
    ("Importer URL", "Import URL", "导入链接"),
    ("Mes stickers", "My stickers", "我的贴纸"),
    ("bibliotheque", "library", "贴纸库"),
    ("Tous", "All", "全部"),
    ("Chats", "Cats", "猫"),
    ("Chiens", "Dogs", "狗"),
    ("Manga", "Manga", "漫画"),
    ("Memes", "Memes", "梗图"),
    ("Droles", "Funny", "搞笑"),
    ("Amour", "Love", "爱"),
    ("Chats Mignons", "Cute cats", "可爱猫"),
    ("Memes & Droles", "Memes & Funny", "梗图与搞笑"),
    ("Anime & Manga", "Anime & Manga", "动漫与漫画"),
    ("Animaux", "Animals", "动物"),
    ("Dodo", "Sleep", "睡觉"),

    # --- vue Recherche ---
    ("Rechercher un sticker", "Search a sticker", "搜索贴纸"),
    ("Mode HAUTE RESOLUTION (>= 400 px).", "HIGH RESOLUTION mode (>= 400 px).",
     "高分辨率模式（≥ 400 px）。"),
    ("Clic = copier · clic droit = enregistrer · etoile = favori.",
     "Click = copy · right-click = save · star = favourite.",
     "单击=复制 · 右键=保存 · 星标=收藏。"),
    ("chat, mignon, anime, dormeur...", "cat, cute, anime, sleepy...",
     "猫、可爱、动漫、睡觉"),
    ("Tapez un mot-cle ci-dessus ou choisissez une thematique pour rechercher.",
     "Type a keyword above or pick a theme to search.",
     "在上方输入关键词，或选择一个主题来搜索。"),
    ("Aucune source HD pour cette recherche.", "No HD source for this search.",
     "此搜索没有高清来源。"),
    ("Aucun resultat.", "No result.", "没有结果。"),
    ("Analyse des sources originales (>= 400 px)...",
     "Scanning original sources (>= 400 px)...",
     "正在分析原始来源（ 400 px）"),

    # --- vue Importer ---
    ("Importer une image", "Import an image", "导入图片"),
    ("Adresse directe d'un sticker (PNG, WebP ou GIF)",
     "Direct sticker address (PNG, WebP or GIF)",
     "贴纸直链地址（PNG、WebP 或 GIF）"),
    ("Telecharger", "Download", "下载"),
    ("Fonctionne avec les CDN, StickPNG, HiClipart, etc.",
     "Works with CDNs, StickPNG, HiClipart, etc.",
     "支持各类 CDN，如 StickPNG、HiClipart 等。"),
    ("Le WebP/GIF est converti automatiquement en PNG transparent.",
     "WebP/GIF is automatically converted to transparent PNG.",
     "WebP/GIF 会自动转换为透明 PNG。"),

    # --- vue Mes stickers ---
    ("Actualiser", "Refresh", "刷新"),
    ("🗑️ Supprimer", "🗑️ Delete", "🗑️ 删除"),
    ("Recherche instantanee (nom, dossier, tags)...",
     "Instant search (name, folder, tags)...",
     "即时搜索（名称、文件夹、标签）"),
    ("Effacer", "Clear", "清除"),
    ("Aucun sticker ne correspond a la recherche.", "No sticker matches the search.",
     "没有匹配的贴纸。"),
    ("Aucun sticker enregistre.", "No sticker saved.", "尚未保存贴纸。"),
    ("Etoile ou clic droit dans Recherche pour en ajouter.",
     "Star or right-click in Search to add some.",
     "在搜索页点击星标或右键即可添加。"),
    ("Aucun favori : cliquez l'etoile d'un sticker.",
     "No favourite: click a sticker's star.", "暂无收藏：点击贴纸上的星标。"),
    ("Aucun sticker dans ce dossier.", "No sticker in this folder.",
     "此文件夹中没有贴纸。"),
    ("+ Ajouter une categorie", "+ Add a category", "+ 添加分类"),
    ("Mes stickers ({n})", "My stickers ({n})", "我的贴纸（{n}）"),
    ("Etoiles ({n})", "Stars ({n})", "收藏（{n}）"),
    ("{n} stickers", "{n} stickers", "{n} 张贴纸"),
    ("{n} stickers - clic = copier", "{n} stickers - click = copy",
     "{n} 张贴纸  单击=复制"),
    (" (filtre : {q})", " (filter: {q})", "（筛选：{q}）"),
    (" - clic droit = retirer des favoris", " - right-click = remove from favourites",
     "  右键=取消收藏"),

    # --- vue Boutique ---
    ("Boutique de packs & Thèmes", "Pack & theme shop", "贴纸包与主题商店"),
    ("Téléchargez des collections entières de stickers (Telegram, WhatsApp, Tenor).",
     "Download whole sticker collections (Telegram, WhatsApp, Tenor).",
     "下载整套贴纸合集（Telegram、WhatsApp、Tenor）。"),
    ("Rechercher un thème (WhatsApp, Pusheen, Manga, Mignon...)",
     "Search a theme (WhatsApp, Pusheen, Manga, Cute...)",
     "搜索主题（WhatsApp、Pusheen、漫画、可爱）"),
    ("Rechercher", "Search", "搜索"),
    ("Aucun pack trouvé.", "No pack found.", "未找到贴纸包。"),
    ("Déjà installé", "Already installed", "已安装"),
    ("Installer tout le pack", "Install the whole pack", "安装整个贴纸包"),
    ("< Retour", "< Back", "< 返回"),
    ("Clic sur une vignette = copier l'image",
     "Click a thumbnail to copy the image",
     "单击缩略图即可复制图片"),
    ("Deja installe", "Already installed", "已安装"),
    ("{n} stickers HD - clic = copier · bouton = installer",
     "{n} HD stickers - click = copy · button = install",
     "{n} 张高清贴纸 – 单击=复制 · 按钮=安装"),

    # --- messages (toasts / barre d'etat) ---
    ("Image HD copiee - colle-la (Ctrl+V)", "HD image copied - paste it (Ctrl+V)",
     "高清图片已复制  粘贴（Ctrl+V）"),
    ("Ajoute aux favoris", "Added to favourites", "已加入收藏"),
    ("Retire des favoris", "Removed from favourites", "已取消收藏"),
    ("Enregistrement du favori...", "Saving favourite...", "正在保存收藏"),
    ("Sticker deja dans vos stickers", "Sticker already saved", "该贴纸已存在"),
    ("Recuperation HD...", "Fetching HD...", "正在获取高清"),
    ("Pack installe - ouvert dans Mes stickers",
     "Pack installed - opened in My stickers",
     "贴纸包已安装  已在我的贴纸中打开"),
    ("Enregistre dans Mes stickers", "Saved in My stickers", "已保存到我的贴纸"),
    ("Pack '{nom}' supprime", "Pack '{nom}' deleted", "已删除贴纸包{nom}"),
    ("Categorie '{nom}' ajoutee", "Category '{nom}' added", "已添加分类{nom}"),
    ("Categorie '{nom}' retiree", "Category '{nom}' removed", "已删除分类{nom}"),
    ("{n} doublon(s) supprime(s) automatiquement",
     "{n} duplicate(s) deleted automatically", "已自动删除 {n} 个重复项"),
    ("{n} sticker(s) flou(s) supprime(s)", "{n} blurry sticker(s) deleted",
     "已删除 {n} 张模糊贴纸"),
    ("Index de recherche : {i}/{n}...", "Search index: {i}/{n}...",
     "搜索索引：{i}/{n}"),
    ("Suppression des stickers flous : {i}/{n}...",
     "Deleting blurry stickers: {i}/{n}...", "正在删除模糊贴纸：{i}/{n}"),
    ("Recherche HD : ", "HD search: ", "高清搜索："),
    ("Recherche : ", "Search: ", "搜索："),
    ("{n} stickers locaux trouves (recherche web en cours...)",
     "{n} local stickers found (web search running...)",
     "找到 {n} 个本地贴纸（正在联网搜索）"),

    # --- messages venant de sources.py ---
    ("Recherche : {q}", "Search: {q}", "搜索：{q}"),
    ("Recherche : {q} (cache)", "Search: {q} (cache)", "搜索：{q}（缓存）"),
    ("Aucun resultat trouve sur Tenor", "No result found on Tenor",
     "Tenor 上没有找到结果"),
    ("{n} stickers trouves", "{n} stickers found", "找到 {n} 张贴纸"),
    ("{n} packs disponibles", "{n} packs available", "{n} 个贴纸包可用"),
    ("Recherche de packs : {q}", "Searching packs: {q}", "正在搜索贴纸包：{q}"),
    ("{n} packs trouves", "{n} packs found", "找到 {n} 个贴纸包"),
    ("Aucun sticker trouve a installer", "No sticker found to install",
     "没有可安装的贴纸"),
    ("Pack '{nom}' installe ({n} nouveaux stickers) !",
     "Pack '{nom}' installed ({n} new stickers)!",
     "贴纸包{nom}已安装（新增 {n} 张）！"),
    ("Nettoyage auto des doublons : {i}/{n}...",
     "Auto duplicate cleanup: {i}/{n}...", "自动清理重复项：{i}/{n}"),
    ("Nettoyage automatique des doublons...", "Automatic duplicate cleanup...",
     "正在自动清理重复项"),
    ("Suppression des stickers flous...", "Deleting blurry stickers...",
     "正在删除模糊贴纸"),
    ("Recherche HD : {q}", "HD search: {q}", "高清搜索：{q}"),
    ("{n} groupes de doublons trouves", "{n} duplicate groups found", "找到 {n} 组重复项"),
    ("Index de recherche : {n} stickers", "Search index: {n} stickers", "搜索索引：{n} 张贴纸"),
    ("Cache nettoye : {n} Mo liberes", "Cache cleaned: {n} MB freed", "缓存已清理：释放 {n} MB"),
    ("Telechargement URL...", "Downloading URL...", "正在下载链接…"),
    ("Enregistre en HD : {nom}", "Saved in HD: {nom}", "已保存高清：{nom}"),
    ("Importe : {nom}", "Imported: {nom}", "已导入：{nom}"),
    ("Ouverture {slug}...", "Opening {slug}...", "正在打开 {slug}…"),
    ("Catalogue : {n} packs", "Catalogue: {n} packs", "目录：{n} 个贴纸包"),
    ("{n} packs Telegram prets", "{n} Telegram packs ready", "{n} 个 Telegram 贴纸包已就绪"),
    ("Bibliotheque '{q}' (36 stickers HD Tenor)", "Library '{q}' (36 HD stickers from Tenor)", '图库“{q}”（来自 Tenor 的 36 张高清贴纸）'),
    ("Memes FR de Risibank : {q}", "French memes from Risibank: {q}", "Risibank 法国梗图：{q}"),
    ('Tenor injoignable : active ton VPN/proxy (Clash, Hiddify) puis relance la recherche.', 'Tenor unreachable: turn on your VPN/proxy (Clash, Hiddify) then search again.', '无法连接 Tenor：请打开 VPN/代理（Clash、Hiddify）后重试。'),
]

TRADUCTIONS = {
    "en": {fr: en for fr, en, _zh in TABLE},
    "zh": {fr: zh for fr, _en, zh in TABLE},
}


def charger():
    """Recharge la langue choisie (fichier langue.json)."""
    global LANGUE
    try:
        with open(FICHIER, "r", encoding="utf-8") as f:
            code = json.load(f).get("langue", "fr")
        if code in CODES:
            LANGUE = code
    except Exception:
        pass
    return LANGUE


def sauver():
    try:
        tmp = FICHIER + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"langue": LANGUE}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, FICHIER)
    except Exception:
        pass


def definir(code):
    """Change la langue et la memorise."""
    global LANGUE
    if code in CODES:
        LANGUE = code
        sauver()
    return LANGUE


def T(texte, **champs):
    """Traduit un texte francais. Ne leve jamais d'exception."""
    try:
        if LANGUE == "fr":
            return texte
        trad = TRADUCTIONS.get(LANGUE, {}).get(texte, texte)
        return trad.format(**champs) if champs else trad
    except Exception:
        return texte
