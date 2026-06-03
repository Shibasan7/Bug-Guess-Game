from flask import Flask, request, jsonify, send_from_directory, session
from ollama import Client
from random import choice, sample
import os
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# ----------------------------
# Config
# ----------------------------

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
client = Client(host=OLLAMA_HOST)

DIFFICULTY = {
    "easy": 20,
    "hard": 10
}

BUGS = [
    "butterfly","bumblebee","firefly","dragonfly","moth",
    "housefly","mosquito","honeybee","hornet","ladybug",
    "beetle","ant","termite","cockroach","grasshopper"
]

# ----------------------------
# State helpers
# ----------------------------

def new_state(difficulty="easy"):
    bugs = sample(BUGS, 5)
    return {
        "bugs": bugs,
        "current_bug": choice(bugs),
        "difficulty": difficulty,
        "questions_left": DIFFICULTY[difficulty],
        "score": 0,
        "bugs_guessed": 0,
        "game_over": False
    }


def get_state():
    if "game" not in session:
        session["game"] = new_state()
    return session["game"]


def save_state(state):
    session["game"] = state
    session.modified = True


# ----------------------------
# Prompt
# ----------------------------

def build_prompt(bug, question, difficulty):
    style = (
        "Answer clearly yes/no."
        if difficulty == "easy"
        else "Be vague but still yes/no. No hints."
    )

    return f"""
You are playing 20 Questions.

Secret bug: {bug}

User question: {question}

Rules:
- {style}
- Never reveal the bug
- Keep answer under 2 sentences
"""


# ----------------------------
# Image helper
# ----------------------------

def fetch_image(name):
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{name}"
        r = requests.get(url, timeout=3)
        if r.ok:
            return r.json().get("thumbnail", {}).get("source", "")
    except:
        pass
    return ""


# ----------------------------
# Game logic (clean separation)
# ----------------------------

def is_correct_guess(state, question: str) -> bool:
    """
    More flexible guess detection:
    user can type 'I think it's a butterfly'
    """
    q = question.lower()
    bug = state["current_bug"].lower()
    return bug in q


def advance_game(state):
    """
    Move to next bug or end game
    """
    state["bugs"].remove(state["current_bug"])

    if not state["bugs"]:
        state["game_over"] = True
        return

    state["current_bug"] = choice(state["bugs"])
    state["questions_left"] = DIFFICULTY[state["difficulty"]]


# ----------------------------
# Routes
# ----------------------------

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/health")
def health():
    return "ok", 200

@app.route("/ready")
def ready():
    try:
        import requests
        requests.get("http://ollama:11434", timeout=1)
        return "ready", 200
    except:
        return "not ready", 500

@app.route("/api/state")
def state():
    s = get_state()
    return jsonify({
        "questions_left": s["questions_left"],
        "bugs_remaining": len(s["bugs"]),
        "bugs_guessed": s["bugs_guessed"],
        "score": s["score"],
        "difficulty": s["difficulty"],
        "game_over": s.get("game_over", False)
    })


@app.route("/api/restart", methods=["POST"])
def restart():
    session["game"] = new_state(get_state()["difficulty"])
    return jsonify({"ok": True})


@app.route("/api/set_difficulty", methods=["POST"])
def set_diff():
    data = request.json or {}
    difficulty = data.get("difficulty", "easy")
    session["game"] = new_state(difficulty)
    return jsonify({"ok": True})


@app.route("/api/ask", methods=["POST"])
def ask():
    data = request.json or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Empty question"}), 400

    s = get_state()

    if s.get("game_over"):
        return jsonify({"error": "Game is over"}), 400

    if s["questions_left"] <= 0:
        return jsonify({"error": "No questions left"}), 400

    # decrement AFTER validation
    s["questions_left"] -= 1

    # ----------------------------
    # LLM call (safe wrapper)
    # ----------------------------
    try:
        response = client.chat(
            model="llama3.2",
            messages=[{
                "role": "user",
                "content": build_prompt(
                    s["current_bug"],
                    question,
                    s["difficulty"]
                )
            }]
        )
        answer = response["message"]["content"]
    except Exception:
        answer = "I had trouble thinking just now."

    guessed = is_correct_guess(s, question)

    if guessed:
        s["bugs_guessed"] += 1
        s["score"] += max(s["questions_left"], 1)

    out_of_questions = s["questions_left"] <= 0 and not guessed

    result = {
        "response": answer,
        "guessed": guessed,
        "out_of_questions": out_of_questions,
        "questions_left": s["questions_left"],
        "bugs_remaining": len(s["bugs"]),
        "score": s["score"],
        "revealed_bug": None,
        "bug_image": None,
        "game_over": False
    }

    # ----------------------------
    # End-of-round logic
    # ----------------------------
    if guessed or out_of_questions:
        result["revealed_bug"] = s["current_bug"]
        result["bug_image"] = fetch_image(s["current_bug"])

        advance_game(s)

        if s.get("game_over"):
            result["game_over"] = True

    save_state(s)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)