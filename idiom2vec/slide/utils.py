import pickle
from typing import Generator

from spacy import Language
from spacy.matcher import Matcher
from spacy.tokens.doc import Doc
from config import IDIOM_MATCHER_PKL_PATH, SLIDE_TSV_PATH
from os import path
import csv


# not to include in the vocabulary
EXCEPTIONS = (
    "if needs be"  # duplicate ->  "if need be" is enough.
)


DELIM = "\t"
SEPARATOR = " "
IDIOM_MIN_WC = 3  # aim for the idioms with length greater than 3
IDIOM_MIN_LENGTH = 14


def is_above_min_len(idiom: str) -> bool:
    global IDIOM_MIN_LENGTH
    return len(idiom) >= IDIOM_MIN_LENGTH


def is_above_min_wc(idiom: str) -> bool:
    global IDIOM_MIN_WC, SEPARATOR
    return len(idiom.split(SEPARATOR)) >= IDIOM_MIN_WC


def is_hyphenated(idiom: str) -> bool:
    return idiom.find("-") != -1


def is_not_exception(idiom: str) -> bool:
    global EXCEPTIONS
    return idiom not in EXCEPTIONS


def is_target(idiom: str) -> bool:
    # if it is either long enough or hyphenated, then I'm using it.
    return is_not_exception and \
           (is_above_min_wc(idiom) or is_above_min_len(idiom) or is_hyphenated(idiom))


def load_idioms() -> Generator[str, None, None]:
    with open(SLIDE_TSV_PATH, 'r') as fh:
        slide_tsv = csv.reader(fh, delimiter="\t")
        # skip the  header
        next(slide_tsv)
        for row in slide_tsv:
            yield row[0]


def load_target_idioms() -> Generator[str, None, None]:
    return (
        idiom
        for idiom in load_idioms()
        if is_target(idiom)
    )


def load_idiom_matcher() -> Matcher:
    if not path.exists(IDIOM_MATCHER_PKL_PATH):
        raise ValueError
    with open(IDIOM_MATCHER_PKL_PATH, 'rb') as fh:
        return pickle.loads(fh.read())


class MergeIdiomComponent:
    def __init__(self, idiom_matcher):
        self.idiom_matcher: Matcher = idiom_matcher

    def __call__(self, doc: Doc) -> Doc:
        # use lowercase version of the doc.
        matches = self.idiom_matcher(doc)
        for match_id, start, end in matches:
            # get back the lemma for this match
            # note: matcher has references to the vocab on its own!
            match_lemma = self.idiom_matcher.vocab.strings[match_id]
            # retokenise
            with doc.retokenize() as retokeniser:
                retokeniser.merge(doc[start:end],
                                  # set tag as the idiom
                                  attrs={'LEMMA': match_lemma, 'TAG': 'IDIOM'})
        return doc


# factory method for the component
def create_merge_idiom_component(nlp, name, idiom_matcher) -> MergeIdiomComponent:
    if not idiom_matcher:
        raise ValueError("idiom_matcher does not exist.")
    return MergeIdiomComponent(idiom_matcher)


class IdiomNLP:
    def __init__(self, nlp: Language, idiom_matcher: Matcher):
        self.nlp = nlp
        self.idiom_matcher = idiom_matcher
        # factory for merge_idiom pipeline.
        Language.factory(
            name="merge_idiom",
            retokenizes=True,
            default_config={"idiom_matcher": self.idiom_matcher},
            func=create_merge_idiom_component
        )
        # add the pipe, and save it to disk
        nlp.add_pipe("merge_idiom", after="lemmatizer")

    def __call__(self, text: str, *args, **kwargs):
        # just a wrapper, to construct the pipeline on init.
        # I know that you'd lose some information here.. (Kate -> kate. NOT Proper Noun anymore, just a Noun).
        # but, we've got to make a compromise here.
        return self.nlp(text.lower())
