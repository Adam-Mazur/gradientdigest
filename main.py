from flask_login import LoginManager, login_required, login_user, logout_user, user_logged_out, current_user
from flask import Flask, render_template, redirect, url_for, flash, session
from wtforms import StringField, SubmitField, BooleanField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm
from database import db, User, Paper
from flask_session import Session
from arxiv_scraper import get_papers
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from recommender import update_user_profile, cosine
import logging
import bcrypt
import json
import atexit
import os

app = Flask(__name__)

# ---------------------------------------------------------
# App configuration
app.config.from_file('config.json', load=json.load)
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
    return User.query.get(user_id)

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

# This prevents scheduling one function twice in the debug mode. More info: https://stackoverflow.com/questions/14874782/apscheduler-in-flask-executes-twice
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler()
    # Download papers everyday at 00:30 AM in arxiv timezone (they work in 24 hour cycles)
    scheduler.add_job(download_papers, trigger="cron", hour=0, minute=30, timezone=ARXIV_TIMEZONE)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

# ---------------------------------------------------------
# Forms
class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = StringField("Password", validators=[DataRequired()])
    login_submit = SubmitField("Login")

class SignUpForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = StringField("Password", validators=[DataRequired()])
    repeat_password = StringField("Repeat password", validators=[DataRequired()])
    sign_up_submit = SubmitField("Sign up")

    def validate(self, **kwargs):
        validators = FlaskForm.validate(self)
        if validators and self.password.data == self.repeat_password.data:
            return True
        return False

class InterestsForm(FlaskForm):
    field_nlp = BooleanField("NLP")
    field_transformers = BooleanField("Transformers")
    field_neural_networks = BooleanField("Neural networks")
    field_robotics = BooleanField("Robotics")
    field_deep_learning = BooleanField("Deep learning")
    field_optimization = BooleanField("Optimization")
    field_computer_vision = BooleanField("Computer vision")
    field_supervised_learning = BooleanField("Supervised learning")
    field_unsupervised_learning = BooleanField("Unsupervised learning")
    field_reinforcement_learning = BooleanField("Reinforcement learning")
    interests_submit = SubmitField("Submit")

    def validate(self, **kwargs):
        validators = FlaskForm.validate(self)
        # At least one field must be selected 
        attribures = list(map(lambda x: getattr(self, x), dir(self)))
        if validators and any(map(lambda x: isinstance(x, BooleanField) and x.data, attribures)):
            return True
        return False

# ---------------------------------------------------------
# Endpoints
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.get(form.email.data)
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
            return redirect(url_for('home_page'))

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

@app.route('/interests', methods=['GET', 'POST'])
def interests():
    if not session['email']:
        flash("You cannot access this page")
        return redirect(url_for('login')) 
    form = InterestsForm()
    if form.validate_on_submit():
        user = User.query.get(session['email'])
        # Getting data from the form to the database
        label_to_tokens = {
            "NLP": ["nlp"],
            "Transformers": ["transformers"],
            "Neural networks": ["neural", "network"],
            "Robotics": ["robotics"],
            "Deep learning": ["deep", "learn"],
            "Optimization": ["optimization"],
            "Computer vision": ["computer", "vision"],
            "Supervised learning": ["supervised", "learn"],
            "Unsupervised learning": ["unsupervised", "learn"],
            "Reinforcement learning": ["reinforcement", "learn"]
        }
        temp_dict = dict()
        for attr in map(lambda x: getattr(form, x), dir(form)):
            if not isinstance(attr, BooleanField) or isinstance(attr, SubmitField):
                continue
            tokens = label_to_tokens[attr.label.text]
            for token in tokens:
                temp_dict[token] = 1 if attr.data else 0

        user.vector = temp_dict
        try:
            db.session.commit()
            flash("Updated interests")
            login_user(user, remember=True)
            session['email'] = ""
            return redirect(url_for('home_page'))
        except:
            db.session.rollback()
            flash("Something went wrong, try again")

    return render_template("interests.html", interests_form=form)

@app.template_filter("display_date")
def display_date(date):
    months = [
        "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"
    ]
    return months[date.month] + " " + str(date.year)

@app.route('/')
@login_required
def home_page():
    papers = Paper.query.all()
    papers.sort(key=lambda x: cosine(current_user.vector, x.vector), reverse=True)
    return render_template("index.html", papers=papers[:10])

@app.route('/logout')
@login_required
def logout():
    logging.info(f"User with email: {current_user.email} logged out")
    logout_user()
    flash("Logged out successfully")
    return redirect(url_for("login"))