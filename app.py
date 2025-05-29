from flask import Flask, render_template, request, redirect, session, flash, url_for
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from pymongo import DESCENDING
import cloudinary
import cloudinary.uploader
from io import BytesIO
import random


cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# Connect MongoDB
client = MongoClient(os.getenv("MONGO_URI"))
db = client.chemistry_site
submissions = db["submissions"]
videos = db.videos
notes = db.notes
exams = db.exams
routines = db.routines
playlists = db.playlists 
notices = db.notices
helpers_collection = db["helpers"]

ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")


@app.route("/")
def index():
    return redirect("/welcome")

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/class")
def class_page():
    data = list(videos.find().sort("_id", DESCENDING))  
    return render_template("class.html", videos=data)

@app.route("/note")
def note_page():
    data = list(notes.find().sort("_id", DESCENDING))  
    return render_template("note.html", notes=data)

@app.route("/exam")
def exam_page():
    data = list(exams.find().sort("_id", DESCENDING))  
    return render_template("exam.html", videos=data)

@app.route("/routine")
def routine_page():
    data = list(routines.find())
    return render_template("routine.html", routines=data)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/playlist-list")
def playlists_page():
    all_playlists = list(playlists.find().sort("_id", DESCENDING))
    return render_template("playlist-list.html", playlists=all_playlists)

@app.route("/playlist/<playlist_id>")
def playlist_page(playlist_id):
    playlist = playlists.find_one({"_id": ObjectId(playlist_id)})
    if not playlist:
        return "Playlist not found", 404
    return render_template("playlist.html", playlist=playlist)


@app.route("/playlist-create", methods=["GET", "POST"])
def playlist_create():
    if not session.get("admin"):
        return redirect("/admin")

    if request.method == "POST":
        playlist_name = request.form.get("playlist_name")
        playlist_image = request.form.get("playlist_image")  
        video_titles = request.form.getlist("video_title")
        video_links = request.form.getlist("video_link")

        if not playlist_name:
            flash("Playlist name is required.", "error")
            return redirect("/playlist-create")

        if not playlist_image:
            flash("Playlist image link is required.", "error")
            return redirect("/playlist-create")

        videos_list = []
        for title, link in zip(video_titles, video_links):
            if title.strip() and link.strip():
                videos_list.append({"title": title.strip(), "link": link.strip()})

        if not videos_list:
            flash("At least one video with title and link is required.", "error")
            return redirect("/playlist-create")

        playlist_doc = {
            "name": playlist_name,
            "image": playlist_image,     
            "videos": videos_list
        }

        inserted = playlists.insert_one(playlist_doc)
        flash("Playlist created successfully!", "success")
        return redirect(f"/playlist/{inserted.inserted_id}")

    return render_template("playlist_create.html")



@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form["username"]
        pw = request.form["password"]
        if user == ADMIN_USER and pw == ADMIN_PASS:
            session["admin"] = True
            return redirect("/admin-panel")
        else:
            error = "Wrong username or password"
            return render_template("admin.html", error=error)
    return render_template("admin.html")


@app.route("/admin-panel", methods=["GET", "POST"])
def admin_panel():
    if not session.get("admin"):
        return redirect("/admin")

    if request.method == "POST":
        content_type = request.form.get("type")

        # Handle simple uploads (class, note, exam, routine)
        if content_type in ["class", "note", "exam", "routine"]:
            if content_type == "routine":
                title = request.form.get("routine_title")
                chapter = request.form.get("routine_chapter")
                if not title or not chapter:
                    flash("Routine title and chapter are required.", "error")
                    return redirect("/admin-panel")

                entry = {"title": title, "chapter": chapter}
                routines.insert_one(entry)
                flash("Routine uploaded successfully.", "success")
            else:
                title = request.form.get("title")
                link = request.form.get("link")
                if not title or not link:
                    flash(f"{content_type.capitalize()} title and link are required.", "error")
                    return redirect("/admin-panel")

                entry = {"title": title, "link": link}
                if content_type == "class":
                    videos.insert_one(entry)
                    flash("Class content uploaded successfully.", "success")
                elif content_type == "note":
                    notes.insert_one(entry)
                    flash("Note uploaded successfully.", "success")
                elif content_type == "exam":
                    exams.insert_one(entry)
                    flash("Exam uploaded successfully.", "success")

        # Handle detailed exam creation
        elif content_type == "create_exam" or content_type is None:
            exam_title = request.form.get("exam_title")
            start_time_str = request.form.get("start_time")
            duration = request.form.get("duration")

            if not exam_title or not start_time_str:
                flash("Exam title and start time are required.", "error")
                return redirect("/admin-panel")

            try:
                start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
                duration = int(duration)
            except ValueError:
                flash("Invalid start time format or duration.", "error")
                return redirect("/admin-panel")

            questions = []
            keys = request.form.keys()
            question_numbers = set()

            for key in keys:
                if "_" in key:
                    parts = key.split("_")
                    try:
                        qnum = int(parts[-1])
                        question_numbers.add(qnum)
                    except:
                        pass

            for qnum in sorted(question_numbers):
                mcq_question = request.form.get(f"mcq_question_{qnum}")
                cq_question = request.form.get(f"cq_question_{qnum}")

                if mcq_question:
                    options = []
                    for i in range(1, 5):
                        opt = request.form.get(f"mcq_option{i}_{qnum}")
                        if opt:
                            options.append(opt)

                    correct_option = request.form.get(f"mcq_correct_{qnum}")
                    try:
                        correct_option = int(correct_option)
                    except:
                        correct_option = None

                    image_file = request.files.get(f"mcq_image_{qnum}")
                    image_url = None
                    if image_file and image_file.filename != "":
                        result = cloudinary.uploader.upload(image_file)
                        image_url = result.get("secure_url")

                    question_data = {
                        "type": "mcq",
                        "question": mcq_question,
                        "options": options,
                        "correct_option": correct_option,
                        "image": image_url
                    }
                    questions.append(question_data)

                elif cq_question:
                    image_file = request.files.get(f"cq_image_{qnum}")
                    image_url = None
                    if image_file and image_file.filename != "":
                        result = cloudinary.uploader.upload(image_file)
                        image_url = result.get("secure_url")

                    question_data = {
                        "type": "cq",
                        "question": cq_question,
                        "image": image_url
                    }
                    questions.append(question_data)

            exam_entry = {
                "title": exam_title,
                "start_time": start_time,
                "duration": duration,
                "questions": questions
            }
            exams.insert_one(exam_entry)
            flash("Detailed exam created successfully.", "success")

    return render_template("admin_panel.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/admin")

