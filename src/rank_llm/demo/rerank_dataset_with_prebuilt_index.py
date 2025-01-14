import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
parent = os.path.dirname(SCRIPT_DIR)
parent = os.path.dirname(parent)
sys.path.append(parent)

from rank_llm.retrieve.retriever import Retriever
from rank_llm.retrieve.pyserini_retriever import RetrievalMethod
from rank_llm.rerank.vicuna_reranker import VicunaReranker

# By default uses BM25 for retrieval
dataset_name = "dl19"
retrieved_results = Retriever.from_dataset_with_prebuit_index(dataset_name)
reranker = VicunaReranker()
rerank_results = reranker.rerank(retrieved_results)
print(rerank_results)

# Users can specify other retrieval methods:
retrieved_results = Retriever.from_dataset_with_prebuit_index(
    dataset_name, RetrievalMethod.SPLADE_P_P_ENSEMBLE_DISTIL
)
reranker = VicunaReranker()
rerank_results = reranker.rerank(retrieved_results)
print(rerank_results)
