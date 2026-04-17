#!/usr/bin/env python3
"""
TokInsight Backend — Scrape real TikTok data via yt-dlp
Run: python3 server.py
Then open: http://localhost:5000
"""

import json
import subprocess
import re
import sys
import os
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ── Category detection via keywords ──────────────────────────────
CATEGORY_RULES = [
    {"id": "dance", "label": "Dance", "emoji": "💃", "keywords": ["dance", "choreo", "chorégraphie", "dancechallenge", "dancetok", "dancer", "danse", "dancing"]},
    {"id": "lipsync", "label": "Lip Sync", "emoji": "🎤", "keywords": ["lipsync", "lip sync", "dubsmash", "lypsync", "lip-sync", "synchro"]},
    {"id": "grwm", "label": "GRWM", "emoji": "💄", "keywords": ["grwm", "getreadywithme", "get ready", "makeup", "maquillage", "skincare", "beauty", "beauté"]},
    {"id": "haul", "label": "Haul / Try-on", "emoji": "🛍️", "keywords": ["haul", "tryon", "try on", "try-on", "unboxing", "shopping", "ootd", "fashion", "mode"]},
    {"id": "comedy", "label": "Comédie", "emoji": "😂", "keywords": ["comedy", "funny", "humor", "humour", "mdr", "lol", "skit", "joke", "blague", "drôle"]},
    {"id": "storytime", "label": "Storytime", "emoji": "📖", "keywords": ["storytime", "story time", "histoire", "part 1", "part 2", "pov"]},
    {"id": "transition", "label": "Transition", "emoji": "✨", "keywords": ["transition", "glow", "glowup", "glow up", "beforeafter", "before after", "avant après"]},
    {"id": "lifestyle", "label": "Lifestyle", "emoji": "🌸", "keywords": ["lifestyle", "aesthetic", "vlog", "routine", "dayinmylife", "day in my life", "journée"]},
    {"id": "food", "label": "Food", "emoji": "🍜", "keywords": ["food", "recipe", "recette", "cooking", "cuisine", "eat", "manger", "cook", "foodtok", "asmr"]},
    {"id": "fitness", "label": "Fitness", "emoji": "💪", "keywords": ["fitness", "workout", "gym", "training", "sport", "exercise", "musculation", "fit"]},
    {"id": "trend", "label": "Trend", "emoji": "🔥", "keywords": ["trend", "trending", "challenge", "viral"]},
    {"id": "collab", "label": "Collab", "emoji": "🤝", "keywords": ["collab", "duet", "duo", "with @", "feat", "together"]},
]
DEFAULT_CAT = {"id": "other", "label": "Autre", "emoji": "📱"}


def detect_category(text):
    text_lower = text.lower()
    best = None
    best_score = 0
    for rule in CATEGORY_RULES:
        score = sum(1 for kw in rule["keywords"] if kw in text_lower)
        if score > best_score:
            best_score = score
            best = rule
    if best:
        return {"id": best["id"], "label": best["label"], "emoji": best["emoji"]}
    return DEFAULT_CAT


def clean_username(raw):
    raw = raw.strip()
    m = re.search(r'tiktok\.com/@([^/?#]+)', raw)
    if m:
        return m.group(1)
    raw = raw.lstrip('@/')
    return raw.split('?')[0].split('#')[0]


def scrape_tiktok(username, max_videos=1000):
    url = f"https://www.tiktok.com/@{username}"
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist", "--dump-json",
        "--playlist-items", f"1-{max_videos}",
        "--no-warnings", url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "Timeout: le scraping a pris trop de temps"

    if result.returncode != 0 and not result.stdout.strip():
        err = result.stderr.strip()
        return None, f"Erreur yt-dlp: {err[:200]}"

    videos = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        desc = data.get("description") or data.get("title") or ""
        cat = detect_category(desc)
        hashtags = re.findall(r'#\w+', desc)
        thumb = ""
        thumbs = data.get("thumbnails") or []
        for t in thumbs:
            if t.get("id") == "originCover":
                thumb = t["url"]
                break
            if t.get("id") == "cover":
                thumb = t["url"]
        if not thumb and thumbs:
            thumb = thumbs[0].get("url", "")
        videos.append({
            "id": data.get("id", ""),
            "url": data.get("webpage_url") or data.get("url", ""),
            "description": desc, "hashtags": hashtags[:6], "category": cat,
            "views": data.get("view_count") or 0, "likes": data.get("like_count") or 0,
            "comments": data.get("comment_count") or 0, "shares": data.get("repost_count") or 0,
            "saves": data.get("save_count") or 0, "duration": data.get("duration") or 0,
            "thumbnail": thumb, "date": data.get("upload_date", ""),
            "timestamp": data.get("timestamp") or 0,
        })

    if not videos:
        return None, "Aucune vidéo trouvée pour ce compte"

    for v in videos:
        total = v["views"] if v["views"] > 0 else 1
        v["engagement"] = round((v["likes"] + v["comments"] + v["shares"]) / total * 100, 2)

    first = json.loads(result.stdout.strip().split('\n')[0])
    profile = {
        "username": username,
        "displayName": first.get("channel") or first.get("uploader") or username,
        "profileUrl": f"https://www.tiktok.com/@{username}",
    }
    return {"profile": profile, "videos": videos}, None


