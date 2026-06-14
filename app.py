from flask import Flask, render_template, request, redirect, session, flash, jsonify, Response
from functools import wraps
from questions import get_shuffled_questions, CATEGORIES, ALL_QUESTIONS
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib, time, json, os, csv, io, datetime, re
import requests as http_req

# ── Make psycopg2 return timestamps as strings (templates use [:10] slicing) ──
def _cast_ts(val, cur):
    return val[:19] if val else None          # 'YYYY-MM-DD HH:MM:SS'
def _cast_date(val, cur):
    return val[:10] if val else None          # 'YYYY-MM-DD'
psycopg2.extensions.register_type(
    psycopg2.extensions.new_type((1114,), 'TIMESTAMP',   _cast_ts))
psycopg2.extensions.register_type(
    psycopg2.extensions.new_type((1184,), 'TIMESTAMPTZ', _cast_ts))
psycopg2.extensions.register_type(
    psycopg2.extensions.new_type((1082,), 'DATE',        _cast_date))

# ── AI module ────────────────────────────────────────────────────────
from ai import beebot_reply, generate_questions

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "beewise_secret_2025")  # ⚠️ Set SECRET_KEY env var in production!

QUIZ_LIMIT  = 25
RAPID_LIMIT = 25
RAPID_TIME  = 180
QUIZ_TIME   = 180
DATABASE_URL = os.environ.get("DATABASE_URL", "")
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
{"id":"secret_all_wrong","name":"Trying to Fail",    "desc":"Score 0% in a quiz (really%s)",        "icon":"🤡","secret":True},
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
]
ACH_MAP = {a["id"]: a for a in ACHIEVEMENTS}

# ── DB ──────────────────────────────────────────────────────────────
def get_db():
    import contextlib
    class _PGConn:
        """Thin wrapper making psycopg2 behave like sqlite3 for our usage."""
        def __init__(self):
            self._conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            self._conn.autocommit = False
        def execute(self, sql, params=()):
            sql = _pg_sql(sql)
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur
        def executemany(self, sql, seq):
            sql = _pg_sql(sql)
            cur = self._conn.cursor()
            for p in seq:
                cur.execute(sql, p)
            return cur
        def executescript(self, script):
            cur = self._conn.cursor()
            for stmt in script.split(';'):
                s = stmt.strip()
                if s:
                    try:
                        cur.execute(_pg_sql(s))
                    except Exception:
                        self._conn.rollback()
                        raise
            return cur
        def commit(self):   self._conn.commit()
        def rollback(self): self._conn.rollback()
        def close(self):
            try: self._conn.commit()
            except: pass
            self._conn.close()
        def __enter__(self): return self
        def __exit__(self, exc_type, *_):
            if exc_type: self._conn.rollback()
            else:        self._conn.commit()
            self._conn.close()
    return _PGConn()

def _pg_sql(sql):
    """Convert SQLite SQL to PostgreSQL SQL."""
    sql = sql.replace('?', '%s')
    sql = re.sub(r'INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY', sql, flags=re.IGNORECASE)
    sql = re.sub(r'BIGINT PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY', sql, flags=re.IGNORECASE)
    # datetime('now', offset) variants
    sql = re.sub(r"datetime\('now',\s*'([^']+)'\)", lambda m: _sqlite_interval(m.group(1)), sql, flags=re.IGNORECASE)
    sql = re.sub(r"datetime\('now'\)", 'NOW()', sql, flags=re.IGNORECASE)
    sql = re.sub(r"date\('now'\)", 'CURRENT_DATE', sql, flags=re.IGNORECASE)
    sql = re.sub(r"DATE\('now'\)", 'CURRENT_DATE', sql, flags=re.IGNORECASE)
    # date(column) used as cast → column::date
    sql = re.sub(r'\bdate\((\w+)\)', r'\1::date', sql, flags=re.IGNORECASE)
    # strftime('%w', col) IN ('0','6') → EXTRACT(DOW FROM col) IN (0,6)
    sql = re.sub(r"strftime\('%w',\s*(\w+)\)\s*IN\s*\('0','6'\)", r"EXTRACT(DOW FROM \1) IN (0,6)", sql, flags=re.IGNORECASE)
    # datetime(col) used for casting text to timestamp
    sql = re.sub(r'\bdatetime\((\w+)\)', r'\1::timestamp', sql, flags=re.IGNORECASE)
    return sql

def _sqlite_interval(offset_str):
    """Convert SQLite datetime offset like '-1 second' to PostgreSQL NOW() expression."""
    offset_str = offset_str.strip()
    m = re.match(r'^([+-])(\d+)\s+(\w+)$', offset_str)
    if m:
        sign, n, unit = m.group(1), m.group(2), m.group(3).rstrip('s') + 's'
        op = '-' if sign == '-' else '+'
        return f"NOW() {op} INTERVAL '{n} {unit}'"
    return 'NOW()'


