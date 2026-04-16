#!/usr/bin/env python3
"""
TokInsight Backend — Scrape real TikTok data via yt-dlp
Run: python3 server.py
Then open: http://localhost:8080
"""

import json
import subprocess
import re
import sys
import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

CATEGORY_RULES = [
    {"id": "dance", "label": "Dance", "emoji": "💃", "keywords": ["dance", "choreo", "dancechallenge", "dancetok", "dancer", "danse", "dancing"]},
    {"id": "lipsync", "label": "Lip Sync", "emoji": "🎤", "keywords": ["lipsync", "lip sync", "dubsmash", "lip-sync", "synchro"]},
    {"id": "grwm", "label": "GRWM", "emoji": "💄", "keywords": ["grwm", "getreadywithme", "get ready", "makeup", "maquillage", "skincare", "beauty"]},
    {"id": "haul", "label": "Haul / Try-on", "emoji": "🛒", "keywords": ["haul", "tryon", "try on", "try-on", "unboxing", "shopping", "ootd", "fashion", "mode"]},
    {"id": "comedy", "label": "Comedy", "emoji": "😂", "keywords": ["comedy", "funny", "humor", "humour", "mdr", "lol", "skit", "joke", "blague"]},
    {"id": "storytime", "label": "Storytime", "emoji": "📖", "keywords": ["storytime", "story time", "histoire", "part 1", "part 2", "pov"]},
    {"id": "transition", "label": "Transition", "emoji": "✨", "keywords": ["transition", "glow", "glowup", "glow up", "beforeafter", "avant"]},
    {"id": "lifestyle", "label": "Lifestyle", "emoji": "🌸", "keywords": ["lifestyle", "aesthetic", "vlog", "routine", "dayinmylife"]},
    {"id": "food", "label": "Food", "emoji": "🍜", "keywords": ["food", "recipe", "recette", "cooking", "cuisine", "eat", "manger", "cook", "foodtok", "asmr"]},
    {"id": "fitness", "label": "Fitness", "emoji": "💪", "keywords": ["fitness", "workout", "gym", "training", "sport", "exercise", "musculation"]},
    {"id": "trend", "label": "Trend", "emoji": "🔥", "keywords": ["trend", "trending", "challenge", "viral"]},
    {"id": "collab", "label": "Collab", "emoji": "🤝", "keywords": ["collab", "duet", "duo", "with @", "feat", "together"]},
]
DEFAULT_CAT = {"id": "other", "label": "Autre", "emoji": "📱"}


def detect_category(text):
    text_lower = text.lower()
    best, best_score = None, 0
    for rule in CATEGORY_RULES:
        score = sum(1 for kw in rule["keywords"] if kw in text_lower)
        if score > best_score:
            best_score = score
            best = rule
    return {"id": best["id"], "label": best["label"], "emoji": best["emoji"]} if best else DEFAULT_CAT


def clean_username(raw):
    raw = raw.strip()
    m = re.search(r'tiktok\.com/@([^/?#]+)', raw)
    if m: return m.group(1)
    raw = raw.lstrip('@/')
    return raw.split('?')[0].split('#')[0]


def scrape_tiktok(username, max_videos=1000):
    url = f"https://www.tiktok.com/@{username}"
    cmd = [sys.executable, "-m", "yt_dlp", "--flat-playlist", "--dump-json", "--playlist-items", f"1-{max_videos}", "--no-warnings", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "Timeout: le scraping a pris trop de temps"
    if result.returncode != 0 and not result.stdout.strip():
        return None, f"Erreur yt-dlp: {result.stderr.strip()[:200]}"

    videos = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip(): continue
        try: data = json.loads(line)
        except json.JSONDecodeError: continue
        desc = data.get("description") or data.get("title") or ""
        cat = detect_category(desc)
        hashtags = re.findall(r'#\w+', desc)
        thumb = ""
        for t in (data.get("thumbnails") or []):
            if t.get("id") in ("originCover", "cover"):
                thumb = t["url"]; break
        if not thumb and data.get("thumbnails"):
            thumb = data["thumbnails"][0].get("url", "")
        videos.append({
            "id": data.get("id", ""), "url": data.get("webpage_url") or data.get("url", ""),
            "description": desc, "hashtags": hashtags[:6], "category": cat,
            "views": data.get("view_count") or 0, "likes": data.get("like_count") or 0,
            "comments": data.get("comment_count") or 0, "shares": data.get("repost_count") or 0,
            "saves": data.get("save_count") or 0, "duration": data.get("duration") or 0,
            "thumbnail": thumb, "date": data.get("upload_date", ""), "timestamp": data.get("timestamp") or 0,
        })
    if not videos:
        return None, "Aucune video trouvee pour ce compte"
    for v in videos:
        total = v["views"] if v["views"] > 0 else 1
        v["engagement"] = round((v["likes"] + v["comments"] + v["shares"]) / total * 100, 2)
    first = json.loads(result.stdout.strip().split('\n')[0])
    profile = {"username": username, "displayName": first.get("channel") or first.get("uploader") or username, "profileUrl": f"https://www.tiktok.com/@{username}"}
    return {"profile": profile, "videos": videos}, None


@app.route('/')
def index():
    return send_from_directory('.', 'tiktok-analytics.html')


@app.route('/api/analyze', methods=['GET'])
def analyze():
    raw = request.args.get('username', '').strip()
    max_vids = min(int(request.args.get('max', 1000)), 1000)
    if not raw: return jsonify({"error": "Parametre 'username' manquant"}), 400
    username = clean_username(raw)
    if not username: return jsonify({"error": "Username invalide"}), 400
    data, error = scrape_tiktok(username, max_vids)
    if error: return jsonify({"error": error}), 422
    return jsonify(data)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print("TokInsight server running on port", port)
    app.run(host='0.0.0.0', port=port, debug=False)
