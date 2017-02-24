from __future__ import division, unicode_literals

import os
import sys
from subprocess import Popen, PIPE, call
import logging
import codecs
import ner
import re
import atexit
from socket import error as SocketError
import errno

from text.protein_entity import ProteinEntity
from text.offset import Offsets, Offset
from classification.results import ResultsNER
from classification.ner.simpletagger import SimpleTaggerModel, create_entity
from config import config


class BANNERModel(SimpleTaggerModel):
    RAM = config.stanford_ner_train_ram
    RAM_TEST = config.stanford_ner_test_ram
    #STANFORD_BASE = config.stanford_ner_dir
    #STANFORD_NER = "{}/stanford-ner.jar".format(STANFORD_BASE)
    #NER_PROP = "{}/base.prop".format(STANFORD_BASE)
    BANNER_BASE = "bin/banner/trunk/"
    BANNER_CONFIG = "config/banner_BC2GM_TEST.xml"
    # logging.info(NER_PROP)
    #PARAMS = ["./scripts/banner.sh", "tag", ]
    #logging.info(PARAMS)
    TEST_SENT = "Structure-activity relationships have been investigated for inhibition of DNA-dependent protein kinase (DNA-PK) and ATM kinase by a series of pyran-2-ones, pyran-4-ones, thiopyran-4-ones, and pyridin-4-ones."

    def __init__(self, path, etype, **kwargs):
        super(BANNERModel, self).__init__(path, etype, **kwargs)
        self.process = None
        self.tagger = None
        self.params = []

    def load_tagger(self, port=9181):
        """
        Start the server process with the classifier
        :return:
        """
        # TODO: check if it already loaded (and then kill that instance)
        pass

        # out = ner.communicate("Structure-activity relationships have been investigated for inhibition of DNA-dependent protein kinase (DNA-PK) and ATM kinase by a series of pyran-2-ones, pyran-4-ones, thiopyran-4-ones, and pyridin-4-ones.")
        # logging.info(out)
        # print 'Success!!'



    def test(self, corpus, port=9181):
        # self.tagger = ner.SocketNER("localhost", port, output_format='inlineXML')
        base_dir = os.getcwd()
        os.chdir(self.BANNER_BASE)
        tagged_sentences = []
        ichunk = 0
        chunk_size = 5000
        for sidsx in chunks(self.sids, chunk_size):
            with codecs.open("temp/banner_input{}.txt".format(ichunk), 'w', 'utf-8') as inputfile:
                for i, sid in enumerate(sidsx):
                    inputfile.write("{}\t{}\n".format(sid, self.sentences[i+(ichunk*chunk_size)]))
            self.params = ["./scripts/banner.sh", "tag", self.BANNER_CONFIG, "temp/banner_input{}.txt".format(ichunk),
                           "temp/banner_output{}.txt".format(ichunk)]
            logging.info(' '.join(self.params))
            # process.communicate()
            logging.info("Starting banner tagger ({})".format(ichunk))
            self.process = Popen(self.params, stdin=PIPE, stdout=PIPE, stderr=PIPE)
            while True:
                output = self.process.stdout.readline()
                if output == '' and self.process.poll() is not None:
                    break
                if output:
                    logging.info(output.strip())
            ichunk += 1
        # merge outputs
        with open("temp/banner_output.txt", 'w') as outfile:
            for i in range(ichunk):
                with open("temp/banner_output{}.txt".format(i)) as chunkfile:
                    outfile.write(chunkfile.read())

        os.chdir(base_dir)
        results = self.process_results(self.BANNER_BASE + "/temp/banner_output.txt", corpus)
        return results

    def process_results(self, outputfile, corpus):
        results = ResultsNER(self.path)
        results.corpus = corpus
        with codecs.open(outputfile, 'r', 'utf-8') as ofile:
            for line in ofile:
                sid, genetype, start, end, etext = line.strip().split("\t")
                sentence = corpus.get_sentence(sid)
                tokens = sentence.find_tokens_between(int(start), int(end), relativeto="sent")
                if tokens:
                    new_entity = create_entity(tokens=tokens,
                                               sid=sentence.sid, did=sentence.did,
                                               text=etext, score=1, etype=self.etype)
                    eid = sentence.tag_entity(start=new_entity.tokens[0].start,
                                              end=new_entity.tokens[-1].end, etype=self.etype,
                                              entity=new_entity, source=self.path)
                    new_entity.eid = eid
                    results.entities[eid] = new_entity
                    new_entity = None
                else:
                    logging.info("No tokens found: {}-{}".format(start, end))
                    logging.info(sentence.text)
        logging.info("found {} entities".format(len(results.entities)))
        return results


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i+n]