@app.route("/contact")
def contact():
    notices = list(db.notices.find({}, {"_id": 0, "message": 1}).sort("_id", -1))
    notice_messages = [n["message"] for n in notices]
    return render_template("upcoming.html", notice_messages=notice_messages)

@app.route("/admin/notice", methods=["GET", "POST"])
def admin_notice():
    if not session.get("admin"):
        return redirect("/admin")

    notice_doc = notices.find_one(sort=[('_id', -1)])

    if request.method == "POST":
        message = request.form.get("notice_message", "").strip()
        if message:
            # Insert or update notice (for simplicity insert new)
            notices.insert_one({"message": message})
            flash("Notice updated successfully!", "success")
            return redirect("/admin/notice")
        else:
            flash("Notice message cannot be empty.", "error")

    return render_template("notice.html", notice_message=notice_doc['message'] if notice_doc else "")

@app.route("/success")
def success():
    score = request.args.get("score")
    total = request.args.get("total")
    return render_template("success.html", score=score, total=total)

@app.route("/exam/<exam_id>/start", methods=["GET", "POST"])
def start_exam(exam_id):
    exam = exams.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        return "Exam not found", 404

    if request.method == "POST":
        name = request.form.get("name")
        number = request.form.get("number")

        answers = []
        score = 0
        total_mcq = 0

        for i, q in enumerate(exam['questions']):
            q_type = q.get("type").lower()
            answer_text = request.form.get(f"answer_{i}")
            image_file = request.files.get(f"image_{i}")  # for CQ, may be None for MCQ

            if q_type == "mcq":
                total_mcq += 1
                correct = str(q.get("correct_option"))
                is_correct = (answer_text == correct)
                if is_correct:
                    score += 1
                answers.append({
                    "question": q["question"],
                    "type": "MCQ",
                    "answer": answer_text,
                    "correct_answer": correct,
                    "is_correct": is_correct
                })

            elif q_type == "cq":
                answer_data = {
                    "question": q["question"],
                    "type": "CQ",
                    "answer_text": answer_text
                }

                if image_file and image_file.filename != "":
                    # Upload image to Cloudinary
                    upload_result = cloudinary.uploader.upload(image_file)
                    image_url = upload_result.get("secure_url")
                    if image_url:
                        answer_data["image_url"] = image_url

                answers.append(answer_data)

        # Save submission to MongoDB
        submission_doc = {
            "exam_id": ObjectId(exam_id),
            "submitted_at": datetime.utcnow(),
            "name": name,
            "number": number,
            "answers": answers,
            "score": score,
            "total_mcq": total_mcq
        }
        submissions.insert_one(submission_doc)

        # Redirect with score info
        return redirect(url_for("success", score=score, total=total_mcq))

    # GET: Render exam page
    return render_template("takeexam.html", exam=exam, enumerate=enumerate, duration=exam['duration'])


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route("/members")
def members():
    helpers = list(helpers_collection.find({}, {"_id": 0}))
    return render_template("members.html", helpers=helpers)

@app.route("/addmember", methods=["GET", "POST"])
def add_member():
    if request.method == "POST":
        name = request.form["name"]
        qualification = request.form["qualification"]
        contact = request.form.get("contact", "No Contact")
        image_url = request.form["image_url"]
        role = request.form["role"].lower()  # Ensure role is in lowercase

        helper = {
            "name": name,
            "qualification": qualification,
            "contact": contact if contact else "No Contact",
            "image_url": image_url,
            "role": role  # Must be 'admin', 'moderator', or 'ambassador'
        }

        helpers_collection.insert_one(helper)
        return redirect(url_for("members"))

    return render_template("add_members.html")

if __name__ == "__main__":
    app.run(debug=True)


