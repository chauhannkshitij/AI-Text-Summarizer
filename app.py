from flask import Flask, render_template, request, jsonify
import os
import requests
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import docx
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file

app = Flask(__name__)

# Load API key securely from environment
API_KEY = os.getenv("API_KEY")

# ✅ Allowed file formats
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx'}


def allowed_file(filename):
    """Check if uploaded file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ✅ Extract text from PDF, TXT, DOCX
def extract_text(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    text = ""
    if ext == 'pdf':
        reader = PdfReader(file_path)
        for page in reader.pages:
            text += page.extract_text() or ""
    elif ext == 'txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    elif ext == 'docx':
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
    return text.strip()


# ✅ Generate summary via Gemini API
def generate_summary(text, summary_type="paragraph"):
    try:
        # Determine length instruction
        if summary_type == "1-line":
            length_instruction = "in one short line"
        elif summary_type == "3-line":
            length_instruction = "in three concise lines"
        elif summary_type == "5-line":
            length_instruction = "in five short lines"
        else:
            length_instruction = "as a concise paragraph"

        # Build refined prompt
        prompt = (
            f"Summarize the following text {length_instruction}. "
            "Do NOT start with phrases like 'This document is about', 'This text contains', or similar. "
            "Provide only the summary without introduction phrases.\n\n"
            f"{text}"
        )

        # Gemini API endpoint
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": prompt}]}]}

        response = requests.post(f"{url}?key={API_KEY}", headers=headers, json=data)
        result = response.json()

        if "candidates" in result:
            summary_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            return summary_text
        elif "error" in result and result["error"].get("code") == 429:
            return "⚠️ API quota exceeded — please retry after some time."
        else:
            print("Error generating summary:", result)
            return "Error generating summary. Please check your API key or model."
    except Exception as e:
        print("Exception:", e)
        return "An unexpected error occurred during summarization."


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/summarize', methods=['POST'])
def summarize():
    summaries = []
    texts = []

    # 🔹 Get summary type from dropdown
    summary_type = request.form.get('summary_type', 'paragraph')

    # 🔹 Handle uploaded files
    if 'files' in request.files:
        uploaded_files = request.files.getlist('files')
        for file in uploaded_files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                os.makedirs("uploads", exist_ok=True)
                path = os.path.join("uploads", filename)
                file.save(path)
                text = extract_text(path)
                texts.append({"name": filename, "text": text})

    # 🔹 Handle direct text input
    user_text = request.form.get('text')
    if user_text:
        texts.append({"name": "Direct Text Input", "text": user_text})

    # 🔹 Generate summaries for all inputs
    for t in texts:
        original_text = t["text"]
        summary = generate_summary(original_text, summary_type)

        # Calculate percentage reduction
        if len(original_text) > 0:
            reduction = 100 - ((len(summary) / len(original_text)) * 100)
            reduction = max(0, min(100, round(reduction, 2)))  # Clamp between 0–100
        else:
            reduction = 0

        summaries.append({
            "name": t["name"],
            "summary": summary,
            "reduction": reduction
        })

    return jsonify({"summaries": summaries})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
