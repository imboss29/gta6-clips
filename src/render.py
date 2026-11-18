"""Montage d'un clip vertical TikTok à partir d'un passage de rediffusion Kick.

Mise en page 1080x1920 :
  - fond : le jeu agrandi, flouté et assombri
  - en haut : gros logo KICK + « kick.com/<streamer> »
  - au centre : le jeu (recadré en 4:3 pour être plus grand)
  - en bas : sous-titres mot à mot, gros, blancs avec contour noir
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = str(ROOT / "fonts" / "Anton-Regular.ttf")
LOGO = ROOT / "assets" / "kick-logo.png"
W, H = 1080, 1920
GREEN = (83, 252, 24)
GAME_Y = 600               # haut de la zone de jeu
GAME_W, GAME_H = 1080, 810  # jeu recadré en 4:3
CAPTION_Y = 1530           # centre des sous-titres


def run(cmd):
    subprocess.run(cmd, check=True)


def download(source, start, duration, out, quality="1080p60"):
    """Télécharge uniquement le passage voulu de la rediffusion."""
    base = source.rsplit("/", 1)[0]
    url = f"{base}/{quality}/playlist.m3u8"
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", url, "-t", str(duration),
         "-c", "copy", str(out)])


# ---------- sous-titres ----------

def transcribe(video, workdir):
    """Transcription mot à mot. whisper.cpp en local, faster-whisper sur GitHub."""
    wav = workdir / "audio.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-ar", "16000", "-ac", "1", str(wav)])
    model = os.environ.get("WHISPER_MODEL", str(Path.home() / ".whisper" / "ggml-small.bin"))
    if shutil.which("whisper-cli") and Path(model).exists():
        run(["whisper-cli", "-m", model, "-l", os.environ.get("LANGUE", "fr"), "-ml", "1", "-sow", "-osrt", "-np",
             "-of", str(workdir / "words"), "-t", "8", str(wav)])
        return parse_srt((workdir / "words.srt").read_text())
    from faster_whisper import WhisperModel  # sur GitHub Actions
    m = WhisperModel(os.environ.get("FW_MODEL", "small"), device="cpu", compute_type="int8")
    import wave
    import numpy as np
    with wave.open(str(wav)) as w:   # on décode nous-mêmes : évite le conflit de version de PyAV
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    segs, _ = m.transcribe(pcm, language=os.environ.get("LANGUE", "fr"), word_timestamps=True, vad_filter=True)
    return [(w.start, w.end, w.word.strip()) for s in segs for w in s.words if w.word.strip("-–— ")]


def parse_srt(text):
    words = []
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        a, b = lines[1].split(" --> ")
        word = " ".join(lines[2:]).strip()
        if word and word.strip("-–— "):
            words.append((ts(a), ts(b), word))
    return words


def ts(s):
    h, m, rest = s.strip().split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def chunks(words, size=3, max_gap=0.8):
    """Regroupe les mots par paquets de 3 maximum (style TikTok)."""
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= size or w[0] - cur[-1][1] > max_gap
                    or re.search(r"[.!?,]$", cur[-1][2])):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [(c[0][0], c[-1][1], " ".join(x[2] for x in c)) for c in out]


def caption_png(text, path):
    im = Image.new("RGBA", (W, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    text = text.upper()
    size = 110
    while size > 50:
        font = ImageFont.truetype(FONT, size)
        if d.textlength(text, font=font) <= W - 120:
            break
        size -= 6
    lines = [text]
    if d.textlength(text, font=font) > W - 120:  # trop long : deux lignes
        mid = len(text.split()) // 2 or 1
        lines = [" ".join(text.split()[:mid]), " ".join(text.split()[mid:])]
    y = 200 - len(lines) * size * 0.6
    for i, line in enumerate(lines):
        fill = "white" if i == 0 and len(lines) == 1 else ("white" if i == 0 else (255, 230, 0))
        d.text((W / 2, y), line, font=font, fill=fill, anchor="mt",
               stroke_width=10, stroke_fill="black")
        y += size * 1.15
    im.save(path)


def caption_track(words, duration, workdir):
    """Une piste d'images transparentes (format concat de ffmpeg) avec les sous-titres."""
    blank = workdir / "blank.png"
    Image.new("RGBA", (W, 400), (0, 0, 0, 0)).save(blank)
    lines, t = ["ffconcat version 1.0"], 0.0
    for i, (a, b, text) in enumerate(chunks(words)):
        a, b = max(a, t), min(b + 0.15, duration)
        if b <= a:
            continue
        if a > t:
            lines += [f"file '{blank}'", f"duration {a - t:.3f}"]
        p = workdir / f"cap{i:04d}.png"
        caption_png(text, p)
        lines += [f"file '{p}'", f"duration {b - a:.3f}"]
        t = b
    lines += [f"file '{blank}'", f"duration {max(duration - t, 0.1):.3f}", f"file '{blank}'"]
    track = workdir / "captions.txt"
    track.write_text("\n".join(lines) + "\n")
    return track


