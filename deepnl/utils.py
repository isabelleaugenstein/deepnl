# -*- coding: utf-8 -*-

"""
Utility functions
"""

import re
import logging
import numpy as np
from itertools import islice

def tokenize(text, sent_splitter, tokenizer, clean=True):
    """
    Returns a list of lists of the tokens in text, separated by sentences.
    Each line break in the text starts a new list.
    
    :param sent_splitter: a sentence splitter sucg as
        nltk.tokenize.regexp.punkt
    :param tokenzier: a tokenizer, such as
        nltk.tokenize.regexp.RegexpTokenizer
    :param clean: If True, performs some cleaning action on the text, such as replacing
        all digits for 9 (by calling :func:`clean_text`)
    """
    ret = []
    
    if type(text) != unicode:
        text = unicode(text, 'utf-8')
    
    if clean:
        text = clean_text(text, correct=True)
    
    text = _clitic_regexp.sub(r' -\1', text)
    
   
    # the sentence tokenizer doesn't consider line breaks as sentence delimiters, so
    # we split them manually where there are two consecutive line breaks.
    sentences = []
    lines = text.split('\n\n')
    for line in lines:
        sentences.extend(sent_tokenizer.tokenize(line, realign_boundaries=True))
    
    for p in sentences:
        if p.strip() == '':
            continue
        
        new_sent = _tokenizer.tokenize(p)
        ret.append(new_sent)
        
    return ret

def clean_text(text, correct=True):
    """
    Apply some transformations to the text, such as 
    replacing digits for 9 and simplifying quotation marks.
    
    :param correct: If True, tries to correct punctuation misspellings. 
    """
    
    # replaces different kinds of quotation marks with "
    # take care not to remove apostrophes
    text = re.sub(ur"(?u)(^|\W)[‘’′`']", r'\1"', text)
    text = re.sub(ur"(?u)[‘’`′'](\W|$)", r'"\1', text)
    text = re.sub(ur'(?u)[«»“”]', '"', text)
    
    if correct:
        # tries to fix mistyped tokens (common in Wikipedia-pt) as ,, '' ..
        text = re.sub(r'(?<!\.)\.\.(?!\.)', '.', text) # take care with ellipses 
        text = re.sub(r'([,";:])\1,', r'\1', text)
        
        # inserts space after leading hyphen. It happens sometimes in cases like:
        # blablabla -that is, bloblobloblo
        text = re.sub(' -(?=[^\W\d_])', ' - ', text)
    
    # replaces numbers with the 9's
    text = re.sub(r'\d', '9', text)
    
    # replaces special ellipsis character 
    text = text.replace(u'…', '...')
    
    return text

def count_lines(filename):
    """Counts and returns how many non empty lines there are in a file."""
    count = 0
    with open(filename, 'r') as f:
        for line in f:          # avoid reading the whole file in memory
            if f.strip():
                count += 1
    return count

def _create_affix_tables(affix, table_list, num_features):
    """
    Internal helper function for loading suffix or prefix feature tables 
    into the given list.
    affix should be either 'suffix' or 'prefix'.
    """
    logger = logging.getLogger('Logger')
    logger.info('Generating %s features...' % affix)
    tensor = []
    codes = getattr(attributes.Affix, '%s_codes' % affix)
    num_affixes_per_size = getattr(attributes.Affix, 'num_%ses_per_size' % affix)
    for size in codes:
        
        # use num_*_per_size because it accounts for special suffix codes
        num_affixes = num_affixes_per_size[size]
        table = generate_feature_vectors(num_affixes, num_features)
        tensor.append(table)
    
    # affix attribute actually has a 3-dim tensor
    # (concatenation of 2d tables, one for each suffix size)
    for table in tensor:
        table_list.append(table)

