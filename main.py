from flask_login import LoginManager, login_required, login_user, logout_user, user_logged_out, current_user
from flask import Flask, render_template, redirect, url_for, flash, session, request
from wtforms import SubmitField, PasswordField, EmailField
from wtforms.validators import DataRequired, Email, Length
from flask_wtf import FlaskForm
from database import db, User, Paper
from flask_session import Session
from arxiv_scraper import get_papers, vectorizer
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from recommender import update_user_profile, cosine
import logging
import bcrypt
import json
import atexit
import os
from math import ceil

app = Flask(__name__)

# ---------------------------------------------------------
# App configuration
app.config.from_file('config.json', load=json.load)
if not app.debug:
    logging.basicConfig(
        level=logging.DEBUG,
        filename='log.txt',
        filemode='a',
        format='%(asctime)s | %(filename)s:%(lineno)s:%(levelname)s | %(message)s'
    )

# Creating server session to store account info of users that didn't complete the sign up
Session(app)

db.init_app(app)

# ---------------------------------------------------------
# Flask-login stuff
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def user_loader(user_id):
    return db.session.get(User, user_id)

# Remove session variables when logging out, it prevents someone from using a loophole to login without password through interests page
@user_logged_out.connect
def remove_session(*e, **extra):
    session['email'] = ""

# ---------------------------------------------------------
# Scheduling the arXiv scraper
ARXIV_TIMEZONE = timezone.utc
def download_papers():
    with app.app_context():
        today = datetime.now(ARXIV_TIMEZONE)
        yesterday = today - timedelta(days=1)
        yesterday = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        get_papers(yesterday)

# This prevents scheduling the function twice in the debug mode. More info: https://stackoverflow.com/questions/14874782/apscheduler-in-flask-executes-twice
if not app.debug and os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler()
    # Download papers everyday at 00:30 AM in arxiv timezone (they work in 24 hour cycles)
    scheduler.add_job(download_papers, trigger="cron", hour=0, minute=30, timezone=ARXIV_TIMEZONE)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

# ---------------------------------------------------------
# Forms
class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=72)])
    login_submit = SubmitField("Login")

class SignUpForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=72)])
    repeat_password = PasswordField("Repeat password", validators=[DataRequired(), Length(min=8, max=72)])
    sign_up_submit = SubmitField("Sign up")

    def validate(self, **kwargs):
        validators = FlaskForm.validate(self)
        if validators and self.password.data == self.repeat_password.data:
            return True
        return False

# ---------------------------------------------------------
# Endpoints
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.get(User, form.email.data)
        if not user:
            flash("Couldn't find your account")
        elif not bcrypt.checkpw(form.password.data.encode('utf8'), user.password):
            flash("Incorrect password")
        elif len(user.vector) == 0:
            flash("You haven't completed the sign up yet")
            session['email'] = form.email.data
            return redirect(url_for('interests'))
        else:
            user.auth = True
            db.session.commit()
            login_user(user, remember=True)
            flash("Logged in successfully")
            logging.info(f"User with email: {user.email} logged in")
            return redirect(url_for('home_page', page=1))

    return render_template("login.html", login_form=form)

@app.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    form = SignUpForm()
    if form.validate_on_submit():
        new_user = User(
            email = form.email.data,
            password = bcrypt.hashpw(form.password.data.encode('utf8'), bcrypt.gensalt()),
            auth=False,
            vector=dict(),
        )
        db.session.add(new_user)
        try:
            db.session.commit()
            flash("Successfully added a new user")
            logging.info(f"User with email: {new_user.email} created a new account")
            session['email'] = form.email.data
            return redirect(url_for('interests'))
        except:
            db.session.rollback()
            flash("Something went wrong, try again")

    return render_template("sign_up.html", sign_up_form=form)

# The labels for the interests page form and their tokens after text normalization
LABELS = [
    "NLP", "Transformers", "Neural networks", "Robotics", "Deep learning", "Optimization", "Computer vision", "Supervised learning", 
    "Unsupervised learning", "Reinforcement learning"
]

