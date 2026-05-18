"""
tts.py — edge-tts TTS 服务（端口 8082）
支持中文、英文 TTS，统一入口
"""

import subprocess, tempfile, os, urllib.parse, hashlib
from flask import Flask, Response, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["http://43.160.222.242:3000", "http://43.160.222.242:3001", "http://47.243.65.57:3000", "http://47.243.65.57:3001"])

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
RATE  = "+0%"
PITCH = "+0Hz"
EDGE_TTS_CMD = "edge-tts"
CACHE_DIR = "/tmp/tts_cache"

VOICE_MAP = {
    "en":    "en-US-JennyNeural",
    "en-m":  "en-US-BrandonNeural",
    "zh":    "zh-CN-XiaoxiaoNeural",
}

os.makedirs(CACHE_DIR, exist_ok=True)


def cache_key(text, voice_name, rate, pitch):
    h = hashlib.md5(f"{voice_name}|{rate}|{pitch}|{text}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.mp3")


def generate_tts(text, voice_name, rate, pitch):
    """调用 edge-tts 生成音频，返回 mp3 字节数据"""
    out_file = tempfile.mktemp(suffix=".mp3")
    try:
        res = subprocess.run(
            [EDGE_TTS_CMD, "-v", voice_name, "-t", text,
             "--write-media", out_file,
             "--rate", rate, "--pitch", pitch],
            capture_output=True, timeout=15
        )
        if res.returncode != 0 or not os.path.exists(out_file):
            raise RuntimeError(res.stderr.decode() or "edge-tts failed")

        with open(out_file, "rb") as f:
            audio = f.read()
        os.unlink(out_file)
        return audio
    except subprocess.TimeoutExpired:
        raise TimeoutError("edge-tts timeout")
    except FileNotFoundError:
        raise RuntimeError("edge-tts not installed")


@app.route("/tts")
def tts():
    text = request.args.get("text", "")
    voice = request.args.get("voice", DEFAULT_VOICE)
    rate = request.args.get("rate", RATE)
    pitch = request.args.get("pitch", PITCH)
    if not text:
        return Response(b"", status=400)

    voice_name = VOICE_MAP.get(voice, voice)
    ck = cache_key(text, voice_name, rate, pitch)

    # 缓存命中直接返回
    if os.path.exists(ck):
        with open(ck, "rb") as f:
            return Response(f.read(), mimetype="audio/mpeg")

    # 生成并缓存
    try:
        audio = generate_tts(text, voice_name, rate, pitch)
        with open(ck, "wb") as f:
            f.write(audio)
        return Response(audio, mimetype="audio/mpeg")
    except TimeoutError:
        return Response(b"timeout", status=504)
    except RuntimeError as e:
        return Response(str(e).encode(), status=500)
    except Exception as e:
        return Response(str(e).encode(), status=500)


@app.route("/voices")
def voices():
    return Response("\n".join(f"{k} -> {v}" for k, v in VOICE_MAP.items()).encode())


@app.route("/health")
def health():
    return Response(b"ok")


if __name__ == "__main__":
    import os
    port = int(os.environ.get("TTS_PORT", 8082))
    app.run(host="0.0.0.0", port=port, debug=False)
