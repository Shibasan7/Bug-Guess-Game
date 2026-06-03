from flask import Flask, request, jsonify, send_from_directory
from ollama import Client
from random import choice, sample
import os
import requests as http_requests

app = Flask(__name__)

# Ollama runs locally inside the same container
ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
client = Client(host=ollama_host)

ALL_BUGS = [
    "butterfly", "bumblebee", "firefly", "dragonfly", "moth",
    "housefly", "mosquito", "honeybee", "hornet", "damselfly",
    "ladybug", "beetle", "caterpillar", "ant", "termite",
    "cockroach", "earwig", "pill bug", "centipede", "walking stick",
    "grasshopper", "cricket", "flea", "leafhopper", "springtail",
    "praying mantis", "stink bug", "cicada", "walking leaf", "dung beetle"
]

DIFFICULTY_QUESTIONS = {"easy": 20, "hard": 10}

game_state = {}

def new_game(difficulty="easy"):
    bugs = sample(ALL_BUGS, 5)
    return {
        "bugs": bugs,
        "current_bug": choice(bugs),
        "max_questions": DIFFICULTY_QUESTIONS.get(difficulty, 20),
        "questions_left": DIFFICULTY_QUESTIONS.get(difficulty, 20),
        "bugs_guessed": 0,
        "score": 0,
        "difficulty": difficulty,
    }

game_state["session"] = new_game()


def build_prompt(bug, question, difficulty):
    vagueness = (
        "Give helpful, clear yes/no answers."
        if difficulty == "easy"
        else "Be intentionally vague and cryptic. Make it hard. Still answer yes or no but add misleading hedging."
    )
    return f"""You are playing 20 questions. The secret bug is: {bug}

The user said: {question}

Rules:
- {vagueness}
- If the user correctly guessed "{bug}", respond ONLY with: "You guessed it!"
- Never mention or hint at the bug name otherwise.
- Keep answers to 1-2 sentences."""


def fetch_bug_image(bug_name):
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + bug_name.replace(" ", "_")
        r = http_requests.get(url, timeout=4)
        if r.status_code == 200:
            img = r.json().get("thumbnail", {}).get("source", "")
            if img:
                return img
    except Exception:
        pass
    return ""


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/status")
def status():
    try:
        models = client.list()["models"]
        available = [m["name"] for m in models]
        has_model = any("llama3.2" in name for name in available)
        return jsonify({"ok": has_model, "models": available})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/state")
def get_state():
    s = game_state["session"]
    return jsonify({
        "questions_left": s["questions_left"],
        "bugs_remaining": len(s["bugs"]),
        "bugs_guessed": s["bugs_guessed"],
        "score": s["score"],
        "difficulty": s["difficulty"],
    })


@app.route("/api/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    s = game_state["session"]

    if s["questions_left"] <= 0:
        return jsonify({"error": "No questions remaining"}), 400

    s["questions_left"] -= 1

    try:
        response = client.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": build_prompt(s["current_bug"], question, s["difficulty"])}]
        )
        ai_response = response["message"]["content"]
    except Exception as e:
        return jsonify({"error": f"Ollama error: {e}"}), 500

    guessed = "you guessed it" in ai_response.lower()
    out_of_questions = s["questions_left"] <= 0 and not guessed

    result = {
        "response": ai_response,
        "guessed": guessed,
        "out_of_questions": out_of_questions,
        "questions_left": s["questions_left"],
        "bugs_remaining": len(s["bugs"]),
        "bugs_guessed": s["bugs_guessed"],
        "score": s["score"],
        "revealed_bug": None,
        "bug_image": "",
        "game_over": False,
        "sound": None,
    }

    if out_of_questions:
        result["revealed_bug"] = s["current_bug"]
        result["bug_image"] = fetch_bug_image(s["current_bug"])
        result["sound"] = "wrong"

    if guessed:
        points = s["questions_left"] + (10 if s["difficulty"] == "hard" else 0)
        s["score"] += points
        result["score"] = s["score"]
        result["bug_image"] = fetch_bug_image(s["current_bug"])
        result["sound"] = "correct"

    if guessed or out_of_questions:
        s["bugs"].remove(s["current_bug"])
        result["bugs_remaining"] = len(s["bugs"])

        if not s["bugs"]:
            result["game_over"] = True
        else:
            s["current_bug"] = choice(s["bugs"])
            s["questions_left"] = s["max_questions"]
            result["questions_left"] = s["questions_left"]

    return jsonify(result)


@app.route("/api/set_difficulty", methods=["POST"])
def set_difficulty():
    data = request.json
    difficulty = data.get("difficulty", "easy")
    game_state["session"] = new_game(difficulty)
    return jsonify({"ok": True, "difficulty": difficulty})


@app.route("/api/restart", methods=["POST"])
def restart():
    difficulty = game_state["session"].get("difficulty", "easy")
    game_state["session"] = new_game(difficulty)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)