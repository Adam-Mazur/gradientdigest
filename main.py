from flask import Flask, render_template, redirect

app = Flask(__name__)

@app.route('/')
def home():
    return render_template("login.html")

@app.route('/sign-up')
def sign_up():
    return render_template("sign_up.html")

@app.route('/interests')
def interests():
    return render_template("interests.html")

@app.route('/home-page')
def home_page():
    return render_template("index.html")