def init_db():
    """Tables are created via Supabase SQL Editor migration.
    This function just verifies the DB connection is alive."""
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        print(f"[init_db] DB connection check failed: {e}")

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
        user = conn.execute("SELECT streak, last_play FROM users WHERE id=%s", (user_id,)).fetchone()
        last = user["last_play"]
        streak = user["streak"] or 0
        if last == today:
            return streak  # already played today
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        new_streak = streak + 1 if last == yesterday else 1
        conn.execute("UPDATE users SET streak=%s, last_play=%s WHERE id=%s", (new_streak, today, user_id))
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
            "SELECT ach_id FROM achievements WHERE user_id=%s", (user_id,)).fetchall()}
        stats = conn.execute(
            """SELECT COUNT(*) as games,
               MIN(pct) as min_pct, MAX(pct) as max_pct,
               SUM(score) as total_correct
               FROM results WHERE user_id=%s""",
            (user_id,)).fetchone()
        perfect_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s AND pct=100", (user_id,)).fetchone()["c"]
        grade_a_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s AND pct>=80", (user_id,)).fetchone()["c"]
        no_wrong_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s AND score=total", (user_id,)).fetchone()["c"]
        rapid_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s AND mode='RapidBee'", (user_id,)).fetchone()["c"]
        cats_practiced = {r["mode"].split(":")[1] for r in conn.execute(
            "SELECT DISTINCT mode FROM results WHERE user_id=%s AND mode LIKE 'Practice:%%'",
            (user_id,)).fetchall()}
        practice_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s AND mode LIKE 'Practice:%%'",
            (user_id,)).fetchone()["c"]
        cert_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s AND pct>=80", (user_id,)).fetchone()["c"]
        streak = conn.execute("SELECT streak FROM users WHERE id=%s", (user_id,)).fetchone()["streak"]
        prev_best = conn.execute(
            "SELECT MAX(pct) as best FROM results WHERE user_id=%s AND played_at < NOW() - INTERVAL '1 second'",
            (user_id,)).fetchone()["best"] or 0
        same_score = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s AND pct=%s",
            (user_id, pct)).fetchone()["c"]
        days_played = conn.execute(
            "SELECT COUNT(DISTINCT played_at::date) as d FROM results WHERE user_id=%s",
            (user_id,)).fetchone()["d"]

    # Total correct answers ever
    total_correct = stats["total_correct"] or 0
    games         = stats["games"] or 0

    def award(ach_id):
        if ach_id not in existing and ach_id in ACH_MAP:
            with get_db() as conn2:
                try:
                    conn2.execute("INSERT INTO achievements (user_id, ach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (user_id, ach_id))
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
        _uavatar = _conn.execute("SELECT avatar FROM users WHERE id=%s", (user_id,)).fetchone()["avatar"]
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
            "SELECT DISTINCT mode FROM results WHERE user_id=%s AND played_at::date=CURRENT_DATE",
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
            "SELECT COUNT(DISTINCT played_at::date) as c FROM results WHERE user_id=%s AND EXTRACT(DOW FROM played_at) IN (0,6)",
            (user_id,)).fetchone()["c"]
    if weekends >= 2: award("weekend_bee")
    return newly_earned

