import copy
import json
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path
from tqdm import tqdm

class PromptMode(Enum):
    UNSPECIFIED = 0
    RANK_GPT = 1
    LRL = 2
    PRL = 3

class RankLLM(ABC):
    def __init__(self, model:str, context_size:int, dataset: str, prompt_mode: PromptMode):
        self.model_ = model
        self.context_size_ = context_size
        self.dataset_ = dataset
        self.prompt_mode_ = prompt_mode
    
    def max_tokens(self):
        return self.context_size_
    
    @abstractmethod
    def run_llm(self, prompt):
        pass

    @abstractmethod
    def create_prompt(self, retrieved_result, rank_start=0, rank_end=100):
        pass

    @abstractmethod
    def get_num_tokens(self, prompt):
        pass

    @abstractmethod
    def receive_permutation(self, item, permutation, rank_start=0, rank_end=100):
        pass

    @abstractmethod
    def cost_per_1k_token(self, input_token:bool):
        pass

    @abstractmethod
    def num_output_tokens(self):
        pass

    def permutation_pipeline(self, result, rank_start=0, rank_end=100):
        prompt, in_token_count = self.create_prompt(result, rank_start, rank_end)
        permutation, out_token_count = self.run_llm(prompt)
        rerank_result = self.receive_permutation(result, permutation, rank_start, rank_end)
        return rerank_result, in_token_count, out_token_count, prompt, permutation
    
    def sliding_windows(self, retrieved_result, rank_start=0, rank_end=100, window_size=20, step=10):
        in_token_count = 0
        out_token_count = 0
        rerank_result = copy.deepcopy(retrieved_result)
        end_pos = rank_end
        start_pos = rank_end - window_size
        prompts = []
        permutations = []
        while start_pos >= rank_start:
            start_pos = max(start_pos, rank_start)
            rerank_result, in_count, out_count, prompt, permutation = self.permutation_pipeline(rerank_result, start_pos, end_pos)
            in_token_count += in_count
            out_token_count += out_count
            prompts.append(prompt)
            permutations.append(permutation)
            end_pos = end_pos - step
            start_pos = start_pos - step
        return rerank_result, in_token_count, out_token_count, prompts, permutations

    def get_ranking_cost_upperbound(self, num_q, rank_start=0, rank_end=100, window_size=20, step=10):
        # For every prompt generated for every query assume the max context size is used.
        num_promt = (rank_end - rank_start - window_size) / step + 1
        input_token_count = num_q * num_promt * (self.context_size - self.num_output_tokens())
        output_token_count = num_q * num_promt * self.num_output_tokens()
        cost = ((input_token_count * self.cost_per_1k_token(input_token=True)
                 + output_token_count* self.cost_per_1k_token(input_token=False))
                 / 1000.0)
        return (cost, input_token_count + output_token_count)
    
    
    def get_ranking_cost(self, retrieved_results, rank_start=0, rank_end=100, window_size=20, step=10):
        input_token_count = 0
        output_token_count = 0
        # Go through the retrieval result using the sliding window and count the number of tokens for generated prompts.
        # This is an estimated cost analysis since the actual prompts' length will depend on the ranking.
        for result in tqdm(retrieved_results):
            end_pos = rank_end
            start_pos = rank_end - window_size
            while start_pos >= rank_start:
                start_pos = max(start_pos, rank_start)
                prompt = self.create_prompt(result, start_pos, end_pos)
                input_token_count += self.get_num_tokens(prompt)
                end_pos = end_pos - step
                start_pos = start_pos - step
                output_token_count += self.num_output_tokens()
        cost = ((input_token_count * self.cost_per_1k_token(input_token=True)
                 + output_token_count* self.cost_per_1k_token(input_token=False))
                 / 1000.0)
        return (cost, input_token_count + output_token_count)
    
    def write_rerank_results(self, rerank_results, input_token_counts, output_token_counts, prompts, responses):
        # write rerank results
        Path("rerank_results/").mkdir(parents=True, exist_ok=True)
        result_file_name = f'rerank_results/{self.model_}_{self.context_size_}_{self.prompt_mode_}_{self.dataset_}_{datetime.isoformat(datetime.now())}.txt'
        with open(result_file_name, 'w') as f:
            for i in range(len(rerank_results)):
                rank = 1
                hits = rerank_results[i]['hits']
                for hit in hits:
                    f.write(f"{hit['qid']} Q0 {hit['docid']} {rank} {hit['score']} rank\n")
                    rank += 1
        # Write token counts
        Path("token_counts/").mkdir(parents=True, exist_ok=True)
        count_file_name = f'token_counts/{self.model_}_{self.context_size_}_{self.prompt_mode_}_{self.dataset_}_{datetime.isoformat(datetime.now())}.txt'
        counts = {}
        for i, (in_count, out_count) in enumerate(zip(input_token_counts, output_token_counts)):
            counts[rerank_results[i]['query']] = (in_count, out_count)
        with open(count_file_name, 'w') as f:
            json.dump(counts, f, indent = 4)
        # Write prompts and responses
        Path("prompts_and_responses/").mkdir(parents=True, exist_ok=True)
        with open(f'prompts_and_responses/{self.model_}_{self.context_size_}_{self.prompt_mode_}_{self.dataset_}_{datetime.isoformat(datetime.now())}.json', 'w') as f:
            for (p, r) in zip(prompts, responses):
                json.dump({"prompt": p, "response": r}, f, indent = 4)
                f.write(', ')
        return result_file_name