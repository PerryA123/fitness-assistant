import json
from datetime import date, datetime
from pathlib import Path

import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


DATA_DIR = Path("user_data")
DATA_DIR.mkdir(exist_ok=True)

st.set_page_config(
    page_title="Aidan Fitness Coach",
    page_icon="💪",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main {
        background-color: #0e1117;
    }
    .stApp {
        background: linear-gradient(180deg, #0e1117 0%, #111827 100%);
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1100px;
    }
    h1, h2, h3 {
        letter-spacing: 0.2px;
    }
    .hero-box {
        padding: 1.2rem 1.2rem 1rem 1.2rem;
        border-radius: 18px;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 1rem;
    }
    .small-note {
        font-size: 0.92rem;
        opacity: 0.85;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_users():
    try:
        users = st.secrets["users"]
        return dict(users)
    except Exception:
        return {}


def login_user(username: str, password: str) -> bool:
    users = get_users()
    if username in users and str(users[username]) == str(password):
        st.session_state["logged_in"] = True
        st.session_state["username"] = username
        if "messages" not in st.session_state:
            st.session_state["messages"] = []
        return True
    return False


def logout_user():
    st.session_state["logged_in"] = False
    st.session_state["username"] = None
    st.session_state["messages"] = []


def user_file(username: str) -> Path:
    return DATA_DIR / f"{username}_trainer_data.json"


def load_user_data(username: str):
    path = user_file(username)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"profile": {}, "logs": []}


def save_user_data(username: str, data):
    path = user_file(username)
    path.write_text(json.dumps(data, indent=2))


def pounds_to_kg(lb):
    return lb * 0.45359237


def inches_to_cm(inches):
    return inches * 2.54


def calculate_bmr(profile):
    weight_kg = pounds_to_kg(profile["weight_lb"])
    height_cm = inches_to_cm(profile["height_in"])
    age = profile["age"]
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    sex = profile["sex"].lower()
    if sex == "male":
        return base + 5
    if sex == "female":
        return base - 161
    return base - 78


def activity_multiplier(level):
    return {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very active": 1.9,
    }.get(level.lower(), 1.55)


def calorie_targets(profile):
    tdee = calculate_bmr(profile) * activity_multiplier(profile["activity_level"])
    goal = profile["goal"].lower()

    if goal == "cut":
        target = tdee - 400
    elif goal == "bulk":
        target = tdee + 250
    elif goal == "recomp":
        target = tdee - 100
    else:
        target = tdee

    protein = round(profile["weight_lb"] * 0.8)
    return {
        "bmr": round(calculate_bmr(profile)),
        "tdee": round(tdee),
        "calories": round(target),
        "protein_g": protein,
    }


def recovery_score(log):
    score = 50
    sleep = log["sleep_hours"]
    soreness = log["soreness_1_10"]
    stress = log["stress_1_10"]
    intensity = log["workout_intensity_1_10"]

    if sleep >= 8:
        score += 20
    elif sleep >= 7:
        score += 10
    elif sleep < 6:
        score -= 20

    score -= (soreness - 3) * 4
    score -= (stress - 3) * 3
    score -= max(0, intensity - 6) * 2

    return max(0, min(100, round(score)))


def get_recommendation(log):
    rec = recovery_score(log)
    if rec < 35:
        return rec, "Rest / recovery day", "Your body looks pretty beat up today. Keep it light, walk, hydrate, and recover."
    elif rec < 60:
        return rec, "Train, but keep it controlled", "Good day for easier cardio, lighter lifting, or technique work."
    return rec, "Good to train hard", "You look solid today. Warm up well and go after it."


def avg(values):
    return round(sum(values) / len(values), 1) if values else 0


def build_today_plan(profile, latest_log):
    rec = recovery_score(latest_log)
    goal = profile["goal"]

    if rec < 35:
        return "Today’s plan: full recovery day. Easy walk, mobility, plenty of water, and get to bed early."
    if rec < 60:
        if latest_log["workout_type"] == "run":
            return "Today’s plan: easy run or incline walk, then light stretching. Keep effort low."
        if latest_log["workout_type"] == "lift":
            return "Today’s plan: lighter lift, fewer sets, no max effort."
        return "Today’s plan: controlled workout only. Keep it moderate and leave some energy in the tank."
    if goal == "cut":
        return "Today’s plan: train hard, keep intensity up, and stay tight on calories and protein."
    if goal == "bulk":
        return "Today’s plan: hard training day. Push performance and eat enough to recover."
    return "Today’s plan: good day to push a solid workout and stack another good session."


def openai_ready():
    return OpenAI is not None and "OPENAI_API_KEY" in st.secrets


def get_chat_client():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def get_chat_model():
    try:
        return st.secrets["OPENAI_MODEL"]
    except Exception:
        return "gpt-4.1-mini"


def latest_context_summary(profile, logs):
    if not profile:
        return "No profile saved yet."
    recent = sorted(logs, key=lambda x: x["date"])[-7:] if logs else []
    summary = {
        "profile": profile,
        "recent_logs": recent,
    }
    return json.dumps(summary, indent=2)


def ask_fitness_chatbot(user_question, profile, logs):
    client = get_chat_client()
    model = get_chat_model()

    system_prompt = (
        "You are a practical fitness coach inside a workout tracking app. "
        "Give simple, useful answers. Be clear and supportive. "
        "Base advice on the user's saved fitness profile and recent logs when available. "
        "Do not give medical diagnosis. If an injury sounds serious or persistent, tell them to see a licensed professional. "
        "Keep answers concise but helpful."
    )

    context = latest_context_summary(profile, logs)

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"User profile and recent logs:\n{context}\n\nQuestion:\n{user_question}",
            },
        ],
    )
    return response.output_text


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "username" not in st.session_state:
    st.session_state["username"] = None

