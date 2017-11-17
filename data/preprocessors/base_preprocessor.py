import collections
import csv

import pandas as pd
import re
from abc import abstractclassmethod


class BasePreprocessor(object):
    CLEAN_PREFIX = 'clean_'
    TEST_PREFIX = 'clean_test_'
    VOCABULARY_PREFIX = 'vocabulary_'
    VOCABULARY_POS = 'pos_'
    VOCABULARY_CHUNK = 'chunk_'
    VOCABULARY_ENTITY = 'entity_'

    _METADATA_PREFIX = 'metadata_'
    PAD_TOKEN = '<PAD>'
    UNK_TOKEN = '<UNK>'
    UNK_TOKEN_ID = 1
    EOS_TOKEN = '<EOS>'

    DEFAULT_SAVE_DIR = 'asset/train/'

    def __init__(self, path, filename, separator, vocabulary_size, max_data_length, pad_token=PAD_TOKEN,
                 unk_token=UNK_TOKEN, eos_token=EOS_TOKEN):
        self._remove_digits = re.compile(r"""[.+-\/\\]?\d+([.,-:]\d+)?([.:]\d+)?(\.)?""")
        self._dictionary = {}

        self.path = path
        self.filename = filename
        self.separator = separator
        self.pad_token = pad_token
        self.unk_token = unk_token
        self.eos_token = eos_token
        self.vocabulary_size = vocabulary_size
        self.max_data_length = max_data_length
        self.data = None
        self.new_data = None
        self.data_size = 0

    def _build_vocabulary_on_column(self, data, file_name, data_column, word_column, frequency_column):
        most_common = pd.DataFrame(data[data_column].str.split().tolist()).stack().value_counts()
        most_common = most_common.to_frame().reset_index()
        most_common = most_common.rename(columns={'index': word_column, 0: frequency_column})

        most_common.loc[-1] = [self.pad_token, -1]
        most_common.index = most_common.index + 1
        most_common = most_common.sort_index()

        pd.DataFrame(most_common[word_column]).to_csv(self.path + self.VOCABULARY_PREFIX + file_name,
                                                      sep=self.separator,
                                                      index=False, header=False, quoting=csv.QUOTE_NONE,
                                                      encoding='utf-8')

        print('Saved vocabulary file based on %s column' % data_column)

    def _build_dictionary(self, data, column_name, entity_column, pos_column=None, chunk_column=None):
        all_text = []

        for example in data[column_name]:
            all_text.extend(example.split())

        all_words = collections.Counter(all_text).most_common(self.vocabulary_size - 3)

        sorted_by_name = sorted(all_words, key=lambda x: x[0])
        all_words = sorted(sorted_by_name, key=lambda x: x[1], reverse=True)

        tokens = [(self.pad_token, -1), (self.unk_token, -1), (self.eos_token, -1)]
        all_words = tokens + all_words

        assert all_words[BasePreprocessor.UNK_TOKEN_ID][0] == \
               self.unk_token, '<UNK> token id and actual position should match'

        for word in all_words:
            if word[0] not in self._dictionary:
                self._dictionary[word[0]] = len(self._dictionary)

        word_column = 'Word'
        frequency_column = 'Frequency'
        metadata = pd.DataFrame(data=all_words, columns=[word_column, frequency_column])
        self.vocabulary_size = len(self._dictionary)

        print('Built vocabulary with size: %d' % self.vocabulary_size)

        metadata.to_csv(self.path + self._METADATA_PREFIX + self.filename, sep=self.separator, index=False,
                        quoting=csv.QUOTE_NONE, encoding='utf-8')
        print('Saved vocabulary to metadata file')
        pd.DataFrame(metadata[word_column]).to_csv(self.path + self.VOCABULARY_PREFIX + self.filename,
                                                   sep=self.separator, index=False, header=False,
                                                   encoding='utf-8')
        print('Saved vocabulary to vocabulary file')

        self._build_vocabulary_on_column(data, self.VOCABULARY_ENTITY + self.filename, entity_column, word_column,
                                         frequency_column)

        if pos_column is not None:
            self._build_vocabulary_on_column(data, self.VOCABULARY_POS + self.filename, pos_column, word_column,
                                             frequency_column)

        if chunk_column is not None:
            self._build_vocabulary_on_column(data, self.VOCABULARY_CHUNK + self.filename, chunk_column, word_column,
                                             frequency_column)

    def restore_vocabulary_size(self):
        dictionary = pd.read_csv(self.path + self.VOCABULARY_PREFIX + self.filename, sep=self.separator, header=None)
        self.vocabulary_size = dictionary.shape[0]

    def apply_preprocessing(self, column_name, pos_column, chunk_column, entity_column, recreate_dictionary=True):
        assert self.data is not None, 'No input data has been loaded'

        new_data = self.data.loc[self.data[column_name].str.len() < self.max_data_length].copy()
        new_data[column_name] = new_data[column_name].apply(lambda x: self.preprocess_single_entry(x))

        if recreate_dictionary:
            self._build_dictionary(new_data, column_name, entity_column, pos_column=pos_column,
                                   chunk_column=chunk_column)
        else:
            print('Vocabularies already exist, no need to recreate them.')
            self.restore_vocabulary_size()

        self.new_data = new_data
        self.data_size = self.new_data.shape[0]

        print('Applied preprocessing to input data')

    def preprocess_single_entry(self, entry):
        entry = self._regex_preprocess(entry)
        entry = self._custom_preprocessing(entry)

        return entry

    @abstractclassmethod
    def _custom_preprocessing(self, entry):
        """
        Apply custom preprocessing to single data entry. 
        :param entry: 
        :return: the entry after custom preprocessing
        """

        return entry

    def read_file(self):
        raise NotImplementedError

    def save_preprocessed_file(self):
        raise NotImplementedError

    def _regex_preprocess(self, entry):
        entry = self._remove_digits.sub('reg_digitz', entry)
        entry = entry.replace('"', 'reg_quotes')

        return entry

    @staticmethod
    def read_vocabulary(file_path, separator, dictionary=None):
        df = pd.read_csv(file_path, sep=separator, header=None, encoding='utf-8').to_dict()

        dictionary = {} if dictionary is None else dictionary

        # remap value <> key to key <> value
        for k, v in df[0].items():
            v = str(v)
            if v not in dictionary:
                dictionary[v] = len(dictionary)

        return dictionary
