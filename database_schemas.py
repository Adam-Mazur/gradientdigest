from main import db

class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    authors = db.Column(db.String(300), nullable=False)
    abstract = db.Column(db.String(1920), nullable=False)
    pdf_link = db.Column(db.String(40))
    site_link = db.Column(db.String(40), nullable=False)
    popularity = db.Column(db.Integer, index=True)
    vector = db.Column(db.PickleType, nullable=False)
    updated_date = db.Column(db.Date, index=True, nullable=False)
    submited_date = db.Column(db.Date, index=True)