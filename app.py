############## IMPORT LIBRARIES ########################
from flask import Flask, render_template, request
import nltk
from nltk import pos_tag
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from textblob import TextBlob
from nltk.sentiment import SentimentIntensityAnalyzer
from spellchecker import SpellChecker
from transformers import GPT2Tokenizer, GPTNeoForCausalLM
from sklearn.metrics.pairwise import cosine_similarity
import torch
import numpy as np
import requests
from bs4 import BeautifulSoup
import warnings
import re
import asyncio
import nest_asyncio
from rake_nltk import Rake


warnings.filterwarnings("ignore")
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('vader_lexicon')
nltk.download('averaged_perceptron_tagger')
nest_asyncio.apply()

app = Flask(__name__)


#################### FUNCTION : Get Article Content from URL ##################

def get_article(article_url):
    response = requests.get(article_url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        para_tags = soup.find_all('p')
        all_para = [para.get_text() for para in para_tags]
        article_text = " ".join(all_para)
        #article_text = re.sub(r'<.*?>|\n|\t', '', article_text)
        #article_text = re.sub(r'[^a-zA-Z0-9\s]', '', article_text)
        #article_text = article_text.lower()
        return article_text
    else:
        print('----Something went wrong----')
        return False


#################### FUNCTION : Check that article is generated by AI ##################

async def is_generated_by_language_model(article):
    # Load GPT-3.5 tokenizer and model
    tokenizer = GPT2Tokenizer.from_pretrained("EleutherAI/gpt-neo-1.3B")
    model = GPTNeoForCausalLM.from_pretrained("EleutherAI/gpt-neo-1.3B")

    # Tokenize the original article
    inputs = tokenizer.encode(article, return_tensors="pt", add_special_tokens=True)

    # Generate text using the GPT-2 model
    with torch.no_grad():
        outputs = model.generate(inputs, max_length=100, num_return_sequences=1)

    # Decode the generated tokens
    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Truncate or pad the generated text to match the length of the original article
    max_length = max(len(inputs[0]), len(outputs[0]))
    inputs = torch.nn.functional.pad(inputs, (0, max_length - len(inputs[0])))
    outputs = torch.nn.functional.pad(outputs, (0, max_length - len(outputs[0])))

    # Calculate cosine similarity between original article and generated text
    embeddings = model.get_input_embeddings()(inputs).squeeze().detach().numpy()
    generated_embeddings = model.get_input_embeddings()(outputs).squeeze().detach().numpy()

    # Reshape embeddings to 2D arrays
    embeddings = embeddings.reshape(1, -1)
    generated_embeddings = generated_embeddings.reshape(1, -1)

    similarity = cosine_similarity(embeddings, generated_embeddings)[0, 0]
    effort_score = 0.0
    avg_similarity_score = np.mean(similarity)
    effort_score += avg_similarity_score

    if effort_score > 0.90:
        return 0.6
    elif effort_score >= 0.80 and effort_score <0.90:
        return 0.7
    elif effort_score >= 0.60 and effort_score <0.80:
        return 0.8
    elif effort_score >= 0.40 and effort_score <0.60:
        return 0.90
    elif effort_score >= 0.10 and effort_score <0.40:
        return 0.99
    else:
        return 0

def suggest_keywords(article):
    # Initialize the Rake object
    r = Rake()

    # Extract keywords from the article
    r.extract_keywords_from_text(article)

    # Get the top 10 keywords with the highest score
    suggested_keywords = r.get_ranked_phrases()[:10]
    suggested_keywords = list(set(suggested_keywords))

    return suggested_keywords


################ FUNCTION : Evaluate the Quality of the Article ##################

def evaluate_article_quality(article, is_written_by_chatgpt,relevant_keywords_list):
    # Initialize the SentimentIntensityAnalyzer for Indian English
    analyzer = SentimentIntensityAnalyzer()
    sentiment_score = analyzer.polarity_scores(article)
    # 'compound' is a normalized score ranging from -1 to 1
    readability_score = (sentiment_score['compound'] + 1) / 2

    # Vocabulary richness (Simple measure: Count unique words)
    words = TextBlob(article).words
    unique_words_count = len(set(words))
    total_words_count = len(words)
    vocabulary_score = unique_words_count / total_words_count

    relevant_keywords = request.form["relevant_keywords"]
    relevant_keywords_ls = relevant_keywords.split(",")

    # Spelling check using pyspellchecker
    spell = SpellChecker()
    spell.word_frequency.load_words(relevant_keywords_ls)
    misspelled_words = spell.unknown(words)
    spelling_error_count = len(misspelled_words)
    spelling_error_score = 1.0 - (spelling_error_count / total_words_count)

    # Get corrections for misspelled words
    misspelled_words_with_correction = {}
    for word in misspelled_words:
        correction = spell.correction(word)
        misspelled_words_with_correction[word] = correction

    # Relevance keywords
    relevance_score = sum(keyword.lower() in article.lower() for keyword in relevant_keywords) / len(relevant_keywords)

    # Effort check for content written by ChatGPT
    effort_score = 1.0 if not is_written_by_chatgpt else 0.0
    effort_score = is_written_by_chatgpt

    # Calculate the quality score (You can customize the weights as needed)
    quality_score = (readability_score + vocabulary_score + relevance_score +  effort_score +  spelling_error_score)/5

    # Scale the quality score to percentage (0 to 100)
    score_percentage = round((quality_score) * 100,0)  # Mapping from [-1, 1] to [0, 100]

    # Suggest more keywords for SEO improvement
    suggested_keywords = suggest_keywords(article)
    print(suggested_keywords)


    if effort_score == 0.6:
        effort_score_return = 0.90
    elif effort_score == 0.7:
        effort_score_return = 0.80
    elif effort_score == 0.8:
        effort_score_return = 0.60
    elif effort_score == 0.90:
        effort_score_return = 0.40
    elif effort_score == 0.99:
        effort_score_return = 0.10
    else:
        effort_score_return = 0.01

    # Calculate the contribution of each score to the overall score
    contributions = {
        "Readability": round((readability_score) * 100,2),
        "Vocabulary Richness": round((vocabulary_score) * 100,2),
        "Relevance": round((relevance_score) * 100,2),
        "Generated by AI": round((effort_score_return) * 100,2),
        "Spelling Score": round((spelling_error_score) * 100,2)
    }

    return score_percentage, contributions, misspelled_words_with_correction, suggested_keywords

def get_status(score_percentage):
    if score_percentage >= 0.8:
        return "Very Good", "green"
    elif score_percentage >= 0.6:
        return "Good", "SpringGreen"
    elif score_percentage >= 0.4:
        return "Average", "orange"
    elif score_percentage >= 0.2:
        return "Low", "Crimson"
    else:
        return "Very Low", "red"




@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        article_url = request.form["article_url"]
        relevant_keywords_input = request.form["relevant_keywords"]
        relevant_keywords_list = [keyword.strip() for keyword in relevant_keywords_input.split(",")]

        # Fetch the article content using the URL (You may use libraries like requests or urllib for this)
        article_text = get_article(article_url)

        # Use asyncio to call the is_generated_by_language_model asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        is_written_by_chatgpt = loop.run_until_complete(is_generated_by_language_model(article_text))

        # Calculate Effort Score and Contributions
        score_percentage, contributions, misspelled_words_with_correction,suggested_keywords = evaluate_article_quality(article_text, is_written_by_chatgpt, relevant_keywords_list)

        # Calculate the status and status_color
        status, status_color = get_status(score_percentage / 100)

        return render_template("result.html", effort_score=score_percentage, contributions=contributions, status=status, status_color=status_color,misspelled_words_with_correction=misspelled_words_with_correction, suggested_keywords=suggested_keywords)

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0')