# ---------- habillage fixe ----------

def frame_png(streamer, path, hook=""):
    """Habillage fixe : en haut le logo KICK (streamers Kick) ou le nom du streamer en grand
    (streamers Twitch), son lien, puis le texte d'accroche au-dessus du jeu."""
    if isinstance(streamer, str):
        streamer = {"slug": streamer, "nom": streamer}
    slug, nom = streamer["slug"], streamer.get("nom", streamer["slug"])
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 50)
    if streamer.get("plateforme", "kick") == "kick":
        logo = Image.open(LOGO)
        lw = 480
        logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
        im.alpha_composite(logo, ((W - lw) // 2, 60))
        d.text((W / 2, 60 + logo.height + 22), f"kick.com/{slug}", font=f, fill="white",
               anchor="mt", stroke_width=5, stroke_fill="black")
    else:
        fn = ImageFont.truetype(FONT, 140)
        d.text((W / 2, 50), nom.upper(), font=fn, fill="white", anchor="mt",
               stroke_width=8, stroke_fill=(145, 70, 255))
        d.text((W / 2, 232), f"twitch.tv/{slug}", font=f, fill="white",
               anchor="mt", stroke_width=5, stroke_fill="black")
    if hook:
        hook = hook.upper()
        size, lines = 84, [hook]
        while size >= 52:
            font = ImageFont.truetype(FONT, size)
            lines = wrap(d, hook, font, W - 140)
            if len(lines) <= 2:
                break
            size -= 4
        lh = size * 1.12
        top = 335 + (230 - lh * len(lines)) / 2
        box_w = max(d.textlength(l, font=font) for l in lines) + 70
        d.rounded_rectangle(((W - box_w) / 2, top - 18, (W + box_w) / 2, top + lh * len(lines) + 12),
                            22, fill="white")
        for i, line in enumerate(lines):
            d.text((W / 2, top + i * lh), line, font=font, fill="black", anchor="mt")
    im.save(path)


def wrap(d, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if d.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


# ---------- mise en page « écran coupé » : cam en haut, logo au milieu, jeu en bas ----------
CAM_H = 960                              # moitié haute : la cam
SPLIT_GAME_Y = CAM_H                     # moitié basse : le jeu
SPLIT_GAME_H = H - SPLIT_GAME_Y
SEAM = CAM_H                             # logo posé à la jonction des deux moitiés
SPLIT_CAPTION_Y = 1330


def fixed_cam(raw, streamer):
    """Cam à position fixe réglée dans config.json ("cam": [x, y, largeur, hauteur] en fractions
    de l'image), pour les streamers dont la cam n'est pas détectable (détourage, masque…)."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(raw)],
                           capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(probe[0]), int(probe[1])
    fx, fy, fw, fh = streamer["cam"]
    ch = fh * sh
    cw = ch * W / CAM_H
    x0 = max(0, min(sw - cw, (fx + fw / 2) * sw - cw / 2))
    return int(x0), int(fy * sh), int(cw) // 2 * 2, int(ch) // 2 * 2


def find_cam(raw, samples=10):
    """Repère la webcam du streamer : un visage qui reste au même endroit sur tout le clip.
    Renvoie (x, y, w, h) en pixels de la vidéo source, ou None s'il n'y a pas de cam."""
    try:
        import cv2
    except ImportError:
        return None
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:format=duration", "-of", "json", str(raw)],
                           capture_output=True, text=True).stdout
    import json as _json
    info = _json.loads(probe)
    sw, sh = info["streams"][0]["width"], info["streams"][0]["height"]
    dur = float(info["format"]["duration"])
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    work = Path(tempfile.mkdtemp())
    faces, imgs = [], []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        img = work / f"f{i}.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(raw),
                        "-frames:v", "1", str(img)])
        im = cv2.imread(str(img))
        if im is None:
            continue
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        imgs.append(gray)
        found = cascade.detectMultiScale(gray, 1.1, 6, minSize=(int(sh * 0.05), int(sh * 0.05)),
                                         maxSize=(int(sh * 0.4), int(sh * 0.4)))
        faces.append([tuple(map(int, f)) for f in found])
    shutil.rmtree(work, ignore_errors=True)
    # un visage « fixe » = présent au même endroit sur au moins 60 % des images
    best = None
    for frame in faces:
        for (x, y, w, h) in frame:
            cx, cy = x + w / 2, y + h / 2
            hits = [f for fr in faces for f in fr
                    if abs(f[0] + f[2] / 2 - cx) < w * 0.6 and abs(f[1] + f[3] / 2 - cy) < h * 0.6]
            n = len({id(fr) for fr in faces for f in fr if f in hits})
            frames_hit = sum(1 for fr in faces if any(f in hits for f in fr))
            if frames_hit >= max(3, len(faces) * 0.6) and (best is None or frames_hit > best[0]):
                best = (frames_hit, hits)
    if not best:
        return None
    hits = best[1]
    fx = sorted(f[0] + f[2] / 2 for f in hits)[len(hits) // 2]
    fy = sorted(f[1] + f[3] / 2 for f in hits)[len(hits) // 2]
    fw = sorted(f[2] for f in hits)[len(hits) // 2]
    # bords du cadre de la webcam : lignes droites nettes autour du visage
    top, bottom, left, right = cam_edges(imgs, fx, fy, fw, sw, sh)
    # gros plan sur le visage, au format de la zone du haut (1080 x 800), sans sortir du cadre
    ch = min(fw * 2.3, bottom - top)
    cw = ch * W / CAM_H
    if cw > right - left:
        cw = right - left
        ch = cw * CAM_H / W
    x0 = max(left, min(right - cw, fx - cw / 2))
    y0 = max(top, min(bottom - ch, fy - ch * 0.45))
    return int(x0), int(y0), int(cw) // 2 * 2, int(ch) // 2 * 2


def cam_edges(imgs, fx, fy, fw, sw, sh):
    """Cherche les bords (haut, bas, gauche, droite) du rectangle de la webcam autour du visage,
    à partir de l'image moyenne du clip (le jeu bouge, le cadre de la cam reste fixe)."""
    import numpy as np
    if not imgs:
        return 0, sh, 0, sw
    mean = np.mean(np.stack(imgs).astype(np.float32), axis=0)
    gy = np.abs(np.diff(mean, axis=0))       # contours horizontaux
    gx = np.abs(np.diff(mean, axis=1))       # contours verticaux
    x1, x2 = int(max(0, fx - fw)), int(min(sw - 1, fx + fw))
    y1, y2 = int(max(0, fy - fw)), int(min(sh - 1, fy + fw))
    rows = gy[:, x1:x2].mean(axis=1)
    cols = gx[y1:y2, :].mean(axis=0)

    def edge(profile, lo, hi, ref):
        lo, hi = int(max(0, lo)), int(min(len(profile), hi))
        if hi - lo < 3:
            return None
        seg = profile[lo:hi]
        i = int(np.argmax(seg))
        return lo + i if seg[i] > ref * 4 else None

    rref, cref = float(np.median(rows)) + 1e-3, float(np.median(cols)) + 1e-3
    bottom = edge(rows, fy + fw * 0.7, fy + fw * 3, rref) or sh
    top = edge(rows, fy - fw * 3, fy - fw * 0.7, rref) or 0
    right = edge(cols, fx + fw * 0.8, fx + fw * 4, cref) or sw
    left = edge(cols, fx - fw * 4, fx - fw * 0.8, cref) or 0
    return top + 1, bottom, left + 1, right


def glow(layer, radius=18, strength=3):
    """Halo sombre autour d'un élément pour qu'il reste lisible sur n'importe quelle image."""
    from PIL import ImageFilter
    alpha = layer.split()[-1].filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(radius))
    alpha = alpha.point(lambda v: min(255, v * strength))
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 255))
    shadow.putalpha(alpha)
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(shadow)
    out.alpha_composite(layer)
    return out