# ── Routes ───────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'tiktok-analytics.html')


@app.route('/api/analyze', methods=['GET'])
def analyze():
    raw = request.args.get('username', '').strip()
    max_vids = min(int(request.args.get('max', 1000)), 1000)
    if not raw:
        return jsonify({"error": "Paramètre 'username' manquant"}), 400
    username = clean_username(raw)
    if not username:
        return jsonify({"error": "Username invalide"}), 400
    data, error = scrape_tiktok(username, max_vids)
    if error:
        return jsonify({"error": error}), 422
    return jsonify(data)


@app.route('/api/download', methods=['GET'])
def download_video():
    """Download a TikTok video without watermark using yt-dlp."""
    video_url = request.args.get('url', '').strip()
    if not video_url:
        return jsonify({"error": "Paramètre 'url' manquant"}), 400
    if 'tiktok.com' not in video_url:
        return jsonify({"error": "URL TikTok invalide"}), 400

    cmd = [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-warnings", video_url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout lors du téléchargement"}), 504

    if result.returncode != 0:
        err = result.stderr.strip()
        return jsonify({"error": f"Erreur yt-dlp: {err[:200]}"}), 422

    try:
        data = json.loads(result.stdout.strip().split('\n')[0])
    except (json.JSONDecodeError, IndexError):
        return jsonify({"error": "Impossible d'extraire les infos vidéo"}), 422

    video_direct_url = data.get("url", "")
    formats = data.get("formats", [])
    best_url = video_direct_url
    best_quality = 0
    for f in formats:
        if f.get("vcodec", "none") == "none":
            continue
        fmt_id = f.get("format_id", "")
        height = f.get("height") or 0
        if "watermark" not in fmt_id.lower() and height >= best_quality:
            best_quality = height
            best_url = f.get("url", best_url)

    if not best_url:
        return jsonify({"error": "Aucune URL vidéo trouvée"}), 422

    username = data.get("uploader_id") or data.get("channel_id") or "tiktok"
    video_id = data.get("id") or "video"
    filename = f"{username}_{video_id}.mp4"
    return jsonify({"downloadUrl": best_url, "filename": filename, "description": data.get("description", ""), "duration": data.get("duration", 0)})


@app.route('/api/download/stream', methods=['GET'])
def download_stream():
    """Stream the actual video file to the browser for direct download."""
    import tempfile
    video_url = request.args.get('url', '').strip()
    if not video_url:
        return jsonify({"error": "Paramètre 'url' manquant"}), 400
    if 'tiktok.com' not in video_url:
        return jsonify({"error": "URL TikTok invalide"}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    tmp_path = tmp.name
    tmp.close()

    cmd = [sys.executable, "-m", "yt_dlp", "-o", tmp_path, "--no-warnings", "--no-playlist", "--format", "best", video_url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        if os.path.exists(tmp_path): os.unlink(tmp_path)
        return jsonify({"error": "Timeout lors du téléchargement"}), 504

    if result.returncode != 0 or not os.path.exists(tmp_path):
        if os.path.exists(tmp_path): os.unlink(tmp_path)
        return jsonify({"error": "Échec du téléchargement"}), 422

    m_user = re.search(r'@([^/]+)', video_url)
    m_id = re.search(r'/video/(\d+)', video_url)
    username = m_user.group(1) if m_user else "tiktok"
    vid_id = m_id.group(1) if m_id else "video"
    filename = f"{username}_{vid_id}.mp4"

    response = send_file(tmp_path, mimetype='video/mp4', as_attachment=True, download_name=filename)

    @response.call_on_close
    def cleanup():
        if os.path.exists(tmp_path): os.unlink(tmp_path)

    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"\nTokInsight server running on http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=False)
