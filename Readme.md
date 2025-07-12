# 📆 AI Slideshow Creator – Installation Guide

*Also known as Prompt2Slides*

This guide helps you set up the **AI Slideshow Creator**, a Flask web app that uses **Gemini, Pexels, Pixabay, and ElevenLabs APIs** to generate **AI-powered, offline-ready educational slideshows** — complete with narration, images, and videos — all from a single prompt.

> 🎥 [**Pitch Deck**](https://docs.google.com/presentation/d/1la6VuclIqyZKOKgzifkMSvo_3OJAu-2QX1-pff0Y2a0/edit?usp=sharing) – View the official presentation slide submitted for United Hacks V5!
>
> 🌐 [**Live Web App**](http://prompt2slides.eu-north-1.elasticbeanstalk.com/) – Try out the deployed version now!

---

## ✅ Requirements

* Python 3.9+
* `pip` (Python package installer)
* API Keys for:

  * [Google Gemini API](https://makersuite.google.com/)
  * [Pixabay API](https://pixabay.com/api/docs/)
  * [Pexels API](https://www.pexels.com/api/)
  * [ElevenLabs API](https://www.elevenlabs.io/)

---

## 🚀 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/Jerryblessed/slideshowai.git
cd ai-slideshow-creator
```

### 2. (Optional) Create and Activate Virtual Environment

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

You can either:

* Create a `.env` file in the root directory, or
* Set the variables in your terminal environment:

```bash
export GEMINI_API_KEY="your_gemini_api_key"
export PIXABAY_API_KEY="your_pixabay_api_key"
export PEXELS_API_KEY="your_pexels_api_key"
export ELEVENLABS_API_KEY="your_elevenlabs_api_key"
```

For Windows CMD:

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

Then open your browser and visit:

```text
http://127.0.0.1:5000
```

---

## 📁 Output

* Each prompt generates a **.zip file** containing:

  * HTML slideshow
  * Slide-by-slide AI voice narration
  * Embedded images and video links

---

## 💡 Deployment Tip

If deploying on a cloud platform (e.g. Render, Heroku), configure the API keys via environment variable settings in the dashboard.

To keep local development secure and clean, use `.env` + [python-dotenv](https://pypi.org/project/python-dotenv/).

---

📚 For full context and slides, view the
🎞️ **[Official Pitch Deck here »](https://docs.google.com/presentation/d/1la6VuclIqyZKOKgzifkMSvo_3OJAu-2QX1-pff0Y2a0/edit?usp=sharing)**

🌐 **Try it live**: [https://lighteducation.pythonanywhere.com/](http://prompt2slides.eu-north-1.elasticbeanstalk.com/)

Happy hacking, presenting, and teaching — anywhere, even offline! 🧠💡✨
