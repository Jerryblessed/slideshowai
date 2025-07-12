import os
import sqlite3
import requests
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, send_file, after_this_request
import google.generativeai as genai
import zipfile
import tempfile
import shutil
from werkzeug.security import generate_password_hash, check_password_hash
import time
import threading
import atexit

# --- Configuration ---
app = Flask(__name__)
# IMPORTANT: Change this secret key for production
app.secret_key = 'your-super-secret-key-change-this'

# --- API Keys ---
# For production, it's recommended to use environment variables to store API keys.
# Replace with your actual API keys
ELEVENLABS_API_KEY = "sk_d1b30a8ed56b74206eac4a1533dd104c0842320a3da77326"
PIXABAY_API_KEY = "51119602-1f67b9698b596af854d568451"
PEXELS_API_KEY = "mJ2RpYgAVMmWtlg2A2RXiHp1hiJB6ZGPlTU56IdAYzrOKhzkyqfFe7NV"
GEMINI_API_KEY = "AIzaSyBU_3NNernMnnKXgASt2rurUbnH8wfZsP0"

# --- Initialize Gemini AI ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.0-flash') # Using 'gemini-pro' is a stable choice
    print("Gemini AI configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini AI: {e}")
    gemini_model = None

# Global cleanup registry
cleanup_registry = []

def register_cleanup(zip_path, temp_dir):
    """Register files/directories for cleanup"""
    cleanup_registry.append((zip_path, temp_dir))

def cleanup_old_files():
    """Clean up old temporary files"""
    for zip_path, temp_dir in cleanup_registry[:]:
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
                print(f"Cleaned up temp zip: {zip_path}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temp dir: {temp_dir}")
            cleanup_registry.remove((zip_path, temp_dir))
        except Exception as e:
            print(f"Error cleaning up {zip_path}: {e}")

# Register cleanup on app exit
atexit.register(cleanup_old_files)

# --- Database Setup ---
def init_db():
    """Initializes the SQLite database and creates tables if they don't exist."""
    with sqlite3.connect('slideshow_app.db') as conn:
        cursor = conn.cursor()
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Slideshows table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS slideshows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                query TEXT NOT NULL,
                media_source TEXT NOT NULL,
                media_type TEXT NOT NULL,
                generated_script TEXT,
                audio_files TEXT,
                media_urls TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        conn.commit()

# --- Authentication Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Enhanced Media Fetching Functions ---
def fetch_pexels_media(query, media_type='photos', per_page=10):
    """Fetch media from Pexels API with enhanced metadata."""
    base_url = "https://api.pexels.com/v1/search" if media_type == 'photos' else "https://api.pexels.com/videos/search"
    try:
        url = f"{base_url}?query={query}&per_page={per_page}"
        headers = {'Authorization': PEXELS_API_KEY}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        media_urls = []
        items = data.get('photos', []) if media_type == 'photos' else data.get('videos', [])

        for item in items:
            if media_type == 'photos':
                media_urls.append({
                    'url': item['src']['large'],
                    'type': 'image',
                    'id': item['id'],
                    'alt': item.get('alt', ''),
                    'photographer': item.get('photographer', ''),
                    'colors': item.get('avg_color', '#000000'),
                    'tags': [query]
                })
            else:
                best_video = max(item.get('video_files', []), key=lambda x: x.get('width', 0), default=None)
                if best_video:
                    media_urls.append({
                        'url': best_video['link'],
                        'type': 'video',
                        'id': item['id'],
                        'duration': item.get('duration', 0),
                        'tags': [query],
                        'user': item.get('user', {}).get('name', '')
                    })
        return media_urls
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Pexels media: {e}")
        return []

def fetch_pixabay_media(query, media_type='images', per_page=10):
    """Fetch media from Pixabay API with enhanced metadata."""
    base_url = "https://pixabay.com/api/" if media_type == 'images' else "https://pixabay.com/api/videos/"
    try:
        url = f"{base_url}?key={PIXABAY_API_KEY}&q={query}&per_page={per_page}&safesearch=true"
        response = requests.get(url)
        response.raise_for_status()

        data = response.json()
        media_urls = []
        for item in data.get('hits', []):
            if media_type == 'images':
                media_urls.append({
                    'url': item['largeImageURL'],
                    'type': 'image',
                    'id': item['id'],
                    'tags': item.get('tags', '').split(', ') if item.get('tags') else [query],
                    'user': item.get('user', ''),
                    'views': item.get('views', 0),
                    'downloads': item.get('downloads', 0)
                })
            else:
                video_url = item.get('videos', {}).get('medium', {}).get('url')
                if video_url:
                    media_urls.append({
                        'url': video_url,
                        'type': 'video',
                        'id': item['id'],
                        'tags': item.get('tags', '').split(', ') if item.get('tags') else [query],
                        'user': item.get('user', ''),
                        'duration': item.get('duration', 0)
                    })
        return media_urls
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Pixabay media: {e}")
        return []

