from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

table = db.Table(
    'table',
    db.Column('paper_id', db.Integer, db.ForeignKey('paper.id'), primary_key=True),
    db.Column('user_email', db.Integer, db.ForeignKey('user.email'), primary_key=True)
)

class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    authors = db.Column(db.String(300), nullable=False)
    abstract = db.Column(db.String(1920), nullable=False)
    pdf_link = db.Column(db.String(40))
    site_link = db.Column(db.String(40), nullable=False)
    popularity = db.Column(db.Integer)
    vector = db.Column(db.PickleType, nullable=False)
    updated_date = db.Column(db.DateTime, nullable=False)

class User(db.Model):
    email = db.Column(db.String(320), primary_key=True)
    password = db.Column(db.String(72), nullable=False)
    auth = db.Column(db.Boolean, default=False, nullable=False)
    vector = db.Column(db.PickleType, nullable=False)
    liked_papers = db.relationship("Paper", secondary=table, lazy='subquery', backref=db.backref('users', lazy=True))

    def is_active(self):
        return True
    
    def get_id(self):
        return self.email
    
    def is_authenticated(self):
        return self.auth
    
    def is_anonymous(self):
        return False