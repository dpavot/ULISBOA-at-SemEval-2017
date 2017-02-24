from __future__ import unicode_literals

import codecs
import logging
import sys
import itertools
import re

import config.seedev_types
from classification.rext.kernelmodels import ReModel
from classification.results import ResultsRE
from config import config
from text.pair import Pairs


class RuleClassifier(ReModel):
    def __init__(self, corpus, ptype, rules=["triggers"], ner="goldstandard"):
        """
        Rule based classifier
        rules: List of rules to use
        """
        self.rules = rules
        self.ptype = ptype
        self.corpus = corpus
        self.pairs = {}
        self.pids = {}
        self.trigger_words = set([])
        self.ner_model = ner


    def load_classifier(self):
        self.relations = set()
        with codecs.open("seedev_relation.txt", 'r', 'utf-8') as relfile:
            for r in relfile:
                self.relations.add(r.strip())


    def test(self):
        pcount = 0
        ptrue = 0
        unique_relations = {}
        pairtypes = (config.relation_types[self.ptype]["source_types"], config.relation_types[self.ptype]["target_types"])
        # pairtypes = (config.event_types[pairtype]["source_types"], config.event_types[pairtype]["target_types"])
        for sentence in self.corpus.get_sentences(self.ner_model):
            #doc_entities = self.corpus.documents[did].get_entities("goldstandard")
            did = sentence.did
            sentence_entities = [entity for entity in sentence.entities.elist[self.ner_model]]
            # logging.debug("sentence {} has {} entities ({})".format(sentence.sid, len(sentence_entities), len(sentence.entities.elist["goldstandard"])))
            # doc_entities += sentence_entities
            for pair in itertools.permutations(sentence_entities, 2):
                if self.ptype in ("Has_Sequence_Identical_To", "Is_Functionally_Equivalent_To") and pair[0].type != pair[1].type:
                    continue
                if pair[0].text == pair[1].text:
                    continue
                pid = did + ".p" + str(pcount)
                self.pids[pid] = pair
                self.pairs[pid] = 0
                # logging.info("relation: {}=>{}".format(pair[0].type, pair[1].type))
                if pair[0].type in pairtypes[0] and pair[1].type in pairtypes[1]:
                    # logging.info("mirna-dna relation: {}=>{}".format(pair[0].text, pair[1].text))

                    #rel_text = "{0.type}#{0.text}\t{1}\t{2.type}#{2.text}".format(pair[0], self.ptype, pair[1])
                    #if rel_text in self.relations:
                    self.pairs[pid] = 1
                    ptrue += 1
                    self.pids[pid] = pair
                    """if rel_text not in self.relations:
                        #unique_relations[rel_text] = set()
                    if (pair[1].eid, self.ptype) in pair[0].targets:
                        unique_relations[rel_text].add(1)
                    else:
                        unique_relations[rel_text].add(0)"""
                #elif pair[1].type in config.pair_types[self.ptype]["source_types"] and\
                #     pair[0].type in config.pair_types[self.ptype]["target_types"]:
                #    self.pids[pid] = (pair[1], pair[0])
                #    self.pairs[pid] = 1
                #    ptrue += 1
                pcount += 1
        # print unique_relations
        # never relation
        # print len([r for r in unique_relations if 0 in unique_relations[r] and len(unique_relations[r]) == 1])
        # always relation
        # print [r for r in unique_relations if 1 in unique_relations[r] and len(unique_relations[r]) == 1]
        # mix
        # print len([r for r in unique_relations if 1 in unique_relations[r] and 0 in unique_relations[r]])


    def get_predictions(self, corpus):
        results = ResultsRE("")
        # print len(self.pids)
        for p, pid in enumerate(self.pids):
            if self.pairs[pid] < 1:
                # pair.recognized_by["rules"] = -1
                pass
            else:
                did = ".".join(pid.split(".")[:-1])
                if did not in results.document_pairs:
                    results.document_pairs[did] = Pairs()
                pair = corpus.documents[did].add_relation(self.pids[pid][0], self.pids[pid][1], self.ptype, relation=True)
                #pair = self.get_pair(pid, corpus)
                results.document_pairs[did].add_pair(pair, "rules")
                results.pairs[pid] = pair
                pair.recognized_by["rules"] = 1
                logging.info("{0.eid}:{0.text} => {1.eid}:{1.text}".format(pair.entities[0],pair.entities[1]))
            #logging.info("{} - {} SST: {}".format(pair.entities[0], pair.entities[0], score))
        results.corpus = corpus
        return results



