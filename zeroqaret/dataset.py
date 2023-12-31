# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_dataset.ipynb.

# %% auto 0
__all__ = ['udapdr_list', 'our_list', 'BEIRDataset']

# %% ../nbs/01_dataset.ipynb 5
from loguru import logger
import os
from pathlib import Path
from fastcore.basics import patch_to, patch
from fastcore.utils import  *

from beir.datasets.data_loader import GenericDataLoader
from beir import util

from .helper import write_file

import csv
from tqdm import tqdm

from typing import Union, List, Tuple
import re

import pandas as pd
import ujson

# %% ../nbs/01_dataset.ipynb 7
udapdr_list = ['arguana', 'webis-touche2020', 'trec-covid', 'nfcorpus', 'hotpotqa', 'dbpedia-entity', 'climate-fever', 'fever', 'scifact', 'scidocs',  'fiqa']

#| export
our_list = ["fiqa", "trec-covid"]

# %% ../nbs/01_dataset.ipynb 8
class BEIRDataset:
    def __init__(self, 
                 url: str = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/{}.zip"
                ):
        """ Wrapper to load and manage BEIR datasets."""
        # # split the names of the datasets if in string
        # if datasets:
        #     if isinstance(datasets, str):
        #         self.datasets = datasets.split(",")
        #     else:
        #         self.datasets = datasets
        # else: # if None
        #     # these are all the public datasets available on https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/ (retrieved 20231022)
        #     self.datasets = ['fiqa', 'trec-covid']    

        self.url = url
        
        ###  self.out_dir is where we will save all the datasets ###
        try: 
            parent_dir = Path(__file__).absolute().parents[1]
        except:
            parent_dir = Path().absolute().parents[0]
        self.out_dir = (parent_dir /  "datasets").as_posix()
        logger.info(f"Datasets will be saved in '{self.out_dir}'")
        
        ### this is where we will store all the datasets with their corresponding paths ###
        self.datasets = {}
        
    def load_dataset(self,
                     dataset: str,
                     split: str = "test",
                    ): 
        
        if dataset not in self.datasets:
            logger.info(f"Downloading dataset '{dataset}'...")
            cur_url = self.url.format(dataset)
            dataset_path= util.download_and_unzip(cur_url, self.out_dir)
            logger.info(f"Saved on '{dataset_path}'")
    
            self.datasets[dataset] = dataset_path

        return GenericDataLoader(self.datasets[dataset]).load(split=split) # corpus, queries, qrels

    

# %% ../nbs/01_dataset.ipynb 12
@patch_to(BEIRDataset)
def convert_for_colbert(self,
                         dataset: str,
                         split: str = "test",
                        ) -> Tuple[str, str]: 

    """ 
    Converts downloaded BeIR datasets into tsv for ColBERT.
    Returns (collection_path, queries_path)
    """
    
    # load corpus, queries, qrels
    corpus, queries, qrels = self.load_dataset(dataset, split)
    corpus_ids = list(corpus)

        
    # make dir
    os.makedirs(Path(self.datasets[dataset]) / "colbert", exist_ok=True)

    # collection_path and queries_path
    collection_path = (Path(self.datasets[dataset]) / "colbert" / f"{dataset}_collection.tsv").as_posix()
    queries_path = (Path(self.datasets[dataset]) / "colbert" / f"{dataset}_queries.tsv").as_posix()

    
    logger.info("Preprocessing Corpus and Saving to {} ...".format(collection_path))
    with open(collection_path, 'w') as f_in:
        writer = csv.writer(f_in, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        for idx, doc_id in enumerate(tqdm(corpus_ids, total=len(corpus_ids))):
            doc = corpus[doc_id]
            writer.writerow([idx, (self.preprocess(doc.get("title", "")) + " " + self.preprocess(doc.get("text", ""))).strip(), doc_id])

    logger.info("Preprocessing Corpus and Saving to {} ...".format(queries_path))
    with open(queries_path, 'w') as f_in:
        writer = csv.writer(f_in, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        for qid, query in tqdm(queries.items(), total=len(queries)):
            writer.writerow([qid, query])

    return collection_path, queries_path

@patch_to(BEIRDataset)
def preprocess(self, text):
    return text.replace("\r", " ").replace("\t", " ").replace("\n", " ")

# %% ../nbs/01_dataset.ipynb 13
@patch_to(BEIRDataset)
def prepare_qg_for_colbert_training(self,
                                 csv_path: str, # path to CSV training file (containing pid, passage, question, title columns)
                                ) -> (str, str, str):
    """
    Converting and preparing the dataframe loaded from `csv_path` (containing at least 'pid', 'passage' and 'question' columns) for training.
    This will create the following:
        - collection.tsv: TSV containing "pid \t passage text"
        - queries.tsv: TSV containing "generated qid \t title - query"
        - triples.jsonl: jsonl contianing [qid, pid+, pid-] list per line

    Returns tuple of:
        - Path to triples.jsonl
        - Path to queries.tsv
        - Path to collection.tsv
    """
        
    # this is the path to save the files
    save_path = Path(csv_path).parent / "colbert_training"
    # make directory if it does not exist
    save_path.mkdir(exist_ok=True)

    assert not os.listdir(save_path), f"'{save_path}' is not empty! Please ensure that the folder is backed up and cleared before proceeding!"
    
    logger.info(f"Creating ColBERT training files from {save_path}...")
    
    # read csv as dataframe
    train_df = pd.read_csv(csv_path)

    # read csv as dataframe
    train_df = pd.read_csv(csv_path)

    # generate qid as {index}_qid
    train_df["qid"] = train_df.index.astype("str") + "_qid"

    # query as a combination of {title} - {question} 
    train_df["query"] = train_df["title"].astype(str) + " - " + train_df["question"].astype(str)

    # create a shuffled pids for negative sampling
    shuffled_pids = train_df.sample(len(train_df))["pid"]

    # create collection.tsv, queries.tsv and triples.jsonl from train_df
    for pid, pid_n, passage, qid, query in tqdm(zip(train_df["pid"], shuffled_pids, train_df["passage"], train_df["qid"], train_df["query"]), desc="Training files: "):
        write_file(f"{save_path}/triples.jsonl", ujson.dumps([qid, str(pid), str(pid_n)])  + '\n')
        write_file(f"{save_path}/queries.tsv", f"{qid} \t {query} \n")
        write_file(f"{save_path}/collection.tsv", f"{pid} \t {passage} \n")

    logger.info(f"triples.jsonl, queries,tsv and collection.tsv files created in {save_path}.")

    return (f"{save_path}/triples.jsonl", f"{save_path}/queries.tsv", f"{save_path}/collection.tsv")
