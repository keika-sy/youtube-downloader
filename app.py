from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import yt_dlp
import os
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def get_video_info():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL tidak boleh kosong'}), 400
    
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                size = f.get('filesize') or f.get('filesize_approx', 0)
                formats.append({
                    'id': f['format_id'],
                    'resolution': f"{f.get('width', 0)}x{f.get('height', 0)}",
                    'ext': f.get('ext', 'mp4'),
                    'vcodec': f.get('vcodec', 'N/A').split('.')[0] if f.get('vcodec') != 'none' else '-',
                    'acodec': f.get('acodec', 'N/A').split('.')[0] if f.get('acodec') != 'none' else '-',
                    'fps': int(f.get('fps', 0)) if f.get('fps') else '-',
                    'size': human_bytes(size) if size else '~',
                    'note': get_format_note(f)
                })
            
            return jsonify({
                'title': info['title'],
                'uploader': info['uploader'],
                'duration': info['duration_string'],
                'views': f"{info['view_count']:,}",
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    url = request.json.get('url', '').strip()
    format_id = request.json.get('format', '')
    
    try:
        def progress_hook(d):
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                socketio.emit('progress', {
                    'downloaded': downloaded,
                    'total': total,
                    'percent': (downloaded / total * 100) if total > 0 else 0
                })

        ydl_opts = {
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'quiet': True,
            'format': format_id,
            'progress_hooks': [progress_hook]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return jsonify({'success': True, 'filename': ydl.prepare_filename(info)})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_format_note(f):
    notes = []
    if f.get('video_ext') != 'none' and f.get('audio_ext') == 'none':
        notes.append("Video Only")
    if f.get('video_ext') == 'none' and f.get('audio_ext') != 'none':
        notes.append("Audio Only")
    if f.get('asr'):
        notes.append(f"{f['asr']/1000:.0f}kHz")
    if f.get('tbr'):
        notes.append(f"{int(f['tbr'])}kbps")
    return ", ".join(notes) if notes else "-"

def human_bytes(b):
    if not b or b <= 0:
        return "0B"
    for u in ["B","KB","MB","GB","TB"]:
        if b < 1024: return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}PB"

@socketio.on('connect')
def handle_connect():
    print(f"Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected")

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
