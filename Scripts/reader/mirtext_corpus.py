import logging
import xml.etree.ElementTree as ET
import os
import sys

import itertools
import progressbar as pb
import time

from text.corpus import Corpus
from text.document import Document
from text.mirna_entity import mirna_graph
from text.protein_entity import get_uniprot_name
from text.sentence import Sentence

type_match = {"MiRNA": "mirna",
              "Gene": "protein",
              "unknown miRNA-gene regulation": "miRNA-gene",
              "direct miRNA-gene regulation": "miRNA-gene",
              "N/A gene-miRNA regulation": "gene-miRNA"}
              # "gene-miRNA regulation": ""}
class MirtexCorpus(Corpus):
    """
    DDI corpus used for NER and RE on the SemEval DDI tasks of 2011 and 2013.
    self.path is the base directory of the files of this corpus.
    Each file is a document, DDI XML format, sentences already separated.
    """
    def __init__(self, corpusdir, **kwargs):
        super(MirtexCorpus, self).__init__(corpusdir, **kwargs)
        self.subtypes = []

    def load_corpus(self, corenlpserver, process=True):
        # self.path is the base directory of the files of this corpus
        trainfiles = [self.path + '/' + f for f in os.listdir(self.path) if f.endswith('.txt')]
        total = len(trainfiles)
        widgets = [pb.Percentage(), ' ', pb.Bar(), ' ', pb.AdaptiveETA(), ' ', pb.Timer()]
        pbar = pb.ProgressBar(widgets=widgets, maxval=total, redirect_stdout=True).start()
        time_per_abs = []
        for current, f in enumerate(trainfiles):
            #logging.debug('%s:%s/%s', f, current + 1, total)
            print '{}:{}/{}'.format(f, current + 1, total)
            did = f.split(".")[0]
            t = time.time()
            with open(f, 'r') as txt:
                doctext = txt.read()
            newdoc = Document(doctext, process=False, did=did)
            newdoc.sentence_tokenize("biomedical")
            if process:
                newdoc.process_document(corenlpserver, "biomedical")
            self.documents[newdoc.did] = newdoc
            abs_time = time.time() - t
            time_per_abs.append(abs_time)
            #logging.info("%s sentences, %ss processing time" % (len(newdoc.sentences), abs_time))
            pbar.update(current+1)
        pbar.finish()
        abs_avg = sum(time_per_abs)*1.0/len(time_per_abs)
        logging.info("average time per abstract: %ss" % abs_avg)

    def load_annotations(self, ann_dir, etype, pairtype="all"):
        self.clear_annotations()
        self.clear_annotations("protein")
        self.clear_annotations("mirna")
        tagged = 0
        not_tagged = 0
        pmids = []
        annfiles = [ann_dir + '/' + f for f in os.listdir(ann_dir) if f.endswith('.ann')]
        total = len(annfiles)
        time_per_abs = []
        doc_to_relations = {}
        with open(ann_dir + "/" + "annotations.tsv") as afile:
            for l in afile:
                if not l.isspace():
                    v = l.strip().split("\t")
                    did = self.path + '/' + v[0]
                    if pairtype == "all" or type_match.get(" ".join(v[-2:])) == pairtype:
                        if did not in doc_to_relations:
                            doc_to_relations[did] = set()
                        e1 = v[1].split(";")
                        for source in e1:
                            e2 = v[2].split(";")
                            for target in e2:
                                doc_to_relations[did].add((source.strip().replace('"', ''),
                                                            target.strip().replace('"', '')))
        # print doc_to_relations
        # print self.documents.keys()
        # print doc_to_relations.keys()
        for did in self.documents:
            self.documents[did].relations = set()
            if did in doc_to_relations:
                for r in doc_to_relations[did]:
                    self.documents[did].relations.add(r)
                # print did, self.documents[did].relations
        for current, f in enumerate(annfiles):
            logging.debug('%s:%s/%s', f, current + 1, total)
            did = f.split(".")[0]
            pmids.append(did.split("/")[-1])
            with open(f, 'r') as txt:
                for line in txt:
                    # print line
                    if line.startswith("T"):
                        tid, ann, etext = line.strip().split("\t")
                        entity_type, dstart, dend = ann.split(" ")
                        if etype == "all" or (etype != "all" and etype == type_match[entity_type]):
                            dstart, dend = int(dstart), int(dend)
                            sentence = self.documents[did].find_sentence_containing(dstart, dend, chemdner=False)
                            if sentence is not None:
                                # e[0] and e[1] are relative to the document, so subtract sentence offset
                                start = dstart - sentence.offset
                                end = dend - sentence.offset
                                eid = sentence.tag_entity(start, end, type_match[entity_type], text=etext)
                                if eid is not None:
                                    tagged += 1
                                else:
                                    not_tagged += 1
                            else:
                                print "could not find sentence for this span: {}-{}".format(dstart, dend)
        logging.info("normalizing entities...")
        for sentence in self.get_sentences("goldstandard"):
                for e in sentence.entities.elist["goldstandard"]:
                    e.normalize()
        self.find_relations(pairtype)
        # self.evaluate_normalization()
        print "tagged: {} not tagged: {}".format(tagged, not_tagged)
        with open(ann_dir[:-1] + "-pmids.txt", 'w') as pmidsfile:
            pmidsfile.write("\n".join(pmids) + "\n")
        # self.run_ss_analysis(pairtype)


    def find_relations(self, pairtype):
        # automatically find the relations from the gold standard at sentence level
        with open("corpora/miRTex/mirtex_relations.txt", 'w') as rfile:
            for sentence in self.get_sentences(hassource="goldstandard"):
                did = sentence.did
                for pair in itertools.combinations(sentence.entities.elist["goldstandard"], 2):
                    # consider that the first entity may appear before or after the second
                    if (pair[0].text, pair[1].text) in self.documents[did].relations or \
                       (pair[1].text, pair[0].text) in self.documents[did].relations:
                        if (pair[1].text, pair[0].text) in self.documents[did].relations:
                            pair = (pair[1], pair[0])
                        start, end = pair[0].dstart, pair[1].dend
                        if start > end:
                            start, end = pair[1].dstart, pair[0].dend
                        between_text = self.documents[did].text[start:end]
                        if between_text.count(pair[0].text) > 1 or between_text.count(pair[1].text) > 1:
                            # print "excluded:", between_text
                            continue
                        # print between_text
                        pair[0].targets.append((pair[1].eid, pairtype))
                        rfile.write("{}\t{}\n".format(pair[0].normalized, pair[1].normalized))


