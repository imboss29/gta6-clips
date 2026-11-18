"""Textes d'accroche « putaclic » affichés en haut de chaque clip.

Règle : ils promettent une émotion (choc, rire, suspense), jamais un fait inventé
sur le streamer (pas d'accusation, pas de fausse info) pour ne pas risquer de signalement.
"""
import random

GENERIQUES = [
    "Attends la fin, tu vas pas y croire",
    "Regarde jusqu'au bout…",
    "La fin est complètement folle",
    "Ne zappe surtout pas la fin",
    "Tout part en vrille à la fin",
    "Il a vraiment fait ça en live",
    "Personne ne s'attendait à ça",
    "Attends la fin, c'est terrible",
    "Le chat est devenu fou",
    "C'est parti en cacahuète",
    "La pire décision de sa vie",
    "Il s'est fait afficher en direct",
    "Ça a très mal tourné",
    "Il pensait que personne ne verrait",
    "Regarde bien sa réaction",
    "Ce moment a choqué tout le live",
    "Il a pas osé… si, il a osé",
    "Le retournement de situation",
    "Il pète un câble en live",
    "Le moment le plus fou du live",
]

# si un mot apparaît dans ce qui est dit, accroche plus précise
THEMES = [
    (("police", "flic", "keuf", "lspd", "sasp", "menotte"), [
        "La police ne s'attendait pas à ça", "Il provoque la police en direct", "Course-poursuite qui tourne mal"]),
    (("meuf", "copine", "chérie", "date", "bisou", "fiancé"), [
        "Sa meuf va pas aimer ça", "Le date qui tourne au drame", "Elle l'a recalé en direct"]),
    (("argent", "billet", "thune", "million", "euros", "€"), [
        "Il a perdu une fortune en live", "Tout ça pour de l'argent…", "Il a craqué tout son argent"]),
    (("arme", "flingue", "tirer", "balle", "molotov", "braquage"), [
        "Le braquage qui tourne mal", "Il sort l'arme en plein milieu", "Ça a dégénéré en 2 secondes"]),
    (("hôpital", "mort", "tué", "ambulance", "coma"), [
        "Il a frôlé la mort", "Personne n'a pu le sauver", "Fin tragique en direct"]),
    (("rire", "mdr", "ptdr", "drôle", "hahaha"), [
        "Impossible de pas rire", "Il était mort de rire", "Le fou rire de l'année"]),
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
        base = [f"GTA 6 dans {jours} jours : sa réaction", f"Plus que {jours} jours avant GTA 6…",
                "Sa réaction au trailer de GTA 6", "Il découvre GTA 6 et pète un câble"]
    elif jours == 1:
        base = ["GTA 6 sort DEMAIN", "Plus qu'un jour avant GTA 6…"]
    else:
        base = ["GTA 6 est enfin sorti", "Sa première réaction sur GTA 6"]
    libres = [h for h in base if h not in deja]
    return random.Random(seed).choice(libres) if libres else None
