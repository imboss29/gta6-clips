"""Robot GTA 6 : 1 clip par heure et par compte (FR et US), tiré des meilleurs moments
des gros streamers Twitch et Kick (les clips créés par leurs viewers, triés par vues).

Lancé toutes les heures par GitHub Actions (.github/workflows/gta6.yml) :
  python src/gta6.py fr      -> compte FR (profil Upload-Post GTA6)
  python src/gta6.py us      -> compte US (profil Upload-Post default)
  option --essai : choisit et monte le clip sans le publier

Ordre de priorité : clips GTA 6 des dernières 24 h > clips GTA 6 de la semaine > clips GTA (V/RP)
de la semaine. On passe l'heure si un autre post (machines du Mac) est déjà prévu ou sorti
à moins de 35 min, pour rester à environ 1 post par heure.
"""
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
CFG = json.loads((ROOT / "config.json").read_text())
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
API = "https://api.upload-post.com/api/uploadposts"
YTDLP = ["yt-dlp", "--no-warnings", "--quiet", "--socket-timeout", "30", "--retries", "3"]

INTERDITS = ["viol", "pédo", "pedo", "suicide", "nègre", "negro", "bougnoul", "terroris",
             " pd ", "tapette", "nazi", "hitler", " sucer", " suce ", " bite ", "chatte", " nude",
             " nudes", " porn", "branlette", " baiser ",
             " rape", "raping", "kill yourself", " kys ", "nigga", "nigger", "faggot", " fag ",
             "retard", "pussy", " dick ", "blowjob", " cum ", "hentai", "onlyfans"]

GTA6_HOOKS = {
    "fr": ["Il découvre GTA 6 en direct", "Sa première réaction sur GTA 6", "GTA 6 l'a rendu fou",
           "Sa première mission sur GTA 6", "GTA 6 est enfin là…", "Il n'en revient pas sur GTA 6",
           "Le moment le plus fou de GTA 6", "Attends la fin sur GTA 6"],
    "en": ["He plays GTA 6 for the first time", "His first reaction to GTA 6", "GTA 6 broke him",
           "His first mission in GTA 6", "GTA 6 is finally here…", "He can't believe GTA 6",
           "Craziest GTA 6 moment so far", "Wait for the end… GTA 6"],
}


def log(*a):
    print(*a, flush=True)


def fichier_etat(compte):
    return ROOT / f"etat-{compte}.json"   # un fichier par compte : les deux tournent en même temps


def charger_etat(compte):
    f = fichier_etat(compte)
    e = json.loads(f.read_text()) if f.exists() else {}
    e.setdefault("faits", [])
    e.setdefault("posts", [])
    return e


def est_gta(cat):
    c = (cat or "").lower()
    return "grand theft auto" in c or re.search(r"\bgta\b", c) is not None


def est_gta6(cat):
    c = (cat or "").lower()
    return est_gta(c) and re.search(r"\b(vi|6)\b", c) is not None


# ---------- candidats ----------

def clips_twitch(slug, periode):
    """Clips Twitch d'une chaîne (périodes : 24hr, 7d), du plus vu au moins vu."""
    url = f"https://www.twitch.tv/{slug}/clips?filter=clips&range={periode}"
    try:
        out = subprocess.run(YTDLP + ["--flat-playlist", "--playlist-end", "8", "-J", url],
                             capture_output=True, text=True, timeout=90).stdout
        entries = json.loads(out).get("entries") or []
    except Exception:
        return []
    return [{"id": "tw-" + e["url"].rsplit("/", 1)[-1], "url": e["url"], "slug": slug,
             "plateforme": "twitch", "vues": e.get("view_count") or 0,
             "duree": e.get("duration") or 0, "titre": e.get("title") or "", "cat": None}
            for e in entries if e.get("url")]