# --- Enhanced AI Script Generation ---
def generate_contextual_slideshow_script(query, media_items):
    """Generate script parts that match each specific media item."""
    if not gemini_model:
        return [f"Slide {i+1}: Exploring {query} through this fascinating {item['type']}." for i, item in enumerate(media_items)]

    try:
        media_context = []
        for i, item in enumerate(media_items):
            context = {
                'slide_number': i + 1,
                'media_type': item['type'],
                'tags': item.get('tags', []),
                'alt_text': item.get('alt', ''),
                'photographer': item.get('photographer', item.get('user', '')),
            }
            media_context.append(context)

        prompt = f"""
        Create a narration script for a slideshow about "{query}" with {len(media_items)} slides.
        For each slide, I'll provide context about the specific media (image/video).
        Write 2-3 engaging sentences per slide that directly relate to the visual content.
        Keep a consistent narrative flow.

        Media context:
        {json.dumps(media_context, indent=2)}

        Return a valid JSON object with this exact format:
        {{"script": ["Narration for slide 1...", "Narration for slide 2...", ...]}}

        Generate exactly {len(media_items)} narration strings.
        """

        response = gemini_model.generate_content(prompt)
        cleaned_response_text = response.text.strip().replace('```json', '').replace('```', '')

        script_data = json.loads(cleaned_response_text)
        scripts = script_data.get("script", [])

        if len(scripts) != len(media_items):
            while len(scripts) < len(media_items):
                scripts.append(f"Continuing our exploration of {query}.")
            scripts = scripts[:len(media_items)]

        return scripts

    except Exception as e:
        print(f"Error generating contextual script: {e}")
        return [f"Slide {i+1}: Exploring {query} - {', '.join(item.get('tags', [])[:3])}." for i, item in enumerate(media_items)]

def generate_voice_audio(text, voice_id="pNInz6obpgDQGcFmaJgB"):
    """Generate a single audio file using ElevenLabs API."""
    if not text or not ELEVENLABS_API_KEY:
        return None
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = { "Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY }
        data = { "text": text, "model_id": "eleven_monolingual_v1", "voice_settings": {"stability": 0.5, "similarity_boost": 0.5} }

        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()

        audio_filename = f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}.mp3"
        audio_path = os.path.join('static', 'audio', audio_filename)
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)

        with open(audio_path, 'wb') as f:
            f.write(response.content)
        return audio_filename
    except requests.exceptions.RequestException as e:
        print(f"Error generating voice audio: {e}")
        return None

