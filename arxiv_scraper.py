from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.tokenize import TweetTokenizer
from nltk.tag import pos_tag
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet
import dateutil.parser
import warnings
import fitz
import feedparser
import requests
import logging

logging.basicConfig(
    level=logging.DEBUG,
    filename='log.txt',
    filemode='a',
    format='%(asctime)s | %(filename)s:%(lineno)s:%(levelname)s | %(message)s'
)

# Ignoring scikit learn warnings from the tf-idf vectorizer
warnings.filterwarnings("ignore")

def get_papers(starting_date, debug=False):
    """Download all the papers from the arxiv API that were submitted since [starting_date] and add them to the database.
    [strating_date] needs to have all the parameters (year, month, day, hour,...) and include tzinfo."""
    BASE_URL = 'http://export.arxiv.org/api/query?search_query='
    SEARCH_CATEGORIES = 'cat:cs.CV+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.AI+OR+cat:cs.NE+OR+cat:cs.RO'
    MAX_RESULTS = 10

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

    collection = []
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
            # Comparing the updated date of the article and the [starting_date]
            if 'updated' not in article:
                logging.error(f"\'updated\' key wasn't in the article dictionary, meaning that the response from the API was invalid. Search query: {url}")
                continue
            date = dateutil.parser.isoparse(article['updated'])
            if date < starting_date:
                not_last = False
                break

            # Getting the link to the pdf
            if 'links' not in article or len(article['links']) < 2 or 'href' not in article['links'][1]:
                logging.error(f"Couldn't get the link from the API response, search query: {url}")
                continue
            link = article['links'][1]['href']
            logging.info(f"The link to the pdf from the arXiv API: {link}")

            # Downloading the pdf
            try:
                response = requests.get(link)
                logging.info(f"Attempted to download the pdf, status code: {response.status_code}")
            except:
                response = try_again(link)
                if response == -1:
                    continue
        
            if response.status_code != 200:
                response = try_again(link)
                if response == -1:
                    continue
            
            # Converting the pdf to text
            try:
                with fitz.open("pdf", response.content) as document:
                    text = chr(12).join([page.get_text() for page in document])
                collection.append(text)
                logging.info(f"Succesfully converted the pdf from this link: {link}")
            except:
                logging.error(f"Couldn't convert the pdf from this link: {link}")

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
    vector = vectorizer.fit_transform(collection)
    
    if debug: return vector, vectorizer