def save_result(user_id, mode, score, total, pct, grade, time_taken, answer_log_data, tab_switches=0):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO results (user_id,mode,score,total,pct,grade,time_taken,tab_switches) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (user_id, mode, score, total, pct, grade, time_taken, tab_switches))
        result_id = cur.fetchone()["id"]
        for entry in answer_log_data:
            conn.execute(
                "INSERT INTO answer_log (result_id,question,category,correct,user_ans,correct_ans,time_spent) VALUES (%s,%s,%s,%s,%s,%s,%s)",
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
            WHERE u.is_admin=0 GROUP BY u.id, u.username, u.avatar ORDER BY best DESC LIMIT 3
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
            if len(password) < 6:
                flash("Password must be at least 6 characters.", "error")
                return redirect("/")
            if not re.search(r'[A-Za-z]', password) or not re.search(r'[0-9]', password):
                flash("Password must contain both letters and numbers.", "error")
                return redirect("/")
            admin_code   = request.form.get("admin_code","").strip()
            teacher_code = request.form.get("teacher_code","").strip()
            if admin_code and admin_code == ADMIN_CODE:
                role = "admin"
                is_admin = 1
            elif teacher_code and teacher_code == TEACHER_CODE:
                role = "teacher"
                is_admin = 0
            else:
                role = "student"
                is_admin = 0
            if admin_code and admin_code != ADMIN_CODE and not teacher_code:
                flash("Invalid code. Registered as student.", "error")
            try:
                with get_db() as conn:
                    conn.execute("INSERT INTO users (username,password,is_admin,role) VALUES (%s,%s,%s,%s)",
                                 (username, hash_pw(password), is_admin, role))
                flash("Account created! Please log in." + (" (Teacher 🏫)" if role == "teacher" else ""), "success")
            except psycopg2.errors.UniqueViolation:
                flash("Username already taken.", "error")
            return redirect("/")
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=%s AND password=%s",
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
                _c.execute("INSERT INTO achievements (user_id, ach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
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
                user = conn.execute("SELECT * FROM users WHERE id=%s AND password=%s",
                                    (session["user_id"], hash_pw(old_pw))).fetchone()
            if not user:
                flash("Current password is incorrect.", "error")
            elif len(new_pw) < 4:
                flash("New password must be at least 6 characters with letters and numbers.", "error")
            else:
                with get_db() as conn:
                    conn.execute("UPDATE users SET password=%s WHERE id=%s",
                                 (hash_pw(new_pw), session["user_id"]))
                flash("Password updated! 🔐", "success")
        elif action == "change_avatar":
            avatar = request.form.get("avatar","🐝")
            if avatar in AVATARS:
                with get_db() as conn:
                    conn.execute("UPDATE users SET avatar=%s WHERE id=%s", (avatar, session["user_id"]))
                session["avatar"] = avatar
                flash("Avatar updated!", "success")
        return redirect("/profile")

    with get_db() as conn:
        user  = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        stats = conn.execute(
            "SELECT COUNT(*) as games, ROUND(AVG(pct)) as avg_pct, MAX(pct) as best, SUM(time_taken) as total_time FROM results WHERE user_id=%s",
            (session["user_id"],)).fetchone()
        cat_stats = conn.execute("""
            SELECT al.category, ROUND(AVG(al.correct)*100) as pct, COUNT(*) as total
            FROM answer_log al JOIN results r ON r.id=al.result_id
            WHERE r.user_id=%s GROUP BY al.category
        """, (session["user_id"],)).fetchall()
        earned = conn.execute(
            "SELECT ach_id, earned_at FROM achievements WHERE user_id=%s ORDER BY earned_at DESC",
            (session["user_id"],)).fetchall()
    earned_ids = {e["ach_id"] for e in earned}
    with get_db() as conn:
        my_classes = conn.execute("""
            SELECT c.id, c.name, c.code
            FROM classes c JOIN class_members cm ON cm.class_id=c.id
            WHERE cm.user_id=%s
        """, (session["user_id"],)).fetchall()
        all_results = conn.execute(
            "SELECT * FROM results WHERE user_id=%s ORDER BY played_at DESC LIMIT 20",
            (session["user_id"],)).fetchall()
    return render_template("profile.html", user=user, stats=stats, cat_stats=cat_stats,
                           earned=earned, earned_ids=earned_ids, my_classes=my_classes,
                           all_results=all_results,
                           all_achievements=ACHIEVEMENTS, avatars=AVATARS)

# ── Dashboard ────────────────────────────────────────────────────────
@app.route("/dashboard")
@require_login
def dashboard():
    streak = update_streak(session["user_id"])
    with get_db() as conn:
        history  = conn.execute(
            "SELECT * FROM results WHERE user_id=%s ORDER BY played_at DESC LIMIT 10",
            (session["user_id"],)).fetchall()
        stats    = conn.execute(
            "SELECT COUNT(*) as games, ROUND(AVG(pct)) as avg_pct, MAX(pct) as best FROM results WHERE user_id=%s",
            (session["user_id"],)).fetchone()
        cat_stats = conn.execute("""
            SELECT al.category, COUNT(*) as total_q, SUM(al.correct) as correct_q,
                   ROUND(AVG(al.correct)*100) as pct
            FROM answer_log al JOIN results r ON r.id=al.result_id
            WHERE r.user_id=%s GROUP BY al.category ORDER BY pct ASC
        """, (session["user_id"],)).fetchall()
        progress = list(reversed(conn.execute(
            "SELECT pct, mode, played_at FROM results WHERE user_id=%s ORDER BY played_at DESC LIMIT 10",
            (session["user_id"],)).fetchall()))
        recent_badges = conn.execute(
            "SELECT ach_id, earned_at FROM achievements WHERE user_id=%s ORDER BY earned_at DESC LIMIT 3",
            (session["user_id"],)).fetchall()
        user = conn.execute("SELECT avatar, streak FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    return render_template("dashboard.html", history=history, stats=stats,
                           cat_stats=cat_stats, progress=progress,
                           recent_badges=recent_badges, ach_map=ACH_MAP,
                           streak=streak, user=user, categories=CATEGORIES)

# ── Mode ─────────────────────────────────────────────────────────────
@app.route("/mode")
@require_login
def mode():
    with get_db() as conn:
        exams = conn.execute("""
            SELECT * FROM exam_sessions WHERE active=1
            AND NOW() BETWEEN start_time::timestamp AND end_time::timestamp
        """).fetchall()
    return render_template("mode.html", categories=CATEGORIES, exams=exams)

# ── BeeWise ──────────────────────────────────────────────────────────
@app.route("/quiz")
@require_login
def quiz():
    session["questions"]    = get_shuffled_questions(QUIZ_LIMIT, balanced=True)
    session["quiz_start"]   = time.time()
    session["tab_switches"] = 0
    return render_template("quiz.html", questions=session["questions"], quiz_time=QUIZ_TIME)

@app.route("/submit_quiz", methods=["POST"])
@require_login
def submit_quiz():
    qs         = session.get("questions", [])
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
    for k in ("questions","quiz_start","tab_switches"): session.pop(k, None)
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
            conn.execute("DELETE FROM rb_temp WHERE user_id=%s", (uid,))
            conn.execute("""INSERT INTO rb_temp (user_id, questions_json, log_json, score, tabs)
                            VALUES (%s,%s,%s,0,0)""",
                         (uid, __import__("json").dumps(qs), __import__("json").dumps([])))
        session["rb_index"]   = 0
        session["rb_end"]     = time.time() + RAPID_TIME
        session["rb_q_start"] = time.time()

    if request.method == "POST":
        import json
        with get_db() as conn:
            row = conn.execute("SELECT * FROM rb_temp WHERE user_id=%s", (uid,)).fetchone()
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
            conn.execute("UPDATE rb_temp SET log_json=%s, score=%s, tabs=%s WHERE user_id=%s",
                         (__import__("json").dumps(log), new_score, new_tabs, uid))
        session["rb_index"]   = index + 1
        session["rb_q_start"] = time.time()

    # Load current state
    import json
    with get_db() as conn:
        row = conn.execute("SELECT * FROM rb_temp WHERE user_id=%s", (uid,)).fetchone()
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
            conn.execute("DELETE FROM rb_temp WHERE user_id=%s", (uid,))
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
@app.route("/practice/setup")
@require_login
def practice_setup():
    cat = request.args.get("cat","")
    if cat not in CATEGORIES:
        flash("Invalid category.", "error")
        return redirect("/mode")
    return render_template("practice_setup.html", cat=cat)

@app.route("/practice")
@require_login
def practice():
    import random
    cat    = request.args.get("cat","")
    chosen = int(request.args.get("timer", 180))
    chosen = max(30, min(chosen, 900))
    qcount = int(request.args.get("qcount", 10))
    qcount = qcount if qcount in (10, 15, 25) else 10

    if cat not in CATEGORIES:
        flash("Invalid category.", "error")
        return redirect("/mode")

    # Clear old session
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
                           total=len(final), cat=cat,
                           left=chosen, chosen=chosen, qcount=qcount)

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
            WHERE u.is_admin=0 GROUP BY r.user_id, u.username, u.avatar
            ORDER BY best_pct DESC LIMIT 10
        """).fetchall()
        top_games = conn.execute("""
            SELECT u.username, u.avatar, COUNT(r.id) as games, ROUND(AVG(r.pct)) as avg_pct
            FROM results r JOIN users u ON u.id=r.user_id
            WHERE u.is_admin=0 GROUP BY r.user_id, u.username, u.avatar
            ORDER BY games DESC LIMIT 10
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
            SELECT al.category, COUNT(*) as attempts,
                   ROUND(SUM(CASE WHEN al.correct=0 THEN 1.0 ELSE 0.0 END)/COUNT(*)*100) as fail_pct
            FROM answer_log al GROUP BY al.category
            HAVING COUNT(*) >= 3 ORDER BY fail_pct DESC LIMIT 10
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
            GROUP BY c.id, c.name, c.code, c.created ORDER BY c.created DESC
        """).fetchall()
        quiz_rooms = conn.execute("""
            SELECT qr.id, qr.title, qr.code, qr.time_limit, qr.created,
                   LENGTH(qr.questions) as qs_len,
                   COUNT(rr.id) as submission_count
            FROM quiz_rooms qr
            LEFT JOIN room_results rr ON rr.room_id = qr.id
            WHERE qr.active=1
            GROUP BY qr.id, qr.title, qr.code, qr.time_limit, qr.created, qr.questions ORDER BY qr.created DESC
        """).fetchall()
        # Add question count to each room
        import json as _j
        quiz_rooms_list = []
        for room in quiz_rooms:
            r = dict(room)
            try:
                qs = _j.loads(conn.execute("SELECT questions FROM quiz_rooms WHERE id=%s", (r["id"],)).fetchone()["questions"])
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
                WHERE cm.class_id = %s
                GROUP BY u.id, u.username, u.avatar ORDER BY best_pct DESC
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
    return render_template("admin.html", students=students, hardest=hardest,
                           flagged=flagged, recent_results=recent_results,
                           total_games=total_games, total_users=total_users,
                           db_questions=db_questions, cat_performance=cat_performance,
                           exams=exams, classes=classes,
                           class_members_detail=class_members_detail,
                           quiz_rooms=quiz_rooms,
                           beexam_papers=beexam_papers,
                           beexam_exam_types=beexam_exam_types,
                           categories=["HTML","CSS","Python","SQL","Flask","General"])

@app.route("/admin/student/<int:uid>")
@require_login
@require_admin
def student_report(uid):
    with get_db() as conn:
        student = conn.execute("SELECT * FROM users WHERE id=%s AND is_admin=0", (uid,)).fetchone()
        if not student: flash("Student not found.", "error"); return redirect("/admin")
        results = conn.execute(
            "SELECT * FROM results WHERE user_id=%s ORDER BY played_at DESC", (uid,)).fetchall()
        stats = conn.execute(
            "SELECT COUNT(*) as games, ROUND(AVG(pct)) as avg_pct, MAX(pct) as best, MIN(pct) as worst, SUM(time_taken) as total_time FROM results WHERE user_id=%s",
            (uid,)).fetchone()
        cat_stats = conn.execute("""
            SELECT al.category, COUNT(*) as total, SUM(al.correct) as correct,
                   ROUND(AVG(al.correct)*100) as pct
            FROM answer_log al JOIN results r ON r.id=al.result_id
            WHERE r.user_id=%s GROUP BY al.category ORDER BY pct DESC
        """, (uid,)).fetchall()
        earned = conn.execute(
            "SELECT ach_id, earned_at FROM achievements WHERE user_id=%s ORDER BY earned_at DESC",
            (uid,)).fetchall()
        progress = list(reversed(conn.execute(
            "SELECT pct, mode, played_at FROM results WHERE user_id=%s ORDER BY played_at DESC LIMIT 15",
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
        conn.execute("INSERT INTO questions_db (question,opt0,opt1,opt2,opt3,answer,category) VALUES (%s,%s,%s,%s,%s,%s,%s)",
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
                conn.execute("INSERT INTO questions_db (question,opt0,opt1,opt2,opt3,answer,category) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                             (q,o0,o1,o2,o3,0,cat))
                count += 1
            except: errors += 1
    flash(f"Imported {count} questions! ✅" + (f" ({errors} skipped)" if errors else ""), "success")
    return redirect("/admin")

@app.route("/admin/delete_question/<int:qid>", methods=["POST"])
@require_login
@require_admin
def delete_question(qid):
    with get_db() as conn: conn.execute("DELETE FROM questions_db WHERE id=%s", (qid,))
    flash("Question deleted.", "success"); return redirect("/admin")

@app.route("/admin/delete_student/<int:uid>", methods=["POST"])
@require_login
@require_admin
def delete_student(uid):
    with get_db() as conn:
        conn.execute("DELETE FROM answer_log WHERE result_id IN (SELECT id FROM results WHERE user_id=%s)",(uid,))
        conn.execute("DELETE FROM results WHERE user_id=%s",(uid,))
        conn.execute("DELETE FROM achievements WHERE user_id=%s",(uid,))
        conn.execute("DELETE FROM users WHERE id=%s AND is_admin=0",(uid,))
    flash("Student removed.", "success"); return redirect("/admin")

@app.route("/admin/create_exam", methods=["POST"])
@require_login
@require_admin
def create_exam():
    title,start,end = (request.form.get(k,"").strip() for k in ("title","start_time","end_time"))
    if not all([title,start,end]):
        flash("All fields required.", "error"); return redirect("/admin")
    with get_db() as conn:
        conn.execute("INSERT INTO exam_sessions (title,start_time,end_time,created_by) VALUES (%s,%s,%s,%s)",
                     (title,start,end,session["user_id"]))
    flash(f"Exam '{title}' scheduled! 🎓", "success"); return redirect("/admin")

@app.route("/admin/delete_exam/<int:eid>", methods=["POST"])
@require_login
@require_admin
def delete_exam(eid):
    with get_db() as conn: conn.execute("DELETE FROM exam_sessions WHERE id=%s", (eid,))
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
                    "INSERT INTO questions_db (question,opt0,opt1,opt2,opt3,answer,category) VALUES (%s,%s,%s,%s,%s,%s,%s)",
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
            WHERE r.user_id = %s
            GROUP BY al.category ORDER BY pct ASC
        """, (session["user_id"],)).fetchall()
        total_games = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE user_id=%s",
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
        _c.execute("INSERT INTO achievements (user_id, ach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                   (session["user_id"], "ask_beebot"))
        _c.execute("INSERT INTO achievements (user_id, ach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                   (session["user_id"], "beebot_first_reply"))
        beebot_asks = _c.execute(
            "SELECT COUNT(*) as c FROM achievements WHERE user_id=%s AND ach_id='ask_beebot'",
            (session["user_id"],)).fetchone()["c"]
    if beebot_asks >= 10:
        with get_db() as _c:
            _c.execute("INSERT INTO achievements (user_id, ach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                       (session["user_id"], "beebot_10"))

    return jsonify({"reply": reply})



# ── CustomizeBee Mode ────────────────────────────────────────────────────────
@app.route("/customizebee", methods=["GET","POST"])
@require_login
def customizebee():
    """CustomizeBee setup page — upload CSV or generate via AI."""
    return render_template("customizebee.html")

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
            conn.execute("DELETE FROM cb_sessions WHERE user_id=%s", (session["user_id"],))
            conn.execute("""INSERT INTO cb_sessions
                (user_id, questions, idx, score, log, total, end_time)
                VALUES (%s,%s,0,0,'[]',%s,%s)""",
                (session["user_id"], _json.dumps(questions), len(questions), end_time))
        session["cb_active"] = True
        msg = f"Loaded {len(questions)} questions!"
        if errors:
            msg += f" ({len(errors)} rows skipped)"
        flash(msg, "success")
        # Award CSV upload achievements
        with get_db() as _c:
            _c.execute("INSERT INTO achievements (user_id, ach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                       (session["user_id"], "try_customizebee"))
            _c.execute("INSERT INTO achievements (user_id, ach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                       (session["user_id"], "first_csv_upload"))
        return redirect("/customizebee/quiz")
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
        conn.execute("DELETE FROM cb_sessions WHERE user_id=%s", (session["user_id"],))
        conn.execute("""INSERT INTO cb_sessions
            (user_id, questions, idx, score, log, total, end_time)
            VALUES (%s,%s,0,0,'[]',%s,%s)""",
            (session["user_id"], _json.dumps(final), len(final), end_time))
    session["cb_active"] = True
    return redirect("/customizebee/quiz")

@app.route("/customizebee/quiz", methods=["GET","POST"])
@require_login
def customizebee_quiz():
    """Run the custom quiz — questions stored in DB to avoid session cookie size limit."""
    import json as _json
    uid = session["user_id"]

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cb_sessions WHERE user_id=%s", (uid,)
        ).fetchone()

    if not row:
        flash("No questions loaded. Please upload a CSV or generate via AI.", "error")
        return redirect("/customizebee")

    qs    = _json.loads(row["questions"])
    idx   = row["idx"]
    score = row["score"]
    log   = _json.loads(row["log"])
    total = row["total"]
    end_t = row["end_time"]

    if request.method == "POST":
        q      = qs[idx]
        chosen = int(request.form.get("answer", -1))
        if chosen == q["a"]:
            score += 1
        log.append({
            "q":       q["q"],
            "options": q["options"],
            "chosen":  chosen,
            "correct": q["a"],
            "cat":     q.get("cat","Custom")
        })
        idx += 1
        with get_db() as conn:
            conn.execute(
                "UPDATE cb_sessions SET idx=%s, score=%s, log=%s WHERE user_id=%s",
                (idx, score, _json.dumps(log), uid)
            )

    # Finished%s
    if idx >= total or time.time() > end_t:
        pct = round(score / total * 100) if total else 0
        with get_db() as conn:
            conn.execute("DELETE FROM cb_sessions WHERE user_id=%s", (uid,))
        return render_template("customizebee_result.html",
                               score=score, total=total, pct=pct, log=log)

    q    = qs[idx]
    left = max(0, int(end_t - time.time()))
    return render_template("customizebee_quiz.html",
                           q=q, num=idx+1, total=total, left=left)

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
        conn.execute("UPDATE questions_db SET question=%s,opt0=%s,opt1=%s,opt2=%s,opt3=%s,category=%s WHERE id=%s",
                     (q, o0, o1, o2, o3, cat, qid))
    flash("Question updated! 🐝", "success")
    return redirect("/admin")

# ── Class code system ─────────────────────────────────────────────────
def init_classes():
    # Tables already exist in Supabase — just backfill admin_id where missing
    try:
        with get_db() as conn:
            conn.execute("UPDATE classes SET admin_id=created_by WHERE admin_id IS NULL")
    except Exception as e:
        print(f"[init_classes] skipped: {e}")
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
            conn.execute("INSERT INTO classes (name,code,created_by,admin_id) VALUES (%s,%s,%s,%s)",
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
        conn.execute("DELETE FROM class_members WHERE class_id=%s", (cid,))
        conn.execute("DELETE FROM classes WHERE id=%s", (cid,))
    flash("Class deleted.", "success")
    return redirect("/admin?tab=classes")

@app.route("/join_class", methods=["POST"])
@require_login
def join_class():
    code = request.form.get("class_code","").strip().upper()
    with get_db() as conn:
        cls = conn.execute("SELECT * FROM classes WHERE code=%s", (code,)).fetchone()
        if not cls:
            flash("Invalid class code. Check and try again.", "error")
            return redirect("/profile")
        try:
            conn.execute("INSERT INTO class_members (class_id,user_id) VALUES (%s,%s)",
                         (cls["id"], session["user_id"]))
            flash(f"Joined class '{cls['name']}'! 🎓", "success")
        except:
            flash("You are already in this class.", "error")
    return redirect("/profile")

@app.route("/leave_class/<int:cid>", methods=["POST"])
@require_login
def leave_class(cid):
    with get_db() as conn:
        conn.execute("DELETE FROM class_members WHERE class_id=%s AND user_id=%s",
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
                "INSERT INTO quiz_rooms (title,code,created_by,questions,time_limit) VALUES (%s,%s,%s,%s,%s)",
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
        conn.execute("DELETE FROM room_results WHERE room_id=%s", (rid,))
        conn.execute("DELETE FROM quiz_rooms WHERE id=%s", (rid,))
    flash("Room deleted.", "success")
    return redirect("/admin?tab=rooms")

@app.route("/admin/room_results/<int:rid>")
@require_login
@require_admin
def admin_room_results(rid):
    with get_db() as conn:
        room = conn.execute("SELECT * FROM quiz_rooms WHERE id=%s", (rid,)).fetchone()
        if not room:
            flash("Room not found.", "error")
            return redirect("/admin?tab=rooms")
        results = conn.execute("""
            SELECT u.username, u.avatar, rr.score, rr.total, rr.pct,
                   rr.time_taken, rr.finished
            FROM room_results rr
            JOIN users u ON u.id = rr.user_id
            WHERE rr.room_id = %s
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
                "SELECT * FROM quiz_rooms WHERE code=%s AND active=1", (code,)
            ).fetchone()
        if not room:
            flash("Room not found. Check the code and try again.", "error")
            return redirect("/room")
        # Check already submitted
        with get_db() as conn:
            already = conn.execute(
                "SELECT id FROM room_results WHERE room_id=%s AND user_id=%s",
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
        room = conn.execute("SELECT * FROM quiz_rooms WHERE id=%s AND active=1",(rid,)).fetchone()
    if not room:
        flash("Room not found or no longer active.", "error")
        return redirect("/room")
    already = False
    with get_db() as conn:
        already = conn.execute(
            "SELECT id FROM room_results WHERE room_id=%s AND user_id=%s",
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
        conn.execute("DELETE FROM room_quiz_sessions WHERE user_id=%s", (session["user_id"],))
        conn.execute("""INSERT INTO room_quiz_sessions
            (user_id, room_id, room_title, questions, idx, score, total, start_time, end_time)
            VALUES (%s,%s,%s,%s,0,0,%s,%s,%s)""",
            (session["user_id"], rid, room["title"],
             _j2.dumps(final), len(final), start_t, end_t))
    session["rq_active"] = rid
    return redirect("/room/quiz")

@app.route("/room/quiz", methods=["GET","POST"])
@require_login
def room_quiz():
    import json as _j3
    uid = session["user_id"]

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM room_quiz_sessions WHERE user_id=%s", (uid,)
        ).fetchone()

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

    if request.method == "POST":
        chosen  = int(request.form.get("answer", -1))
        if chosen == qs[idx]["a"]:
            score += 1
        idx += 1
        with get_db() as conn:
            conn.execute(
                "UPDATE room_quiz_sessions SET idx=%s, score=%s WHERE user_id=%s",
                (idx, score, uid)
            )

    # Finished%s
    if idx >= total or time.time() > end_t:
        pct        = round(score / total * 100) if total else 0
        time_taken = int(time.time() - start_t)
        with get_db() as conn:
            try:
                conn.execute(
                    "INSERT INTO room_results (room_id,user_id,score,total,pct,time_taken) VALUES (%s,%s,%s,%s,%s,%s)",
                    (rid, uid, score, total, pct, time_taken)
                )
            except: pass
            conn.execute("DELETE FROM room_quiz_sessions WHERE user_id=%s", (uid,))
        session.pop("rq_active", None)
        return render_template("room_result.html",
                               score=score, total=total, pct=pct,
                               time_taken=time_taken, title=title, rid=rid)

    q    = qs[idx]
    left = max(0, int(end_t - time.time()))
    return render_template("room_quiz.html",
                           q=q, num=idx+1, total=total, left=left, title=title)





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


# ── BeeXam ─────────────────────────────────────────────────────────────────────
def init_beexam():
    pass  # Tables already created in Supabase via migration SQL


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
                    conn.execute("INSERT INTO beexam_exam_types (name, exam_group) VALUES (%s,%s)",
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
            "SELECT * FROM beexam_papers WHERE id=%s", (paper_id,)
        ).fetchone()
        if not paper:
            flash("Paper not found.", "error")
            return redirect("/beexam")
        raw_qs = conn.execute(
            "SELECT * FROM beexam_questions WHERE paper_id=%s ORDER BY id", (paper_id,)
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
    return redirect("/beexam/quiz")


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

    if request.method == "POST":
        ans = request.form.get("answer")
        answers = session.get("bx_answers", [])
        answers.append(int(ans) if ans is not None and ans != "" else -1)
        session["bx_answers"] = answers
        session["bx_index"]   = idx + 1
        idx += 1

    # Time up or all answered → go to result
    if time_left <= 0 or idx >= len(questions):
        # Pad skipped
        answers = session.get("bx_answers", [])
        while len(answers) < len(questions):
            answers.append(-1)
        session["bx_answers"] = answers
        return redirect("/beexam/result")

    q = questions[idx]
    with get_db() as conn:
        paper = conn.execute(
            "SELECT * FROM beexam_papers WHERE id=%s", (session["bx_paper_id"],)
        ).fetchone()

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
            "SELECT * FROM beexam_papers WHERE id=%s", (paper_id,)
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
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (exam_name, subject, year, time_limit, cutoff, exam_group, session["user_id"])
            )
            paper_id = cur.fetchone()["id"]
            count = 0
            for row in rows:
                if len(row) < 5: continue
                cat = row[5].strip() if len(row) > 5 else ""
                conn.execute("""
                    INSERT INTO beexam_questions
                      (paper_id, question, opt0, opt1, opt2, opt3, category)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (paper_id, row[0].strip(), row[1].strip(),
                      row[2].strip(), row[3].strip(), row[4].strip(), cat))
                count += 1
            conn.execute(
                "UPDATE beexam_papers SET question_count=%s WHERE id=%s",
                (count, paper_id)
            )
        flash(f"✅ Uploaded {count} questions for {exam_name} {year}!", "success")
    except Exception as e:
        flash(f"Upload failed: {e}", "error")

    return redirect("/admin?tab=beexam")


@app.route("/admin/beexam/create_exam_type", methods=["POST"])
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
            conn.execute("INSERT INTO beexam_exam_types (name, exam_group) VALUES (%s,%s)", (name, group))
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
            VALUES (%s,%s,%s,%s,%s,%s,%s)""", (paper_id, question, opt0, opt1, opt2, opt3, category))
        conn.execute("UPDATE beexam_papers SET question_count = question_count+1 WHERE id=%s", (paper_id,))
    flash("✅ Question added!", "success")
    return redirect("/admin?tab=beexam")


@app.route("/admin/beexam/delete_exam_type/<exam_name>", methods=["POST"])
@require_login
@require_admin
def admin_beexam_delete_type(exam_name):
    init_beexam()
    with get_db() as conn:
        # Delete all questions + papers under this exam, then the type
        papers = conn.execute("SELECT id FROM beexam_papers WHERE exam_name=%s", (exam_name,)).fetchall()
        for p in papers:
            conn.execute("DELETE FROM beexam_questions WHERE paper_id=%s", (p["id"],))
        conn.execute("DELETE FROM beexam_papers WHERE exam_name=%s", (exam_name,))
        conn.execute("DELETE FROM beexam_exam_types WHERE name=%s", (exam_name,))
    flash(f"Deleted '{exam_name}' and all its papers.", "success")
    return redirect("/admin?tab=beexam")


@app.route("/admin/beexam/delete/<int:paper_id>", methods=["POST"])
@require_login
@require_admin
def admin_beexam_delete(paper_id):
    init_beexam()
    with get_db() as conn:
        paper = conn.execute(
            "SELECT exam_name, year FROM beexam_papers WHERE id=%s", (paper_id,)
        ).fetchone()
        if paper:
            conn.execute("DELETE FROM beexam_questions WHERE paper_id=%s", (paper_id,))
            conn.execute("DELETE FROM beexam_papers WHERE id=%s", (paper_id,))
            flash(f"Deleted {paper['exam_name']} {paper['year']}.", "success")
    return redirect("/admin?tab=beexam")


# ── Teacher Dashboard ──────────────────────────────────────────────────────────
@app.route("/teacher")
@require_login
@require_teacher
def teacher_dashboard():
    tid = session["user_id"]
    with get_db() as conn:
        classes = conn.execute(
            "SELECT * FROM classes WHERE admin_id=%s", (tid,)
        ).fetchall()
        class_data = []
        for cls in classes:
            students = conn.execute("""
                SELECT u.id, u.username, u.avatar, u.streak,
                       COUNT(r.id)              AS games,
                       ROUND(AVG(r.pct),1)      AS avg_pct,
                       MAX(r.pct)               AS best,
                       MAX(r.played_at)         AS last_played
                FROM class_members cm
                JOIN users    u ON u.id = cm.user_id
                LEFT JOIN results r ON r.user_id = u.id
                WHERE cm.class_id=%s
                GROUP BY u.id, u.username, u.avatar, u.streak
                ORDER BY avg_pct DESC
            """, (cls["id"],)).fetchall()
            class_data.append({"cls": cls, "students": students})
    return render_template("teacher_dashboard.html",
                           class_data=class_data,
                           total_classes=len(classes))


@app.route("/teacher/student/<int:uid>")
@require_login
@require_teacher
def teacher_student_view(uid):
    tid = session["user_id"]
    with get_db() as conn:
        allowed = conn.execute("""
            SELECT 1 FROM class_members cm
            JOIN classes c ON c.id = cm.class_id
            WHERE cm.user_id=%s AND c.admin_id=%s
        """, (uid, tid)).fetchone()
        if not allowed:
            flash("You can only view students in your own classes.", "error")
            return redirect("/teacher")
        student = conn.execute(
            "SELECT id, username, avatar, streak FROM users WHERE id=%s", (uid,)
        ).fetchone()
        results = conn.execute("""
            SELECT mode, score, total, pct, grade, time_taken,
                   tab_switches, played_at
            FROM results WHERE user_id=%s
            ORDER BY played_at DESC LIMIT 50
        """, (uid,)).fetchall()
        stats = conn.execute("""
            SELECT COUNT(*)           AS games,
                   ROUND(AVG(pct),1)  AS avg_pct,
                   MAX(pct)           AS best,
                   MIN(pct)           AS worst
            FROM results WHERE user_id=%s
        """, (uid,)).fetchone()
        cat_stats = conn.execute("""
            SELECT al.category,
                   COUNT(*)                                   AS total,
                   SUM(al.correct)                           AS correct,
                   ROUND(100.0*SUM(al.correct)/COUNT(*),1)  AS pct
            FROM answer_log al
            JOIN results r ON r.id = al.result_id
            WHERE r.user_id=%s
            GROUP BY al.category
            ORDER BY pct ASC
        """, (uid,)).fetchall()
        earned = conn.execute(
            "SELECT ach_id FROM achievements WHERE user_id=%s", (uid,)
        ).fetchall()
    return render_template("student_report.html",
                           student=student, results=results,
                           stats=stats, cat_stats=cat_stats,
                           earned=earned, ach_map={},
                           back_url="/teacher", progress=[])


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
            "INSERT INTO classes (name, code, created_by, admin_id) VALUES (%s,%s,%s,%s)",
            (name, code, session["user_id"], session["user_id"])
        )
    flash(f'Class "{name}" created! Join code: {code}', "success")
    return redirect("/teacher")


if __name__ == "__main__":
    app.run(debug=False)