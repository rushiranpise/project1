"""
load train and test file
train agorithm
save metric and paramters
"""
import os
#import warning
import sys
import json
import re
import string
import argparse
import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import TweetTokenizer
from get_data import read_params
import joblib
import mlflow
import mlflow.sklearn
from urllib.parse import urlparse

def process_tweet(tweet):
    """Process tweet function.
    Input:
        tweet: a string containing a tweet
    Output:
        tweets_clean: a list of words containing the processed tweet

    """
    stemmer = PorterStemmer()
    stopwords_english = stopwords.words('english')
    # remove stock market tickers like $GE
    tweet = re.sub(r'\$\w*', '', tweet)
    # remove old style retweet text "RT"
    tweet = re.sub(r'^RT[\s]+', '', tweet)
    # remove hyperlinks
    tweet = re.sub(r'https?:\/\/.*[\r\n]*', '', tweet)
    # remove hashtags
    # only removing the hash # sign from the word
    tweet = re.sub(r'#', '', tweet)
    # tokenize tweets
    tokenizer = TweetTokenizer(preserve_case=False, strip_handles=True,
                               reduce_len=True)
    tweet_tokens = tokenizer.tokenize(tweet)

    tweets_clean = []
    for word in tweet_tokens:
        if (word not in stopwords_english and  # remove stopwords
                word not in string.punctuation):  # remove punctuation
            # tweets_clean.append(word)
            stem_word = stemmer.stem(word)  # stemming word
            tweets_clean.append(stem_word)

    return tweets_clean


def build_freqs(tweets, ys):
    """Build frequencies.
    Input:
        tweets: a list of tweets
        ys: an m x 1 array with the sentiment label of each tweet
            (either 0 or 1)
    Output:
        freqs: a dictionary mapping each (word, sentiment) pair to its
        frequency
    """
    # Convert np array to list since zip needs an iterable.
    # The squeeze is necessary or the list ends up with one element.
    # Also note that this is just a NOP if ys is already a list.
    yslist = np.squeeze(ys).tolist()

    # Start with an empty dictionary and populate it by looping over all tweets
    # and over all processed words in each tweet.
    freqs = {}
    for y, tweet in zip(yslist, tweets):
        for word in process_tweet(tweet):
            pair = (word, y)
            if pair in freqs:
                freqs[pair] += 1
            else:
                freqs[pair] = 1

    return freqs


def extract_features(tweet, freqs):
    '''
    Input: 
        tweet: a list of words for one tweet
        freqs: a dictionary corresponding to the frequencies of each tuple (word, label)
    Output: 
        x: a feature vector of dimension (1,3)
    '''
    # process_tweet tokenizes, stems, and removes stopwords
    word_l = process_tweet(tweet)
    # 3 elements in the form of a 1 x 3 vector
    x = np.zeros((1, 3))

    # bias term is set to 1
    x[0, 0] = 1
    # loop through each word in the list of words
    for word in word_l:

        # increment the word count for the positive label 1
        x[0, 1] += freqs.get((word, 1.0), 0)

        # increment the word count for the negative label 0
        x[0, 2] += freqs.get((word, 0.0), 0)
    assert(x.shape == (1, 3))
    return x


def eval_metrics(actual, pred):
    accuracy = accuracy_score(actual, pred)
    ps = precision_score(actual, pred)
    rs = recall_score(actual, pred)
    fs=f1_score(actual, pred)
    return accuracy, ps, rs,fs


def train_and_evaluate(config_path):
    config = read_params(config_path)
    test_data_path = config["split_data"]["test_path"]
    train_data_path = config["split_data"]["train_path"]
    #random_state = config["base"]["random_state"]
    model_dir = config["model_dir"]
    target = config["base"]["target_col"]
    gamma = config["estimators"]["SupportVectorClassifier"]["params"]["gamma"]
    random_state = config["estimators"]["SupportVectorClassifier"]["params"]["random_state"]
    train_data = pd.read_csv(train_data_path)
    test_data = pd.read_csv(test_data_path)
    train_y = train_data[target]
    test_y = test_data[target]
    train_x = train_data["content"]
    test_x = test_data["content"]
    freqs = build_freqs(train_x, train_y)
    # transformation ###############################33
    X = np.zeros((len(train_x), 3))
    for i in range(len(train_x)):
        X[i, :] = extract_features(train_x[i], freqs)
    Y = train_y
    X_t = np.zeros((len(test_x), 3))
    for i in range(len(test_x)):
        X_t[i, :] = extract_features(test_x[i], freqs)
    Y_t = test_y
    ###########################Model tracking ################################
    mlflow_config=config["mlflow_config"]
    remote_server_uri=mlflow_config["remote_server_uri"]
    mlflow.set_tracking_uri(remote_server_uri)
    mlflow.set_experiment(mlflow_config["experiment_name"])
    with mlflow.start_run(run_name=mlflow_config["run_name"]) as run:
    ########################Model training#######################################
        svm_clf = SVC(C=0.7 ,random_state=random_state)
        svm_clf.fit(X, Y)
        ######################Evaluating############################################
        predicted_qualities = svm_clf.predict(X_t)

        (acc, ps, rs,fs) = eval_metrics(Y_t, predicted_qualities)

        mlflow.log_param("gamma", gamma)
        mlflow.log_param("random_State",random_state)
        mlflow.log_metric("accuracy",acc)
        mlflow.log_metric("Precision",ps)
        mlflow.log_metric("Recall",rs)
        mlflow.log_metric("F1",fs)

        tracking_url_type_store= urlparse(mlflow.get_artifact_uri()).scheme 
        if tracking_url_type_store != "file":
            mlflow.sklearn.log_model(svm_clf, "model", registered_model_name=mlflow_config["registered_model_name"])
        else:
            mlflow.sklearn.load_model(svm_clf,"model")



if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--config", default="params.yaml")
    parsed_args = args.parse_args()
    train_and_evaluate(config_path=parsed_args.config)
