# 📦 AI Slideshow Creator – Installation Guide

This guide helps you set up the **AI Slideshow Creator AKA prompt2slides**, a Flask app that uses Gemini, Pexels, Pixabay, and ElevenLabs APIs to generate educational slideshows (offline-ready) with text, images, videos, and narration.

---

## ✅ Requirements

* Python 3.9+
* pip (Python package installer)
* API keys for:

  * [Google Gemini API](https://makersuite.google.com/)
  * [Pixabay API](https://pixabay.com/api/docs/)
  * [Pexels API](https://www.pexels.com/api/)
  * [ElevenLabs API](https://www.elevenlabs.io/)

---

## 🚀 Setup Instructions

### 1. Clone the Repository

```bash
https://github.com/Jerryblessed/slideshowai.git
cd ai-slideshow-creator
```

### 2. Create and Activate Virtual Environment (Optional but Recommended)

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Add Your API Keys

Create a `.env` file or set the keys as environment variables in your terminal:

```bash
export GEMINI_API_KEY="your_gemini_api_key"
export PIXABAY_API_KEY="your_pixabay_api_key"
export PEXELS_API_KEY="your_pexels_api_key"
export ELEVENLABS_API_KEY="your_elevenlabs_api_key"
```

On Windows CMD:

```cmd
set GEMINI_API_KEY=your_gemini_api_key
set PIXABAY_API_KEY=your_pixabay_api_key
set PEXELS_API_KEY=your_pexels_api_key
set ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

### 5. Run the Flask App

```bash
python app.py
```

Visit `http://127.0.0.1:5000` in your browser.

---

## 📁 Output

* Downloadable `.zip` packages containing the entire slideshow (HTML + assets)

---

## 💡 Tip

If you plan to deploy, consider setting up environment variables securely using a `.env` manager like `python-dotenv`, or store secrets on your hosting platform (e.g., Heroku Config Vars).

---

For more documentation or walkthroughs, check the `docs/` folder or contact the developer.

Enjoy creating AI-powered offline learning content! 🎓✨
