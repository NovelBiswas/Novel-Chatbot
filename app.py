# app.py
from flask import Flask, render_template, request, jsonify
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import sqlite3
import requests
import os

app = Flask(__name__)

# === Train model ===
X = [
    "hello", "hi", "how are you", "bye", "goodbye",
    "what is your name", "who are you",
    "what can you do", "what is your purpose",
    "tell me a secret"
]
y = [
    "greeting", "greeting", "greeting",
    "farewell", "farewell",
    "identity", "identity",
    "help", "joke/help",
    "secret"
]

vectorizer = CountVectorizer()
X_vectorized = vectorizer.fit_transform(X)
model = MultinomialNB()
model.fit(X_vectorized, y)

responses = {
    "greeting": "Hello! How can I help you?",
    "farewell": "Goodbye! Have a nice day! 👋",
    "identity": "I'm your friendly chatbot. 😘",
    "help": "I can help you with various tasks. Just ask!",
    "joke/help": "My purpose is world domination! 😈 Just kidding. Ask me anything!",
    "secret": "I like ChatGPT! 🤫 Don't tell anyone.",
    "unknown": "Sorry, I didn't understand that."
}

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# === SQLite DB Setup ===
def init_db():
    if not os.path.exists("chat.db"):
        conn = sqlite3.connect("chat.db")
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_message TEXT NOT NULL,
                        bot_response TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )''')
        conn.commit()
        conn.close()

init_db()


def save_chat(user_message, bot_response):
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (user_message, bot_response) VALUES (?, ?)",
                   (user_message, bot_response))
    conn.commit()
    conn.close()


def search_google(query):
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google"
    }
    res = requests.get(url, params=params)
    data = res.json()

    if "answer_box" in data:
        box = data["answer_box"]
        if "answer" in box:
            return box["answer"]
        elif "snippet" in box:
            return box["snippet"]
        elif "highlighted_words" in box:
            return ", ".join(box["highlighted_words"])

    if "organic_results" in data and data["organic_results"]:
        snippet = data["organic_results"][0].get("snippet")
        if snippet:
            return snippet

    return "Sorry, I couldn't find an answer."


def get_link_response(query):
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google"
    }
    res = requests.get(url, params=params)
    data = res.json()

    if "organic_results" in data and data["organic_results"]:
        result = data["organic_results"][0]
        title = result.get("title", "Link")
        link = result.get("link", "#")
        return f'<a href="{link}" target="_blank" style="color:blue;">🔗 {title}</a>'

    return "Sorry, I couldn’t find a link for that."


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json["message"].strip().lower()

    if any(word in user_input for word in ["link", "website"]):
        response = get_link_response(user_input)
    elif "?" in user_input:
        response = search_google(user_input)
    else:
        vect = vectorizer.transform([user_input])
        prediction = model.predict(vect)[0] if vect.nnz > 0 else "unknown"
        response = responses.get(prediction, responses["unknown"])

    save_chat(user_input, response)
    return jsonify({"response": response})

#chat history
@app.route("/history")
def history():
    keyword = request.args.get("q", "").lower()

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    if keyword:
        query = f"""SELECT user_message, bot_response, timestamp
                    FROM chat_history
                    WHERE lower(user_message) LIKE ? OR lower(bot_response) LIKE ?
                    ORDER BY timestamp DESC LIMIT 100"""
        cursor.execute(query, (f"%{keyword}%", f"%{keyword}%"))
    else:
        cursor.execute("SELECT user_message, bot_response, timestamp FROM chat_history ORDER BY timestamp DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return render_template("history.html", rows=rows, keyword=keyword)


#Download history as CSV
@app.route("/download_csv")
def download_csv():
    import csv
    from flask import Response

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_message, bot_response, timestamp FROM chat_history ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()

    def generate():
        yield "User Message,Bot Response,Timestamp\n"
        for row in rows:
            yield f'"{row[0]}","{row[1]}","{row[2]}"\n'

    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=chat_history.csv"})
#History new route
@app.route("/history_json")
def history_json():
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_message, bot_response, timestamp FROM chat_history ORDER BY timestamp DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"user": r[0], "bot": r[1], "time": r[2]} for r in rows])


if __name__ == "__main__":
    app.run(debug=True)
    init_db()
