from flask import Flask, render_template, request, redirect, session, flash, jsonify, Response
from functools import wraps
from questions import get_shuffled_questions, CATEGORIES, ALL_QUESTIONS
import sqlite3, hashlib, time, json, os, csv, io, datetime, requests as http_req

# ── AI module ────────────────────────────────────────────────────────
from ai import beebot_reply, generate_questions

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "beewise_secret_2025")  # ⚠️ Set SECRET_KEY env var in production!
app.config["PERMANENT_SESSION_LIFETIME"] = __import__("datetime").timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"]    = True
app.config["SESSION_COOKIE_SAMESITE"]   = "Lax"

QUIZ_LIMIT  = 25
RAPID_LIMIT = 25
RAPID_TIME  = 180
QUIZ_TIME   = 180
DB_PATH     = os.environ.get("DB_PATH", "beewise.db")
ADMIN_CODE   = os.environ.get("ADMIN_CODE",   "ADMIN2025")   # ⚠️ Set ADMIN_CODE env var in production!
TEACHER_CODE = os.environ.get("TEACHER_CODE", "TEACHER2025")

# ── Achievements definition ──────────────────────────────────────────
ACHIEVEMENTS = [
# ── EASY (play these naturally) ───────────────────────────────────────
{"id":"first_game",      "name":"First Buzz",        "desc":"Play your first game",                "icon":"🐣","secret":False},
{"id":"first_rapidbee",  "name":"Speed Taster",      "desc":"Play RapidBee for the first time",    "icon":"⚡","secret":False},
{"id":"first_practice",  "name":"Study Mode",        "desc":"Complete any practice session",        "icon":"📚","secret":False},
{"id":"grade_a",         "name":"A-Bee-C",           "desc":"Get Grade A (80%+) in any quiz",      "icon":"🌟","secret":False},
{"id":"grade_b",         "name":"Solid Bee",         "desc":"Get Grade B (60%+) in any quiz",      "icon":"👍","secret":False},
{"id":"games_5",         "name":"Frequent Flyer",    "desc":"Play 5 games total",                  "icon":"✈️","secret":False},
{"id":"games_10",        "name":"Hive Regular",      "desc":"Play 10 games total",                 "icon":"🏠","secret":False},
{"id":"games_20",        "name":"Getting Serious",   "desc":"Play 20 games total",                 "icon":"💼","secret":False},
{"id":"games_25",        "name":"Bee Veteran",       "desc":"Play 25 games total",                 "icon":"🎖️","secret":False},
{"id":"games_50",        "name":"Honey Grinder",     "desc":"Play 50 games total",                 "icon":"🍯","secret":False},
{"id":"games_100",       "name":"Century Club",      "desc":"Play 100 games total",                "icon":"💯","secret":False},
{"id":"streak_2",        "name":"Back to Back",      "desc":"Play 2 days in a row",                "icon":"📅","secret":False},
{"id":"streak_3",        "name":"3-Day Streak",      "desc":"Play 3 days in a row",                "icon":"🔥","secret":False},
{"id":"streak_5",        "name":"5-Day Streak",      "desc":"Play 5 days in a row",                "icon":"🌶️","secret":False},
{"id":"streak_7",        "name":"Week Warrior",      "desc":"Play 7 days in a row",                "icon":"🗓️","secret":False},
{"id":"streak_14",       "name":"Two Week Terror",   "desc":"Play 14 days in a row",               "icon":"🏆","secret":False},
{"id":"streak_30",       "name":"Monthly Master",    "desc":"Play 30 days in a row",               "icon":"👑","secret":False},
{"id":"pct_50",          "name":"Half Way Bee",      "desc":"Score 50% or above in any quiz",      "icon":"🎯","secret":False},
{"id":"pct_60",          "name":"Above Average",     "desc":"Score 60% or above in any quiz",      "icon":"📈","secret":False},
{"id":"pct_70",          "name":"Good Bee",          "desc":"Score 70% or above in any quiz",      "icon":"😊","secret":False},
{"id":"pct_80",          "name":"High Achiever",     "desc":"Score 80% or above in any quiz",      "icon":"🌟","secret":False},
{"id":"pct_90",          "name":"Almost Perfect",    "desc":"Score 90% or above in any quiz",      "icon":"🔑","secret":False},
{"id":"perfect_score",   "name":"Perfect Hive",      "desc":"Score 100% in any quiz",              "icon":"💎","secret":False},
{"id":"practice_html",   "name":"HTML Hero",         "desc":"Complete HTML practice mode",          "icon":"🌐","secret":False},
{"id":"practice_css",    "name":"Style Queen",       "desc":"Complete CSS practice mode",           "icon":"🎨","secret":False},
{"id":"practice_python", "name":"Python Pro",        "desc":"Complete Python practice mode",        "icon":"🐍","secret":False},
{"id":"practice_sql",    "name":"SQL Star",          "desc":"Complete SQL practice mode",           "icon":"🗄️","secret":False},
{"id":"practice_flask",  "name":"Flask Fanatic",     "desc":"Complete Flask practice mode",         "icon":"🧪","secret":False},
{"id":"practice_general","name":"General Genius",    "desc":"Complete General practice mode",       "icon":"🧠","secret":False},
{"id":"all_cats",        "name":"Jack of All Bees",  "desc":"Practice all 6 categories",           "icon":"🦄","secret":False},
{"id":"no_wrong",        "name":"Flawless",          "desc":"Get 0 wrong answers in a quiz",       "icon":"🛡️","secret":False},
{"id":"quiz_morning",    "name":"Early Bee",         "desc":"Play a quiz before 9 AM",             "icon":"🌅","secret":False},
{"id":"quiz_night",      "name":"Night Owl Bee",     "desc":"Play a quiz after 10 PM",             "icon":"🦉","secret":False},
{"id":"cert_earned",     "name":"Certified Bee",     "desc":"Earn your first certificate",         "icon":"📜","secret":False},

# ── MEDIUM ────────────────────────────────────────────────────────────
{"id":"games_75",        "name":"Dedicated Bee",     "desc":"Play 75 games total",                 "icon":"🏅","secret":False},
{"id":"perfect_twice",   "name":"Double Perfect",    "desc":"Score 100% twice",                    "icon":"💫","secret":False},
{"id":"perfect_5",       "name":"Perfection Machine","desc":"Score 100% five times",               "icon":"🤖","secret":False},
{"id":"grade_a_5",       "name":"Consistent Bee",    "desc":"Get Grade A five times",              "icon":"🌠","secret":False},
{"id":"grade_a_10",      "name":"A-Lister",          "desc":"Get Grade A ten times",               "icon":"👸","secret":False},
{"id":"grade_a_25",      "name":"A+ Legend",         "desc":"Get Grade A twenty-five times",       "icon":"🏆","secret":False},
{"id":"speed_demon",     "name":"Speed Demon",       "desc":"Finish a quiz in under 60 seconds",   "icon":"⚡","secret":False},
{"id":"speed_30",        "name":"Lightning Bee",     "desc":"Finish RapidBee in under 30 seconds", "icon":"🌩️","secret":False},
{"id":"no_wrong_3",      "name":"Triple Flawless",   "desc":"Get 0 wrong 3 times",                 "icon":"🛡️","secret":False},
{"id":"no_wrong_10",     "name":"Untouchable",       "desc":"Get 0 wrong 10 times",                "icon":"🦸","secret":False},
{"id":"rapid_5",         "name":"Rapid Bee",         "desc":"Play RapidBee 5 times",               "icon":"🐝","secret":False},
{"id":"rapid_20",        "name":"Rapid Expert",      "desc":"Play RapidBee 20 times",              "icon":"💨","secret":False},
{"id":"practice_master", "name":"Practice Makes Perfect","desc":"Complete 10 practice sessions",   "icon":"📝","secret":False},
{"id":"html_perfect",    "name":"HTML Perfection",   "desc":"Score 100% in HTML practice",         "icon":"🌐","secret":False},
{"id":"python_perfect",  "name":"Python Perfection", "desc":"Score 100% in Python practice",       "icon":"🐍","secret":False},
{"id":"sql_perfect",     "name":"SQL Perfection",    "desc":"Score 100% in SQL practice",          "icon":"🗄️","secret":False},
{"id":"css_perfect",     "name":"CSS Perfection",    "desc":"Score 100% in CSS practice",          "icon":"🎨","secret":False},
{"id":"flask_perfect",   "name":"Flask Perfection",  "desc":"Score 100% in Flask practice",        "icon":"🧪","secret":False},
{"id":"comeback",        "name":"Comeback King",     "desc":"Score 80%+ after previously scoring below 40%","icon":"💪","secret":False},
{"id":"improvement",     "name":"Level Up",          "desc":"Beat your previous best score",       "icon":"📊","secret":False},
{"id":"cert_3",          "name":"Certificate Bee",   "desc":"Earn 3 certificates",                 "icon":"📜","secret":False},
{"id":"leaderboard_top3","name":"Podium Bee",        "desc":"Reach top 3 on the leaderboard",      "icon":"🥉","secret":False},
{"id":"leaderboard_top1","name":"Number One Bee",    "desc":"Reach #1 on the leaderboard",         "icon":"🥇","secret":False},
{"id":"q_correct_50",    "name":"50 Right",          "desc":"Answer 50 questions correctly total", "icon":"✅","secret":False},
{"id":"q_correct_100",   "name":"Century of Correct","desc":"Answer 100 questions correctly",      "icon":"💯","secret":False},
{"id":"q_correct_250",   "name":"Quarter Thousand",  "desc":"Answer 250 questions correctly",      "icon":"🎖️","secret":False},
{"id":"q_correct_500",   "name":"500 Club",          "desc":"Answer 500 questions correctly",      "icon":"🌟","secret":False},
{"id":"html_expert",     "name":"HTML Expert",       "desc":"Average 80%+ in HTML over 5 games",  "icon":"💻","secret":False},
{"id":"python_expert",   "name":"Python Expert",     "desc":"Average 80%+ in Python over 5 games","icon":"🐍","secret":False},
{"id":"sql_expert",      "name":"SQL Expert",        "desc":"Average 80%+ in SQL over 5 games",   "icon":"🗃️","secret":False},
{"id":"weekend_bee",     "name":"Weekend Warrior",   "desc":"Play on both Saturday and Sunday",    "icon":"📆","secret":False},
{"id":"ten_in_row_correct","name":"Hot Streak",      "desc":"Answer 10 questions correctly in a row","icon":"🔥","secret":False},

# ── HARD ─────────────────────────────────────────────────────────────
{"id":"games_200",       "name":"Bee Obsessed",      "desc":"Play 200 games total",                "icon":"🐝","secret":False},
{"id":"games_500",       "name":"Hive Mind",         "desc":"Play 500 games total",                "icon":"🧠","secret":False},
{"id":"perfect_10",      "name":"Perfect Ten",       "desc":"Score 100% ten times",                "icon":"🔟","secret":False},
{"id":"perfect_20",      "name":"Perfect Score God", "desc":"Score 100% twenty times",             "icon":"👼","secret":False},
{"id":"grade_a_50",      "name":"Grade A Machine",   "desc":"Get Grade A fifty times",             "icon":"⚙️","secret":False},
{"id":"streak_60",       "name":"Two Month Beast",   "desc":"Play 60 days in a row",               "icon":"🦁","secret":False},
{"id":"streak_100",      "name":"100 Day Legend",    "desc":"Play 100 days in a row",              "icon":"💎","secret":False},
{"id":"all_perfect",     "name":"Category God",      "desc":"Score 100% in all 6 categories",      "icon":"🌈","secret":False},
{"id":"no_wrong_25",     "name":"Perfect Machine",   "desc":"Get 0 wrong 25 times",                "icon":"🤖","secret":False},
{"id":"speed_15",        "name":"Supersonic Bee",    "desc":"Finish RapidBee in under 15 seconds", "icon":"🚀","secret":False},
{"id":"q_correct_1000",  "name":"Thousand Club",     "desc":"Answer 1000 questions correctly",     "icon":"🏰","secret":False},
{"id":"q_correct_2500",  "name":"Question Master",   "desc":"Answer 2500 questions correctly",     "icon":"👑","secret":False},
{"id":"cert_10",         "name":"Certificate King",  "desc":"Earn 10 certificates",                "icon":"🏅","secret":False},
{"id":"rapid_50",        "name":"RapidBee Master",   "desc":"Play RapidBee 50 times",              "icon":"⚡","secret":False},
{"id":"rapid_100",       "name":"Speed Legend",      "desc":"Play RapidBee 100 times",             "icon":"🌩️","secret":False},
{"id":"all_expert",      "name":"Ultimate Expert",   "desc":"Average 80%+ across all 6 categories","icon":"🎓","secret":False},

# ── SECRET ────────────────────────────────────────────────────────────
{"id":"secret_midnight", "name":"Midnight Bee",      "desc":"Play between 12 AM and 3 AM",         "icon":"🌙","secret":True},
{"id":"secret_1am",      "name":"Insomniac",         "desc":"Play at exactly 1 AM",                "icon":"😴","secret":True},
{"id":"secret_score42",  "name":"42",                "desc":"Score exactly 42% in a quiz",         "icon":"🌌","secret":True},
{"id":"secret_score69",  "name":"Nice",              "desc":"Score exactly 69% in a quiz",         "icon":"😏","secret":True},
{"id":"secret_all_wrong","name":"Trying to Fail",    "desc":"Score 0% in a quiz (really?)",        "icon":"🤡","secret":True},
{"id":"secret_same_score","name":"Consistent Mess",  "desc":"Get the exact same score 3 times",    "icon":"🔄","secret":True},
{"id":"secret_rapid_all","name":"Bee Unstoppable",   "desc":"Play all 3 modes in the same day",    "icon":"🌀","secret":True},
{"id":"secret_comeback2","name":"Phoenix Bee",       "desc":"Go from 0% to 100% in consecutive games","icon":"🔥","secret":True},
{"id":"secret_no_time",  "name":"Procrastinator",    "desc":"Let the quiz timer expire",            "icon":"⌛","secret":True},
{"id":"secret_top_all",  "name":"Absolute Legend",   "desc":"Be #1 on both leaderboard tabs",      "icon":"🦋","secret":True},

# ── MORE EASY ─────────────────────────────────────────────────────────────────
{"id":"first_login",       "name":"Welcome Bee",       "desc":"Log in for the first time",                   "icon":"👋","secret":False},
{"id":"choose_avatar",     "name":"Style Check",       "desc":"Change your avatar",                          "icon":"🐾","secret":False},
{"id":"first_cert",        "name":"Certified!",        "desc":"Download your first certificate",             "icon":"📜","secret":False},
{"id":"play_morning",      "name":"Morning Buzz",      "desc":"Play a quiz before 9 AM",                     "icon":"🌅","secret":False},
{"id":"play_evening",      "name":"Evening Bee",       "desc":"Play a quiz between 5 PM and 8 PM",           "icon":"🌇","secret":False},
{"id":"join_class",        "name":"Class Bee",         "desc":"Join a class with a code",                    "icon":"🏫","secret":False},
{"id":"first_room",        "name":"Room Service",      "desc":"Complete a Quiz Room",                        "icon":"🎮","secret":False},
{"id":"try_customizebee",  "name":"Curious Bee",       "desc":"Try CustomizeBee mode",                       "icon":"🎨","secret":False},
{"id":"first_csv_upload",  "name":"CSV Master",        "desc":"Upload your own CSV quiz",                    "icon":"📄","secret":False},
{"id":"ask_beebot",        "name":"Smart Bee",         "desc":"Ask BeeBot a question",                       "icon":"🤖","secret":False},
{"id":"score_60_first",    "name":"First 60",          "desc":"Score 60% or above for the first time",       "icon":"🎯","secret":False},
{"id":"score_70_first",    "name":"First 70",          "desc":"Score 70% or above for the first time",       "icon":"🎯","secret":False},
{"id":"complete_profile",  "name":"Profile Done",      "desc":"Add an avatar and play 5 games",              "icon":"👤","secret":False},
{"id":"play_friday",       "name":"TGIF Bee",          "desc":"Play on a Friday",                            "icon":"🎉","secret":False},
{"id":"play_sunday",       "name":"Sunday Buzz",       "desc":"Play on a Sunday",                            "icon":"☀️","secret":False},
{"id":"rapid_first_win",   "name":"Speed Win",         "desc":"Score 80%+ in RapidBee for the first time",   "icon":"⚡","secret":False},
{"id":"practice_score80",  "name":"Practice Perfect",  "desc":"Score 80%+ in any practice session",          "icon":"📚","secret":False},
{"id":"q_correct_10",      "name":"Ten Right",         "desc":"Answer 10 questions correctly total",         "icon":"✅","secret":False},
{"id":"q_correct_25",      "name":"Quarter Century",   "desc":"Answer 25 questions correctly total",         "icon":"🎯","secret":False},
{"id":"games_3",           "name":"Trio",              "desc":"Play 3 games total",                          "icon":"3️⃣","secret":False},
{"id":"play_3_modes",      "name":"Mode Explorer",     "desc":"Try BeeWise.quiz, RapidBee, and Practice",         "icon":"🗺️","secret":False},

# ── MORE MEDIUM ───────────────────────────────────────────────────────────────
{"id":"rapid_10_avg70",    "name":"Speed Consistent",  "desc":"Average 70%+ over 10 RapidBee games",         "icon":"📈","secret":False},
{"id":"perfect_rapid",     "name":"Rapid Perfection",  "desc":"Score 100% in RapidBee",                      "icon":"⚡","secret":False},
{"id":"zero_wrong_rapid",  "name":"Rapid Flawless",    "desc":"Get 0 wrong in RapidBee",                     "icon":"🛡️","secret":False},
{"id":"room_top",          "name":"Room Leader",       "desc":"Finish #1 in a Quiz Room",                    "icon":"🏆","secret":False},
{"id":"room_5",            "name":"Room Regular",      "desc":"Complete 5 Quiz Rooms",                       "icon":"🎮","secret":False},
{"id":"csv_upload_5",      "name":"CSV Pro",           "desc":"Upload 5 different CSV quizzes",              "icon":"📊","secret":False},
{"id":"streak_10",         "name":"Ten Day Streak",    "desc":"Play 10 days in a row",                       "icon":"🔥","secret":False},
{"id":"streak_21",         "name":"Three Week Bee",    "desc":"Play 21 days in a row",                       "icon":"🌙","secret":False},
{"id":"games_40",          "name":"Forty Games",       "desc":"Play 40 games total",                         "icon":"4️⃣","secret":False},
{"id":"games_60",          "name":"Sixty Club",        "desc":"Play 60 games total",                         "icon":"6️⃣","secret":False},
{"id":"html_5_80",         "name":"HTML Regular",      "desc":"Score 80%+ in HTML practice 5 times",         "icon":"🌐","secret":False},
{"id":"python_5_80",       "name":"Python Regular",    "desc":"Score 80%+ in Python practice 5 times",       "icon":"🐍","secret":False},
{"id":"sql_5_80",          "name":"SQL Regular",       "desc":"Score 80%+ in SQL practice 5 times",          "icon":"🗄️","secret":False},
{"id":"css_5_80",          "name":"CSS Regular",       "desc":"Score 80%+ in CSS practice 5 times",          "icon":"🎨","secret":False},
{"id":"flask_5_80",        "name":"Flask Regular",     "desc":"Score 80%+ in Flask practice 5 times",        "icon":"🧪","secret":False},
{"id":"cert_5",            "name":"Five Certs",        "desc":"Earn 5 certificates",                         "icon":"📜","secret":False},
{"id":"cert_7",            "name":"Lucky Seven",       "desc":"Earn 7 certificates",                         "icon":"🍀","secret":False},
{"id":"q_correct_200",     "name":"200 Right",         "desc":"Answer 200 questions correctly",              "icon":"💯","secret":False},
{"id":"q_correct_750",     "name":"750 Club",          "desc":"Answer 750 questions correctly",              "icon":"🏅","secret":False},
{"id":"perfect_3",         "name":"Triple Perfect",    "desc":"Score 100% three times",                      "icon":"💎","secret":False},
{"id":"perfect_7",         "name":"Lucky Perfect",     "desc":"Score 100% seven times",                      "icon":"🍀","secret":False},
{"id":"grade_a_3",         "name":"A Student",         "desc":"Get Grade A three times",                     "icon":"📝","secret":False},
{"id":"no_wrong_2",        "name":"Double Flawless",   "desc":"Get 0 wrong twice",                           "icon":"🛡️","secret":False},
{"id":"no_wrong_5",        "name":"Five Flawless",     "desc":"Get 0 wrong five times",                      "icon":"⚔️","secret":False},
{"id":"speed_45",          "name":"Fast Bee",          "desc":"Finish RapidBee in under 45 seconds",         "icon":"🏃","secret":False},
{"id":"play_4_modes",      "name":"All Modes",         "desc":"Play all 4 modes (BeeWise, Rapid, Practice, Custom)", "icon":"🌈","secret":False},
{"id":"class_active",      "name":"Active Student",    "desc":"Play 10 games while in a class",              "icon":"📚","secret":False},
{"id":"room_perfect",      "name":"Room Perfect",      "desc":"Score 100% in a Quiz Room",                   "icon":"🎮","secret":False},
{"id":"beebot_10",         "name":"BeeBot Fan",        "desc":"Ask BeeBot 10 questions",                     "icon":"🤖","secret":False},
{"id":"weekend_5",         "name":"Weekend Warrior+",  "desc":"Play on 5 weekends",                          "icon":"🏖️","secret":False},
{"id":"month_player",      "name":"Month Player",      "desc":"Play in 4 different weeks",                   "icon":"📆","secret":False},

# ── MORE HARD ─────────────────────────────────────────────────────────────────
{"id":"games_150",         "name":"150 Strong",        "desc":"Play 150 games total",                        "icon":"💪","secret":False},
{"id":"games_300",         "name":"300 Games",         "desc":"Play 300 games total",                        "icon":"🔱","secret":False},
{"id":"games_400",         "name":"400 Legend",        "desc":"Play 400 games total",                        "icon":"👑","secret":False},
{"id":"streak_45",         "name":"45 Day Grind",      "desc":"Play 45 days in a row",                       "icon":"🔥","secret":False},
{"id":"streak_90",         "name":"Quarter Year",      "desc":"Play 90 days in a row",                       "icon":"📅","secret":False},
{"id":"perfect_15",        "name":"15 Perfects",       "desc":"Score 100% fifteen times",                    "icon":"💫","secret":False},
{"id":"grade_a_30",        "name":"Grade A Pro",       "desc":"Get Grade A 30 times",                        "icon":"🌟","secret":False},
{"id":"grade_a_75",        "name":"A+ Forever",        "desc":"Get Grade A 75 times",                        "icon":"🏆","secret":False},
{"id":"q_correct_1500",    "name":"1500 Right",        "desc":"Answer 1500 questions correctly",             "icon":"🎖️","secret":False},
{"id":"q_correct_3000",    "name":"3000 Club",         "desc":"Answer 3000 questions correctly",             "icon":"🌠","secret":False},
{"id":"q_correct_5000",    "name":"5000 Master",       "desc":"Answer 5000 questions correctly",             "icon":"👑","secret":False},
{"id":"all_cats_10",       "name":"Category King",     "desc":"Score 80%+ in all 6 categories 10 times each","icon":"🦁","secret":False},
{"id":"room_10",           "name":"Room Veteran",      "desc":"Complete 10 Quiz Rooms",                      "icon":"🎮","secret":False},
{"id":"room_top5",         "name":"Room Elite",        "desc":"Finish top 3 in 5 different rooms",           "icon":"🥇","secret":False},
{"id":"rapid_centurion",         "name":"RapidBee Centurion","desc":"Play RapidBee 100 times",                     "icon":"⚡","secret":False},
{"id":"rapid_perfect_5",   "name":"Speed Perfectionist","desc":"Score 100% in RapidBee 5 times",             "icon":"🌩️","secret":False},
{"id":"no_wrong_15",       "name":"Untouchable+",      "desc":"Get 0 wrong 15 times",                        "icon":"🦸","secret":False},
{"id":"no_wrong_20",       "name":"Perfect Machine+",  "desc":"Get 0 wrong 20 times",                        "icon":"🤖","secret":False},
{"id":"cert_15",           "name":"15 Certs",          "desc":"Earn 15 certificates",                        "icon":"🏅","secret":False},
{"id":"cert_20",           "name":"20 Certs",          "desc":"Earn 20 certificates",                        "icon":"👑","secret":False},
{"id":"speed_10",          "name":"Lightning++",       "desc":"Finish RapidBee in under 10 seconds",         "icon":"⚡","secret":False},
{"id":"all_secret",        "name":"Secret Hunter",     "desc":"Unlock all 10 secret achievements",           "icon":"🕵️","secret":False},
{"id":"leaderboard_week",  "name":"Week Champion",     "desc":"Hold #1 spot for a full week",                "icon":"👑","secret":False},
{"id":"play_1000",         "name":"One Thousand",      "desc":"Play 1000 games total",                       "icon":"🌌","secret":False},

# ── MORE SECRET ────────────────────────────────────────────────────────────────
{"id":"secret_3am",        "name":"Night Owl+",        "desc":"Play at exactly 3 AM",                        "icon":"🦉","secret":True},
{"id":"secret_score100_rapid","name":"Flash",          "desc":"Score 100% in RapidBee under 20 seconds",     "icon":"⚡","secret":True},
{"id":"secret_5room_1day", "name":"Room Addict",       "desc":"Complete 5 Quiz Rooms in one day",            "icon":"🎮","secret":True},
{"id":"secret_new_year",   "name":"New Year Bee",      "desc":"Play on January 1st",                         "icon":"🎆","secret":True},
{"id":"secret_birthday",   "name":"Birthday Bee",      "desc":"Play on a special date (Apr 21)",             "icon":"🎂","secret":True},
{"id":"secret_lose_win",   "name":"Redemption Arc",    "desc":"Score 0% then immediately score 100%",        "icon":"🦋","secret":True},
{"id":"secret_exact_50",   "name":"Fifty Fifty",       "desc":"Score exactly 50% three times",               "icon":"⚖️","secret":True},
{"id":"secret_speed_5",    "name":"Blink",             "desc":"Answer 5 questions in a row under 5s each",   "icon":"👁️","secret":True},
{"id":"secret_all_4modes", "name":"Quad Master",       "desc":"Score 80%+ in all 4 modes in one day",        "icon":"🌀","secret":True},
{"id":"secret_7777",       "name":"Lucky Number",      "desc":"Play your 77th game on a Monday",             "icon":"🎰","secret":True},
{"id":"secret_play_rain",  "name":"Rainy Day Bee",     "desc":"Play 10 games in a single session",           "icon":"🌧️","secret":True},
{"id":"secret_share",      "name":"Influencer Bee",    "desc":"Join and complete a Quiz Room twice",         "icon":"📢","secret":True},
{"id":"secret_comeback3",  "name":"Three Peat Comeback","desc":"Come back from below 40% to 80%+ three times","icon":"🔥","secret":True},
{"id":"secret_2hr_session","name":"Marathon Bee",      "desc":"Play for over 2 hours in one day",            "icon":"🏃","secret":True},
{"id":"secret_exact_88",   "name":"88 Keys",           "desc":"Score exactly 88% in a quiz",                 "icon":"🎹","secret":True},

# ── MILESTONE EASY ────────────────────────────────────────────────────────────
{"id":"games_7",           "name":"Lucky Seven",       "desc":"Play 7 games",                                "icon":"7️⃣","secret":False},
{"id":"games_15",          "name":"Fifteen",           "desc":"Play 15 games",                               "icon":"🎯","secret":False},
{"id":"games_30",          "name":"Thirty",            "desc":"Play 30 games",                               "icon":"3️⃣","secret":False},
{"id":"first_rapidbee_win","name":"Quick Win",         "desc":"Score above 50% in first RapidBee",           "icon":"⚡","secret":False},
{"id":"pct_40",            "name":"Getting There",     "desc":"Score 40% or above in any quiz",              "icon":"📈","secret":False},
{"id":"answer_5_row",      "name":"On a Roll",         "desc":"Answer 5 questions correctly in a row",       "icon":"🎯","secret":False},
{"id":"play_2_days",       "name":"Two Day Player",    "desc":"Play on 2 different calendar days",           "icon":"📅","secret":False},
{"id":"complete_rapid_10", "name":"10 Rapids",         "desc":"Complete 10 RapidBee sessions",               "icon":"⚡","secret":False},
{"id":"class_joined_play", "name":"Class Player",      "desc":"Play a quiz after joining a class",           "icon":"🏫","secret":False},
{"id":"beebot_first_reply","name":"AI Chat",           "desc":"Receive your first BeeBot reply",             "icon":"💬","secret":False},
{"id":"play_quiz_night",   "name":"Quiz Night",        "desc":"Play a quiz between 7 PM and 10 PM",          "icon":"🌙","secret":False},
{"id":"score_exactly_80",  "name":"Just Right",        "desc":"Score exactly 80% in a quiz",                 "icon":"🎯","secret":False},
{"id":"first_practice_win","name":"Practice Win",      "desc":"Score above 70% in first practice session",   "icon":"📚","secret":False},
{"id":"play_5_different",  "name":"Variety Pack",      "desc":"Play 5 games of different modes",             "icon":"🌈","secret":False},
{"id":"games_8",           "name":"Octave",            "desc":"Play 8 games",                                "icon":"🎵","secret":False},

# ── CATEGORY MILESTONE MEDIUM ──────────────────────────────────────────────────
{"id":"html_10",           "name":"HTML Veteran",      "desc":"Complete HTML practice 10 times",             "icon":"🌐","secret":False},
{"id":"css_10",            "name":"CSS Veteran",       "desc":"Complete CSS practice 10 times",              "icon":"🎨","secret":False},
{"id":"python_10",         "name":"Python Veteran",    "desc":"Complete Python practice 10 times",           "icon":"🐍","secret":False},
{"id":"sql_10",            "name":"SQL Veteran",       "desc":"Complete SQL practice 10 times",              "icon":"🗄️","secret":False},
{"id":"flask_10",          "name":"Flask Veteran",     "desc":"Complete Flask practice 10 times",            "icon":"🧪","secret":False},
{"id":"general_10",        "name":"General Veteran",   "desc":"Complete General practice 10 times",          "icon":"🧠","secret":False},
{"id":"html_master",       "name":"HTML Master",       "desc":"Average 90%+ in HTML across 5 sessions",      "icon":"🌐","secret":False},
{"id":"python_master",     "name":"Python Master",     "desc":"Average 90%+ in Python across 5 sessions",    "icon":"🐍","secret":False},
{"id":"sql_master",        "name":"SQL Master",        "desc":"Average 90%+ in SQL across 5 sessions",       "icon":"🗄️","secret":False},
{"id":"css_master",        "name":"CSS Master",        "desc":"Average 90%+ in CSS across 5 sessions",       "icon":"🎨","secret":False},
{"id":"flask_master",      "name":"Flask Master",      "desc":"Average 90%+ in Flask across 5 sessions",     "icon":"🧪","secret":False},
{"id":"all_cats_5",        "name":"All Rounder",       "desc":"Score 80%+ in all 6 categories 5 times",      "icon":"🌟","secret":False},
{"id":"rapid_avg80",       "name":"Rapid Average",     "desc":"Maintain 80%+ average in RapidBee over 5 games","icon":"⚡","secret":False},
{"id":"quiz_avg80",        "name":"Quiz Average",      "desc":"Maintain 80%+ average in BeeWise over 5 games","icon":"📝","secret":False},
{"id":"practice_25",       "name":"Practice Grinder",  "desc":"Complete 25 practice sessions",               "icon":"📚","secret":False},
{"id":"practice_50",       "name":"Practice Veteran",  "desc":"Complete 50 practice sessions",               "icon":"📖","secret":False},

# ── SCORE MILESTONES ──────────────────────────────────────────────────────────
{"id":"score_5_perfect_diff","name":"Perfect Variety", "desc":"Score 100% in 5 different categories",        "icon":"🌈","secret":False},
{"id":"no_wrong_4",        "name":"Four Flawless",     "desc":"Get 0 wrong 4 times",                         "icon":"🛡️","secret":False},
{"id":"no_wrong_7",        "name":"Seven Flawless",    "desc":"Get 0 wrong 7 times",                         "icon":"🗡️","secret":False},
{"id":"q_correct_150",     "name":"150 Right",         "desc":"Answer 150 questions correctly",              "icon":"✅","secret":False},
{"id":"q_correct_400",     "name":"400 Right",         "desc":"Answer 400 questions correctly",              "icon":"🎖️","secret":False},
{"id":"q_correct_750b",    "name":"750 Right",         "desc":"Answer 750 questions correctly",              "icon":"🏅","secret":False},
{"id":"perfect_4",         "name":"Quad Perfect",      "desc":"Score 100% four times",                       "icon":"💎","secret":False},
{"id":"grade_a_15",        "name":"Grade A Achiever",  "desc":"Get Grade A 15 times",                        "icon":"📝","secret":False},
{"id":"grade_a_20",        "name":"Grade A Expert",    "desc":"Get Grade A 20 times",                        "icon":"📋","secret":False},

# ── TIME MILESTONES HARD ──────────────────────────────────────────────────────
{"id":"streak_45b",        "name":"45 Warrior",        "desc":"Play 45 consecutive days",                    "icon":"🌶️","secret":False},
{"id":"games_250",         "name":"Quarter K",         "desc":"Play 250 games total",                        "icon":"🏰","secret":False},
{"id":"games_350",         "name":"350 Club",          "desc":"Play 350 games total",                        "icon":"🎖️","secret":False},
{"id":"rapid_75",          "name":"75 Rapids",         "desc":"Play RapidBee 75 times",                      "icon":"⚡","secret":False},
{"id":"rapid_150",         "name":"RapidBee Veteran",  "desc":"Play RapidBee 150 times",                     "icon":"🌩️","secret":False},
{"id":"cert_25",           "name":"25 Certs",          "desc":"Earn 25 certificates",                        "icon":"📜","secret":False},
{"id":"room_25",           "name":"Room Master",       "desc":"Complete 25 Quiz Rooms",                      "icon":"🎮","secret":False},
{"id":"grade_a_100",       "name":"A+ Century",        "desc":"Get Grade A 100 times",                       "icon":"💯","secret":False},
{"id":"q_correct_2000",    "name":"2000 Right",        "desc":"Answer 2000 questions correctly",             "icon":"🌟","secret":False},
{"id":"q_correct_4000",    "name":"4000 Right",        "desc":"Answer 4000 questions correctly",             "icon":"👑","secret":False},

# ── MORE SECRET ────────────────────────────────────────────────────────────────
{"id":"secret_feb29",      "name":"Leap Year Bee",     "desc":"Play on Feb 29th",                            "icon":"🐸","secret":True},
{"id":"secret_score_13",   "name":"Unlucky 13",        "desc":"Score exactly 13% in a quiz",                 "icon":"🎃","secret":True},
{"id":"secret_rapid_1",    "name":"One and Done",      "desc":"Play exactly 1 RapidBee and stop",            "icon":"🚪","secret":True},
{"id":"secret_name_change","name":"New Identity",      "desc":"Change your username",                        "icon":"🎭","secret":True},
{"id":"secret_zero_twice",  "name":"Champion Loser",    "desc":"Get 0% in a quiz twice",                      "icon":"🤡","secret":True},

# ── FINAL BATCH TO 260 ────────────────────────────────────────────────────────
{"id":"games_45",          "name":"45 Done",           "desc":"Play 45 games total",                         "icon":"🎯","secret":False},
{"id":"games_80",          "name":"Eighty",            "desc":"Play 80 games total",                         "icon":"8️⃣","secret":False},
{"id":"games_90",          "name":"Ninety",             "desc":"Play 90 games total",                         "icon":"9️⃣","secret":False},
{"id":"games_120",         "name":"Dozen Tens",        "desc":"Play 120 games total",                        "icon":"🔢","secret":False},
{"id":"streak_4",          "name":"4 Day Streak",      "desc":"Play 4 days in a row",                        "icon":"🔥","secret":False},
{"id":"streak_6",          "name":"6 Day Streak",      "desc":"Play 6 days in a row",                        "icon":"🔥","secret":False},
{"id":"streak_10b",        "name":"10 Day Streak",     "desc":"Play 10 days in a row",                       "icon":"🔥","secret":False},
{"id":"streak_20",         "name":"20 Day Streak",     "desc":"Play 20 days in a row",                       "icon":"🔥","secret":False},
{"id":"streak_25",         "name":"25 Day Streak",     "desc":"Play 25 days in a row",                       "icon":"🌶️","secret":False},
{"id":"pct_55",            "name":"55%",               "desc":"Score 55% or above",                          "icon":"📊","secret":False},
{"id":"pct_65",            "name":"65%",               "desc":"Score 65% or above",                          "icon":"📊","secret":False},
{"id":"pct_75",            "name":"75%",               "desc":"Score 75% or above",                          "icon":"📊","secret":False},
{"id":"pct_85",            "name":"85%",               "desc":"Score 85% or above",                          "icon":"📊","secret":False},
{"id":"pct_95",            "name":"95%",               "desc":"Score 95% or above",                          "icon":"🌟","secret":False},
{"id":"q_correct_75",      "name":"75 Right",          "desc":"Answer 75 questions correctly",               "icon":"✅","secret":False},
{"id":"q_correct_300",     "name":"300 Right",         "desc":"Answer 300 questions correctly",              "icon":"🎖️","secret":False},
{"id":"rapid_30",          "name":"30 Rapids",         "desc":"Play RapidBee 30 times",                      "icon":"⚡","secret":False},
{"id":"rapid_40",          "name":"40 Rapids",         "desc":"Play RapidBee 40 times",                      "icon":"⚡","secret":False},
{"id":"rapid_60",          "name":"60 Rapids",         "desc":"Play RapidBee 60 times",                      "icon":"⚡","secret":False},
{"id":"grade_a_7",         "name":"Grade A Regular",   "desc":"Get Grade A 7 times",                         "icon":"🌟","secret":False},
{"id":"perfect_6",         "name":"Six Perfect",       "desc":"Score 100% six times",                        "icon":"💎","secret":False},
{"id":"perfect_8",         "name":"Eight Perfect",     "desc":"Score 100% eight times",                      "icon":"🎱","secret":False},
{"id":"room_3",            "name":"Room Starter",      "desc":"Complete 3 Quiz Rooms",                       "icon":"🎮","secret":False},
{"id":"room_15",           "name":"Room Pro",          "desc":"Complete 15 Quiz Rooms",                      "icon":"🎮","secret":False},
{"id":"cert_2",            "name":"Two Certs",         "desc":"Earn 2 certificates",                         "icon":"📜","secret":False},
{"id":"cert_4",            "name":"Four Certs",        "desc":"Earn 4 certificates",                         "icon":"📜","secret":False},
{"id":"cert_6",            "name":"Six Certs",         "desc":"Earn 6 certificates",                         "icon":"📜","secret":False},
{"id":"cert_8",            "name":"Eight Certs",       "desc":"Earn 8 certificates",                         "icon":"📜","secret":False},
{"id":"practice_15",       "name":"15 Practices",      "desc":"Complete 15 practice sessions",               "icon":"📚","secret":False},
{"id":"practice_30",       "name":"30 Practices",      "desc":"Complete 30 practice sessions",               "icon":"📚","secret":False},
{"id":"no_wrong_6",        "name":"Six Flawless",      "desc":"Get 0 wrong 6 times",                         "icon":"🛡️","secret":False},
{"id":"no_wrong_8",        "name":"Eight Flawless",    "desc":"Get 0 wrong 8 times",                         "icon":"⚔️","secret":False},
{"id":"speed_20",          "name":"Speedy Bee",        "desc":"Finish RapidBee in under 20 seconds",         "icon":"🏃","secret":False},
{"id":"speed_25",          "name":"Very Fast Bee",     "desc":"Finish RapidBee in under 25 seconds",         "icon":"💨","secret":False},
{"id":"leaderboard_top5",  "name":"Top 5",             "desc":"Reach top 5 on the leaderboard",              "icon":"🏅","secret":False},
{"id":"games_160",         "name":"160 Games",         "desc":"Play 160 games total",                        "icon":"🎮","secret":False},
{"id":"games_180",         "name":"180 Games",         "desc":"Play 180 games total",                        "icon":"🎮","secret":False},
{"id":"games_220",         "name":"220 Games",         "desc":"Play 220 games total",                        "icon":"🎮","secret":False},
{"id":"q_correct_600",     "name":"600 Right",         "desc":"Answer 600 questions correctly",              "icon":"🌟","secret":False},
{"id":"q_correct_800",     "name":"800 Right",         "desc":"Answer 800 questions correctly",              "icon":"🏅","secret":False},
# ── GAMESPACE ─────────────────────────────────────────────────────────────────
{"id":"first_game_memory",  "name":"Memory Bee",        "desc":"Play Memory Match for the first time",        "icon":"🧠","secret":False},
{"id":"first_speedmath",    "name":"Math Bee",          "desc":"Play Speed Math for the first time",          "icon":"🔢","secret":False},
{"id":"first_scramble",     "name":"Word Bee",          "desc":"Play Word Scramble for the first time",       "icon":"🔤","secret":False},
{"id":"first_chess",        "name":"Chess Bee",         "desc":"Play your first chess game",                  "icon":"♟️","secret":False},
{"id":"all_games",          "name":"Game Explorer",     "desc":"Try all 4 GameSpace games",                   "icon":"🕹️","secret":False},
{"id":"memory_hard",        "name":"Hard Memory",       "desc":"Complete Hard (6x4) Memory Match",            "icon":"🧠","secret":False},
{"id":"memory_under60",     "name":"Memory Flash",      "desc":"Complete Easy Memory Match under 60 seconds", "icon":"⚡","secret":False},
{"id":"speedmath_streak5",  "name":"Math Streak",       "desc":"Get a 5-answer streak in Speed Math",         "icon":"🔥","secret":False},
{"id":"speedmath_hard",     "name":"Hard Maths",        "desc":"Complete Hard Speed Math with 7+ correct",    "icon":"💀","secret":False},
{"id":"scramble_noskip",    "name":"No Skip",           "desc":"Complete Word Scramble without skipping",     "icon":"🔤","secret":False},
{"id":"scramble_perfect",   "name":"Scramble Master",   "desc":"Solve all 10 words in Word Scramble",         "icon":"🏆","secret":False},
{"id":"games_played_10",    "name":"Gamer Bee",         "desc":"Play any GameSpace game 10 times",            "icon":"🎮","secret":False},
{"id":"chess_expert",       "name":"Chess Expert",      "desc":"Play a game on Expert difficulty",            "icon":"♛","secret":False},
{"id":"chess_win",          "name":"Chess Victor",      "desc":"Beat Stockfish on any difficulty",            "icon":"🏆","secret":False},
{"id":"chess_win_medium",   "name":"Rising Chess Star", "desc":"Beat Stockfish on Medium",                    "icon":"♟️","secret":False},
{"id":"chess_win_hard",     "name":"Chess Master",      "desc":"Beat Stockfish on Hard",                      "icon":"🎖️","secret":False},
{"id":"chess_20moves",      "name":"Long Game",         "desc":"Play a chess game lasting 20+ moves",         "icon":"⏱️","secret":False},
# ── BEEXAM ────────────────────────────────────────────────────────────────────
{"id":"first_beexam",       "name":"Exam Bee",          "desc":"Complete your first BeeXam paper",            "icon":"🎓","secret":False},
{"id":"beexam_pass",        "name":"BeeXam Pass",       "desc":"Score above the cutoff in a BeeXam paper",    "icon":"✅","secret":False},
{"id":"beexam_perfect",     "name":"BeeXam Perfect",    "desc":"Score 100% in a BeeXam paper",                "icon":"💎","secret":False},
{"id":"beexam_5",           "name":"Exam Regular",      "desc":"Complete 5 BeeXam papers",                    "icon":"📋","secret":False},
{"id":"beexam_neet",        "name":"NEET Candidate",    "desc":"Complete a NEET past paper",                  "icon":"🩺","secret":False},
{"id":"beexam_jee",         "name":"JEE Candidate",     "desc":"Complete a JEE past paper",                   "icon":"⚗️","secret":False},
{"id":"beexam_sat",         "name":"SAT Taker",         "desc":"Complete a SAT past paper",                   "icon":"📐","secret":False},
{"id":"beexam_fulltime",    "name":"Full Timer",        "desc":"Complete a BeeXam using the official time",   "icon":"⏱️","secret":False},
{"id":"beexam_80",          "name":"Exam Star",         "desc":"Score 80%+ in a BeeXam paper",               "icon":"⭐","secret":False},
{"id":"beexam_3diff",       "name":"Multi-Exam Bee",    "desc":"Complete papers from 3 different exams",      "icon":"🌍","secret":False},
# ── NEW SECRET ────────────────────────────────────────────────────────────────
{"id":"secret_chess_draw",       "name":"Honorable Draw",     "desc":"Draw against Stockfish",                         "icon":"🤝","secret":True},
{"id":"secret_chess_expert_win", "name":"The Grandmaster",    "desc":"Beat Stockfish on Expert difficulty",            "icon":"👑","secret":True},
{"id":"secret_chess_undo",       "name":"Take It Back",       "desc":"Use Undo 5 times in one chess game",             "icon":"↩️","secret":True},
{"id":"secret_memory_1min",      "name":"Photographic",       "desc":"Complete Hard Memory Match under 60 seconds",    "icon":"📸","secret":True},
{"id":"secret_all_gamespace",    "name":"GameSpace God",      "desc":"Get a win/perfect in all 4 GameSpace games",     "icon":"🕹️","secret":True},
{"id":"secret_math_expert_10",   "name":"Calculator Brain",   "desc":"Get 10 correct in Expert Speed Math",            "icon":"🧮","secret":True},
{"id":"secret_scramble_5s",      "name":"Unscrambler",        "desc":"Solve a Word Scramble word in under 5 seconds",  "icon":"⚡","secret":True},
{"id":"secret_beexam_midnight",  "name":"Night Exam",         "desc":"Complete a BeeXam paper after midnight",         "icon":"🌙","secret":True},
{"id":"secret_beexam_3inday",    "name":"Exam Marathon",      "desc":"Complete 3 BeeXam papers in one day",            "icon":"📚","secret":True},
{"id":"secret_chess_noqueen",    "name":"No Queen?",          "desc":"Win chess without moving your Queen",            "icon":"🤯","secret":True},
{"id":"first_jigsaw",       "name":"Puzzle Bee",      "desc":"Complete your first Jigsaw puzzle",          "icon":"🧩","secret":False},
{"id":"jigsaw_hard",        "name":"Hard Puzzle",     "desc":"Complete a 5x5 Jigsaw puzzle",               "icon":"🧩","secret":False},
{"id":"secret_jigsaw_fast", "name":"Speed Puzzler",   "desc":"Solve any Jigsaw puzzle in under 2 minutes",  "icon":"⚡","secret":True},
{"id":"secret_jigsaw_5x5_fast","name":"Puzzle Master","desc":"Solve a 5x5 Jigsaw in under 3 minutes",      "icon":"👑","secret":True},
]
ACH_MAP = {a["id"]: a for a in ACHIEVEMENTS}