def get_mirtex_gold_ann_set(goldpath, entitytype, pairtype):
    logging.info("loading gold standard... {}".format(goldpath))
    annfiles = [goldpath + '/' + f for f in os.listdir(goldpath) if f.endswith('.ann')]
    gold_offsets = set()
    for current, f in enumerate(annfiles):
            did = f.split(".")[0]
            with open(f, 'r') as txt:
                for line in txt:
                    if line.startswith("T"):
                        tid, ann, etext = line.strip().split("\t")
                        etype, dstart, dend = ann.split(" ")
                        if entitytype == type_match[etype]:
                            dstart, dend = int(dstart), int(dend)
                            gold_offsets.add((did, dstart, dend, etext))
    gold_relations = {}
    with open(goldpath + "/" + "annotations.tsv") as afile:
        for l in afile:
            v = l.strip().split("\t")
            if len(v) < 3:
                continue
            did = goldpath + '/' + v[0]
            # logging.info("{} {} {}".format(did, pairtype, v[-1]))
            if pairtype == "all" or type_match.get(" ".join(v[-2:])) == pairtype:
                e1 = v[1].split(";")
                for mirna in e1:
                    mirna = mirna.replace('"', '')
                    # logging.info(mirna)
                    norm_mirna = mirna_graph.map_label(mirna)
                    if norm_mirna < 99:
                        norm_mirna[0] = mirna
                    e2 = v[2].split(";")
                    for gene in e2:
                        gene = gene.replace('"', '')
                        # logging.info(gene)
                        norm_gene = get_uniprot_name(gene)
                        #gold_relations.add((did, norm_mirna[0], norm_gene[0]))
                        gold_relations[(did, norm_mirna[0], norm_gene[0], norm_mirna[0] + "=>" + norm_gene[0])] = []
    return gold_offsets, gold_relations