def split_frame_png(streamer, path, hook=""):
    """Habillage de l'écran coupé : accroche en haut, logo à la jonction cam / jeu (sans bandeau)."""
    if isinstance(streamer, str):
        streamer = {"slug": streamer, "nom": streamer}
    slug, nom = streamer["slug"], streamer.get("nom", streamer["slug"])
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(mid)
    f = ImageFont.truetype(FONT, 46)
    if streamer.get("plateforme", "kick") == "kick":
        logo = Image.open(LOGO)
        lw = 460
        logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
        mid.alpha_composite(logo, ((W - lw) // 2, SEAM - logo.height // 2))
        d.text((W / 2, SEAM + logo.height // 2 + 12), f"kick.com/{slug}", font=f, fill="white",
               anchor="mt", stroke_width=5, stroke_fill="black")
    else:
        fn = ImageFont.truetype(FONT, 120)
        d.text((W / 2, SEAM), nom.upper(), font=fn, fill="white", anchor="mm",
               stroke_width=7, stroke_fill=(145, 70, 255))
        d.text((W / 2, SEAM + 78), f"twitch.tv/{slug}", font=f, fill="white", anchor="mt",
               stroke_width=5, stroke_fill="black")
    im.alpha_composite(glow(mid))
    d = ImageDraw.Draw(im)
    if hook:
        hook = hook.upper()
        size = 76
        while size >= 50:
            font = ImageFont.truetype(FONT, size)
            lines = wrap(d, hook, font, W - 140)
            if len(lines) <= 2:
                break
            size -= 4
        lh = size * 1.12
        top = 60
        box_w = max(d.textlength(l, font=font) for l in lines) + 70
        d.rounded_rectangle(((W - box_w) / 2, top - 18, (W + box_w) / 2, top + lh * len(lines) + 12),
                            22, fill="white")
        for i, line in enumerate(lines):
            d.text((W / 2, top + i * lh), line, font=font, fill="black", anchor="mt")
    im.save(path)


def compose(raw, streamer, out, words=None, hook=""):
    work = Path(tempfile.mkdtemp())
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(raw)],
        capture_output=True, text=True).stdout.strip())
    if words is None:
        words = transcribe(raw, work)
    frame = work / "frame.png"
    track = caption_track(words, dur, work)
    cam = fixed_cam(raw, streamer) if isinstance(streamer, dict) and streamer.get("cam") else find_cam(raw)
    # barre de progression verte : incite à regarder jusqu'au bout
    bar = f"[3:v]format=rgba[bar];"
    if cam:
        cx, cy, cw, ch = cam
        split_frame_png(streamer, frame, hook)
        filt = (
            f"[0:v]split[a][b];"
            f"[a]crop={cw}:{ch}:{cx}:{cy},scale={W}:{CAM_H}[cam];"
            f"[b]crop=ih*{W}/{SPLIT_GAME_H}:ih,scale={W}:{SPLIT_GAME_H}[game];"
            f"color=c=black:s={W}x{H}:r=30[base];"
            f"[base][cam]overlay=0:0[v0];[v0][game]overlay=0:{SPLIT_GAME_Y}:shortest=1[v1];"
            + bar +
            f"[v1][bar]overlay=x='-{W}+{W}*t/{dur:.2f}':y={SEAM - 6}[v2];"
            f"[v2][1:v]overlay=0:0[v3];"
            f"[2:v]format=rgba[cap];"
            f"[v3][cap]overlay=0:{SPLIT_CAPTION_Y - 200}:eof_action=pass,fps=30,format=yuv420p[v]"
        )
    else:
        frame_png(streamer, frame, hook)
        filt = (
        f"[0:v]split[a][b];"
        f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5,"
        f"eq=brightness=-0.25[bg];"
        f"[b]crop=ih*4/3:ih,scale={GAME_W}:{GAME_H}[game];"
        f"[bg][game]overlay=0:{GAME_Y}[v1];"
        f"[v1][1:v]overlay=0:0[v2];" + bar +
        f"[v2][bar]overlay=x='-{W}+{W}*t/{dur:.2f}':y={GAME_Y + GAME_H}[v3];"
        f"[2:v]format=rgba[cap];"
        f"[v3][cap]overlay=0:{CAPTION_Y - 200}:eof_action=pass,fps=30,format=yuv420p[v]"
        )
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-loop", "1", "-i", str(frame),
         "-f", "concat", "-safe", "0", "-i", str(track),
         "-f", "lavfi", "-i", f"color=c=0x53FC18:s={W}x12:r=30", "-filter_complex", filt,
         "-map", "[v]", "-map", "0:a?", "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "3500k", "-bufsize", "7000k", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(out)])
    shutil.rmtree(work, ignore_errors=True)
    return words
