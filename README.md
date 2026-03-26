<<<<<<< HEAD
AI Customer Support Quality Auditor
📌 Project Overview
AI-powered Quality Assurance platform for customer support conversations.

Processes:

🔊 Call recordings → Speech-to-Text → Analysis

💬 Chat logs → Text processing → Analysis

Generates: AI-powered summaries, sentiment analysis, performance scores

New: ✨ Web UI for instant analysis of uploaded files

🚀 Tasks Completed
✅ Backend Pipeline
text
Audio Files → Deepgram Transcription → LLM Analysis → JSON Insights
Chat Files → Text Processing → LLM Analysis → JSON Insights
✅ Web Frontend
Drag & drop file upload (.txt, .mp3, .wav, .m4a, .json)

Real-time AI analysis

Clean, responsive UI

Instant summary display

Task 1 — Audio Transcription
Deepgram Nova-2 model

Multi-format support (.mp3, .wav, .m4a)

Error handling & retries

Batch processing capability

Task 2 — Chat Processing
Raw .txt chat log parsing

JSON structure conversion

Content validation

Multi-format detection

Task 3 — LLM Analysis
OpenRouter API integration

Mistral-7B-Instruct model

Structured JSON output

Robust error recovery

Task 4 — Web Interface (NEW)
Flask-based web app

File upload & processing

AJAX-powered UI updates

Responsive glassmorphism design

📂 Project Structure
text
genai/
│
├── app.py                 # 🔥 Flask Web App (NEW)
├── analyzer.py           # LLM Analysis Engine
├── static/
│   └── style.css         # Modern UI Styles (NEW)
├── templates/
│   └── index.html        # Web Interface (NEW)
├── transcription/
│   ├── deepgram_processor.py
│   └── chat_processor.py
├── uploads/              # Temp uploads (auto-created)
├── config/
│   └── .env              # API Keys
├── sample_data/
│   ├── audio/           # Test audio files
│   └── chats/           # Test chat files
├── analysis_results/     # Batch analysis outputs
└── tests/
    └── test_transcription.py
⚙️ Quick Setup (2 Minutes)
1️⃣ Install Dependencies
bash
cd genai
pip install flask requests python-dotenv deepgram-sdk
2️⃣ Add API Keys
Create genai/config/.env:

text
DEEPGRAM_API_KEY=your_deepgram_key
OPENROUTER_API_KEY=your_openrouter_key
3️⃣ Launch Web App (Recommended)
bash
python app.py
Open: http://127.0.0.1:5000

4️⃣ OR Run Batch Pipeline
bash
python transcription/deepgram_processor.py
python transcription/chat_processor.py  
python llm/openrouter_tester.py
🎯 Usage
Method	Command	Output
Web UI	python app.py	http://localhost:5000
Audio Batch	deepgram_processor.py	transcription/sample_outputs/*.txt
Chat Batch	chat_processor.py	transcription/sample_outputs/*.json
Analysis	openrouter_tester.py	analysis_results/*.json
📱 Web UI Features
text
1. Drag & drop ANY file (.txt, .mp3, .wav, .json)
2. Auto-detects: Audio vs Chat content  
3. AI analysis in ~3 seconds
4. Clean summary display
5. Works on mobile/desktop
Demo Flow:

text
Upload human_chat.txt → AI detects chat → LLM analyzes → "Customer inquired about order delay..."
📊 Sample Outputs
text
Web UI:     "Customer switched from Pixel to Samsung for withdrawal setup"
JSON File:  {"summary": "Miriam resolved withdrawal issue via remote troubleshooting"}
🧪 Testing
bash
# Validate batch outputs
python tests/test_transcription.py

# Test web app (manual)
curl -F "file=@sample_data/chats/human_chat.txt" http://localhost:5000/analyze_ajax
🔐 Environment Variables
text
genai/config/.env
├── DEEPGRAM_API_KEY=sk-...
└── OPENROUTER_API_KEY=sk-or-...
🛠️ Tech Stack
text
Backend:     Python, Flask, Deepgram API, OpenRouter
Frontend:    HTML5, Vanilla JS, CSS3 (Glassmorphism)
APIs:        REST, JSON, AJAX
Deployment:  Single Python file (app.py)
✅ Status: COMPLETE ✅
=======
# CallAudit-Pro-
CallAudit Pro is a call analysis and auditing platform designed to help teams review conversations, track performance metrics, ensure compliance, and generate meaningful insights from call data.
>>>>>>> f2aab85fcc9a21468c2c465ead4702c9e6ca096a