# ── DB ──────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT UNIQUE NOT NULL,
                password  TEXT NOT NULL,
                is_admin  INTEGER DEFAULT 0,
                avatar    TEXT DEFAULT '🐝',
                streak    INTEGER DEFAULT 0,
                last_play TEXT DEFAULT NULL,
                created   TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS results (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                mode         TEXT NOT NULL,
                score        INTEGER NOT NULL,
                total        INTEGER NOT NULL,
                pct          INTEGER NOT NULL,
                grade        TEXT NOT NULL,
                time_taken   INTEGER DEFAULT 0,
                tab_switches INTEGER DEFAULT 0,
                played_at    TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS jigsaw_levels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                image_path  TEXT NOT NULL,
                grid_size   INTEGER DEFAULT 4,
                order_num   INTEGER DEFAULT 0,
                created     TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS jigsaw_progress (
                user_id     INTEGER NOT NULL,
                level_id    INTEGER NOT NULL,
                completed   INTEGER DEFAULT 0,
                best_time   INTEGER DEFAULT 0,
                stars       INTEGER DEFAULT 0,
                completed_at TEXT,
                PRIMARY KEY(user_id, level_id)
            );
            CREATE TABLE IF NOT EXISTS rb_temp (
                user_id        INTEGER PRIMARY KEY,
                questions_json TEXT NOT NULL,
                log_json       TEXT DEFAULT '[]',
                score          INTEGER DEFAULT 0,
                tabs           INTEGER DEFAULT 0,
                created        TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS bw_temp (
                user_id        INTEGER PRIMARY KEY,
                questions_json TEXT NOT NULL,
                answers_json   TEXT DEFAULT '[]',
                tabs           INTEGER DEFAULT 0,
                created        TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS scheduled_tests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id  INTEGER NOT NULL,
                room_id     INTEGER NOT NULL,
                class_id    INTEGER,
                scheduled_at TEXT NOT NULL,
                note        TEXT DEFAULT '',
                created     TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS answer_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id   INTEGER NOT NULL,
                question    TEXT NOT NULL,
                category    TEXT NOT NULL,
                correct     INTEGER NOT NULL,
                user_ans    INTEGER DEFAULT -1,
                correct_ans INTEGER DEFAULT 0,
                time_spent  INTEGER DEFAULT 0,
                FOREIGN KEY (result_id) REFERENCES results(id)
            );
            CREATE TABLE IF NOT EXISTS questions_db (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                question  TEXT NOT NULL,
                opt0      TEXT NOT NULL,
                opt1      TEXT NOT NULL,
                opt2      TEXT NOT NULL,
                opt3      TEXT NOT NULL,
                answer    INTEGER NOT NULL DEFAULT 0,
                category  TEXT NOT NULL DEFAULT 'General',
                active    INTEGER DEFAULT 1,
                created   TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS exam_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time   TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                active     INTEGER DEFAULT 1,
                created    TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS achievements (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                ach_id     TEXT NOT NULL,
                earned_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, ach_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS cb_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL UNIQUE,
                questions  TEXT NOT NULL,
                idx        INTEGER DEFAULT 0,
                score      INTEGER DEFAULT 0,
                log        TEXT DEFAULT '[]',
                total      INTEGER DEFAULT 0,
                end_time   REAL DEFAULT 0,
                created    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS room_quiz_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL UNIQUE,
                room_id    INTEGER NOT NULL,
                room_title TEXT NOT NULL,
                questions  TEXT NOT NULL,
                idx        INTEGER DEFAULT 0,
                score      INTEGER DEFAULT 0,
                total      INTEGER DEFAULT 0,
                start_time REAL DEFAULT 0,
                end_time   REAL DEFAULT 0,
                created    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS quiz_rooms (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                code       TEXT UNIQUE NOT NULL,
                created_by INTEGER NOT NULL,
                questions  TEXT NOT NULL,
                time_limit INTEGER DEFAULT 30,
                active     INTEGER DEFAULT 1,
                created    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS room_results (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id    INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                score      INTEGER DEFAULT 0,
                total      INTEGER DEFAULT 0,
                pct        INTEGER DEFAULT 0,
                time_taken INTEGER DEFAULT 0,
                finished   TEXT DEFAULT (datetime('now')),
                UNIQUE(room_id, user_id)
            );
        """)
        # Safe column migrations for existing DBs
        for col, defn in [
            ("tab_switches","INTEGER DEFAULT 0"),
            ("user_ans","INTEGER DEFAULT -1"),
            ("correct_ans","INTEGER DEFAULT 0"),
            ("avatar","TEXT DEFAULT '🐝'"),
            ("streak","INTEGER DEFAULT 0"),
            ("last_play","TEXT DEFAULT NULL"),
            ("role","TEXT DEFAULT 'student'"),
        ]:
            try:
                tbl = "users" if col in ("avatar","streak","last_play","role") else \
                      "results" if col == "tab_switches" else "answer_log"
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {defn}")
            except: pass

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def get_grade_msg(pct, mode):
    grade = "A" if pct >= 80 else "B" if pct >= 60 else "C" if pct >= 40 else "D"
    if mode == "RapidBee":
        msg = "Rapid Master! ⚡" if pct >= 80 else "Good Speed! 🐝" if pct >= 60 else "Try Faster!"
    elif "Practice" in mode:
        msg = "Perfect Practice! 🌟" if pct >= 80 else "Good Practice! 🐝" if pct >= 60 else "Keep Studying!"
    else:
        msg = "Excellent Work! 🐝" if pct >= 80 else "Good Job! 🌟" if pct >= 60 else "Keep Practicing!"
    return grade, msg

def update_streak(user_id):
    """Update daily streak and return current streak count."""
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        user = conn.execute("SELECT streak, last_play FROM users WHERE id=?", (user_id,)).fetchone()
        last = user["last_play"]
        streak = user["streak"] or 0
        if last == today:
            return streak  # already played today
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        new_streak = streak + 1 if last == yesterday else 1
        conn.execute("UPDATE users SET streak=?, last_play=? WHERE id=?", (new_streak, today, user_id))
        return new_streak

def check_and_award(user_id, result_data):
    """Check all 120 achievements and award new ones. Returns list of newly earned."""
    newly_earned = []
    pct       = result_data.get("pct", 0)
    wrong     = result_data.get("wrong", 1)
    mode      = result_data.get("mode", "")
    time_taken= result_data.get("time_taken", 9999)

    with get_db() as conn:
        existing = {r["ach_id"] for r in conn.execute(
            "SELECT ach_id FROM achievements WHERE user_id=?", (user_id,)).fetchall()}
        stats = conn.execute(
            """SELECT COUNT(*) as games,
               MIN(pct) as min_pct, MAX(pct) as max_pct,
               SUM(score) as total_correct
               FROM results WHERE user_id=?""",
            (user_id,)).fetchone()
        perfect_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=? AND pct=100", (user_id,)).fetchone()["c"]
        grade_a_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=? AND pct>=80", (user_id,)).fetchone()["c"]
        no_wrong_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=? AND score=total", (user_id,)).fetchone()["c"]
        rapid_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=? AND mode='RapidBee'", (user_id,)).fetchone()["c"]
        cats_practiced = {r["mode"].split(":")[1] for r in conn.execute(
            "SELECT DISTINCT mode FROM results WHERE user_id=? AND mode LIKE 'Practice:%'",
            (user_id,)).fetchall()}
        practice_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=? AND mode LIKE 'Practice:%'",
            (user_id,)).fetchone()["c"]
        cert_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=? AND pct>=80", (user_id,)).fetchone()["c"]
        streak = conn.execute("SELECT streak FROM users WHERE id=?", (user_id,)).fetchone()["streak"]
        prev_best = conn.execute(
            "SELECT MAX(pct) as best FROM results WHERE user_id=? AND played_at < datetime('now','-1 second')",
            (user_id,)).fetchone()["best"] or 0
        same_score = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=? AND pct=?",
            (user_id, pct)).fetchone()["c"]
        days_played = conn.execute(
            "SELECT COUNT(DISTINCT date(played_at)) as d FROM results WHERE user_id=?",
            (user_id,)).fetchone()["d"]

    # Total correct answers ever
    total_correct = stats["total_correct"] or 0
    games         = stats["games"] or 0

    def award(ach_id):
        if ach_id not in existing and ach_id in ACH_MAP:
            with get_db() as conn2:
                try:
                    conn2.execute("INSERT INTO achievements (user_id, ach_id) VALUES (?,?)", (user_id, ach_id))
                    newly_earned.append(ACH_MAP[ach_id])
                    existing.add(ach_id)
                except: pass

    # ── EASY ──
    if games >= 1:   award("first_game")
    if games >= 3:   award("games_3")
    if games >= 5:   award("games_5")
    if games >= 7:   award("games_7")
    if games >= 8:   award("games_8")
    if games >= 10:  award("games_10")
    if games >= 15:  award("games_15")
    if games >= 20:  award("games_20")
    if games >= 25:  award("games_25")
    if games >= 30:  award("games_30")
    if games >= 40:  award("games_40")
    if games >= 45:  award("games_45")
    if games >= 50:  award("games_50")
    if games >= 60:  award("games_60")
    if games >= 75:  award("games_75")
    if games >= 80:  award("games_80")
    if games >= 90:  award("games_90")
    if games >= 100: award("games_100")
    if games >= 120: award("games_120")
    if games >= 150: award("games_150")
    if games >= 160: award("games_160")
    if games >= 180: award("games_180")
    if games >= 200: award("games_200")
    if games >= 220: award("games_220")
    if games >= 250: award("games_250")
    if games >= 300: award("games_300")
    if games >= 350: award("games_350")
    if games >= 400: award("games_400")
    if games >= 500: award("games_500")
    if mode == "RapidBee" and games >= 1: award("first_rapidbee")
    if "Practice" in mode: award("first_practice")
    if pct >= 40:    award("pct_40")
    if pct >= 50:    award("pct_50")
    if pct >= 55:    award("pct_55")
    if pct >= 60:    award("pct_60"); award("grade_b")
    if pct >= 65:    award("pct_65")
    if pct >= 70:    award("pct_70")
    if pct >= 75:    award("pct_75")
    if pct >= 80:    award("pct_80"); award("grade_a"); award("cert_earned")
    if pct >= 85:    award("pct_85")
    if pct >= 90:    award("pct_90")
    if pct >= 95:    award("pct_95")
    if pct == 100:   award("perfect_score")
    if pct == 42:    award("secret_score42")
    if pct == 69:    award("secret_score69")
    if pct == 88:    award("secret_exact_88")
    if pct == 80 and total_correct > 0: award("score_exactly_80")
    if streak >= 2:  award("streak_2")
    if streak >= 3:  award("streak_3")
    if streak >= 4:  award("streak_4")
    if streak >= 5:  award("streak_5")
    if streak >= 6:  award("streak_6")
    if streak >= 7:  award("streak_7")
    if streak >= 10: award("streak_10"); award("streak_10b")
    if streak >= 14: award("streak_14")
    if streak >= 20: award("streak_20")
    if streak >= 21: award("streak_21")
    if streak >= 25: award("streak_25")
    if streak >= 30: award("streak_30")
    if streak >= 45: award("streak_45"); award("streak_45b")
    if streak >= 60: award("streak_60")
    if streak >= 90: award("streak_90")
    if streak >= 100:award("streak_100")
    if days_played >= 2: award("play_2_days")
    if wrong == 0:   award("no_wrong")
    # First-time score milestones (only if this is the first time hitting them)
    if pct >= 60 and grade_a_count <= 1: award("score_60_first")
    if pct >= 70 and grade_a_count <= 1: award("score_70_first")
    if mode == "RapidBee" and pct >= 80 and rapid_count == 1: award("rapid_first_win"); award("first_rapidbee_win")
    # Complete profile: has non-default avatar and 5+ games
    with get_db() as _conn:
        _uavatar = _conn.execute("SELECT avatar FROM users WHERE id=?", (user_id,)).fetchone()["avatar"]
    if _uavatar != "🐝" and games >= 5: award("complete_profile"); award("choose_avatar")
    # Time-based
    hour = datetime.datetime.now().hour
    dow  = datetime.datetime.now().weekday()  # 0=Mon … 6=Sun
    if hour < 9:      award("quiz_morning"); award("play_morning")
    if hour >= 22:    award("quiz_night")
    if 17 <= hour < 20: award("play_evening")
    if 19 <= hour < 22: award("play_quiz_night")
    if 0 <= hour < 3: award("secret_midnight")
    if hour == 1:     award("secret_1am")
    if hour == 3:     award("secret_3am")
    if dow == 4:      award("play_friday")   # Friday
    if dow == 6:      award("play_sunday")   # Sunday
    today_dt = datetime.date.today()
    if today_dt.month == 1 and today_dt.day == 1:   award("secret_new_year")
    if today_dt.month == 4 and today_dt.day == 21:  award("secret_birthday")
    if today_dt.month == 2 and today_dt.day == 29:  award("secret_feb29")
    # Practice categories
    if "Practice:HTML"    in (mode,): award("practice_html")
    if "Practice:CSS"     in (mode,): award("practice_css")
    if "Practice:Python"  in (mode,): award("practice_python")
    if "Practice:SQL"     in (mode,): award("practice_sql")
    if "Practice:Flask"   in (mode,): award("practice_flask")
    if "Practice:General" in (mode,): award("practice_general")
    if len(cats_practiced) >= 6: award("all_cats")
    # Perfect in category
    if mode == "Practice:HTML"   and pct == 100: award("html_perfect")
    if mode == "Practice:Python" and pct == 100: award("python_perfect")
    if mode == "Practice:SQL"    and pct == 100: award("sql_perfect")
    if mode == "Practice:CSS"    and pct == 100: award("css_perfect")
    if mode == "Practice:Flask"  and pct == 100: award("flask_perfect")

    # ── MEDIUM ──
    if perfect_count >= 2:  award("perfect_twice")
    if perfect_count >= 3:  award("perfect_3")
    if perfect_count >= 4:  award("perfect_4")
    if perfect_count >= 5:  award("perfect_5")
    if perfect_count >= 6:  award("perfect_6")
    if perfect_count >= 7:  award("perfect_7")
    if perfect_count >= 8:  award("perfect_8")
    if perfect_count >= 10: award("perfect_10")
    if perfect_count >= 15: award("perfect_15")
    if perfect_count >= 20: award("perfect_20")
    if grade_a_count >= 3:  award("grade_a_3")
    if grade_a_count >= 5:  award("grade_a_5")
    if grade_a_count >= 7:  award("grade_a_7")
    if grade_a_count >= 10: award("grade_a_10")
    if grade_a_count >= 15: award("grade_a_15")
    if grade_a_count >= 20: award("grade_a_20")
    if grade_a_count >= 25: award("grade_a_25")
    if grade_a_count >= 30: award("grade_a_30")
    if grade_a_count >= 50: award("grade_a_50")
    if grade_a_count >= 75: award("grade_a_75")
    if grade_a_count >= 100:award("grade_a_100")
    if no_wrong_count >= 2:  award("no_wrong_2")
    if no_wrong_count >= 3:  award("no_wrong_3")
    if no_wrong_count >= 4:  award("no_wrong_4")
    if no_wrong_count >= 5:  award("no_wrong_5")
    if no_wrong_count >= 6:  award("no_wrong_6")
    if no_wrong_count >= 7:  award("no_wrong_7")
    if no_wrong_count >= 8:  award("no_wrong_8")
    if no_wrong_count >= 10: award("no_wrong_10")
    if no_wrong_count >= 15: award("no_wrong_15")
    if no_wrong_count >= 20: award("no_wrong_20")
    if no_wrong_count >= 25: award("no_wrong_25")
    if mode == "RapidBee":
        if time_taken < 60: award("speed_demon")
        if time_taken < 30: award("speed_30")
        if time_taken < 15: award("speed_15")
    if rapid_count >= 5:   award("rapid_5")
    if rapid_count >= 10:  award("complete_rapid_10")
    if rapid_count >= 20:  award("rapid_20")
    if rapid_count >= 30:  award("rapid_30")
    if rapid_count >= 40:  award("rapid_40")
    if rapid_count >= 50:  award("rapid_50")
    if rapid_count >= 60:  award("rapid_60")
    if rapid_count >= 75:  award("rapid_75")
    if rapid_count >= 100: award("rapid_100"); award("rapid_centurion")
    if rapid_count >= 150: award("rapid_150")
    if practice_count >= 10: award("practice_master")
    if cert_count >= 3:   award("cert_3")
    if cert_count >= 10:  award("cert_10")
    if total_correct >= 10:   award("q_correct_10")
    if total_correct >= 25:   award("q_correct_25")
    if total_correct >= 50:   award("q_correct_50")
    if total_correct >= 75:   award("q_correct_75")
    if total_correct >= 100:  award("q_correct_100")
    if total_correct >= 150:  award("q_correct_150")
    if total_correct >= 200:  award("q_correct_200")
    if total_correct >= 250:  award("q_correct_250")
    if total_correct >= 300:  award("q_correct_300")
    if total_correct >= 400:  award("q_correct_400")
    if total_correct >= 500:  award("q_correct_500")
    if total_correct >= 600:  award("q_correct_600")
    if total_correct >= 750:  award("q_correct_750"); award("q_correct_750b")
    if total_correct >= 800:  award("q_correct_800")
    if total_correct >= 1000: award("q_correct_1000")
    if total_correct >= 1500: award("q_correct_1500")
    if total_correct >= 2000: award("q_correct_2000")
    if total_correct >= 2500: award("q_correct_2500")
    if total_correct >= 3000: award("q_correct_3000")
    if total_correct >= 4000: award("q_correct_4000")
    if total_correct >= 5000: award("q_correct_5000")
    # Comeback
    if pct >= 80 and (stats["min_pct"] or 100) < 40: award("comeback")
    if pct == 0 and wrong > 0: award("secret_all_wrong")
    # Improvement
    if pct > prev_best and prev_best > 0: award("improvement")
    # Same score 3 times
    if same_score >= 3: award("secret_same_score")
    # Secret: played all 3 modes today
    with get_db() as conn3:
        modes_today = {r["mode"] for r in conn3.execute(
            "SELECT DISTINCT mode FROM results WHERE user_id=? AND date(played_at)=date('now')",
            (user_id,)).fetchall()}
    has_qb = any("BeeWise" in m and "RapidBee" not in m and "Practice" not in m for m in modes_today)
    has_rb = "RapidBee" in modes_today
    has_pr = any("Practice" in m for m in modes_today)
    if has_qb and has_rb and has_pr: award("secret_rapid_all")
    # Secret: timer expired
    if result_data.get("timeout"): award("secret_no_time")
    # Weekend
    dow = datetime.datetime.now().weekday()
    with get_db() as conn4:
        weekends = conn4.execute(
            "SELECT COUNT(DISTINCT date(played_at)) as c FROM results WHERE user_id=? AND strftime('%w',played_at) IN ('0','6')",
            (user_id,)).fetchone()["c"]
    if weekends >= 2: award("weekend_bee")
    # BeeXam achievements
    beexam_count = conn.execute(
        "SELECT COUNT(*) FROM beexam_results WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    if beexam_count >= 1:  award("first_beexam")
    if beexam_count >= 5:  award("beexam_5")
    if mode == "BeeXam":
        if pct >= 80:      award("beexam_80")
        if pct >= 100:     award("beexam_perfect")
        # Check exam name for specific exam achievements
        exam_name = result_data.get("exam_name","")
        if "NEET"    in exam_name: award("beexam_neet")
        if "JEE"     in exam_name: award("beexam_jee")
        if "SAT"     in exam_name: award("beexam_sat")
        cutoff    = result_data.get("cutoff", 0)
        raw_score = result_data.get("raw_score", 0)
        if cutoff and raw_score >= cutoff: award("beexam_pass")
        if result_data.get("used_official_time"): award("beexam_fulltime")
        # 3 different exams
        diff_exams = conn.execute("""
            SELECT COUNT(DISTINCT bp.exam_name) FROM beexam_results br
            JOIN beexam_papers bp ON bp.id = br.paper_id
            WHERE br.user_id=?
        """, (user_id,)).fetchone()[0]
        if diff_exams >= 3: award("beexam_3diff")
        # Secret midnight BeeXam
        hour = __import__("datetime").datetime.now().hour
        if hour == 0: award("secret_beexam_midnight")
        # 3 BeeXam in one day
        today_exams = conn.execute("""
            SELECT COUNT(*) FROM beexam_results
            WHERE user_id=? AND DATE(played_at)=DATE('now')
        """, (user_id,)).fetchone()[0]
        if today_exams >= 3: award("secret_beexam_3inday")

    return newly_earned

def save_result(user_id, mode, score, total, pct, grade, time_taken, answer_log_data, tab_switches=0):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO results (user_id,mode,score,total,pct,grade,time_taken,tab_switches) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, mode, score, total, pct, grade, time_taken, tab_switches))
        result_id = cur.lastrowid
        for entry in answer_log_data:
            conn.execute(
                "INSERT INTO answer_log (result_id,question,category,correct,user_ans,correct_ans,time_spent) VALUES (?,?,?,?,?,?,?)",
                (result_id, entry["q"], entry["cat"], entry["correct"],
                 entry.get("user_ans",-1), entry.get("correct_ans",0), entry.get("time_spent",0)))
    return result_id

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session: return redirect("/")
        return f(*args, **kwargs)
    return decorated

def require_teacher(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") not in ("teacher", "admin"):
            flash("Teacher access required.", "error")
            return redirect("/dashboard")
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin" and not session.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect("/dashboard")
        return f(*args, **kwargs)
    return decorated

init_db()

# ── Auth ────────────────────────────────────────────────────────────
@app.route("/landing")
def landing():
    """Product landing page — shown to visitors who aren't logged in."""
    if "user_id" in session: return redirect("/dashboard")
    with get_db() as conn:
        total_users  = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()["c"]
        total_games  = conn.execute("SELECT COUNT(*) as c FROM results").fetchone()["c"]
        top_players  = conn.execute("""
            SELECT u.username, u.avatar, MAX(r.pct) as best, COUNT(r.id) as games
            FROM users u JOIN results r ON r.user_id=u.id
            WHERE u.is_admin=0 GROUP BY u.id ORDER BY best DESC LIMIT 3
        """).fetchall()
    return render_template("landing.html",
                           total_users=total_users,
                           total_games=total_games,
                           top_players=top_players)

@app.route("/", methods=["GET","POST"])
def login():
    if "user_id" in session: return redirect("/dashboard")
    # Redirect GET requests with no action to landing page
    if request.method == "GET" and not request.args.get("tab"):
        return redirect("/landing")
    if request.method == "POST":
        action   = request.form.get("action")
        username = request.form.get("username","").strip()[:30]
        password = request.form.get("password","")
        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect("/")
        if action == "register":
            import re
            if not re.match(r'^[A-Za-z0-9_]{3,30}$', username):
                flash("Username must be 3–30 characters, letters/numbers/underscores only.", "error")
                return redirect("/")
            if len(password) < 6:
                flash("Password must be at least 6 characters.", "error")
                return redirect("/")
            if not re.search(r'[A-Za-z]', password) or not re.search(r'[0-9]', password):
                flash("Password must contain both letters and numbers.", "error")
                return redirect("/")
            # Admin code still works secretly for admin accounts
            # Everyone else registers as student — teachers get promoted by admin
            admin_code = request.form.get("admin_code","").strip()
            if admin_code and admin_code == ADMIN_CODE:
                role = "admin"; is_admin = 1
            else:
                role = "student"; is_admin = 0
            try:
                with get_db() as conn:
                    conn.execute("INSERT INTO users (username,password,is_admin,role) VALUES (?,?,?,?)",
                                 (username, hash_pw(password), is_admin, role))
                flash("Account created! Please log in. 🐝", "success")
            except sqlite3.IntegrityError:
                flash("Username already taken.", "error")
            return redirect("/")
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                                (username, hash_pw(password))).fetchone()
        if user:
            session.clear()
            session["user_id"]    = user["id"]
            session["username"]   = user["username"]
            role = user["role"] if "role" in user.keys() else ("admin" if user["is_admin"] else "student")
            session["role"]       = role
            session["is_admin"]   = (role == "admin")
            session["is_teacher"] = (role == "teacher")
            session["avatar"]     = user["avatar"] or "🐝"
            check_and_award(user["id"], {"pct": 0, "wrong": 0, "mode": "__login__", "time_taken": 0})
            with get_db() as _c:
                _c.execute("INSERT OR IGNORE INTO achievements (user_id, ach_id) VALUES (?,?)",
                           (user["id"], "first_login"))
            # Redirect teachers to their dashboard
            if role == "teacher":
                return redirect("/teacher")
            return redirect("/dashboard")
        flash("Wrong username or password.", "error")
        return redirect("/")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ── Profile ─────────────────────────────────────────────────────────
AVATARS = ["🐝","🦋","🐛","🦗","🐞","🦟","🪲","🐜","🪳","🦂","🐢","🦎","🐸","🐧","🦉","🦊","🐺","🦁","🐯","🐻"]

@app.route("/profile", methods=["GET","POST"])
@require_login
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "change_password":
            old_pw  = request.form.get("old_password","")
            new_pw  = request.form.get("new_password","")
            with get_db() as conn:
                user = conn.execute("SELECT * FROM users WHERE id=? AND password=?",
                                    (session["user_id"], hash_pw(old_pw))).fetchone()
            if not user:
                flash("Current password is incorrect.", "error")
            elif len(new_pw) < 4:
                flash("New password must be at least 6 characters with letters and numbers.", "error")
            else:
                with get_db() as conn:
                    conn.execute("UPDATE users SET password=? WHERE id=?",
                                 (hash_pw(new_pw), session["user_id"]))
                flash("Password updated! 🔐", "success")
        elif action == "change_avatar":
            avatar = request.form.get("avatar","🐝")
            if avatar in AVATARS:
                with get_db() as conn:
                    conn.execute("UPDATE users SET avatar=? WHERE id=?", (avatar, session["user_id"]))
                session["avatar"] = avatar
                flash("Avatar updated!", "success")
        return redirect("/profile")

    with get_db() as conn:
        user  = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        stats = conn.execute(
            "SELECT COUNT(*) as games, ROUND(AVG(pct)) as avg_pct, MAX(pct) as best, SUM(time_taken) as total_time FROM results WHERE user_id=?",
            (session["user_id"],)).fetchone()
        cat_stats = conn.execute("""
            SELECT al.category, ROUND(AVG(al.correct)*100) as pct, COUNT(*) as total
            FROM answer_log al JOIN results r ON r.id=al.result_id
            WHERE r.user_id=? GROUP BY al.category
        """, (session["user_id"],)).fetchall()
        earned = conn.execute(
            "SELECT ach_id, earned_at FROM achievements WHERE user_id=? ORDER BY earned_at DESC",
            (session["user_id"],)).fetchall()
    earned_ids = {e["ach_id"] for e in earned}
    with get_db() as conn:
        my_classes = conn.execute("""
            SELECT c.id, c.name, c.code
            FROM classes c JOIN class_members cm ON cm.class_id=c.id
            WHERE cm.user_id=?
        """, (session["user_id"],)).fetchall()
        all_results = conn.execute(
            "SELECT * FROM results WHERE user_id=? ORDER BY played_at DESC LIMIT 20",
            (session["user_id"],)).fetchall()
    return render_template("profile.html", user=user, stats=stats, cat_stats=cat_stats,
                           earned=earned, earned_ids=earned_ids, my_classes=my_classes,
                           all_results=all_results,
                           all_achievements=ACHIEVEMENTS, avatars=AVATARS)

# ── Dashboard ────────────────────────────────────────────────────────
@app.route("/dashboard")
@require_login
def dashboard():
    uid    = session["user_id"]
    streak = update_streak(uid)
    with get_db() as conn:
        history  = conn.execute(
            "SELECT * FROM results WHERE user_id=? ORDER BY played_at DESC LIMIT 10",
            (uid,)).fetchall()
        stats    = conn.execute(
            "SELECT COUNT(*) as games, ROUND(AVG(pct)) as avg_pct, MAX(pct) as best FROM results WHERE user_id=?",
            (uid,)).fetchone()
        cat_stats = conn.execute("""
            SELECT al.category, COUNT(*) as total_q, SUM(al.correct) as correct_q,
                   ROUND(AVG(al.correct)*100) as pct
            FROM answer_log al JOIN results r ON r.id=al.result_id
            WHERE r.user_id=? GROUP BY al.category ORDER BY pct ASC
        """, (uid,)).fetchall()
        progress = list(reversed(conn.execute(
            "SELECT pct, mode, played_at FROM results WHERE user_id=? ORDER BY played_at DESC LIMIT 10",
            (uid,)).fetchall()))
        recent_badges = conn.execute(
            "SELECT ach_id, earned_at FROM achievements WHERE user_id=? ORDER BY earned_at DESC LIMIT 3",
            (uid,)).fetchall()
        user = conn.execute("SELECT avatar, streak FROM users WHERE id=?", (uid,)).fetchone()

        # Scheduled tests — find classes this student belongs to,
        # then show upcoming tests for those classes (or all-student tests)
        try:
            scheduled_tests = conn.execute("""
                SELECT st.id, st.scheduled_at, st.note,
                       qr.title   AS room_title,
                       qr.code    AS room_code,
                       qr.id      AS room_id,
                       c.name     AS class_name,
                       u.username AS teacher_name
                FROM scheduled_tests st
                JOIN quiz_rooms qr ON qr.id = st.room_id
                LEFT JOIN classes c ON c.id = st.class_id
                JOIN users u ON u.id = st.teacher_id
                WHERE st.scheduled_at >= datetime('now')
                  AND (
                    st.class_id IS NULL
                    OR st.class_id IN (
                        SELECT class_id FROM class_members WHERE user_id=?
                    )
                  )
                ORDER BY st.scheduled_at ASC
                LIMIT 5
            """, (uid,)).fetchall()
        except Exception:
            scheduled_tests = []

    return render_template("dashboard.html", history=history, stats=stats,
                           cat_stats=cat_stats, progress=progress,
                           recent_badges=recent_badges, ach_map=ACH_MAP,
                           streak=streak, user=user, categories=CATEGORIES,
                           scheduled_tests=scheduled_tests)

# ── Mode ─────────────────────────────────────────────────────────────
@app.route("/mode")
@require_login
def mode():
    with get_db() as conn:
        exams = conn.execute("""
            SELECT * FROM exam_sessions WHERE active=1
            AND datetime('now') BETWEEN datetime(start_time) AND datetime(end_time)
        """).fetchall()
    from collections import Counter
    cat_counts = Counter(q["cat"] for q in ALL_QUESTIONS)
    return render_template("mode.html", categories=CATEGORIES, exams=exams, cat_counts=cat_counts)

# ── BeeWise ──────────────────────────────────────────────────────────
@app.route("/quiz")
@require_login
def quiz():
    import json as _j
    uid = session["user_id"]
    qs  = get_shuffled_questions(QUIZ_LIMIT, balanced=True)
    with get_db() as conn:
        conn.execute("DELETE FROM bw_temp WHERE user_id=?", (uid,))
        conn.execute("INSERT INTO bw_temp (user_id, questions_json) VALUES (?,?)",
                     (uid, _j.dumps(qs)))
    session["quiz_start"]   = time.time()
    session["tab_switches"] = 0
    return render_template("quiz.html", questions=qs, quiz_time=QUIZ_TIME)

@app.route("/submit_quiz", methods=["POST"])
@require_login
def submit_quiz():
    import json as _j
    uid = session["user_id"]
    with get_db() as conn:
        row = conn.execute("SELECT questions_json FROM bw_temp WHERE user_id=?", (uid,)).fetchone()
    qs         = _j.loads(row["questions_json"]) if row else []
    start      = session.get("quiz_start", time.time())
    time_taken = int(time.time() - start)
    tab_sw     = int(request.form.get("tab_switches", 0))
    score = 0; log = []; review = []
    for i, q in enumerate(qs):
        ans     = request.form.get(f"q{i}")
        u_ans   = int(ans) if ans is not None else -1
        correct = (u_ans == q["a"])
        if correct: score += 1
        log.append({"q":q["q"],"cat":q.get("cat","General"),"correct":int(correct),
                    "user_ans":u_ans,"correct_ans":q["a"],"time_spent":0})
        review.append({"q":q["q"],"options":q["options"],"user_ans":u_ans,
                       "correct_ans":q["a"],"correct":correct,"cat":q.get("cat","General")})
    total = len(qs)
    pct   = round((score/total)*100) if total else 0
    grade, msg = get_grade_msg(pct, "BeeWise")
    save_result(session["user_id"], "BeeWise", score, total, pct, grade, time_taken, log, tab_sw)
    streak  = update_streak(session["user_id"])
    new_ach = check_and_award(session["user_id"], {"pct":pct,"wrong":total-score,"mode":"BeeWise","time_taken":time_taken})
    with get_db() as conn:
        conn.execute("DELETE FROM bw_temp WHERE user_id=?", (uid,))
    for k in ("quiz_start","tab_switches"): session.pop(k, None)
    return render_template("result.html", mode="BeeWise", score=score, wrong=total-score,
                           total=total, pct=pct, grade=grade, msg=msg,
                           time_taken=time_taken, tab_switches=tab_sw,
                           review=review, new_achievements=new_ach, streak=streak)

# ── RapidBee ─────────────────────────────────────────────────────────
@app.route("/rapidbee", methods=["GET","POST"])
@require_login
def rapidbee():
    uid = session["user_id"]

    if request.method == "GET":
        qs = get_shuffled_questions(RAPID_LIMIT, balanced=True)
        # Store bulky data server-side, keep only index/score/timing in session
        with get_db() as conn:
            conn.execute("DELETE FROM rb_temp WHERE user_id=?", (uid,))
            conn.execute("""INSERT INTO rb_temp (user_id, questions_json, log_json, score, tabs)
                            VALUES (?,?,?,0,0)""",
                         (uid, __import__("json").dumps(qs), __import__("json").dumps([])))
        session["rb_index"]   = 0
        session["rb_end"]     = time.time() + RAPID_TIME
        session["rb_q_start"] = time.time()

    if request.method == "POST":
        import json
        with get_db() as conn:
            row = conn.execute("SELECT * FROM rb_temp WHERE user_id=?", (uid,)).fetchone()
        if not row:
            flash("Session expired. Starting over.", "error")
            return redirect("/rapidbee")
        qs    = __import__("json").loads(row["questions_json"])
        log   = __import__("json").loads(row["log_json"])
        index = session.get("rb_index", 0)
        spent = int(time.time() - session.get("rb_q_start", time.time()))
        ans   = request.form.get("ans")
        u_ans = int(ans) if ans is not None else -1
        correct = (u_ans == qs[index]["a"])
        log.append({"q": qs[index]["q"], "cat": qs[index].get("cat","General"),
                    "correct": int(correct), "user_ans": u_ans,
                    "correct_ans": qs[index]["a"], "time_spent": spent,
                    "opts": qs[index]["options"]})
        new_score = row["score"] + (1 if correct else 0)
        new_tabs  = int(request.form.get("tab_switches", 0))
        with get_db() as conn:
            conn.execute("UPDATE rb_temp SET log_json=?, score=?, tabs=? WHERE user_id=?",
                         (__import__("json").dumps(log), new_score, new_tabs, uid))
        session["rb_index"]   = index + 1
        session["rb_q_start"] = time.time()

    # Load current state
    import json
    with get_db() as conn:
        row = conn.execute("SELECT * FROM rb_temp WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return redirect("/rapidbee")
    qs    = json.loads(row["questions_json"])
    log   = json.loads(row["log_json"])
    score = row["score"]
    index = session.get("rb_index", 0)

    if index >= len(qs) or time.time() >= session["rb_end"]:
        total      = len(qs)
        time_taken = RAPID_TIME - max(0, int(session["rb_end"] - time.time()))
        tab_sw     = row["tabs"]
        pct        = round((score/total)*100) if total else 0
        grade, msg = get_grade_msg(pct, "RapidBee")
        review     = [{"q":e["q"],"options":e.get("opts",[]),"user_ans":e["user_ans"],
                       "correct_ans":e["correct_ans"],"correct":bool(e["correct"]),
                       "cat":e["cat"],"time_spent":e.get("time_spent",0)} for e in log]
        save_result(uid,"RapidBee",score,total,pct,grade,time_taken,log,tab_sw)
        streak  = update_streak(uid)
        new_ach = check_and_award(uid,{"pct":pct,"wrong":total-score,"mode":"RapidBee","time_taken":time_taken})
        with get_db() as conn:
            conn.execute("DELETE FROM rb_temp WHERE user_id=?", (uid,))
        session.pop("rb_index", None)
        session.pop("rb_end", None)
        session.pop("rb_q_start", None)
        return render_template("result.html", mode="RapidBee", score=score, wrong=total-score,
                               total=total, pct=pct, grade=grade, msg=msg,
                               time_taken=time_taken, tab_switches=tab_sw,
                               review=review, new_achievements=new_ach, streak=streak)

    q    = qs[index]
    left = max(0, int(session["rb_end"] - time.time()))
    return render_template("rapidbee.html", q=q, num=index+1,
                           total=len(qs), left=left)

# ── Practice ─────────────────────────────────────────────────────────
@app.route("/practice")
@require_login
def practice():
    import random
    cat    = request.args.get("cat","")
    chosen = int(request.args.get("timer", 180))
    chosen = max(30, min(chosen, 600))
    qcount = int(request.args.get("qcount", 10))
    qcount = qcount if qcount in (10,15,25) else 10

    if cat not in CATEGORIES:
        flash("Invalid category.", "error")
        return redirect("/mode")

    # If same category is already active and user just changed the timer,
    # only update the timer — don't wipe the questions or progress
    if (session.get("pr_cat") == cat
            and session.get("pr_qs")
            and request.args.get("timer")
            and session.get("pr_index", 0) > 0):
        session["pr_end"]      = time.time() + chosen
        session["pr_duration"] = chosen
        q    = session["pr_qs"][session["pr_index"]]
        left = chosen
        return render_template("practice.html", q=q,
                               num=session["pr_index"]+1,
                               total=len(session["pr_qs"]),
                               cat=cat, left=left, chosen=chosen,
                               qcount=len(session["pr_qs"]))

    # Fresh start
    for k in ("pr_qs","pr_index","pr_score","pr_end","pr_log","pr_q_start","pr_cat","pr_duration"):
        session.pop(k, None)

    pool     = [q for q in ALL_QUESTIONS if q["cat"] == cat]
    selected = random.sample(pool, min(qcount, len(pool)))
    final    = []
    for q in selected:
        opts    = q["options"][:]
        correct = q["options"][q["a"]]
        random.shuffle(opts)
        final.append({"q":q["q"],"options":opts,"a":opts.index(correct),"cat":cat})

    session["pr_qs"]       = final
    session["pr_cat"]      = cat
    session["pr_index"]    = 0
    session["pr_score"]    = 0
    session["pr_end"]      = time.time() + chosen
    session["pr_duration"] = chosen
    session["pr_log"]      = []
    session["pr_q_start"]  = time.time()

    return render_template("practice.html", q=final[0], num=1,
                           total=len(final), cat=cat, left=chosen,
                           chosen=chosen, qcount=qcount)

@app.route("/practice/set_timer")
@require_login
def practice_set_timer():
    """Update only the timer without restarting the quiz — called by JS fetch."""
    chosen = int(request.args.get("timer", 180))
    chosen = max(30, min(chosen, 600))
    session["pr_end"]      = time.time() + chosen
    session["pr_duration"] = chosen
    return {"ok": True}


@app.route("/submit_practice", methods=["POST"])
@require_login
def submit_practice():
    index   = session.get("pr_index", 0)
    qs      = session.get("pr_qs", [])
    cat     = session.get("pr_cat", "General")
    spent   = int(time.time() - session.get("pr_q_start", time.time()))
    ans     = request.form.get("ans")
    u_ans   = int(ans) if ans is not None else -1
    correct = (u_ans == qs[index]["a"])
    if correct:
        session["pr_score"] = session.get("pr_score", 0) + 1
    log = session.get("pr_log", [])
    log.append({"q": qs[index]["q"], "cat": cat, "correct": int(correct),
                "user_ans": u_ans, "correct_ans": qs[index]["a"], "time_spent": spent})
    session["pr_log"]     = log
    session["pr_index"]   = index + 1
    session["pr_q_start"] = time.time()

    # Check if done
    if session["pr_index"] >= len(qs) or time.time() >= session["pr_end"]:
        score      = session["pr_score"]
        total      = len(qs)
        pr_duration = session.get("pr_duration", 180)
        time_taken = pr_duration - max(0, int(session["pr_end"] - time.time()))
        pct        = round((score/total)*100) if total else 0
        grade, msg = get_grade_msg(pct, "Practice")
        review = [{"q":e["q"],"options":qs[i]["options"],"user_ans":e["user_ans"],
                   "correct_ans":e["correct_ans"],"correct":bool(e["correct"]),"cat":e["cat"]}
                  for i,e in enumerate(log)]
        save_result(session["user_id"], f"Practice:{cat}", score, total, pct, grade, time_taken, log)
        streak  = update_streak(session["user_id"])
        new_ach = check_and_award(session["user_id"],{"pct":pct,"wrong":total-score,
                  "mode":f"Practice:{cat}","time_taken":time_taken})
        for k in ("pr_qs","pr_index","pr_score","pr_end","pr_log","pr_q_start","pr_cat"):
            session.pop(k, None)
        return render_template("result.html", mode=f"Practice — {cat}", score=score,
                               wrong=total-score, total=total, pct=pct, grade=grade,
                               msg=msg, time_taken=time_taken, tab_switches=0,
                               review=review, new_achievements=new_ach, streak=streak)

    # Next question
    q    = qs[session["pr_index"]]
    left = max(0, int(session["pr_end"] - time.time()))
    return render_template("practice.html", q=q, num=session["pr_index"]+1,
                           total=len(qs), cat=cat, left=left)

# ── Leaderboard ──────────────────────────────────────────────────────
@app.route("/leaderboard")
@require_login
def leaderboard():
    with get_db() as conn:
        top_pct = conn.execute("""
            SELECT u.username, u.avatar, MAX(r.pct) as best_pct, COUNT(r.id) as games
            FROM results r JOIN users u ON u.id=r.user_id
            WHERE u.is_admin=0 GROUP BY r.user_id ORDER BY best_pct DESC LIMIT 10
        """).fetchall()
        top_games = conn.execute("""
            SELECT u.username, u.avatar, COUNT(r.id) as games, ROUND(AVG(r.pct)) as avg_pct
            FROM results r JOIN users u ON u.id=r.user_id
            WHERE u.is_admin=0 GROUP BY r.user_id ORDER BY games DESC LIMIT 10
        """).fetchall()
        top_streak = conn.execute("""
            SELECT username, avatar, streak FROM users
            WHERE is_admin=0 AND streak > 0 ORDER BY streak DESC LIMIT 10
        """).fetchall()
    return render_template("leaderboard.html", top_pct=top_pct,
                           top_games=top_games, top_streak=top_streak)

# ── Admin ─────────────────────────────────────────────────────────────
@app.route("/admin")
@require_login
@require_admin
def admin():
    with get_db() as conn:
        students = conn.execute("""
            SELECT u.id, u.username, u.avatar, u.created, u.streak,
                   COUNT(r.id) as games, ROUND(AVG(r.pct)) as avg_pct,
                   MAX(r.pct) as best_pct, MAX(r.tab_switches) as max_tabs
            FROM users u LEFT JOIN results r ON r.user_id=u.id
            WHERE u.is_admin=0 GROUP BY u.id ORDER BY u.username
        """).fetchall()
        hardest = conn.execute("""
            SELECT al.question, al.category, COUNT(*) as attempts,
                   ROUND(SUM(CASE WHEN al.correct=0 THEN 1.0 END)/COUNT(*)*100) as fail_pct
            FROM answer_log al GROUP BY al.question
            HAVING attempts >= 3 ORDER BY fail_pct DESC LIMIT 10
        """).fetchall()
        flagged = conn.execute("""
            SELECT u.username, r.mode, r.tab_switches, r.pct, r.played_at
            FROM results r JOIN users u ON u.id=r.user_id
            WHERE r.tab_switches > 0 ORDER BY r.tab_switches DESC LIMIT 20
        """).fetchall()
        recent_results = conn.execute("""
            SELECT u.username, r.mode, r.pct, r.tab_switches, r.played_at
            FROM results r JOIN users u ON u.id=r.user_id
            WHERE u.is_admin=0
            ORDER BY r.played_at DESC LIMIT 25
        """).fetchall()
        total_games = conn.execute("SELECT COUNT(*) as c FROM results").fetchone()["c"]
        total_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()["c"]
        db_questions = conn.execute("SELECT * FROM questions_db ORDER BY created DESC").fetchall()
        cat_performance = conn.execute("""
            SELECT al.category, COUNT(*) as total, SUM(al.correct) as correct,
                   ROUND(SUM(al.correct)*100.0/COUNT(*)) as pct
            FROM answer_log al GROUP BY al.category ORDER BY pct ASC
        """).fetchall()
        exams = conn.execute("SELECT * FROM exam_sessions ORDER BY created DESC LIMIT 20").fetchall()
        classes = conn.execute("""
            SELECT c.id, c.name, c.code, c.created, COUNT(cm.user_id) as member_count
            FROM classes c LEFT JOIN class_members cm ON cm.class_id=c.id
            GROUP BY c.id ORDER BY c.created DESC
        """).fetchall()
        quiz_rooms = conn.execute("""
            SELECT qr.id, qr.title, qr.code, qr.time_limit, qr.created,
                   LENGTH(qr.questions) as qs_len,
                   COUNT(rr.id) as submission_count
            FROM quiz_rooms qr
            LEFT JOIN room_results rr ON rr.room_id = qr.id
            WHERE qr.active=1
            GROUP BY qr.id ORDER BY qr.created DESC
        """).fetchall()
        # Add question count to each room
        import json as _j
        quiz_rooms_list = []
        for room in quiz_rooms:
            r = dict(room)
            try:
                qs = _j.loads(conn.execute("SELECT questions FROM quiz_rooms WHERE id=?", (r["id"],)).fetchone()["questions"])
                r["q_count"] = len(qs)
            except:
                r["q_count"] = "?"
            quiz_rooms_list.append(r)
        quiz_rooms = quiz_rooms_list
        # For each class, get member details with their stats
        class_members_detail = {}
        for cl in classes:
            members = conn.execute("""
                SELECT u.id, u.username, u.avatar,
                       COUNT(r.id) as games,
                       ROUND(AVG(r.pct),1) as avg_pct,
                       MAX(r.pct) as best_pct
                FROM class_members cm
                JOIN users u ON u.id = cm.user_id
                LEFT JOIN results r ON r.user_id = u.id
                WHERE cm.class_id = ?
                GROUP BY u.id ORDER BY best_pct DESC
            """, (cl["id"],)).fetchall()
            class_members_detail[cl["id"]] = [dict(m) for m in members]
    init_beexam()
    with get_db() as conn:
        beexam_papers = conn.execute(
            "SELECT * FROM beexam_papers ORDER BY exam_name, year DESC"
        ).fetchall()
        beexam_exam_types_raw = conn.execute(
            "SELECT * FROM beexam_exam_types ORDER BY name"
        ).fetchall()
    # Attach paper count to each exam type
    count_map = {}
    for p in beexam_papers:
        count_map[p["exam_name"]] = count_map.get(p["exam_name"], 0) + 1
    beexam_exam_types = [{"name": et["name"], "group": et["exam_group"],
                          "paper_count": count_map.get(et["name"], 0)} for et in beexam_exam_types_raw]
    with get_db() as conn:
        jigsaw_levels = conn.execute(
            "SELECT * FROM jigsaw_levels ORDER BY order_num ASC"
        ).fetchall()
    return render_template("admin.html", students=students, hardest=hardest,
                           flagged=flagged, recent_results=recent_results,
                           total_games=total_games, total_users=total_users,
                           db_questions=db_questions, cat_performance=cat_performance,
                           exams=exams, classes=classes,
                           class_members_detail=class_members_detail,
                           quiz_rooms=quiz_rooms,
                           beexam_papers=beexam_papers,
                           beexam_exam_types=beexam_exam_types,
                           jigsaw_levels=jigsaw_levels,
                           categories=["HTML","CSS","Python","SQL","Flask","General"])

@app.route("/admin/student/<int:uid>")
@require_login
@require_admin
def student_report(uid):
    with get_db() as conn:
        student = conn.execute("SELECT * FROM users WHERE id=? AND is_admin=0", (uid,)).fetchone()
        if not student: flash("Student not found.", "error"); return redirect("/admin")
        results = conn.execute(
            "SELECT * FROM results WHERE user_id=? ORDER BY played_at DESC", (uid,)).fetchall()
        stats = conn.execute(
            "SELECT COUNT(*) as games, ROUND(AVG(pct)) as avg_pct, MAX(pct) as best, MIN(pct) as worst, SUM(time_taken) as total_time FROM results WHERE user_id=?",
            (uid,)).fetchone()
        cat_stats = conn.execute("""
            SELECT al.category, COUNT(*) as total, SUM(al.correct) as correct,
                   ROUND(AVG(al.correct)*100) as pct
            FROM answer_log al JOIN results r ON r.id=al.result_id
            WHERE r.user_id=? GROUP BY al.category ORDER BY pct DESC
        """, (uid,)).fetchall()
        earned = conn.execute(
            "SELECT ach_id, earned_at FROM achievements WHERE user_id=? ORDER BY earned_at DESC",
            (uid,)).fetchall()
        progress = list(reversed(conn.execute(
            "SELECT pct, mode, played_at FROM results WHERE user_id=? ORDER BY played_at DESC LIMIT 15",
            (uid,)).fetchall()))
    return render_template("student_report.html", student=student, results=results,
                           stats=stats, cat_stats=cat_stats, earned=earned,
                           ach_map=ACH_MAP, progress=progress)

@app.route("/admin/export_csv")
@require_login
@require_admin
def export_csv():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.username, r.mode, r.score, r.total, r.pct, r.grade,
                   r.time_taken, r.tab_switches, r.played_at
            FROM results r JOIN users u ON u.id=r.user_id
            WHERE u.is_admin=0 ORDER BY r.played_at DESC
        """).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Username","Mode","Score","Total","Percentage","Grade","Time(s)","Tab Switches","Date"])
    for r in rows:
        writer.writerow([r["username"],r["mode"],r["score"],r["total"],
                         f"{r['pct']}%",r["grade"],r["time_taken"],r["tab_switches"],r["played_at"]])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment;filename=beewise_results.csv"})

@app.route("/admin/add_question", methods=["POST"])
@require_login
@require_admin
def add_question():
    q,o0,o1,o2,o3 = (request.form.get(k,"").strip() for k in ("question","opt0","opt1","opt2","opt3"))
    cat = request.form.get("category","General")
    if not all([q,o0,o1,o2,o3]):
        flash("All fields are required.", "error"); return redirect("/admin")
    with get_db() as conn:
        conn.execute("INSERT INTO questions_db (question,opt0,opt1,opt2,opt3,answer,category) VALUES (?,?,?,?,?,?,?)",
                     (q,o0,o1,o2,o3,0,cat))
    flash(f"Question added to {cat}! 🐝", "success")
    return redirect("/admin")

@app.route("/admin/import_csv", methods=["POST"])
@require_login
@require_admin
def import_csv():
    f = request.files.get("csv_file")
    if not f or not f.filename.endswith(".csv"):
        flash("Please upload a .csv file.", "error"); return redirect("/admin")
    stream = io.StringIO(f.stream.read().decode("utf-8"), newline=None)
    reader = csv.DictReader(stream)
    count = errors = 0
    with get_db() as conn:
        for row in reader:
            try:
                q,o0,o1,o2,o3 = (row.get(k,"").strip() for k in ("question","opt0","opt1","opt2","opt3"))
                cat = row.get("category","General").strip()
                if not all([q,o0,o1,o2,o3]): errors+=1; continue
                conn.execute("INSERT INTO questions_db (question,opt0,opt1,opt2,opt3,answer,category) VALUES (?,?,?,?,?,?,?)",
                             (q,o0,o1,o2,o3,0,cat))
                count += 1
            except: errors += 1
    flash(f"Imported {count} questions! ✅" + (f" ({errors} skipped)" if errors else ""), "success")
    return redirect("/admin")

@app.route("/admin/delete_question/<int:qid>", methods=["POST"])
@require_login
@require_admin
def delete_question(qid):
    with get_db() as conn: conn.execute("DELETE FROM questions_db WHERE id=?", (qid,))
    flash("Question deleted.", "success"); return redirect("/admin")

@app.route("/admin/delete_student/<int:uid>", methods=["POST"])
@require_login
@require_admin
def delete_student(uid):
    with get_db() as conn:
        conn.execute("DELETE FROM answer_log WHERE result_id IN (SELECT id FROM results WHERE user_id=?)",(uid,))
        conn.execute("DELETE FROM results WHERE user_id=?",(uid,))
        conn.execute("DELETE FROM achievements WHERE user_id=?",(uid,))
        conn.execute("DELETE FROM users WHERE id=? AND is_admin=0",(uid,))
    flash("Student removed.", "success"); return redirect("/admin")

@app.route("/admin/create_exam", methods=["POST"])
@require_login
@require_admin
def create_exam():
    title,start,end = (request.form.get(k,"").strip() for k in ("title","start_time","end_time"))
    if not all([title,start,end]):
        flash("All fields required.", "error"); return redirect("/admin")
    with get_db() as conn:
        conn.execute("INSERT INTO exam_sessions (title,start_time,end_time,created_by) VALUES (?,?,?,?)",
                     (title,start,end,session["user_id"]))
    flash(f"Exam '{title}' scheduled! 🎓", "success"); return redirect("/admin")

@app.route("/admin/delete_exam/<int:eid>", methods=["POST"])
@require_login
@require_admin
def delete_exam(eid):
    with get_db() as conn: conn.execute("DELETE FROM exam_sessions WHERE id=?", (eid,))
    flash("Exam deleted.", "success"); return redirect("/admin")

# ════════════════════════════════════════════════════════════════════
# AI FEATURE 1 — AI Question Generator (Admin only)
# ════════════════════════════════════════════════════════════════════
@app.route("/admin/ai_generate", methods=["POST"])
@require_login
@require_admin
def ai_generate_questions():
    topic    = request.form.get("topic", "").strip()
    category = request.form.get("ai_category", "General")
    count    = min(int(request.form.get("count", 5)), 10)

    if not topic:
        return jsonify({"error": "Please describe a topic first."}), 400

    questions, err = generate_questions(topic, category, count)
    if err:
        return jsonify({"error": err}), 200

    # Save to DB
    saved = 0
    with get_db() as conn:
        for q in questions:
            try:
                conn.execute(
                    "INSERT INTO questions_db (question,opt0,opt1,opt2,opt3,answer,category) VALUES (?,?,?,?,?,?,?)",
                    (q["question"], q["opt0"], q["opt1"], q["opt2"], q["opt3"], 0, category)
                )
                saved += 1
            except Exception:
                pass

    return jsonify({"success": True, "saved": saved, "questions": questions})


# ════════════════════════════════════════════════════════════════════
# AI FEATURE 2 — AI Study Buddy (Student chat)
# ════════════════════════════════════════════════════════════════════
@app.route("/ai_chat", methods=["POST"])
@require_login
def ai_chat():
    message = request.form.get("message", "").strip()
    if not message:
        return jsonify({"error": "Say something!"}), 400

    # Get student's category performance to personalise responses
    with get_db() as conn:
        cat_stats = conn.execute("""
            SELECT al.category, ROUND(AVG(al.correct)*100) as pct
            FROM answer_log al
            JOIN results r ON r.id = al.result_id
            WHERE r.user_id = ?
            GROUP BY al.category ORDER BY pct ASC
        """, (session["user_id"],)).fetchall()
        total_games = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=?",
            (session["user_id"],)).fetchone()["c"]

    weak = [f"{r['category']} ({r['pct']}%)" for r in cat_stats if r['pct'] and r['pct'] < 70]
    strong = [f"{r['category']} ({r['pct']}%)" for r in cat_stats if r['pct'] and r['pct'] >= 70]

    reply, err = beebot_reply(session["username"], message,
                              weak_cats=weak, strong_cats=strong,
                              total_games=total_games)
    if err:
        return jsonify({"error": err}), 200

    # Award BeeBot achievements
    with get_db() as _c:
        _c.execute("INSERT OR IGNORE INTO achievements (user_id, ach_id) VALUES (?,?)",
                   (session["user_id"], "ask_beebot"))
        _c.execute("INSERT OR IGNORE INTO achievements (user_id, ach_id) VALUES (?,?)",
                   (session["user_id"], "beebot_first_reply"))
        beebot_asks = _c.execute(
            "SELECT COUNT(*) as c FROM achievements WHERE user_id=? AND ach_id='ask_beebot'",
            (session["user_id"],)).fetchone()["c"]
    if beebot_asks >= 10:
        with get_db() as _c:
            _c.execute("INSERT OR IGNORE INTO achievements (user_id, ach_id) VALUES (?,?)",
                       (session["user_id"], "beebot_10"))

    return jsonify({"reply": reply})



# ── CustomizeBee Mode ────────────────────────────────────────────────────────
@app.route("/customizebee", methods=["GET","POST"])
@require_login
def customizebee():
    """CustomizeBee setup page — upload CSV or generate via AI."""
    return render_template("customizebee.html")

@app.route("/customizebee/pick_format")
@require_login
def customizebee_pick_format():
    """Show format picker for CustomizeBee."""
    import json as _j
    uid = session["user_id"]
    with get_db() as conn:
        row = conn.execute("SELECT total FROM cb_sessions WHERE user_id=?", (uid,)).fetchone()
    if not row:
        flash("No questions loaded yet.", "error")
        return redirect("/customizebee")
    return render_template("format_picker.html",
        mode="customizebee",
        beewise_url="/customizebee/quiz?fmt=beewise",
        rapidbee_url="/customizebee/quiz?fmt=rapidbee",
        back_url="/customizebee")

@app.route("/customizebee/from_csv", methods=["POST"])
@require_login
def customizebee_csv():
    """Load questions from uploaded CSV and start a custom quiz."""
    import csv, io, random
    f = request.files.get("csvfile")
    if not f or f.filename == "":
        flash("Please upload a CSV file.", "error")
        return redirect("/customizebee")
    try:
        raw = f.stream.read()
        # Try utf-8-sig first (handles BOM), fallback to latin-1
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                content = raw.decode(enc)
                break
            except Exception:
                continue
        # Fix Windows line endings and common unicode issues
        content = content.replace("\r\n","\n").replace("\r","\n")
        content = content.replace("\u2019","'").replace("\u2018","'")
        content = content.replace("\u201c",'"').replace("\u201d",'"')
        content = content.replace("\u2013","-").replace("\u2014","-")
        content = content.replace("\ufffd","")

        stream = io.StringIO(content)
        reader = csv.DictReader(stream)
        # Normalise headers — strip spaces and lowercase
        if reader.fieldnames:
            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

        questions = []
        errors    = []
        for i, row in enumerate(reader, 1):
            try:
                # Accept both "opt0" and "option1/option2..." style headers
                q   = (row.get("question") or row.get("q","")).strip()
                o0  = (row.get("opt0") or row.get("option1") or row.get("correct","")).strip()
                o1  = (row.get("opt1") or row.get("option2","")).strip()
                o2  = (row.get("opt2") or row.get("option3","")).strip()
                o3  = (row.get("opt3") or row.get("option4","")).strip()
                cat = (row.get("category") or row.get("subject","Custom")).strip() or "Custom"

                if not q:
                    errors.append(f"Row {i}: empty question")
                    continue
                if not o0:
                    errors.append(f"Row {i}: missing correct answer (opt0)")
                    continue
                if not o1:
                    errors.append(f"Row {i}: need at least 2 options")
                    continue

                opts    = [x for x in [o0,o1,o2,o3] if x]
                correct = o0
                random.shuffle(opts)
                # Pad to 4 if less
                while len(opts) < 4:
                    opts.append(opts[-1])
                questions.append({
                    "q":       q,
                    "options": opts,
                    "a":       opts.index(correct),
                    "cat":     cat
                })
            except Exception as e:
                errors.append(f"Row {i}: {e}")

        if not questions:
            err_preview = "; ".join(errors[:3]) if errors else "Check that your CSV has: question, opt0, opt1, opt2, opt3 columns"
            flash(f"No valid questions found. {err_preview}", "error")
            return redirect("/customizebee")

        questions = questions[:100]
        import json as _json
        end_time = time.time() + 600
        with get_db() as conn:
            conn.execute("""INSERT OR REPLACE INTO cb_sessions
                (user_id, questions, idx, score, log, total, end_time)
                VALUES (?,?,0,0,'[]',?,?)""",
                (session["user_id"], _json.dumps(questions), len(questions), end_time))
        session["cb_active"] = True
        msg = f"Loaded {len(questions)} questions!"
        if errors:
            msg += f" ({len(errors)} rows skipped)"
        flash(msg, "success")
        # Award CSV upload achievements
        with get_db() as _c:
            _c.execute("INSERT OR IGNORE INTO achievements (user_id, ach_id) VALUES (?,?)",
                       (session["user_id"], "try_customizebee"))
            _c.execute("INSERT OR IGNORE INTO achievements (user_id, ach_id) VALUES (?,?)",
                       (session["user_id"], "first_csv_upload"))
        return redirect("/customizebee/pick_format")
    except Exception as e:
        flash(f"Could not read CSV: {str(e)}", "error")
        return redirect("/customizebee")

@app.route("/customizebee/from_ai", methods=["POST"])
@require_login
def customizebee_ai():
    """Generate questions via AI and start a custom quiz."""
    from ai import generate_questions
    import random
    topic    = request.form.get("topic","").strip()
    count    = int(request.form.get("count","10"))
    count    = max(5, min(count, 25))
    if not topic:
        flash("Please enter a topic.", "error")
        return redirect("/customizebee")
    questions, err = generate_questions(topic, "Custom", count)
    if err or not questions:
        flash(f"AI could not generate questions: {err or 'No questions returned. Try a different topic.'}", "error")
        return redirect("/customizebee")
    final = []
    for q in questions:
        opts = [q["opt0"], q["opt1"], q["opt2"], q["opt3"]]
        correct = q["opt0"]
        random.shuffle(opts)
        final.append({
            "q":       q["question"],
            "options": opts,
            "a":       opts.index(correct),
            "cat":     "Custom"
        })
    final = final[:100]
    import json as _json
    end_time = time.time() + 600
    with get_db() as conn:
        conn.execute("""INSERT OR REPLACE INTO cb_sessions
            (user_id, questions, idx, score, log, total, end_time)
            VALUES (?,?,0,0,'[]',?,?)""",
            (session["user_id"], _json.dumps(final), len(final), end_time))
    session["cb_active"] = True
    return redirect("/customizebee/pick_format")

@app.route("/customizebee/quiz", methods=["GET","POST"])
@require_login
def customizebee_quiz():
    """Run the custom quiz — supports beewise (all at once) and rapidbee (one at a time) formats."""
    import json as _j
    uid = session["user_id"]

    with get_db() as conn:
        row = conn.execute("SELECT * FROM cb_sessions WHERE user_id=?", (uid,)).fetchone()

    if not row:
        flash("No questions loaded. Please upload a CSV or generate via AI.", "error")
        return redirect("/customizebee")

    qs    = _j.loads(row["questions"])
    idx   = row["idx"]
    score = row["score"]
    log   = _j.loads(row["log"])
    total = row["total"]
    end_t = row["end_time"]

    # Get or set format — default to beewise
    fmt = request.args.get("fmt") or session.get("cb_fmt","beewise")
    if request.args.get("fmt"):
        session["cb_fmt"] = fmt

    # ── BEEWISE FORMAT (all questions at once) ────────────────────────
    if fmt == "beewise":
        if request.method == "POST":
            score = 0
            log   = []
            for i, q in enumerate(qs):
                chosen = int(request.form.get(f"q{i}", -1))
                correct = (chosen == q["a"])
                if correct: score += 1
                log.append({"q":q["q"],"options":q["options"],"chosen":chosen,"correct":q["a"],"cat":q.get("cat","Custom")})
            with get_db() as conn:
                conn.execute("DELETE FROM cb_sessions WHERE user_id=?", (uid,))
            session.pop("cb_fmt", None)
            pct = round(score / total * 100) if total else 0
            return render_template("customizebee_result.html", score=score, total=total, pct=pct, log=log)

        left = max(0, int(end_t - time.time()))
        return render_template("customizebee_beewise.html", questions=qs, total=total, left=left)

    # ── RAPIDBEE FORMAT (one at a time) ──────────────────────────────
    if request.method == "POST":
        q      = qs[idx]
        chosen = int(request.form.get("answer", -1))
        if chosen == q["a"]: score += 1
        log.append({"q":q["q"],"options":q["options"],"chosen":chosen,"correct":q["a"],"cat":q.get("cat","Custom")})
        idx += 1
        with get_db() as conn:
            conn.execute("UPDATE cb_sessions SET idx=?,score=?,log=? WHERE user_id=?",
                         (idx, score, _j.dumps(log), uid))

    if idx >= total or time.time() > end_t:
        pct = round(score / total * 100) if total else 0
        with get_db() as conn:
            conn.execute("DELETE FROM cb_sessions WHERE user_id=?", (uid,))
        session.pop("cb_fmt", None)
        return render_template("customizebee_result.html", score=score, total=total, pct=pct, log=log)

    q    = qs[idx]
    left = max(0, int(end_t - time.time()))
    return render_template("customizebee_quiz.html", q=q, num=idx+1, total=total, left=left)

# ── Edit question ─────────────────────────────────────────────────────
@app.route("/admin/edit_question/<int:qid>", methods=["POST"])
@require_login
@require_admin
def edit_question(qid):
    q   = request.form.get("question","").strip()
    o0  = request.form.get("opt0","").strip()
    o1  = request.form.get("opt1","").strip()
    o2  = request.form.get("opt2","").strip()
    o3  = request.form.get("opt3","").strip()
    cat = request.form.get("category","General")
    diff = request.form.get("difficulty","Medium")
    if not all([q, o0, o1, o2, o3]):
        flash("All fields are required.", "error")
        return redirect("/admin")
    with get_db() as conn:
        conn.execute("UPDATE questions_db SET question=?,opt0=?,opt1=?,opt2=?,opt3=?,category=? WHERE id=?",
                     (q, o0, o1, o2, o3, cat, qid))
    flash("Question updated! 🐝", "success")
    return redirect("/admin")

# ── Class code system ─────────────────────────────────────────────────
def init_classes():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS classes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                code       TEXT UNIQUE NOT NULL,
                created_by INTEGER NOT NULL,
                admin_id   INTEGER,
                created    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS class_members (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                joined   TEXT DEFAULT (datetime('now')),
                UNIQUE(class_id, user_id)
            );
        """)
        # Migration: add admin_id if missing (for existing databases)
        try:
            conn.execute("ALTER TABLE classes ADD COLUMN admin_id INTEGER")
        except: pass
        # Backfill admin_id from created_by for existing rows
        conn.execute("UPDATE classes SET admin_id=created_by WHERE admin_id IS NULL")
init_classes()

@app.route("/admin/create_class", methods=["GET","POST"])
@require_login
@require_admin
def create_class():
    if request.method == "GET":
        return redirect("/admin?tab=classes")
    import random as _rnd, string as _str
    name = request.form.get("class_name","").strip()
    if not name:
        flash("Class name is required.", "error")
        return redirect("/admin?tab=classes")
    code = ''.join(_rnd.choices(_str.ascii_uppercase + _str.digits, k=6))
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO classes (name,code,created_by,admin_id) VALUES (?,?,?,?)",
                         (name, code, session["user_id"], session["user_id"]))
        flash(f"Class '{name}' created! Share this code with students: {code} 🎓", "success")
    except Exception as e:
        flash(f"Error creating class: {str(e)}", "error")
    return redirect("/admin?tab=classes")

@app.route("/admin/delete_class/<int:cid>", methods=["POST"])
@require_login
@require_admin
def delete_class(cid):
    with get_db() as conn:
        conn.execute("DELETE FROM class_members WHERE class_id=?", (cid,))
        conn.execute("DELETE FROM classes WHERE id=?", (cid,))
    flash("Class deleted.", "success")
    return redirect("/admin?tab=classes")

@app.route("/join_class", methods=["POST"])
@require_login
def join_class():
    code = request.form.get("class_code","").strip().upper()
    with get_db() as conn:
        cls = conn.execute("SELECT * FROM classes WHERE code=?", (code,)).fetchone()
        if not cls:
            flash("Invalid class code. Check and try again.", "error")
            return redirect("/profile")
        try:
            conn.execute("INSERT INTO class_members (class_id,user_id) VALUES (?,?)",
                         (cls["id"], session["user_id"]))
            flash(f"Joined class '{cls['name']}'! 🎓", "success")
        except:
            flash("You are already in this class.", "error")
    return redirect("/profile")

@app.route("/leave_class/<int:cid>", methods=["POST"])
@require_login
def leave_class(cid):
    with get_db() as conn:
        conn.execute("DELETE FROM class_members WHERE class_id=? AND user_id=?",
                     (cid, session["user_id"]))
    flash("Left class.", "success")
    return redirect("/profile")

# ══════════════════════════════════════════════════════════════════════════════
# QUIZ ROOM — Teacher creates a room, students join with a code
# Each student gets a SHUFFLED version — different order every time
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/admin/create_room", methods=["GET","POST"])
@require_login
@require_admin
def create_room():
    if request.method == "GET":
        return redirect("/admin?tab=rooms")
    import random as _r, string as _s, json as _j, csv as _csv, io as _io

    title      = request.form.get("room_title","").strip()
    time_limit = int(request.form.get("time_limit", 30))
    source     = request.form.get("source","csv")

    if not title:
        flash("Room title is required.", "error")
        return redirect("/admin?tab=rooms")

    questions = []

    if source == "csv":
        f = request.files.get("room_csv")
        if not f or f.filename == "":
            flash("Please upload a CSV file.", "error")
            return redirect("/admin?tab=rooms")
        try:
            raw = f.stream.read()
            for enc in ("utf-8-sig","utf-8","latin-1"):
                try: content = raw.decode(enc); break
                except: continue
            content = content.replace("\r\n","\n").replace("\r","\n")
            content = content.replace("\u2019","'").replace("\u2018","'")
            content = content.replace("\u201c",'"').replace("\u201d",'"')
            content = content.replace("\u2013","-").replace("\ufffd","")
            reader = _csv.DictReader(_io.StringIO(content))
            if reader.fieldnames:
                reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
            for row in reader:
                q  = (row.get("question") or "").strip()
                o0 = (row.get("opt0") or row.get("correct","")).strip()
                o1 = (row.get("opt1","")).strip()
                o2 = (row.get("opt2","")).strip()
                o3 = (row.get("opt3","")).strip()
                if q and o0 and o1:
                    questions.append({
                        "q": q,
                        "correct": o0,
                        "options_raw": [o for o in [o0,o1,o2,o3] if o]
                    })
        except Exception as e:
            flash(f"CSV error: {e}", "error")
            return redirect("/admin?tab=rooms")

    if not questions:
        flash("No valid questions found in the CSV.", "error")
        return redirect("/admin?tab=rooms")

    # Store RAW questions (unshuffled) — shuffling happens per student at quiz time
    code = ''.join(_r.choices(_s.ascii_uppercase + _s.digits, k=6))
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO quiz_rooms (title,code,created_by,questions,time_limit) VALUES (?,?,?,?,?)",
                (title, code, session["user_id"], _j.dumps(questions), time_limit)
            )
        flash(f"Room '{title}' created! Code: {code}", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect("/admin?tab=rooms")

@app.route("/admin/delete_room/<int:rid>", methods=["POST"])
@require_login
@require_admin
def delete_room(rid):
    with get_db() as conn:
        conn.execute("DELETE FROM room_results WHERE room_id=?", (rid,))
        conn.execute("DELETE FROM quiz_rooms WHERE id=?", (rid,))
    flash("Room deleted.", "success")
    return redirect("/admin?tab=rooms")

@app.route("/admin/room_results/<int:rid>")
@require_login
@require_admin
def admin_room_results(rid):
    with get_db() as conn:
        room = conn.execute("SELECT * FROM quiz_rooms WHERE id=?", (rid,)).fetchone()
        if not room:
            flash("Room not found.", "error")
            return redirect("/admin?tab=rooms")
        results = conn.execute("""
            SELECT u.username, u.avatar, rr.score, rr.total, rr.pct,
                   rr.time_taken, rr.finished
            FROM room_results rr
            JOIN users u ON u.id = rr.user_id
            WHERE rr.room_id = ?
            ORDER BY rr.pct DESC, rr.time_taken ASC
        """, (rid,)).fetchall()
    return render_template("room_results.html", room=room, results=results)

@app.route("/room", methods=["GET","POST"])
@require_login
def room_join():
    """Student enters a room code to start the quiz."""
    if request.method == "POST":
        code = request.form.get("room_code","").strip().upper()
        with get_db() as conn:
            room = conn.execute(
                "SELECT * FROM quiz_rooms WHERE code=? AND active=1", (code,)
            ).fetchone()
        if not room:
            flash("Room not found. Check the code and try again.", "error")
            return redirect("/room")
        # Check already submitted
        with get_db() as conn:
            already = conn.execute(
                "SELECT id FROM room_results WHERE room_id=? AND user_id=?",
                (room["id"], session["user_id"])
            ).fetchone()
        if already:
            flash("You have already completed this quiz room.", "error")
            return redirect("/room")
        return redirect(f"/room/{room['id']}/start")
    return render_template("room_join.html")

@app.route("/room/<int:rid>/start")
@require_login
def room_start(rid):
    """Shuffle questions uniquely for this student and begin."""
    import random, json as _j
    with get_db() as conn:
        room = conn.execute("SELECT * FROM quiz_rooms WHERE id=? AND active=1",(rid,)).fetchone()
    if not room:
        flash("Room not found or no longer active.", "error")
        return redirect("/room")
    already = False
    with get_db() as conn:
        already = conn.execute(
            "SELECT id FROM room_results WHERE room_id=? AND user_id=?",
            (rid, session["user_id"])
        ).fetchone()
    if already:
        flash("You already completed this room.", "error")
        return redirect("/mode")

    raw_qs = _j.loads(room["questions"])

    # ── SHUFFLE SYSTEM ──────────────────────────────────────────────────
    # 1. Shuffle the ORDER of questions
    random.shuffle(raw_qs)
    # 2. For each question, shuffle the OPTIONS independently
    final = []
    for q in raw_qs:
        opts    = q["options_raw"][:]
        correct = q["correct"]
        random.shuffle(opts)
        # Pad to 4 if needed
        while len(opts) < 4:
            opts.append(opts[-1])
        final.append({
            "q":       q["q"],
            "options": opts,
            "a":       opts.index(correct) if correct in opts else 0,
            "cat":     "Quiz Room"
        })
    # ───────────────────────────────────────────────────────────────────

    import json as _j2
    start_t = time.time()
    end_t   = start_t + room["time_limit"] * len(final)
    with get_db() as conn:
        conn.execute("""INSERT OR REPLACE INTO room_quiz_sessions
            (user_id, room_id, room_title, questions, idx, score, total, start_time, end_time)
            VALUES (?,?,?,?,0,0,?,?,?)""",
            (session["user_id"], rid, room["title"],
             _j2.dumps(final), len(final), start_t, end_t))
    session["rq_active"] = rid
    # Go to format picker
    with get_db() as conn:
        room = conn.execute("SELECT title FROM quiz_rooms WHERE id=?", (rid,)).fetchone()
    return render_template("format_picker.html",
        mode="room",
        room_title=room["title"] if room else "Quiz Room",
        beewise_url=f"/room/quiz?fmt=beewise",
        rapidbee_url=f"/room/quiz?fmt=rapidbee",
        back_url="/room")

@app.route("/room/quiz", methods=["GET","POST"])
@require_login
def room_quiz():
    import json as _j3
    uid = session["user_id"]

    with get_db() as conn:
        row = conn.execute("SELECT * FROM room_quiz_sessions WHERE user_id=?", (uid,)).fetchone()

    if not row:
        flash("No active room session.", "error")
        return redirect("/room")

    qs      = _j3.loads(row["questions"])
    idx     = row["idx"]
    score   = row["score"]
    total   = row["total"]
    rid     = row["room_id"]
    title   = row["room_title"]
    start_t = row["start_time"]
    end_t   = row["end_time"]

    fmt = request.args.get("fmt") or session.get("rq_fmt","rapidbee")
    if request.args.get("fmt"):
        session["rq_fmt"] = fmt

    def finish_room(sc):
        pct        = round(sc / total * 100) if total else 0
        time_taken = int(time.time() - start_t)
        with get_db() as conn2:
            try:
                conn2.execute("INSERT INTO room_results (room_id,user_id,score,total,pct,time_taken) VALUES (?,?,?,?,?,?)",
                              (rid, uid, sc, total, pct, time_taken))
            except: pass
            conn2.execute("DELETE FROM room_quiz_sessions WHERE user_id=?", (uid,))
        session.pop("rq_active", None); session.pop("rq_fmt", None)
        return render_template("room_result.html", score=sc, total=total, pct=pct,
                               time_taken=time_taken, title=title, rid=rid)

    # ── BEEWISE FORMAT ────────────────────────────────────────────────
    if fmt == "beewise":
        if request.method == "POST":
            sc = 0
            for i, q in enumerate(qs):
                chosen = int(request.form.get(f"q{i}", -1))
                if chosen == q["a"]: sc += 1
            return finish_room(sc)
        left = max(0, int(end_t - time.time()))
        return render_template("room_beewise.html", questions=qs, total=total, left=left, title=title)

    # ── RAPIDBEE FORMAT ───────────────────────────────────────────────
    if request.method == "POST":
        chosen = int(request.form.get("answer", -1))
        if chosen == qs[idx]["a"]: score += 1
        idx += 1
        with get_db() as conn:
            conn.execute("UPDATE room_quiz_sessions SET idx=?,score=? WHERE user_id=?", (idx, score, uid))

    if idx >= total or time.time() > end_t:
        return finish_room(score)

    q    = qs[idx]
    left = max(0, int(end_t - time.time()))
    return render_template("room_quiz.html", q=q, num=idx+1, total=total, left=left, title=title)





# ── GameSpace ──────────────────────────────────────────────────────────────────
@app.route("/games")
@require_login
def gamespace():
    return render_template("gamespace.html")

@app.route("/games/memory")
@require_login
def game_memory():
    return render_template("game_memory.html")

@app.route("/games/speedmath")
@require_login
def game_speedmath():
    return render_template("game_speedmath.html")

@app.route("/games/scramble")
@require_login
def game_scramble():
    return render_template("game_scramble.html")

@app.route("/games/jigsaw")
@require_login
def game_jigsaw():
    uid = session["user_id"]
    with get_db() as conn:
        levels = conn.execute(
            "SELECT * FROM jigsaw_levels ORDER BY order_num ASC"
        ).fetchall()
        progress = {
            row["level_id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM jigsaw_progress WHERE user_id=?", (uid,)
            ).fetchall()
        }
    # Pre-compute locked status in Python — cleaner than complex Jinja
    levels_data = []
    for i, lv in enumerate(levels):
        prog = progress.get(lv["id"])
        if lv["order_num"] == 0:
            locked = False
        else:
            # Find the level with order_num one less
            prev = next((l for l in levels if l["order_num"] == lv["order_num"]-1), None)
            locked = not (prev and progress.get(prev["id"], {}).get("completed", 0))
        levels_data.append({
            "id":          lv["id"],
            "title":       lv["title"],
            "description": lv["description"],
            "image_path":  lv["image_path"],
            "grid_size":   lv["grid_size"],
            "order_num":   lv["order_num"],
            "locked":      locked,
            "completed":   prog["completed"] if prog else 0,
            "stars":       prog["stars"]     if prog else 0,
            "best_time":   prog["best_time"] if prog else 0,
        })
    return render_template("game_jigsaw.html", levels=levels_data)


@app.route("/games/jigsaw/<int:level_id>")
@require_login
def game_jigsaw_play(level_id):
    uid = session["user_id"]
    with get_db() as conn:
        level = conn.execute(
            "SELECT * FROM jigsaw_levels WHERE id=?", (level_id,)
        ).fetchone()
        if not level:
            flash("Level not found.", "error")
            return redirect("/games/jigsaw")
        # Check level is unlocked (first level always unlocked,
        # others need previous level completed)
        if level["order_num"] > 0:
            prev = conn.execute(
                "SELECT id FROM jigsaw_levels WHERE order_num=? ORDER BY order_num",
                (level["order_num"]-1,)
            ).fetchone()
            if prev:
                prog = conn.execute(
                    "SELECT completed FROM jigsaw_progress WHERE user_id=? AND level_id=?",
                    (uid, prev["id"])
                ).fetchone()
                if not prog or not prog["completed"]:
                    flash("Complete the previous level first! 🔒", "error")
                    return redirect("/games/jigsaw")
        progress = conn.execute(
            "SELECT * FROM jigsaw_progress WHERE user_id=? AND level_id=?",
            (uid, level_id)
        ).fetchone()
    return render_template("game_jigsaw_play.html",
                           level=level, progress=progress)


@app.route("/games/jigsaw/complete", methods=["POST"])
@require_login
def game_jigsaw_complete():
    import json as _j
    uid      = session["user_id"]
    level_id = request.json.get("level_id")
    time_s   = request.json.get("time", 0)
    stars    = request.json.get("stars", 1)
    if not level_id:
        return {"ok": False}, 400
    with get_db() as conn:
        existing = conn.execute(
            "SELECT best_time, stars FROM jigsaw_progress WHERE user_id=? AND level_id=?",
            (uid, level_id)
        ).fetchone()
        if existing:
            best = min(existing["best_time"], time_s) if existing["best_time"] > 0 else time_s
            best_stars = max(existing["stars"], stars)
            conn.execute("""UPDATE jigsaw_progress
                SET completed=1, best_time=?, stars=?, completed_at=datetime('now')
                WHERE user_id=? AND level_id=?""",
                (best, best_stars, uid, level_id))
        else:
            conn.execute("""INSERT INTO jigsaw_progress
                (user_id, level_id, completed, best_time, stars, completed_at)
                VALUES (?,?,1,?,?,datetime('now'))""",
                (uid, level_id, time_s, stars))
    # Check achievements
    with get_db() as conn:
        total_done = conn.execute(
            "SELECT COUNT(*) FROM jigsaw_progress WHERE user_id=? AND completed=1", (uid,)
        ).fetchone()[0]
    achs = ["first_jigsaw"]
    if stars == 3:        achs.append("secret_jigsaw_fast")
    if total_done >= 5:   achs.append("jigsaw_hard")
    awarded = []
    with get_db() as conn:
        existing_achs = {r[0] for r in conn.execute(
            "SELECT ach_id FROM achievements WHERE user_id=?", (uid,))}
        for ach_id in achs:
            if ach_id in ACH_MAP and ach_id not in existing_achs:
                conn.execute("INSERT INTO achievements (user_id,ach_id) VALUES (?,?)",
                             (uid, ach_id))
                awarded.append(ACH_MAP[ach_id])
    return {"ok": True, "awarded": awarded}


# ── Jigsaw Admin ───────────────────────────────────────────────────
@app.route("/admin/jigsaw/upload", methods=["POST"])
@require_login
@require_admin
def admin_jigsaw_upload():
    import os as _os
    title    = request.form.get("title","").strip()
    desc     = request.form.get("description","").strip()
    grid     = request.form.get("grid_size", type=int, default=4)
    order    = request.form.get("order_num", type=int, default=0)
    img_file = request.files.get("image")
    if not title or not img_file:
        flash("Title and image are required.", "error")
        return redirect("/admin?tab=jigsaw")
    # Save image
    ext = img_file.filename.rsplit(".",1)[-1].lower()
    if ext not in ("jpg","jpeg","png","webp","gif"):
        flash("Only JPG, PNG, WebP images allowed.", "error")
        return redirect("/admin?tab=jigsaw")
    import uuid as _uuid
    fname = f"jigsaw_{_uuid.uuid4().hex[:8]}.{ext}"
    img_file.save(f"static/{fname}")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO jigsaw_levels (title,description,image_path,grid_size,order_num) VALUES (?,?,?,?,?)",
            (title, desc, fname, grid, order)
        )
    flash(f"✅ Level '{title}' added!", "success")
    return redirect("/admin?tab=jigsaw")


@app.route("/admin/jigsaw/delete/<int:lid>", methods=["POST"])
@require_login
@require_admin
def admin_jigsaw_delete(lid):
    with get_db() as conn:
        conn.execute("DELETE FROM jigsaw_levels WHERE id=?", (lid,))
        conn.execute("DELETE FROM jigsaw_progress WHERE level_id=?", (lid,))
    flash("Level deleted.", "success")
    return redirect("/admin?tab=jigsaw")

@app.route("/games/chess")
@require_login
def game_chess():
    return render_template("game_chess.html")

@app.route("/games/award", methods=["POST"])
@require_login
def games_award():
    """Called by GameSpace JS to award achievements without full quiz flow"""
    ach_ids = request.json.get("achievements", [])
    if not ach_ids or not isinstance(ach_ids, list):
        return {"ok": False}, 400
    uid = session["user_id"]
    awarded = []
    with get_db() as conn:
        existing = {r[0] for r in conn.execute(
            "SELECT ach_id FROM achievements WHERE user_id=?", (uid,))}
        for ach_id in ach_ids[:10]:  # cap at 10 per call
            if ach_id in ACH_MAP and ach_id not in existing:
                conn.execute("INSERT INTO achievements (user_id,ach_id) VALUES (?,?)",
                             (uid, ach_id))
                awarded.append(ACH_MAP[ach_id])
                existing.add(ach_id)
    return {"ok": True, "awarded": awarded}


# ── BeeXam ─────────────────────────────────────────────────────────────────────
def init_beexam():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS beexam_exam_types (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                exam_group TEXT DEFAULT 'Other',
                created    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS beexam_papers (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_name      TEXT NOT NULL,
                subject        TEXT,
                year           INTEGER NOT NULL,
                time_limit     INTEGER NOT NULL DEFAULT 10800,
                cutoff         INTEGER,
                exam_group     TEXT DEFAULT 'Other',
                question_count INTEGER DEFAULT 0,
                created_by     INTEGER,
                created        TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS beexam_questions (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id  INTEGER NOT NULL,
                question  TEXT NOT NULL,
                opt0      TEXT NOT NULL,
                opt1      TEXT NOT NULL,
                opt2      TEXT NOT NULL,
                opt3      TEXT NOT NULL,
                category  TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS beexam_results (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                paper_id   INTEGER NOT NULL,
                score      INTEGER DEFAULT 0,
                wrong      INTEGER DEFAULT 0,
                skipped    INTEGER DEFAULT 0,
                total      INTEGER DEFAULT 0,
                pct        REAL DEFAULT 0,
                grade      TEXT DEFAULT 'F',
                time_taken INTEGER DEFAULT 0,
                played_at  TEXT DEFAULT (datetime('now'))
            );
        """)


@app.route("/beexam")
@require_login
def beexam_landing():
    init_beexam()
    with get_db() as conn:
        papers         = conn.execute("SELECT * FROM beexam_papers ORDER BY year DESC").fetchall()
        exam_types_raw = conn.execute("SELECT * FROM beexam_exam_types ORDER BY name").fetchall()

    # Build count map from actual papers
    count_map = {}
    for p in papers:
        count_map[p["exam_name"]] = count_map.get(p["exam_name"], 0) + 1

    # Use exam_types table if populated, otherwise auto-generate from papers
    if exam_types_raw:
        exam_types = [{"name": et["name"], "group": et["exam_group"],
                       "count": count_map.get(et["name"], 0)} for et in exam_types_raw]
    else:
        # Auto-create from existing papers so nothing looks empty
        seen = {}
        for p in papers:
            if p["exam_name"] not in seen:
                seen[p["exam_name"]] = {"name": p["exam_name"],
                                         "group": p["exam_group"] or "Other",
                                         "count": 0}
            seen[p["exam_name"]]["count"] += 1
        exam_types = list(seen.values())
        # Also insert them into the table so admin panel works
        with get_db() as conn:
            for et in exam_types:
                try:
                    conn.execute("INSERT OR IGNORE INTO beexam_exam_types (name, exam_group) VALUES (?,?)",
                                 (et["name"], et["group"]))
                except: pass

    return render_template("beexam.html", papers=papers, exam_types=exam_types)


@app.route("/beexam/start/<int:paper_id>")
@require_login
def beexam_start(paper_id):
    init_beexam()
    time_limit = request.args.get("time", type=int)
    with get_db() as conn:
        paper = conn.execute(
            "SELECT * FROM beexam_papers WHERE id=?", (paper_id,)
        ).fetchone()
        if not paper:
            flash("Paper not found.", "error")
            return redirect("/beexam")
        raw_qs = conn.execute(
            "SELECT * FROM beexam_questions WHERE paper_id=? ORDER BY id", (paper_id,)
        ).fetchall()

    if not raw_qs:
        flash("This paper has no questions yet.", "error")
        return redirect("/beexam")

    # Shuffle questions and options (anti-cheat system preserved)
    import random
    questions = []
    for q in raw_qs:
        opts = [q["opt0"], q["opt1"], q["opt2"], q["opt3"]]
        correct_text = opts[0]       # opt0 is always correct in CSV
        random.shuffle(opts)
        questions.append({
            "q":       q["question"],
            "options": opts,
            "a":       opts.index(correct_text),
            "cat":     q["category"] or ""
        })
    random.shuffle(questions)

    time_limit = time_limit or paper["time_limit"]
    session["bx_questions"]  = questions
    session["bx_paper_id"]   = paper_id
    session["bx_time_limit"] = time_limit
    session["bx_start_time"] = int(__import__("time").time())
    session["bx_answers"]    = []
    session["bx_index"]      = 0
    # Show format picker
    return render_template("format_picker.html",
        mode="beexam",
        paper_title=f"{paper['exam_name']} {paper['year']}",
        beewise_url="/beexam/quiz?fmt=beewise",
        rapidbee_url="/beexam/quiz?fmt=rapidbee",
        back_url="/beexam")


@app.route("/beexam/quiz", methods=["GET", "POST"])
@require_login
def beexam_quiz():
    init_beexam()
    questions = session.get("bx_questions")
    if not questions:
        flash("No active BeeXam session.", "error")
        return redirect("/beexam")

    import time as _time
    elapsed   = int(_time.time()) - session.get("bx_start_time", int(_time.time()))
    time_left = max(0, session["bx_time_limit"] - elapsed)
    idx       = session.get("bx_index", 0)
    paper_id  = session.get("bx_paper_id")

    fmt = request.args.get("fmt") or session.get("bx_fmt", "rapidbee")
    if request.args.get("fmt"):
        session["bx_fmt"] = fmt

    with get_db() as conn:
        paper = conn.execute("SELECT * FROM beexam_papers WHERE id=?", (paper_id,)).fetchone()

    def finish_beexam(answers):
        while len(answers) < len(questions):
            answers.append(-1)
        session["bx_answers"] = answers
        session.pop("bx_fmt", None)
        return redirect("/beexam/result")

    # ── BEEWISE FORMAT ────────────────────────────────────────────────
    if fmt == "beewise":
        if request.method == "POST" or time_left <= 0:
            answers = []
            for i in range(len(questions)):
                ans = request.form.get(f"q{i}")
                answers.append(int(ans) if ans is not None and ans != "" else -1)
            return finish_beexam(answers)
        return render_template("beexam_beewise.html",
                               questions=questions, paper=paper,
                               total=len(questions), left=time_left,
                               total_time=session["bx_time_limit"])

    # ── RAPIDBEE FORMAT ───────────────────────────────────────────────
    if request.method == "POST":
        ans = request.form.get("answer")
        answers = session.get("bx_answers", [])
        answers.append(int(ans) if ans is not None and ans != "" else -1)
        session["bx_answers"] = answers
        session["bx_index"]   = idx + 1
        idx += 1

    if time_left <= 0 or idx >= len(questions):
        return finish_beexam(session.get("bx_answers", []))

    q = questions[idx]
    return render_template("beexam_quiz.html",
                           q=q, paper=paper,
                           num=idx + 1, total=len(questions),
                           left=time_left,
                           total_time=session["bx_time_limit"])


@app.route("/beexam/result")
@require_login
def beexam_result():
    init_beexam()
    import time as _time
    questions = session.get("bx_questions", [])
    answers   = session.get("bx_answers", [])
    paper_id  = session.get("bx_paper_id")

    if not questions or not paper_id:
        return redirect("/beexam")

    with get_db() as conn:
        paper = conn.execute(
            "SELECT * FROM beexam_papers WHERE id=?", (paper_id,)
        ).fetchone()

    score = wrong = skipped = 0
    review    = []
    cat_map   = {}

    for i, q in enumerate(questions):
        u_ans   = answers[i] if i < len(answers) else -1
        correct = (u_ans == q["a"])
        cat     = q.get("cat", "")

        if u_ans == -1:
            skipped += 1
        elif correct:
            score += 1
        else:
            wrong += 1

        if cat:
            if cat not in cat_map:
                cat_map[cat] = {"correct": 0, "total": 0}
            cat_map[cat]["total"]   += 1
            if correct and u_ans != -1:
                cat_map[cat]["correct"] += 1

        review.append({
            "q":            q["q"],
            "correct":      correct and u_ans != -1,
            "skipped":      u_ans == -1,
            "user_text":    q["options"][u_ans] if u_ans != -1 else "—",
            "correct_text": q["options"][q["a"]],
        })

    total  = len(questions)
    pct    = round(score / total * 100, 1) if total else 0
    elapsed = int(_time.time()) - session.get("bx_start_time", int(_time.time()))
    grade  = "A+" if pct >= 90 else "A" if pct >= 80 else "B" if pct >= 70 \
             else "C" if pct >= 60 else "D" if pct >= 50 else "F"

    cat_stats = [
        {"cat": k, "pct": round(v["correct"] / v["total"] * 100, 1) if v["total"] else 0}
        for k, v in cat_map.items()
    ]
    cat_stats.sort(key=lambda x: x["pct"])

    with get_db() as conn:
        conn.execute("""
            INSERT INTO beexam_results
              (user_id, paper_id, score, wrong, skipped, total, pct, grade, time_taken)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (session["user_id"], paper_id, score, wrong, skipped, total, pct, grade, elapsed))

    # Clear session
    for k in ["bx_questions","bx_paper_id","bx_time_limit","bx_start_time","bx_answers","bx_index"]:
        session.pop(k, None)

    return render_template("beexam_result.html",
                           paper=paper, score=score, wrong=wrong,
                           skipped=skipped, total=total, pct=pct,
                           grade=grade, cat_stats=cat_stats, review=review)


# ── BeeXam Admin ───────────────────────────────────────────────────────────────
@app.route("/admin/beexam/upload", methods=["POST"])
@require_login
@require_admin
def admin_beexam_upload():
    init_beexam()
    import csv, io
    exam_name  = request.form.get("exam_name","").strip()
    subject    = request.form.get("subject","").strip()
    year       = request.form.get("year", type=int)
    time_limit = (request.form.get("time_limit", type=int) or 180) * 60
    cutoff     = request.form.get("cutoff", type=int)
    exam_group = request.form.get("exam_group","Other").strip()
    csv_file   = request.files.get("csv_file")

    if not csv_file or not exam_name or not year:
        flash("Exam name, year, and CSV file are required.", "error")
        return redirect("/admin?tab=beexam")

    try:
        text   = csv_file.read().decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        rows   = [r for r in reader if any(c.strip() for c in r)]
        # Skip header if first row looks like a header
        if rows and rows[0][0].lower() in ("question", "q", "#"):
            rows = rows[1:]

        if not rows:
            flash("CSV file is empty.", "error")
            return redirect("/admin?tab=beexam")

        with get_db() as conn:
            cur = conn.execute(
                """INSERT INTO beexam_papers
                   (exam_name, subject, year, time_limit, cutoff, exam_group, created_by)
                   VALUES (?,?,?,?,?,?,?)""",
                (exam_name, subject, year, time_limit, cutoff, exam_group, session["user_id"])
            )
            paper_id = cur.lastrowid
            count = 0
            for row in rows:
                if len(row) < 5: continue
                cat = row[5].strip() if len(row) > 5 else ""
                conn.execute("""
                    INSERT INTO beexam_questions
                      (paper_id, question, opt0, opt1, opt2, opt3, category)
                    VALUES (?,?,?,?,?,?,?)
                """, (paper_id, row[0].strip(), row[1].strip(),
                      row[2].strip(), row[3].strip(), row[4].strip(), cat))
                count += 1
            conn.execute(
                "UPDATE beexam_papers SET question_count=? WHERE id=?",
                (count, paper_id)
            )
        flash(f"✅ Uploaded {count} questions for {exam_name} {year}!", "success")
    except Exception as e:
        flash(f"Upload failed: {e}", "error")

    return redirect("/admin?tab=beexam")


@app.route("/admin/promote", methods=["POST"])
@require_login
@require_admin
def admin_promote_user():
    username = request.form.get("username","").strip()
    new_role = request.form.get("role","student")
    if new_role not in ("student","teacher","admin"):
        flash("Invalid role.", "error")
        return redirect("/admin")
    with get_db() as conn:
        user = conn.execute("SELECT id,username,role FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            flash(f"User '{username}' not found.", "error")
            return redirect("/admin")
        is_admin = 1 if new_role == "admin" else 0
        conn.execute("UPDATE users SET role=?, is_admin=? WHERE username=?",
                     (new_role, is_admin, username))
    role_labels = {"student":"Student 🎓","teacher":"Teacher 👩‍🏫","admin":"Admin ⚙️"}
    flash(f"✅ {username} promoted to {role_labels.get(new_role, new_role)}!", "success")
    return redirect("/admin")


@app.route("/admin/users")
@require_login
@require_admin
def admin_users():
    q = request.args.get("q","").strip()
    with get_db() as conn:
        if q:
            users = conn.execute(
                "SELECT id,username,role,is_admin,created FROM users WHERE username LIKE ? ORDER BY created DESC LIMIT 20",
                (f"%{q}%",)).fetchall()
        else:
            users = conn.execute(
                "SELECT id,username,role,is_admin,created FROM users ORDER BY created DESC LIMIT 50"
            ).fetchall()
    return {"users": [{"id":u["id"],"username":u["username"],"role":u["role"] or "student"} for u in users]}
@require_login
@require_admin
def admin_beexam_create_type():
    init_beexam()
    name  = request.form.get("exam_name","").strip()
    group = request.form.get("exam_group","Other").strip()
    if not name:
        flash("Exam name is required.", "error")
        return redirect("/admin?tab=beexam")
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO beexam_exam_types (name, exam_group) VALUES (?,?)", (name, group))
        flash(f"✅ Exam panel '{name}' created!", "success")
    except Exception:
        flash(f"'{name}' already exists.", "error")
    return redirect("/admin?tab=beexam")


@app.route("/admin/beexam/add_question", methods=["POST"])
@require_login
@require_admin
def admin_beexam_add_question():
    init_beexam()
    paper_id = request.form.get("paper_id", type=int)
    question = request.form.get("question","").strip()
    opt0     = request.form.get("opt0","").strip()
    opt1     = request.form.get("opt1","").strip()
    opt2     = request.form.get("opt2","").strip()
    opt3     = request.form.get("opt3","").strip()
    category = request.form.get("category","").strip()
    if not all([paper_id, question, opt0, opt1, opt2, opt3]):
        flash("All fields are required.", "error")
        return redirect("/admin?tab=beexam")
    with get_db() as conn:
        conn.execute("""INSERT INTO beexam_questions
            (paper_id, question, opt0, opt1, opt2, opt3, category)
            VALUES (?,?,?,?,?,?,?)""", (paper_id, question, opt0, opt1, opt2, opt3, category))
        conn.execute("UPDATE beexam_papers SET question_count = question_count+1 WHERE id=?", (paper_id,))
    flash("✅ Question added!", "success")
    return redirect("/admin?tab=beexam")


@app.route("/admin/beexam/delete_exam_type/<exam_name>", methods=["POST"])
@require_login
@require_admin
def admin_beexam_delete_type(exam_name):
    init_beexam()
    with get_db() as conn:
        # Delete all questions + papers under this exam, then the type
        papers = conn.execute("SELECT id FROM beexam_papers WHERE exam_name=?", (exam_name,)).fetchall()
        for p in papers:
            conn.execute("DELETE FROM beexam_questions WHERE paper_id=?", (p["id"],))
        conn.execute("DELETE FROM beexam_papers WHERE exam_name=?", (exam_name,))
        conn.execute("DELETE FROM beexam_exam_types WHERE name=?", (exam_name,))
    flash(f"Deleted '{exam_name}' and all its papers.", "success")
    return redirect("/admin?tab=beexam")


@app.route("/admin/beexam/delete/<int:paper_id>", methods=["POST"])
@require_login
@require_admin
def admin_beexam_delete(paper_id):
    init_beexam()
    with get_db() as conn:
        paper = conn.execute(
            "SELECT exam_name, year FROM beexam_papers WHERE id=?", (paper_id,)
        ).fetchone()
        if paper:
            conn.execute("DELETE FROM beexam_questions WHERE paper_id=?", (paper_id,))
            conn.execute("DELETE FROM beexam_papers WHERE id=?", (paper_id,))
            flash(f"Deleted {paper['exam_name']} {paper['year']}.", "success")
    return redirect("/admin?tab=beexam")


# ── Teacher Quiz Room ──────────────────────────────────────────────────────────
@app.route("/teacher/room/create", methods=["POST"])
@require_login
@require_teacher
def teacher_create_room():
    import random as _r, string as _s, json as _j, csv as _csv, io as _io
    title      = request.form.get("room_title","").strip()
    time_limit = int(request.form.get("time_limit", 30))
    if not title:
        flash("Room title is required.", "error")
        return redirect("/teacher")
    f = request.files.get("room_csv")
    if not f or f.filename == "":
        flash("Please upload a CSV file.", "error")
        return redirect("/teacher")
    questions = []
    try:
        raw = f.stream.read()
        for enc in ("utf-8-sig","utf-8","latin-1"):
            try: content = raw.decode(enc); break
            except: continue
        content = content.replace("\r\n","\n").replace("\r","\n")
        reader  = _csv.DictReader(_io.StringIO(content))
        if reader.fieldnames:
            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
        for row in reader:
            q  = (row.get("question") or "").strip()
            o0 = (row.get("opt0") or row.get("correct","")).strip()
            o1 = (row.get("opt1","")).strip()
            o2 = (row.get("opt2","")).strip()
            o3 = (row.get("opt3","")).strip()
            if q and o0 and o1:
                questions.append({"q":q,"correct":o0,"options_raw":[o for o in [o0,o1,o2,o3] if o]})
    except Exception as e:
        flash(f"CSV error: {e}", "error")
        return redirect("/teacher")
    if not questions:
        flash("No valid questions in CSV.", "error")
        return redirect("/teacher")
    code = ''.join(_r.choices(_s.ascii_uppercase + _s.digits, k=6))
    with get_db() as conn:
        conn.execute("INSERT INTO quiz_rooms (title,code,created_by,questions,time_limit) VALUES (?,?,?,?,?)",
                     (title, code, session["user_id"], _j.dumps(questions), time_limit))
    flash(f"Room '{title}' created! Code: {code}", "success")
    return redirect("/teacher")


@app.route("/teacher/room/delete/<int:rid>", methods=["POST"])
@require_login
@require_teacher
def teacher_delete_room(rid):
    with get_db() as conn:
        room = conn.execute("SELECT created_by FROM quiz_rooms WHERE id=?", (rid,)).fetchone()
        if not room or room["created_by"] != session["user_id"]:
            flash("Not authorised.", "error")
            return redirect("/teacher")
        conn.execute("DELETE FROM room_results WHERE room_id=?", (rid,))
        conn.execute("DELETE FROM quiz_rooms WHERE id=?", (rid,))
    flash("Room deleted.", "success")
    return redirect("/teacher")


@app.route("/teacher/room/results/<int:rid>")
@require_login
@require_teacher
def teacher_room_results(rid):
    with get_db() as conn:
        room = conn.execute("SELECT * FROM quiz_rooms WHERE id=? AND created_by=?",
                            (rid, session["user_id"])).fetchone()
        if not room:
            flash("Room not found.", "error")
            return redirect("/teacher")
        results = conn.execute("""
            SELECT u.username, u.avatar, rr.score, rr.total, rr.pct,
                   rr.time_taken, rr.finished
            FROM room_results rr
            JOIN users u ON u.id = rr.user_id
            WHERE rr.room_id=?
            ORDER BY rr.pct DESC, rr.time_taken ASC
        """, (rid,)).fetchall()
    return render_template("room_results.html", room=room, results=results)


@app.route("/teacher/schedule", methods=["POST"])
@require_login
@require_teacher
def teacher_schedule_test():
    room_id      = request.form.get("room_id", type=int)
    class_id     = request.form.get("class_id", type=int)
    scheduled_at = request.form.get("scheduled_at","").strip()
    note         = request.form.get("note","").strip()
    if not room_id or not scheduled_at:
        flash("Room and scheduled time are required.", "error")
        return redirect("/teacher")
    with get_db() as conn:
        # Verify teacher owns this room
        room = conn.execute("SELECT id FROM quiz_rooms WHERE id=? AND created_by=?",
                            (room_id, session["user_id"])).fetchone()
        if not room:
            flash("You can only schedule your own rooms.", "error")
            return redirect("/teacher")
        conn.execute("""INSERT INTO scheduled_tests
            (teacher_id, room_id, class_id, scheduled_at, note) VALUES (?,?,?,?,?)""",
            (session["user_id"], room_id, class_id, scheduled_at, note))
    flash("Test scheduled! ✅", "success")
    return redirect("/teacher")


@app.route("/teacher/schedule/delete/<int:sid>", methods=["POST"])
@require_login
@require_teacher
def teacher_delete_schedule(sid):
    with get_db() as conn:
        conn.execute("DELETE FROM scheduled_tests WHERE id=? AND teacher_id=?",
                     (sid, session["user_id"]))
    flash("Schedule removed.", "success")
    return redirect("/teacher")


# ── Teacher Dashboard ──────────────────────────────────────────────────────────
@app.route("/teacher")
@require_login
@require_teacher
def teacher_dashboard():
    tid = session["user_id"]
    with get_db() as conn:
        classes = conn.execute("SELECT * FROM classes WHERE admin_id=?", (tid,)).fetchall()
        class_data = []
        for cls in classes:
            # Only class-level stats — NOT personal quiz history
            students = conn.execute("""
                SELECT u.id, u.username, u.avatar, u.streak,
                       COUNT(DISTINCT r.id)         AS games,
                       ROUND(AVG(r.pct),1)          AS avg_pct,
                       MAX(r.pct)                   AS best,
                       MAX(r.played_at)             AS last_played,
                       SUM(r.tab_switches)          AS total_tab_switches
                FROM class_members cm
                JOIN users u ON u.id = cm.user_id
                LEFT JOIN results r ON r.user_id = u.id
                WHERE cm.class_id=?
                GROUP BY u.id
                ORDER BY avg_pct DESC
            """, (cls["id"],)).fetchall()
            class_data.append({"cls": cls, "students": students})

        # Teacher's quiz rooms
        rooms = conn.execute(
            "SELECT * FROM quiz_rooms WHERE created_by=? ORDER BY id DESC", (tid,)
        ).fetchall()

        # Room results for anti-cheat — tab switches per student per room
        room_results = {}
        for room in rooms:
            rr = conn.execute("""
                SELECT u.username, u.avatar, rr.score, rr.total, rr.pct,
                       rr.time_taken, rr.finished
                FROM room_results rr
                JOIN users u ON u.id = rr.user_id
                WHERE rr.room_id=?
                ORDER BY rr.pct DESC
            """, (room["id"],)).fetchall()
            room_results[room["id"]] = rr

        # Scheduled tests
        schedules = conn.execute("""
            SELECT st.*, qr.title AS room_title, c.name AS class_name
            FROM scheduled_tests st
            JOIN quiz_rooms qr ON qr.id = st.room_id
            LEFT JOIN classes c ON c.id = st.class_id
            WHERE st.teacher_id=?
            ORDER BY st.scheduled_at ASC
        """, (tid,)).fetchall()

    return render_template("teacher_dashboard.html",
                           class_data=class_data,
                           total_classes=len(classes),
                           rooms=rooms,
                           room_results=room_results,
                           schedules=schedules)


@app.route("/teacher/student/<int:uid>")
@require_login
@require_teacher
def teacher_student_view(uid):
    tid = session["user_id"]
    with get_db() as conn:
        allowed = conn.execute("""
            SELECT 1 FROM class_members cm
            JOIN classes c ON c.id = cm.class_id
            WHERE cm.user_id=? AND c.admin_id=?
        """, (uid, tid)).fetchone()
        if not allowed:
            flash("You can only view students in your own classes.", "error")
            return redirect("/teacher")
        student = conn.execute(
            "SELECT id, username, avatar, streak FROM users WHERE id=?", (uid,)
        ).fetchone()
        # Only show quiz ROOM results (teacher-assigned tests) — not personal BeeWise/RapidBee history
        room_results = conn.execute("""
            SELECT qr.title AS room_name, rr.score, rr.total, rr.pct,
                   rr.time_taken, rr.finished
            FROM room_results rr
            JOIN quiz_rooms qr ON qr.id = rr.room_id
            WHERE rr.user_id=? AND qr.created_by=?
            ORDER BY rr.finished DESC
        """, (uid, tid)).fetchall()
        # Category performance from answer_log (academic insight, not personal history)
        cat_stats = conn.execute("""
            SELECT al.category,
                   COUNT(*)                                   AS total,
                   SUM(al.correct)                           AS correct,
                   ROUND(100.0*SUM(al.correct)/COUNT(*),1)  AS pct
            FROM answer_log al
            JOIN results r ON r.id = al.result_id
            WHERE r.user_id=?
            GROUP BY al.category
            ORDER BY pct ASC
        """, (uid,)).fetchall()
        # Overall class stats only
        stats = conn.execute("""
            SELECT COUNT(*)          AS games,
                   ROUND(AVG(pct),1) AS avg_pct,
                   MAX(pct)          AS best,
                   MIN(pct)          AS worst
            FROM results WHERE user_id=?
        """, (uid,)).fetchone()
        # Anti-cheat: tab switches in teacher's rooms
        cheat_flags = conn.execute("""
            SELECT qr.title, rr.pct, rr.time_taken
            FROM room_results rr
            JOIN quiz_rooms qr ON qr.id = rr.room_id
            WHERE rr.user_id=? AND qr.created_by=?
            ORDER BY rr.finished DESC
        """, (uid, tid)).fetchall()
    return render_template("teacher_student_report.html",
                           student=student,
                           room_results=room_results,
                           cat_stats=cat_stats,
                           stats=stats,
                           cheat_flags=cheat_flags,
                           back_url="/teacher")


@app.route("/teacher/class/create", methods=["POST"])
@require_login
@require_teacher
def teacher_create_class():
    name = request.form.get("name","").strip()
    if not name:
        flash("Class name cannot be empty.", "error")
        return redirect("/teacher")
    import secrets as _sec
    code = _sec.token_hex(3).upper()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO classes (name, code, created_by, admin_id) VALUES (?,?,?,?)",
            (name, code, session["user_id"], session["user_id"])
        )
    flash(f'Class "{name}" created! Join code: {code}', "success")
    return redirect("/teacher")


if __name__ == "__main__":
    app.run(debug=False)

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500