def clips_kick(slug, periode):
    t = {"24hr": "day", "7d": "week"}[periode]
    for i in range(4):
        try:
            r = requests.get(f"https://kick.com/api/v2/channels/{slug}/clips?sort=view&time={t}",
                             headers={"User-Agent": UA}, timeout=20)
            d = r.json()
            break
        except Exception:
            time.sleep(2 * (i + 1))
    else:
        return []
    out = []
    for c in d.get("clips") or []:
        out.append({"id": "kk-" + c["id"], "url": c.get("video_url") or c.get("clip_url"), "slug": slug,
                    "plateforme": "kick", "vues": c.get("views") or 0, "duree": c.get("duration") or 0,
                    "titre": c.get("title") or "", "cat": (c.get("category") or {}).get("name", "")})
    return out


def categorie_twitch(clip):
    """La catégorie (jeu) d'un clip Twitch n'est pas dans la liste : on la lit sur la page du clip."""
    try:
        j = json.loads(subprocess.run(YTDLP + ["-J", clip["url"]], capture_output=True, text=True,
                                      timeout=90).stdout)
        clip["nom"] = j.get("channel") or clip["slug"]
        return (j.get("categories") or [""])[0]
    except Exception:
        return ""


def candidats(compte, faits):
    from concurrent.futures import ThreadPoolExecutor
    cc = CFG["comptes"][compte]
    for periode in ("24hr", "7d"):
        jobs = [(clips_twitch, s, periode) for s in cc["twitch"]] + [(clips_kick, s, periode) for s in cc["kick"]]
        with ThreadPoolExecutor(6) as ex:
            listes = list(ex.map(lambda j: j[0](j[1], j[2]), jobs))
        tous = [c for l in listes for c in l if c["id"] not in faits and c["url"] and c["duree"] >= 15]
        tous.sort(key=lambda c: c["vues"], reverse=True)
        log(f"{compte} {periode} : {len(tous)} clips trouvés")
        gta6, gta = [], []
        for c in tous[:60]:   # on ne lit la catégorie que des plus vus
            if c["cat"] is None:
                c["cat"] = categorie_twitch(c)
            if est_gta6(c["cat"]):
                gta6.append(c)
                if len(gta6) >= 3:   # les plus vus des clips GTA 6 (3 en réserve si un montage rate)
                    break
            if est_gta(c["cat"]) and len(gta) < 3:
                gta.append(c)
        if gta6:
            return gta6
        if periode == "7d" and gta:
            return gta
    return []


# ---------- montage ----------

def telecharger(clip, out):
    if clip["plateforme"] == "twitch":
        subprocess.run(YTDLP + ["-f", "best[height<=1080][format_id!*=portrait]/best", "-o", str(out),
                                clip["url"]], check=True, timeout=600)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip["url"], "-c", "copy",
                        "-bsf:a", "aac_adtstoasc", str(out)], check=True, timeout=600)


def monter(compte, clip, deja_hooks):
    import render
    cc = CFG["comptes"][compte]
    os.environ["LANGUE"] = cc["langue"]
    acc = __import__("accroches_fr" if cc["langue"] == "fr" else "accroches_en")
    work = Path(tempfile.mkdtemp())
    raw = work / "raw.mp4"
    telecharger(clip, raw)
    words = render.transcribe(raw, work)
    texte = " " + " ".join(w[2] for w in words).lower() + " "
    if any(m in texte for m in INTERDITS):
        log("  propos interdits dans le clip : on passe")
        return None, None
    rnd = random.Random(clip["id"])
    libres = [h for h in GTA6_HOOKS[cc["langue"]] if h not in deja_hooks]
    hook = rnd.choice(libres) if est_gta6(clip["cat"]) and libres else acc.choose(words, clip["id"], deja_hooks)
    st = {"slug": clip["slug"], "nom": clip.get("nom") or clip["slug"], "plateforme": clip["plateforme"]}
    out = work / "clip.mp4"
    render.compose(raw, st, out, words=words, hook=hook)
    return out, hook


# ---------- publication ----------