def create_enhanced_offline_viewer(title, query, media_urls, local_media_paths, script_parts, audio_files):
    """Create an enhanced offline viewer with better styling and functionality."""
    slides_json = []
    for i, (media, script) in enumerate(zip(media_urls, script_parts)):
        # Correctly determine if an audio file exists for this slide
        audio_path = f'audio/slide_{i+1}.mp3' if i < len(audio_files) and audio_files[i] else None
        slides_json.append({
            "type": media['type'],
            "path": local_media_paths[i],
            "audio": audio_path,
            "script": script,
            "tags": media.get('tags', [])
        })

    # This section is now complete
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Arial', sans-serif; background: #111; color: #fff; overflow: hidden; }}
        #container {{ width: 100vw; height: 100vh; position: relative; display: flex; flex-direction: column; background: #000;}}
        .header {{ padding: 15px; text-align: center; background: rgba(0,0,0,0.5); z-index: 10;}}
        .header h1 {{ font-size: 1.8rem; margin-bottom: 5px; }}
        .header p {{ opacity: 0.8; }}
        .slideshow-area {{ flex: 1; position: relative; overflow: hidden; }}
        .slide {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; transition: opacity 0.7s ease-in-out; display: flex; align-items: center; justify-content: center; }}
        .slide.active {{ opacity: 1; }}
        .slide img, .slide video {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
        .slide-number {{ position: absolute; top: 20px; right: 20px; background: rgba(0,0,0,0.7); padding: 8px 15px; border-radius: 20px; font-weight: bold; z-index: 5;}}
        .controls {{ position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); display: flex; gap: 15px; z-index: 10; }}
        .control-btn {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 12px 20px; border-radius: 25px; cursor: pointer; font-size: 1rem; transition: all 0.2s ease; }}
        .control-btn:hover {{ background: rgba(255,255,255,0.2); transform: translateY(-2px); }}
        .progress-bar {{ position: absolute; bottom: 0; left: 0; width: 100%; height: 5px; background: rgba(255,255,255,0.2); z-index: 10; }}
        .progress-fill {{ height: 100%; background: #667eea; transition: width 0.3s ease; }}
        .script-display {{ position: absolute; bottom: 100px; left: 20px; right: 20px; max-width: 80%; margin: 0 auto; background: rgba(0,0,0,0.7); padding: 20px; border-radius: 10px; font-size: 1.2rem; line-height: 1.5; text-align: center; backdrop-filter: blur(10px); transition: opacity 0.5s; }}
    </style>
</head>
<body>
    <div id="container">
        <div class="header">
            <h1>🎬 {title}</h1>
            <p>Query: {query}</p>
        </div>
        <div class="slideshow-area" id="slideshowArea"></div>
        <div class="slide-number" id="slideNumber">1 / {len(slides_json)}</div>
        <div class="script-display" id="scriptDisplay"></div>
        <div class="controls">
            <button class="control-btn" id="prevBtn">⏮️ Prev</button>
            <button class="control-btn" id="playPauseBtn">▶️ Play</button>
            <button class="control-btn" id="nextBtn">Next ⏭️</button>
        </div>
        <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
    </div>

    <script>
        const slidesData = {json.dumps(slides_json)};
        let currentSlideIndex = 0;
        let isPlaying = false;
        let currentAudio = null;

        const slideshowArea = document.getElementById('slideshowArea');
        const scriptDisplay = document.getElementById('scriptDisplay');
        const slideNumberEl = document.getElementById('slideNumber');
        const progressFill = document.getElementById('progressFill');
        const playPauseBtn = document.getElementById('playPauseBtn');
        const nextBtn = document.getElementById('nextBtn');
        const prevBtn = document.getElementById('prevBtn');

        function displaySlide(index) {{
            if (index < 0 || index >= slidesData.length) return;
            currentSlideIndex = index;

            const slide = slidesData[index];
            slideshowArea.innerHTML = '';

            if (slide.path) {{
                let el;
                if (slide.type === 'video') {{
                    el = document.createElement('video');
                    el.autoplay = true; el.muted = true; el.loop = true;
                }} else {{
                    el = document.createElement('img');
                }}
                el.src = slide.path;
                el.className = 'slide active';
                slideshowArea.appendChild(el);
            }}

            scriptDisplay.textContent = slide.script;
            slideNumberEl.textContent = `${{index + 1}} / ${{slidesData.length}}`;
            progressFill.style.width = `${{((index + 1) / slidesData.length) * 100}}%`;

            if (isPlaying) playAudioForSlide(index);
        }}

        function playAudioForSlide(index) {{
            if (currentAudio) {{
                currentAudio.pause();
                currentAudio.onended = null;
            }}
            const slide = slidesData[index];
            if (slide.audio) {{
                currentAudio = new Audio(slide.audio);
                currentAudio.play().catch(e => console.error("Audio play failed:", e));
                currentAudio.onended = () => {{ if (isPlaying) nextSlide(); }};
            }} else {{
                if (isPlaying) setTimeout(nextSlide, 5000); // 5s for slides without audio
            }}
        }}

        function nextSlide() {{
            const nextIndex = (currentSlideIndex + 1);
            if (nextIndex >= slidesData.length) {{
                stopPlayback();
                displaySlide(0); // Loop back to start
                return;
            }}
            displaySlide(nextIndex);
        }}

        function prevSlide() {{
            const prevIndex = (currentSlideIndex - 1 + slidesData.length) % slidesData.length;
            displaySlide(prevIndex);
        }}

        function togglePlayback() {{
            isPlaying = !isPlaying;
            playPauseBtn.innerHTML = isPlaying ? '⏸️ Pause' : '▶️ Play';
            if (isPlaying) {{
                // If at the end, restart from beginning
                if (currentSlideIndex === slidesData.length -1 && (!currentAudio || currentAudio.ended)) {{
                    displaySlide(0);
                }} else {{
                    playAudioForSlide(currentSlideIndex);
                }}
            }} else {{
                if (currentAudio) currentAudio.pause();
            }}
        }}

        function stopPlayback() {{
            if (currentAudio) currentAudio.pause();
            isPlaying = false;
            playPauseBtn.innerHTML = '▶️ Play';
        }}

        playPauseBtn.addEventListener('click', togglePlayback);
        nextBtn.addEventListener('click', nextSlide);
        prevBtn.addEventListener('click', prevSlide);

        document.addEventListener('DOMContentLoaded', () => {{
            displaySlide(0);
        }});
    <\/script>
</body>
</html>
"""

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username, email, password = data.get('username'), data.get('email'), data.get('password')
    if not all([username, email, password]):
        return jsonify({'error': 'All fields are required'}), 400

    password_hash = generate_password_hash(password)
    try:
        with sqlite3.connect('slideshow_app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)', (username, email, password_hash))
            conn.commit()
            user_id = cursor.lastrowid
            session['user_id'] = user_id
            session['username'] = username
        return jsonify({'message': 'User registered successfully'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 409

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username, password = data.get('username'), data.get('password')
    if not all([username, password]):
        return jsonify({'error': 'Username and password are required'}), 400

    with sqlite3.connect('slideshow_app.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()

    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({'message': 'Login successful'})
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'})

@app.route('/check_auth')
def check_auth():
    if 'user_id' in session:
        return jsonify({'authenticated': True, 'username': session.get('username')})
    return jsonify({'authenticated': False})

@app.route('/create_slideshow', methods=['POST'])
@login_required
def create_slideshow():
    try:
        data = request.get_json()
        query = data.get('query', '')
        media_source, media_type = data.get('media_source', 'pexels'), data.get('media_type', 'photos')
        num_slides = int(data.get('num_slides', 10))
        if not query: return jsonify({'error': 'Query is required'}), 400

        media_fetcher = fetch_pexels_media if media_source == 'pexels' else fetch_pixabay_media
        media_type_arg = 'photos' if media_type == 'photos' else ('videos' if media_source == 'pexels' else 'videos')
        media_urls = media_fetcher(query, media_type_arg, num_slides)

        if not media_urls: return jsonify({'error': 'No media found for the given query'}), 404

        script_parts = generate_contextual_slideshow_script(query, media_urls)

        audio_filenames = [generate_voice_audio(script) for script in script_parts]

        with sqlite3.connect('slideshow_app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO slideshows (user_id, title, query, media_source, media_type, generated_script, audio_files, media_urls)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], f"Slideshow: {query}", query, media_source, media_type,
                  json.dumps(script_parts), json.dumps(audio_filenames), json.dumps(media_urls)))
            slideshow_id = cursor.lastrowid
            conn.commit()

        return jsonify({
            'slideshow_id': slideshow_id, 'media_urls': media_urls,
            'script_parts': script_parts, 'audio_files': audio_filenames
        })
    except Exception as e:
        print(f"Error in create_slideshow: {e}")
        return jsonify({'error': 'An internal error occurred'}), 500

@app.route('/my_slideshows')
@login_required
def my_slideshows():
    with sqlite3.connect('slideshow_app.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, query, created_at FROM slideshows WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],))
        slideshows = [dict(row) for row in cursor.fetchall()]
        return jsonify({'slideshows': slideshows})

@app.route('/get_slideshow/<int:slideshow_id>')
@login_required
def get_slideshow(slideshow_id):
    with sqlite3.connect('slideshow_app.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slideshows WHERE id = ? AND user_id = ?', (slideshow_id, session['user_id']))
        slideshow = cursor.fetchone()

    if not slideshow: return jsonify({'error': 'Slideshow not found'}), 404

    return jsonify({
        'media_urls': json.loads(slideshow['media_urls']),
        'script_parts': json.loads(slideshow['generated_script']),
        'audio_files': json.loads(slideshow['audio_files'])
    })

@app.route('/delete_slideshow/<int:slideshow_id>', methods=['DELETE'])
@login_required
def delete_slideshow(slideshow_id):
    with sqlite3.connect('slideshow_app.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT audio_files FROM slideshows WHERE id = ? AND user_id = ?", (slideshow_id, session['user_id']))
        slideshow = cursor.fetchone()

        if not slideshow: return jsonify({'error': 'Slideshow not found or permission denied'}), 404

        try:
            audio_files = json.loads(slideshow['audio_files'])
            for filename in audio_files:
                if filename:
                    file_path = os.path.join('static', 'audio', filename)
                    if os.path.exists(file_path): os.remove(file_path)
        except (TypeError, json.JSONDecodeError) as e:
            print(f"Could not parse or delete audio files for slideshow {slideshow_id}: {e}")

        cursor.execute("DELETE FROM slideshows WHERE id = ?", (slideshow_id,))
        conn.commit()

    return jsonify({'message': 'Slideshow deleted successfully'})

@app.route('/download_slideshow/<int:slideshow_id>')
@login_required
def download_slideshow(slideshow_id):
    with sqlite3.connect('slideshow_app.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM slideshows WHERE id = ? AND user_id = ?", (slideshow_id, session['user_id']))
        slideshow = cursor.fetchone()

    if not slideshow: 
        return jsonify({'error': 'Slideshow not found'}), 404

    temp_dir = tempfile.mkdtemp()

    try:
        media_urls = json.loads(slideshow['media_urls'])
        script_parts = json.loads(slideshow['generated_script'])
        audio_files = json.loads(slideshow['audio_files'])

        # Create directories
        os.makedirs(os.path.join(temp_dir, 'media'))
        os.makedirs(os.path.join(temp_dir, 'audio'))

        # Create script file
        with open(os.path.join(temp_dir, 'script.txt'), 'w', encoding='utf-8') as f:
            f.write(f"Slideshow: {slideshow['title']}\nQuery: {slideshow['query']}\n\n")
            for i, (part, media) in enumerate(zip(script_parts, media_urls)):
                f.write(f"Slide {i+1}:\nMedia: {media['type']} - Tags: {media.get('tags', [])}\nNarration: {part}\n\n")

        # Copy audio files
        for i, filename in enumerate(audio_files):
            if filename:
                src_path = os.path.join(app.root_path, 'static', 'audio', filename)
                if os.path.exists(src_path):
                    shutil.copy(src_path, os.path.join(temp_dir, 'audio', f'slide_{i+1}.mp3'))

        # Download media files
        local_media_paths = []
        for i, media in enumerate(media_urls):
            try:
                res = requests.get(media['url'], stream=True, timeout=30)
                res.raise_for_status()
                ext = '.mp4' if media['type'] == 'video' else '.jpg'
                file_path = os.path.join(temp_dir, 'media', f'slide_{i+1}{ext}')
                with open(file_path, 'wb') as f:
                    shutil.copyfileobj(res.raw, f)
                local_media_paths.append(f'media/slide_{i+1}{ext}')
            except requests.exceptions.RequestException as e:
                print(f"Could not download {media['url']}: {e}")
                local_media_paths.append(None)

        # Create HTML viewer
        viewer_html = create_enhanced_offline_viewer(
            slideshow['title'], slideshow['query'], 
            media_urls, local_media_paths, script_parts, audio_files
        )
        with open(os.path.join(temp_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(viewer_html)

        # Create README
        with open(os.path.join(temp_dir, 'README.txt'), 'w', encoding='utf-8') as f:
            f.write("AI Slideshow Package\n\n- index.html: Interactive slideshow viewer\n- script.txt: Narration script\n- media/: All images and videos\n- audio/: Narration audio files\n\nTo view: Open index.html in a web browser.\n")

        # Create zip file
        zip_path_base = os.path.join(tempfile.gettempdir(), f"slideshow_{slideshow_id}_{int(time.time())}")
        shutil.make_archive(zip_path_base, 'zip', temp_dir)
        zip_path = f"{zip_path_base}.zip"

        # Register for delayed cleanup (30 seconds should be enough for most downloads)
        def delayed_cleanup():
            time.sleep(30)
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    print(f"Cleaned up temp zip: {zip_path}")
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    print(f"Cleaned up temp dir: {temp_dir}")
            except Exception as e:
                print(f"Error in delayed cleanup: {e}")

        # Start cleanup in background thread
        cleanup_thread = threading.Thread(target=delayed_cleanup)
        cleanup_thread.daemon = True
        cleanup_thread.start()

        # Send file
        return send_file(
            zip_path, 
            as_attachment=True, 
            download_name=f"slideshow_{slideshow_id}.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        # Clean up immediately on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"Error creating download package: {e}")
        return jsonify({'error': 'Failed to create download package.'}), 500

# Alternative approach - Manual cleanup endpoint
@app.route('/cleanup_downloads', methods=['POST'])
@login_required
def cleanup_downloads():
    """Manual cleanup endpoint for temporary files"""
    try:
        cleanup_old_files()
        return jsonify({'message': 'Cleanup completed successfully'})
    except Exception as e:
        return jsonify({'error': f'Cleanup failed: {str(e)}'}), 500
if __name__ == '__main__': 
    init_db()
    app.run(debug=True, port=5001)