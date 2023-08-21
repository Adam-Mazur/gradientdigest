from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.tokenize import TweetTokenizer
from nltk.tag import pos_tag
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet
from database import db, Paper
import dateutil.parser
import warnings
import fitz
import feedparser
import requests
import logging

# Ignoring scikit learn warnings from the tf-idf vectorizer
warnings.filterwarnings("ignore")

def get_papers(starting_date, debug=False):
    """Download all the papers from the arxiv API that were submitted since [starting_date] and add them to the database.
    [strating_date] needs to have all the parameters (year, month, day, hour,...) and include tzinfo."""
    BASE_URL = 'http://export.arxiv.org/api/query?search_query='
    SEARCH_CATEGORIES = 'cat:cs.CV+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.AI+OR+cat:cs.NE+OR+cat:cs.RO'
    MAX_RESULTS = 10
    MAX_VECTOR_LENGTH = 1000

    def try_again(link):
        logging.error("There was a problem with downloading the pdf, trying again...")
        try:
            response = requests.get(link)
            logging.info(f"Attempted to download the pdf again, status code: {response.status_code}")
        except:
            logging.error(f"Couldn't download the pdf from this link: {link}")
            return -1
        if response.status_code != 200:
            logging.error(f"Couldn't download the pdf from this link: {link}")
            return -1
        return response
    
    def check_schema(structure, article):
        """"Checks if the API response has a valid structure"""
        if isinstance(structure, dict):
            for key, item in structure.items():
                if key not in article:
                    logging.error(f"The structure of the API response is invalid. The element: \'{key}\' not found")
                    return False
                if type(item) != type:
                    return check_schema(item, article[key])
                if type(article[key]) != item:
                    logging.error(f"The structure of the API response is invalid. The type of item article[\'{key}\'] is uncorrect")
                    return False
                return True
        else:
            for i, item in enumerate(structure):
                if type(item) != type:
                    return check_schema(item, article[i])
                if type(article[i]) != item:
                    logging.error(f"The structure of the API response is invalid. The type of item article[\'{key}\'] is uncorrect")
                    return False
                return True

    collection = []
    ids = []
    start_index = 0
    not_last = True
    logging.info(f"Downloading the newest papers from the arXiv API since {starting_date} in {'normal mode' if not debug else 'debug mode'}")
    while not_last:
        url_parameters = f'&sortBy=lastUpdatedDate&start={start_index}&max_results={MAX_RESULTS}'
        url = BASE_URL + SEARCH_CATEGORIES + url_parameters
        
        # Sending HTTP GET request to the API and converting the response from the Atom format to python dict
        api_response = feedparser.parse(url)

        if len(api_response['entries']) == 0:
            break

        for article in api_response['entries']:
            # Checking the schema of the API response
            api_structure = {
                'updated': str,
                'published': str,
                'title': str,
                'summary': str,
                'authors': [{'name': str}, {'name': str}, {'name': str}],
                'links': [{'href': str}, {'href': str}]
            }
            if not check_schema(api_structure, article):
                continue

            # Comparing the updated date of the article and the [starting_date]
            updated_date = dateutil.parser.isoparse(article['updated'])
            if updated_date < starting_date:
                not_last = False
                break

            # Getting the data from the API response
            pdf_link = article['links'][1]['href']
            site_link = article['links'][0]['href']
            submited_date = dateutil.parser.isoparse(article['published'])
            title = article['title']
            abstract = article['summary']
            authors = ", ".join(map(lambda x: x['name'], article['authors']))
            logging.info(f"The link to the pdf from the arXiv API: {pdf_link}")

            # Downloading the pdf
            try:
                response = requests.get(pdf_link)
                logging.info(f"Attempted to download the pdf, status code: {response.status_code}")
            except:
                response = try_again(pdf_link)
                if response == -1:
                    continue
        
            if response.status_code != 200:
                response = try_again(pdf_link)
                if response == -1:
                    continue
            
            # Converting the pdf to text
            try:
                with fitz.open("pdf", response.content) as document:
                    text = chr(12).join([page.get_text() for page in document])
                collection.append(text)
                logging.info(f"Succesfully converted the pdf from this link: {pdf_link}")
            except:
                logging.error(f"Couldn't convert the pdf from this link: {pdf_link}")
                continue

            # Creating a new database entry
            if not debug:
                new_paper = Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    pdf_link=pdf_link,
                    site_link=site_link,
                    popularity=5,
                    vector = dict(),
                    updated_date=updated_date,
                    submited_date=submited_date
                )
                db.session.add(new_paper)
                try:
                    db.session.commit()
                    ids.append(new_paper.id)
                except:
                    logging.error(f"Couldn't add a new paper to the database, link: {site_link}")
                    db.session.rollback()

        if debug: break
        start_index += MAX_RESULTS
    
    def get_wordnet_pos(word):
        """Map POS tag to first character lemmatize() accepts"""
        tag = pos_tag([word])[0][1][0].upper()
        # TODO: Make sure this works
        tag_dict = {
            "J": wordnet.ADJ,
            "N": wordnet.NOUN,
            "V": wordnet.VERB,
            "R": wordnet.ADV,
        }
        return tag_dict.get(tag, wordnet.NOUN)
    
    lemmatizer = WordNetLemmatizer()
    tokenizer = TweetTokenizer()
    def text_normalization(text):
        processed = []
        text_tokens = tokenizer.tokenize(text)                
        for token in text_tokens:
            if not any(map(lambda x: x.isalpha(), token)):
                continue
            if len(token) == 1:
                continue
            # Lemmatization
            token = lemmatizer.lemmatize(token, get_wordnet_pos(token))
            processed.append(token)
        return processed

    vectorizer = TfidfVectorizer(
        input='content',
        encoding='str',
        tokenizer=text_normalization,
        lowercase=True,
        use_idf=True,
        smooth_idf=True,
        max_df=0.9,
        stop_words='english'
    )

    if len(collection) == 0:
        logging.error(f"Downloading the pdf's from the arXiv API was unsuccessful. Starting date: {starting_date}")
        return
    
    result = vectorizer.fit_transform(collection)
    if debug: return result, vectorizer

    result = result.toarray()
    for i, id in enumerate(ids):
        paper = db.session.get(Paper, id)
        vector = {}
        for a,b in zip(vectorizer.get_feature_names_out(), result[i]):
            vector[a] = b
        vector = dict(sorted(vector.items(), key=lambda x: x[1], reverse=True)[:MAX_VECTOR_LENGTH])
        paper.vector = vector
    
    db.session.commit()