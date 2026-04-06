import json
from datetime import date
from pathlib import Path

import streamlit as st

DATA_FILE = Path("trainer_data.json")


def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except Exception:
            pass
    return {"profile": {}, "logs": []}


def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))


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
        return rec, "Rest / recovery day", "Your body looks pretty beat up today. Keep it light."
    elif rec < 60:
        return rec, "Train, but keep it controlled", "Good day for easier cardio, lighter lifting, or technique work."
    return rec, "Good to train hard", "You look solid today. Warm up well and go after it."


def avg(values):
    return round(sum(values) / len(values), 1) if values else 0


st.set_page_config(page_title="Fitness Assistant", page_icon="💪", layout="wide")

st.title("💪 Personal Fitness Assistant")
st.caption("Simple calorie tracking, recovery check, and training advice.")

data = load_data()

tab1, tab2, tab3 = st.tabs(["Profile", "Daily Check-In", "Dashboard"])

with tab1:
    st.subheader("Your Profile")
    profile = data.get("profile", {})

    with st.form("profile_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            name = st.text_input("Name", value=profile.get("name", ""))
            age = st.number_input("Age", 12, 100, int(profile.get("age", 21) or 21))
            sex = st.selectbox("Sex", ["male", "female", "other"], index=["male", "female", "other"].index(profile.get("sex", "male")) if profile.get("sex", "male") in ["male", "female", "other"] else 0)
        with col2:
            height_in = st.number_input("Height (inches)", 36.0, 96.0, float(profile.get("height_in", 75.0) or 75.0))
            weight_lb = st.number_input("Weight (lb)", 70.0, 500.0, float(profile.get("weight_lb", 170.0) or 170.0))
            goal = st.selectbox("Goal", ["cut", "maintain", "bulk", "recomp"], index=["cut", "maintain", "bulk", "recomp"].index(profile.get("goal", "maintain")) if profile.get("goal", "maintain") in ["cut", "maintain", "bulk", "recomp"] else 1)
        with col3:
            activity = st.selectbox("Activity level", ["sedentary", "light", "moderate", "active", "very active"], index=["sedentary", "light", "moderate", "active", "very active"].index(profile.get("activity_level", "moderate")) if profile.get("activity_level", "moderate") in ["sedentary", "light", "moderate", "active", "very active"] else 2)

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
            save_data(data)
            st.success("Profile saved.")

    if data.get("profile"):
        targets = calorie_targets(data["profile"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BMR", targets["bmr"])
        c2.metric("Maintenance Calories", targets["tdee"])
        c3.metric("Target Calories", targets["calories"])
        c4.metric("Protein Target (g)", targets["protein_g"])

with tab2:
    st.subheader("Daily Check-In")

    if not data.get("profile"):
        st.info("Set up your profile first.")
    else:
        with st.form("daily_log_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                entry_date = st.date_input("Date", value=date.today())
                calories = st.number_input("Calories eaten", 0, 10000, 2200)
                protein_g = st.number_input("Protein (g)", 0, 500, 160)
                weight_lb = st.number_input("Body weight (lb)", 50.0, 500.0, float(data["profile"].get("weight_lb", 170.0)))
            with col2:
                sleep_hours = st.number_input("Sleep hours", 0.0, 24.0, 7.5, step=0.5)
                soreness = st.slider("Soreness", 1, 10, 4)
                stress = st.slider("Stress", 1, 10, 4)
                steps = st.number_input("Steps", 0, 100000, 8000)
            with col3:
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
                }

                data["profile"]["weight_lb"] = float(weight_lb)

                logs = data["logs"]
                existing = next((i for i, x in enumerate(logs) if x["date"] == str(entry_date)), None)
                if existing is not None:
                    logs[existing] = log
                else:
                    logs.append(log)

                logs.sort(key=lambda x: x["date"])
                save_data(data)

                rec, title, detail = get_recommendation(log)
                st.success("Check-in saved.")
                st.metric("Recovery Score", rec)
                st.subheader(title)
                st.write(detail)

with tab3:
    st.subheader("Dashboard")

    if not data.get("profile") or not data.get("logs"):
        st.info("Add your profile and at least one daily check-in to see your dashboard.")
    else:
        profile = data["profile"]
        logs = sorted(data["logs"], key=lambda x: x["date"])
        latest = logs[-1]
        recent = logs[-7:]
        targets = calorie_targets(profile)
        rec, title, detail = get_recommendation(latest)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Recovery Score", rec)
        c2.metric("Target Calories", targets["calories"])
        c3.metric("Target Protein", targets["protein_g"])
        c4.metric("Latest Weight", f'{latest["weight_lb"]} lb')

        st.markdown(f"### Today: {title}")
        st.write(detail)

        notes = []
        if avg([x["calories"] for x in recent]) < targets["calories"] - 250:
            notes.append("You’ve been under your calorie target lately, which may hurt recovery or performance.")
        if avg([x["protein_g"] for x in recent]) < targets["protein_g"] - 15:
            notes.append("Protein has been low compared to your target.")
        if avg([x["sleep_hours"] for x in recent]) < 7:
            notes.append("Sleep looks like the biggest thing to improve right now.")
        if latest["soreness_1_10"] >= 8:
            notes.append("Soreness is high, so be careful with another hard day.")
        if latest["stress_1_10"] >= 8:
            notes.append("Stress is high, which can mess with recovery even if motivation is there.")

        if not notes:
            notes.append("You’re looking pretty balanced right now. Keep stacking good days.")

        st.markdown("### Coaching Notes")
        for n in notes:
            st.write(f"- {n}")

        st.markdown("### Recent Trends")
        st.line_chart(
            {
                "Calories": [x["calories"] for x in recent],
                "Protein": [x["protein_g"] for x in recent],
                "Sleep": [x["sleep_hours"] for x in recent],
                "Steps": [x["steps"] for x in recent],
            }
        )

        st.markdown("### Recent Check-Ins")
        st.dataframe(recent, use_container_width=True)