if "messages" not in st.session_state:
    st.session_state["messages"] = []


if not st.session_state["logged_in"]:
    st.title("💪 Aidan Fitness Coach")
    st.markdown(
        """
        <div class="hero-box">
            <h3 style="margin-top:0;">Login to your fitness dashboard</h3>
            <div class="small-note">
                Track calories, recovery, training, and ask the built-in coach questions.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    users = get_users()
    if not users:
        st.warning("No login users found yet. Add usernames and passwords in Streamlit Secrets first.")
        st.code(
            """[users]
aidan = "yourpassword"
friend = "anotherpassword"

OPENAI_API_KEY = "your-openai-api-key"
OPENAI_MODEL = "gpt-4.1-mini"
""",
            language="toml",
        )
        st.stop()

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

        if submitted:
            if login_user(username.strip(), password):
                st.success("Logged in.")
                st.rerun()
            else:
                st.error("Wrong username or password.")

    st.stop()


username = st.session_state["username"]
data = load_user_data(username)

col_left, col_right = st.columns([4, 1])
with col_left:
    st.title("💪 Aidan Fitness Coach")
    st.caption(f"Logged in as: {username}")
with col_right:
    st.write("")
    if st.button("Log out", use_container_width=True):
        logout_user()
        st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Profile", "Daily Check-In", "Coach Chat"])

with tab1:
    st.subheader("Your Dashboard")

    if not data.get("profile"):
        st.info("Set up your profile first.")
    else:
        profile = data["profile"]
        logs = sorted(data["logs"], key=lambda x: x["date"]) if data["logs"] else []
        targets = calorie_targets(profile)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Target Calories", targets["calories"])
        c2.metric("Protein Target", targets["protein_g"])
        c3.metric("Maintenance", targets["tdee"])
        c4.metric("Current Weight", f'{profile["weight_lb"]} lb')

        if logs:
            latest = logs[-1]
            rec, title, detail = get_recommendation(latest)

            st.markdown("### Recovery + Plan")
            a, b = st.columns(2)
            with a:
                st.metric("Recovery Score", rec)
                st.write(f"**Status:** {title}")
                st.write(detail)
            with b:
                st.write(f"**{build_today_plan(profile, latest)}**")

            recent = logs[-7:]
            notes = []
            if avg([x["calories"] for x in recent]) < targets["calories"] - 250:
                notes.append("You’ve been under your calorie target lately, which may hurt recovery or performance.")
            if avg([x["protein_g"] for x in recent]) < targets["protein_g"] - 15:
                notes.append("Protein has been low compared to target.")
            if avg([x["sleep_hours"] for x in recent]) < 7:
                notes.append("Sleep looks like the biggest thing to improve right now.")
            if latest["soreness_1_10"] >= 8:
                notes.append("Soreness is high, so be careful with another hard day.")
            if latest["stress_1_10"] >= 8:
                notes.append("Stress is high, which can drag recovery down.")

            if not notes:
                notes.append("You’re looking pretty balanced right now. Keep stacking good days.")

            st.markdown("### Coaching Notes")
            for note in notes:
                st.write(f"- {note}")

            st.markdown("### Recent Trends")
            chart_data = {
                "Calories": [x["calories"] for x in recent],
                "Protein": [x["protein_g"] for x in recent],
                "Sleep": [x["sleep_hours"] for x in recent],
                "Steps": [x["steps"] for x in recent],
                "Weight": [x["weight_lb"] for x in recent],
            }
            st.line_chart(chart_data)

            st.markdown("### Recent Check-Ins")
            st.dataframe(recent, use_container_width=True)
        else:
            st.info("Add a daily check-in to unlock your recovery score and coaching notes.")

with tab2:
    st.subheader("Profile")
    profile = data.get("profile", {})

    with st.form("profile_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Name", value=profile.get("name", ""))
            age = st.number_input("Age", 12, 100, int(profile.get("age", 21) or 21))
            sex = st.selectbox(
                "Sex",
                ["male", "female", "other"],
                index=["male", "female", "other"].index(profile.get("sex", "male"))
                if profile.get("sex", "male") in ["male", "female", "other"] else 0,
            )
        with c2:
            height_in = st.number_input("Height (inches)", 36.0, 96.0, float(profile.get("height_in", 75.0) or 75.0))
            weight_lb = st.number_input("Weight (lb)", 70.0, 500.0, float(profile.get("weight_lb", 170.0) or 170.0))
            goal = st.selectbox(
                "Goal",
                ["cut", "maintain", "bulk", "recomp"],
                index=["cut", "maintain", "bulk", "recomp"].index(profile.get("goal", "maintain"))
                if profile.get("goal", "maintain") in ["cut", "maintain", "bulk", "recomp"] else 1,
            )
        with c3:
            activity = st.selectbox(
                "Activity level",
                ["sedentary", "light", "moderate", "active", "very active"],
                index=["sedentary", "light", "moderate", "active", "very active"].index(profile.get("activity_level", "moderate"))
                if profile.get("activity_level", "moderate") in ["sedentary", "light", "moderate", "active", "very active"] else 2,
            )

        submitted = st.form_submit_button("Save Profile")
        if submitted:
            data["profile"] = {
                "name": name,
                "age": int(age),
                "sex": sex,
                "height_in": float(height_in),
                "weight_lb": float(weight_lb),
                "goal": goal,
                "activity_level": activity,
            }
            save_user_data(username, data)
            st.success("Profile saved.")
            st.rerun()

    if data.get("profile"):
        targets = calorie_targets(data["profile"])
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("BMR", targets["bmr"])
        x2.metric("Maintenance Calories", targets["tdee"])
        x3.metric("Target Calories", targets["calories"])
        x4.metric("Protein Target (g)", targets["protein_g"])

with tab3:
    st.subheader("Daily Check-In")

    if not data.get("profile"):
        st.info("Set up your profile first.")
    else:
        with st.form("daily_log_form"):
            c1, c2, c3 = st.columns(3)

            with c1:
                entry_date = st.date_input("Date", value=date.today())
                calories = st.number_input("Calories eaten", 0, 10000, 2200)
                protein_g = st.number_input("Protein (g)", 0, 500, 160)
                weight_lb = st.number_input("Body weight (lb)", 50.0, 500.0, float(data["profile"].get("weight_lb", 170.0)))

            with c2:
                sleep_hours = st.number_input("Sleep hours", 0.0, 24.0, 7.5, step=0.5)
                soreness = st.slider("Soreness", 1, 10, 4)
                stress = st.slider("Stress", 1, 10, 4)
                steps = st.number_input("Steps", 0, 100000, 8000)

            with c3:
                workout_type = st.selectbox("Workout type", ["rest", "run", "lift", "hybrid", "sport", "cardio"])
                intensity = st.slider("Workout intensity", 1, 10, 6)
                notes = st.text_area("Notes", placeholder="Anything you want to remember...")

            submitted = st.form_submit_button("Save Check-In")

            if submitted:
                log = {
                    "date": str(entry_date),
                    "calories": int(calories),
                    "protein_g": int(protein_g),
                    "weight_lb": float(weight_lb),
                    "sleep_hours": float(sleep_hours),
                    "soreness_1_10": int(soreness),
                    "stress_1_10": int(stress),
                    "workout_type": workout_type,
                    "workout_intensity_1_10": int(intensity),
                    "steps": int(steps),
                    "notes": notes,
                    "updated_at": datetime.utcnow().isoformat(),
                }

                data["profile"]["weight_lb"] = float(weight_lb)

                logs = data["logs"]
                existing = next((i for i, x in enumerate(logs) if x["date"] == str(entry_date)), None)
                if existing is not None:
                    logs[existing] = log
                else:
                    logs.append(log)

                logs.sort(key=lambda x: x["date"])
                save_user_data(username, data)

                rec, title, detail = get_recommendation(log)
                st.success("Check-in saved.")
                z1, z2 = st.columns(2)
                z1.metric("Recovery Score", rec)
                z2.write(f"**{title}**")
                st.write(detail)
                st.write(build_today_plan(data["profile"], log))

with tab4:
    st.subheader("Coach Chat")

    if not openai_ready():
        st.warning("Chatbot is not active yet. Add OPENAI_API_KEY in Streamlit Secrets.")
        st.code(
            """OPENAI_API_KEY = "your-openai-api-key"
OPENAI_MODEL = "gpt-4.1-mini"
""",
            language="toml",
        )
    else:
        st.caption("Ask training, calories, recovery, soreness, running, lifting, or meal questions.")

        for msg in st.session_state["messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        prompt = st.chat_input("Ask your fitness coach anything...")

        if prompt:
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        answer = ask_fitness_chatbot(prompt, data.get("profile", {}), data.get("logs", []))
                    except Exception as e:
                        answer = f"Chatbot error: {e}"

                    st.markdown(answer)

            st.session_state["messages"].append({"role": "assistant", "content": answer})