@app.route('/interests', methods=['GET', 'POST'])
def interests():
    if not session['email']:
        flash("You cannot access this page")
        return redirect(url_for('login')) 
    if request.method == 'POST':
        at_least_one_toggled = False
        # Getting data from the form to the database
        analyzer = vectorizer.build_analyzer()
        vector = dict()
        for chip in request.form:
            if chip != "interests_submit" and request.form[chip] == 'on':
                at_least_one_toggled = True
                tokens = analyzer(chip)
                for token in tokens:
                    vector[token] = 1
        if not at_least_one_toggled:
            flash("You must select at least one field")
        else:
            user = db.session.get(User, session['email'])
            user.vector = vector
            try:
                db.session.commit()
                flash("Updated interests")
            except:
                db.session.rollback()
                flash("Something went wrong, try again")
            login_user(user, remember=True)
            session['email'] = ""
            return redirect(url_for('home_page', page=1))

    return render_template("interests.html", interests_form=LABELS)

# This filter is used to format dates nicely on the home page
@app.template_filter("display_date")
def display_date(date):
    months = [
        "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"
    ]
    return months[date.month-1] + " " + str(date.year)

TIME_OPTIONS_TABLE = ["Day", "Week", "2 Weeks", "Month", "3 Months", "6 Months", "Year"]
PAGE_LENGTH = 20
@app.route('/', methods=['GET', 'POST'])
@login_required
def home_page():
    if request.method == 'POST':
        # The user liked an article
        for name in request.json:
            paper = db.session.get(Paper, int(name))
            if request.json[name]:
                current_user.liked_papers.append(paper)
                current_user.vector = update_user_profile(current_user.vector, paper.vector, 0.95, 0.05, 0.02)
            else:
                current_user.liked_papers.remove(paper)
                current_user.vector = update_user_profile(current_user.vector, paper.vector, 1/0.95, -0.05, 0)
            try:
                db.session.commit()
            except:
                db.session.rollback()

    # Getting the named parameters from the URL
    time_option = request.args.get("time", default=0, type=int)
    sort_option = request.args.get("sort", default="Relevance", type=str)
    page        = request.args.get('page', default=1, type=int)

    # Filtering the results by time period
    match time_option:
        case 0:
            papers = Paper.query.filter(Paper.updated_date >= datetime.now() - timedelta(days=2)).all()
        case 1:
            papers = Paper.query.filter(Paper.updated_date >= datetime.now() - timedelta(weeks=1)).all()
        case 2:
            papers = Paper.query.filter(Paper.updated_date >= datetime.now() - timedelta(weeks=2)).all()
        case 3:
            papers = Paper.query.filter(Paper.updated_date >= datetime.now() - timedelta(weeks=4)).all()
        case 4:
            papers = Paper.query.filter(Paper.updated_date >= datetime.now() - timedelta(weeks=13)).all()
        case 5:
            papers = Paper.query.filter(Paper.updated_date >= datetime.now() - timedelta(weeks=26)).all()
        case 6:
            papers = Paper.query.filter(Paper.updated_date >= datetime.now() - timedelta(weeks=52)).all()
        case _:
            flash("Wrong URL")
            return redirect(url_for('home_page'))

    # Assigning relevance scores to papers
    papers = [[p, cosine(current_user.vector, p.vector)] for p in papers]
    
    # Sort the papers
    match sort_option:
        case "Relevance":
            papers.sort(key=lambda x: x[1], reverse=True)
        case "Popularity":
            papers.sort(key=lambda x: x[0].popularity, reverse=True)
        case "Date":
            papers.sort(key=lambda x: x[0].updated_date, reverse=True)
        case _:
            flash("Wrong URL")
            return redirect(url_for('home_page'))

    # Assigning correct page numbers
    page_number_1 = page - 1
    page_number_2 = page 
    page_number_3 = page + 1
    if page == 1:
        page_number_1 = page
        page_number_2 = page + 1
        page_number_3 = page + 2
    if page == ceil(len(papers) / PAGE_LENGTH):
        page_number_1 = page - 2
        page_number_2 = page - 1
        page_number_3 = page
        
    return render_template(
        "index.html",
        current_page=page,
        page_number_1=page_number_1,
        page_number_2=page_number_2,
        page_number_3=page_number_3,
        number_of_pages=ceil(len(papers) / PAGE_LENGTH),
        papers=[x[0] for x in papers][(page-1)*PAGE_LENGTH:page*PAGE_LENGTH],
        relevances=[x[1] for x in papers][(page-1)*PAGE_LENGTH:page*PAGE_LENGTH],
        time_options=TIME_OPTIONS_TABLE,
        time=time_option,
        sort=sort_option,
        # Passing the zip function, bacause the jinja engine doesn't import it by default
        zip=zip
    )

