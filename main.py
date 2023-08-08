from flask_login import LoginManager, login_required, login_user, logout_user
from flask import Flask, render_template, redirect, url_for, flash
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm
from database import db, User, Paper
import logging
import bcrypt
import json

app = Flask(__name__)

# ---------------------------------------------------------
# App configuration
app.config.from_file('config.json', load=json.load)
logging.basicConfig(
    level=logging.DEBUG,
    # TODO: Uncomment that for production
    # filename='log.txt',
    # filemode='a',
    # format='%(asctime)s | %(filename)s:%(lineno)s:%(levelname)s | %(message)s'
)

db.init_app(app)


# ---------------------------------------------------------
# Flask-login stuff
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def user_loader(user_id):
    return User.query.get(user_id)


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


# ---------------------------------------------------------
# Endpoints
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.get(form.email.data)
        if user:
            if bcrypt.checkpw(form.password.data.encode('utf8'), user.password):
                user.auth = True
                db.session.commit()
                login_user(user, remember=True)
                flash("Logged in successfully")
                return redirect(url_for('home_page'))
            else:
                flash("The password is wrong")
        else:
            flash("Couldn't find your account")

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
            return redirect(url_for('interests'))
        except:
            db.session.rollback()
            flash("Something went wrong, try again")

    return render_template("sign_up.html", sign_up_form=form)

@app.route('/interests')
def interests():
    return render_template("interests.html")

@app.route('/')
@login_required
def home_page():
    return render_template("index.html")

@app.route('/logout')
@login_required
def logout():
    flash("Logged out successfully")
    return redirect(url_for("login"))