def create_feature_tables(args, md, text_reader):
    """
    Create the feature tables to be used by the network. If the args object
    contains the load_features option as true, the feature table for word types
    is loaded instead of being created. The actual number of 
    feature tables will depend on the argument options.
    
    :param arguments: Parameters supplied to the program
    :param md: metadata about the network
    :param text_reader: The TextReader being used.
    :returns: all the feature tables to be used
    """
    
    logger = logging.getLogger("Logger")
    feature_tables = []
    
    if not args.load_types:
        logger.info("Generating word type features...")
        table_size = len(text_reader.word_dict)
        types_table = generate_feature_vectors(table_size, args.num_features)
    else:
        logger.info("Loading word type features...")
        types_table = load_features_from_file(md.paths[md.type_features])
        
        if len(types_table) < len(text_reader.word_dict):
            # the type dictionary provided has more types than
            # the number of feature vectors. So, let's generate
            # feature vectors for the new types by replicating the vector
            # associated with the RARE word
            diff = len(text_reader.word_dict) - len(types_table)
            logger.warning("Number of types in feature table and dictionary differ.")
            logger.warning("Generating features for %d new types." % diff)
            num_features = len(types_table[0])
            new_vecs =  generate_feature_vectors(diff, num_features)
            types_table = np.append(types_table, new_vecs, axis=0)
            
        elif len(types_table) < len(text_reader.word_dict):
            logger.warning("Number of features provided is greater than the number of tokens\
            in the dictionary. The extra features will be ignored.")
    
    feature_tables.append(types_table)
    
    # Capitalization
    if md.use_caps:
        logger.info("Generating capitalization features...")
        caps_table = generate_feature_vectors(attributes.Caps.num_values, args.caps)
        feature_tables.append(caps_table)
    
    # Prefixes
    if md.use_prefix:
        _create_affix_tables('prefix', feature_tables, args.prefix)
    
    # Suffixes
    if md.use_suffix:
        _create_affix_tables('suffix', feature_tables, args.suffix)
    
    # POS tags
    if md.use_pos:
        logger.info("Generating POS features...")
        num_pos_tags = count_lines(md.paths['pos_tags'])
        pos_table = generate_feature_vectors(num_pos_tags, args.pos)
        feature_tables.append(pos_table)
    
    # chunk tags
    if md.use_chunk:
        logger.info("Generating chunk features...")
        num_chunk_tags = count_lines(md.paths['chunk_tags'])
        chunk_table = generate_feature_vectors(num_chunk_tags, args.chunk)
        feature_tables.append(chunk_table)
    
    # gazetteer tags
    if md.use_gazetteer:
        logger.info("Generating gazetteer features...")
        for c in md.gaz_classes:  # 4 classes [LOC, MISC, ORG, PER]
            table = generate_feature_vectors(attributes.num_gazetteer_tags, args.gazetteer)
            feature_tables.append(table)
    
    return feature_tables

def set_distance_features(max_dist=None, 
                          num_target_features=None, num_pred_features=None):
    """
    Returns the distance feature tables to be used by a convolutional network.
    One table is for relative distance to the target predicate, the other
    to the predicate.
    
    :param max_dist: maximum distance to be used in new vectors.
    """
    logger = logging.getLogger("Logger")
    
    # max_dist before/after, 0 distance, and distances above the max
    max_dist = 2 * (max_dist + 1) + 1
    logger.info("Generating target word distance features...")
    target_dist = generate_feature_vectors(max_dist, num_target_features)
    logger.info("Generating predicate distance features...")
    pred_dist = generate_feature_vectors(max_dist, num_pred_features)
    
    return (target_dist, pred_dist)

def set_logger(level):
    """Sets the logger to be used throughout the system."""

    log_format = '%(message)s'
    logging.basicConfig(format=log_format)
    logger = logging.getLogger("Logger")
    logger.setLevel(level)

def boundaries_to_arg_limits(boundaries):
    """
    Converts a sequence of IOBES tags delimiting arguments to an array
    of argument boundaries, used by the network.
    """
    limits = []
    start = None
    
    for i, tag in enumerate(boundaries):
        if tag == 'S': 
            limits.append([i, i])
        elif tag == 'B':
            start = i 
        elif tag == 'E':
            limits.append([start, i])
    
    return np.array(limits, np.int)

# ----------------------------------------------------------------------

def grouper(iterable, n):
    it = iter(iterable)
    while True:
        chunk = tuple(islice(it, n))
        if not chunk:
            return
        yield chunk

# ----------------------------------------------------------------------
# diacritic

import unicodedata
def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

# ----------------------------------------------------------------------

class Trie(dict):
    """Simple trie of ngrams, that keeps counts of their frequencies.
    """

    def __init__(self):
        self.freq = 0           # count the occurrences of ngrams ending here
    
    def __len__(self):
        count = 0
        for trie in super(Trie, self).itervalues():
            if trie.freq:     # terminal node
                count += 1
            count += trie.__len__()
        return count

    def __repr__(self):
        return '<Trie %d, %s>' % (self.freq, super(Trie, self).__repr__())

    def add(self, ngram, lowcase=True, noaccents=True):
        """Insert the ngram :param ngram: into the trie."""
        curr = self
        for tok in ngram:
            if lowcase:
                tok = tok.lower()
            if noaccents:
                tok = strip_accents(tok)
            curr = curr.setdefault(tok, Trie())
        curr.freq += 1

    def prune(self, occurr):
        """prune ngrams that occurr less than :param occurr:"""
        for key, curr in self.items():
            if len(curr) == 0:  # final ngram
                if curr.freq < occurr:            
                    del self[key]
            else:
                curr.prune(occurr)
                # prune dead branch
                if len(curr) == 0:
                    del self[key]

    def iter(self, sent, start=0, lowcase=True, noaccents=True):
        """iterate through all ngrams that occur in :param sent: starting at
        position :param start:
        :param lowcase: compare lower case tokens.
        :param noaccents: compare disregarding accents.
        """
        trie = self
        for cur in xrange(start, len(sent)):
            tok = sent[cur]
            if lowcase:
                tok = tok.lower()
            if noaccents:
                tok = strip_accents(tok)
            if tok in trie:         # part of ngram
                trie = trie[tok]
                if trie.freq:
                    yield cur+1 # ngram end
            else:
                break

    def __iter__(self):
        """Iterate through the ngrams stored in the trie"""
        for key, trie in self.iteritems():
            if trie.freq:     # terminal node
                yield [key]
            for rest in trie:
                yield [key] + rest

