"""Textes d'accroche « putaclic » affichés en haut de chaque clip.

Règle : ils promettent une émotion (choc, rire, suspense), jamais un fait inventé
sur le streamer (pas d'accusation, pas de fausse info) pour ne pas risquer de signalement.
"""
import random

GENERIQUES = [
    "Wait for the ending…",
    "Watch till the end",
    "The ending is insane",
    "Don't skip the end",
    "It all goes wrong at the end",
    "He really did this live",
    "Nobody saw this coming",
    "Chat went crazy",
    "This went south fast",
    "Worst decision of his life",
    "He got exposed live",
    "This did not end well",
    "He thought nobody would notice",
    "Watch his reaction",
    "This moment shocked the whole stream",
    "He didn't… oh, he did",
    "The plot twist",
    "He loses it on stream",
    "Craziest moment of the stream",
    "You won't believe this",
]

# si un mot apparaît dans ce qui est dit, accroche plus précise
THEMES = [
    (("police", "cop", "cops", "officer", "pd ", "cuffs", "arrest"), [
        "The cops didn't expect this", "He trolls the police live", "This chase went horribly wrong"]),
    (("girlfriend", "babe", "date", "kiss", "wife", "married"), [
        "His girl won't like this", "The date that turned into a disaster", "She rejected him live"]),
    (("money", "cash", "million", "bank", "dollars", "rich"), [
        "He lost a fortune live", "All that for money…", "He blew all his money"]),
    (("gun", "shoot", "shot", "rob", "robbery", "heist"), [
        "The heist that went wrong", "He pulls the gun out of nowhere", "It escalated in 2 seconds"]),
    (("hospital", "dead", "died", "kill", "ems", "down"), [
        "He almost died", "Nobody could save him", "Tragic ending live"]),
    (("laugh", "lmao", "lol", "funny", "hahaha"), [
        "Try not to laugh", "He couldn't stop laughing", "Funniest moment of the year"]),
]


def choose(words, seed=None, deja=()):
    """Accroche adaptée à ce qui est dit, sans répéter celles déjà utilisées dans la fournée."""
    rnd = random.Random(seed)
    text = " " + " ".join(w[2] for w in words).lower() + " "
    for keys, hooks in THEMES:
        libres = [h for h in hooks if h not in deja]
        if libres and any(k in text for k in keys):
            return rnd.choice(libres)
    libres = [h for h in GENERIQUES if h not in deja] or GENERIQUES
    return rnd.choice(libres)


SORTIE_GTA6 = __import__("datetime").date(2026, 11, 19)


def gta6(seed=None, deja=()):
    """Accroches pour les réactions aux trailers / annonces de GTA 6, avec compte à rebours."""
    import datetime
    jours = (SORTIE_GTA6 - datetime.date.today()).days
    if jours > 1:
        base = [f"GTA 6 in {jours} days: his reaction", f"Only {jours} days until GTA 6…",
                "His reaction to the GTA 6 trailer", "He sees GTA 6 and loses it"]
    elif jours == 1:
        base = ["GTA 6 drops TOMORROW", "One day left until GTA 6…"]
    else:
        base = ["GTA 6 is finally out", "His first reaction to GTA 6"]
    libres = [h for h in base if h not in deja]
    return random.Random(seed).choice(libres) if libres else None