@app.route('/search', methods=['GET'])
@login_required
def search():
    # Getting the named parameters from the URL
    sort_option = request.args.get("sort", default="Relevance", type=str)
    page        = request.args.get('page', default=1, type=int)
    query       = request.args.get('query', type=str)

    if len(query) == 0:
        flash("Wrong query")
        return redirect(url_for('home_page'))

    analyzer = vectorizer.build_analyzer()
    query_vector = analyzer(query)
    vector = {}
    for token in query_vector:
        if token in vector:
            vector[token] += 1
        else:
            vector[token] = 1

    papers = Paper.query.all()

    # Assigning relevance scores to papers
    papers = [[p, cosine(vector, p.vector)] for p in papers]
    
    # Sort the papers
    match sort_option:
        case "Relevance":
            papers.sort(key=lambda x: x[1], reverse=True)
        case "Popularity":
            papers.sort(key=lambda x: x[0].popularity, reverse=True)
        case "Date":
            papers.sort(key=lambda x: x[0].updated_date, reverse=True)
        case _:
            flash("Wrong URL")
            return redirect(url_for('home_page'))

    # Assigning correct page numbers
    page_number_1 = page - 1
    page_number_2 = page 
    page_number_3 = page + 1
    if page == 1:
        page_number_1 = page
        page_number_2 = page + 1
        page_number_3 = page + 2
    if page == ceil(len(papers) / PAGE_LENGTH):
        page_number_1 = page - 2
        page_number_2 = page - 1
        page_number_3 = page
        
    return render_template(
        "search.html",
        query=query,
        current_page=page,
        page_number_1=page_number_1,
        page_number_2=page_number_2,
        page_number_3=page_number_3,
        number_of_pages=ceil(len(papers) / PAGE_LENGTH),
        papers=[x[0] for x in papers][(page-1)*PAGE_LENGTH:page*PAGE_LENGTH],
        relevances=[x[1] for x in papers][(page-1)*PAGE_LENGTH:page*PAGE_LENGTH],
        time_options=TIME_OPTIONS_TABLE,
        sort=sort_option,
        # Passing the zip function, bacause the jinja engine doesn't import it by default
        zip=zip
    )

@app.route('/logout')
@login_required
def logout():
    logging.info(f"User with email: {current_user.email} logged out")
    logout_user()
    flash("Logged out successfully")
    return redirect(url_for("login"))

# Interest page needs seperate logout route, because after signing up the user is redirected to the interests page 
# and only after going through the form they are logged in. So if the user wants to logout from the interests page
# Their email needs to be deleted from the session, because that's the way the server remembers them.  
@app.route('/logout-interest')
def logout_interests():
    session['email'] = ""
    flash("Logged out successfully")
    return redirect(url_for("login"))

@app.route('/about')
def about():
    if current_user.is_authenticated:
        return render_template('about_logged_in.html')
    else:
        return render_template('about_new_user.html')
