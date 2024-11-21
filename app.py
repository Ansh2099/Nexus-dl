from flask import Flask, request, jsonify, render_template, send_from_directory
import yt_dlp as youtube_dl
import os
import time
from pathlib import Path
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import logging
import tempfile
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["3 per minute", "30 per hour"]
)

def cleanup_old_downloads():
    """Delete files older than 1 hour"""
    cutoff = datetime.now() - timedelta(hours=1)
    for file in DOWNLOAD_DIR.glob('*'):
        if file.stat().st_mtime < cutoff.timestamp():
            try:
                file.unlink()
                logger.info(f"Cleaned up file: {file}")
            except Exception as e:
                logger.error(f"Failed to cleanup file {file}: {e}")

def check_storage_limit():
    """Check if downloads directory exceeds 5GB"""
    total_size = sum(file.stat().st_size for file in DOWNLOAD_DIR.glob('*'))
    return total_size > 5 * 1024 * 1024 * 1024  # 5GB in bytes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/downloads/<path:filename>')
def download_file(filename):
    try:
        safe_filename = secure_filename(filename)
        return send_from_directory(
            directory=DOWNLOAD_DIR,
            path=filename,
            as_attachment=True
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({"error": str(e)}), 404

@app.route('/download', methods=['POST'])
def download_video():
    if check_storage_limit():
        cleanup_old_downloads()
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    try:
        logger.info(f"Starting download for URL: {url}")
        timestamp = int(time.time())
        
        ydl_opts = {
            'format': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[ext=mp4]',
            'noplaylist': True,
            'outtmpl': str(DOWNLOAD_DIR / f'video_{timestamp}_%(title)s.%(ext)s'),
            'quiet': False,
            'verbose': True,
            'no_warnings': False,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'geo_bypass': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'max_comments': [0],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-S906N Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/80.0.3987.119 Mobile Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                video_url = ydl.prepare_filename(info)
                
                if os.path.exists(video_url):
                    filename = os.path.basename(video_url)
                    logger.info(f"Download successful: {filename}")
                    return jsonify({
                        "message": "Download successful",
                        "file_path": filename
                    }), 200
                else:
                    logger.error("File download failed")
                    return jsonify({"error": "File download failed"}), 500
                    
            except youtube_dl.utils.ExtractorError as e:
                logger.error(f"Extraction error: {str(e)}")
                return jsonify({"error": "Could not extract video information"}), 400
            except youtube_dl.utils.DownloadError as e:
                logger.error(f"Download error: {str(e)}")
                return jsonify({"error": "Video download failed"}), 400
                
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)