def creneau_libre(compte, key):
    """Faux s'il y a déjà un post (prévu ou sorti) à moins de 35 min sur ce profil."""
    profil = CFG["comptes"][compte]["profil"]
    auth = {"Authorization": f"Apikey {key}"}
    now = dt.datetime.now(dt.timezone.utc)
    marge = dt.timedelta(minutes=35)
    try:
        for p in requests.get(f"{API}/schedule", headers=auth, timeout=60).json().get("scheduled_posts", []):
            if p.get("profile_username") != profil:
                continue
            d = dt.datetime.fromisoformat(p["scheduled_date"].replace("Z", "+00:00"))
            if d.tzinfo is None:          # Upload-Post renvoie les dates programmées en UTC
                d = d.replace(tzinfo=dt.timezone.utc)
            if abs(d - now) < marge:
                return False
        h = requests.get(f"{API}/history", headers=auth, params={"limit": 50}, timeout=60).json()
        for p in h.get("history") or []:
            if p.get("profile_username") == profil and p.get("upload_timestamp"):
                d = dt.datetime.fromisoformat(p["upload_timestamp"].replace("Z", "+00:00"))
                if now - d < marge:
                    return False
    except Exception as e:
        log(f"  (vérification des créneaux impossible : {e})")
    return True


def publier(compte, clip, video, hook, key):
    cc = CFG["comptes"][compte]
    lien = f"kick.com/{clip['slug']}" if clip["plateforme"] == "kick" else f"twitch.tv/{clip['slug']}"
    nom = clip.get("nom") or clip["slug"]
    tags = " ".join(cc["hashtags"])
    if cc["langue"] == "fr":
        legende = f"{hook} 😱\n🎮 {nom} en live sur {lien}\nAbonne-toi pour les meilleurs moments GTA 6 🔥\n{tags}"
    else:
        legende = f"{hook} 😱\n🎮 {nom} live on {lien}\nFollow for the best GTA 6 moments 🔥\n{tags}"
    for essai in range(3):
        try:
            with open(video, "rb") as f:
                r = requests.post("https://api.upload-post.com/api/upload",
                                  headers={"Authorization": f"Apikey {key}",
                                           "Idempotency-Key": f"gta6-{compte}-{clip['id']}"},
                                  data={"user": cc["profil"], "platform[]": cc["plateformes"],
                                        "title": legende, "privacy_level": "PUBLIC_TO_EVERYONE",
                                        "media_type": "REELS"},
                                  files={"video": f}, timeout=(30, 900))
            log(f"  publication : {r.status_code} {r.text[:300]}")
            return r.status_code < 300
        except requests.exceptions.RequestException as e:
            log(f"  envoi {essai + 1} raté : {e.__class__.__name__}")
            time.sleep(30)
    return False


def main():
    compte = sys.argv[1]
    essai = "--essai" in sys.argv
    key = os.environ.get("UPLOAD_POST_KEY", "")
    e = charger_etat(compte)
    if not essai and not creneau_libre(compte, key):
        log(f"{compte} : un post est déjà prévu ou sorti il y a moins de 35 min, on passe cette heure")
        return
    deja_hooks = [p.get("hook") for p in e["posts"][-8:]]
    for clip in candidats(compte, set(e["faits"])):
        log(f"{compte} : {clip['plateforme']}/{clip['slug']} — {clip['vues']} vues — {clip['cat']} — {clip['titre'][:60]}")
        e["faits"].append(clip["id"])
        try:
            video, hook = monter(compte, clip, deja_hooks)
        except Exception as ex:
            log(f"  montage raté : {ex}")
            continue
        if not video:
            continue
        if essai:
            dest = ROOT / "essai" / f"{compte}.mp4"
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(video.read_bytes())
            log(f"  essai : clip monté dans {dest} (« {hook} »)")
        elif publier(compte, clip, video, hook, key):
            e["posts"].append({"quand": dt.datetime.utcnow().isoformat(timespec="minutes"),
                               "clip": clip["id"], "hook": hook, "vues": clip["vues"], "cat": clip["cat"]})
        break
    else:
        log(f"{compte} : aucun clip GTA disponible cette heure-ci")
    e["faits"] = e["faits"][-3000:]
    e["posts"] = e["posts"][-500:]
    fichier_etat(compte).write_text(json.dumps(e, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
