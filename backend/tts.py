"""
tts.py — edge-tts TTS 服务（端口 8082）
免费，无需 API Key，中文女声晓晓
"""

import subprocess, tempfile, os, urllib.parse
from flask import Flask, Response, request

app = Flask(__name__)

VOICE = "zh-CN-XiaoxiaoNeural"
RATE  = "+0%"
PITCH = "+0Hz"

# edge-tts 可执行路径
EDGE_TTS_CMD = "edge-tts"


@app.route("/tts")
def tts():
    text = request.args.get("text", "")
    if not text:
        return Response(b"", status=400)

    out_file = tempfile.mktemp(suffix=".mp3")

    try:
        res = subprocess.run(
            [EDGE_TTS_CMD, "-v", VOICE, "-t", text, "--write-media", out_file,
             "--rate", RATE, "--pitch", PITCH],
            capture_output=True, timeout=15
        )
        if res.returncode != 0 or not os.path.exists(out_file):
            return Response(b"tts error: " + res.stderr, status=500)

        with open(out_file, "rb") as f:
            audio = f.read()
        os.unlink(out_file)
        return Response(audio, mimetype="audio/mpeg")
    except subprocess.TimeoutExpired:
        return Response(b"timeout", status=504)
    except FileNotFoundError:
        return Response(b"edge-tts not installed", status=503)
    except Exception as e:
        return Response(str(e).encode(), status=500)


@app.route("/health")
def health():
    return Response(b"ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082, debug=False)
