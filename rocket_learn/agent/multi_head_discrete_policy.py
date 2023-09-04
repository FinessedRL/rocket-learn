from typing import Optional, List, Tuple

import numpy as np
import torch as th
from torch import nn
from torch.distributions import Categorical
import torch.nn.functional as F

from rocket_learn.agent.policy import Policy


class MultiHeadDiscretePolicy(Policy):
    def __init__(self, body: nn.Module, heads: Tuple[nn.Module], head_prediction_actual_fns: Tuple[function], head_prediction_grade_fns: Tuple[function],
        shape: Tuple[int, ...] = (3,) * 5 + (2,) * 3, deterministic=False):

        super().__init__(deterministic)
        self.body = body
        self.heads = heads
        self.head_prediction_actual_fns = head_prediction_actual_fns
        self.head_prediction_grade_fns = head_prediction_grade_fns
        self.shape = shape

    def forward(self, obs):
        if isinstance(obs, np.ndarray):
            obs = th.from_numpy(obs).float()
        elif isinstance(obs, tuple):
            obs = tuple(o if isinstance(o, th.Tensor) else th.from_numpy(o).float() for o in obs)
        return self.body(obs)

    def get_aux_heads_loss(self, body_outs, game_states):
        prediction_actuals = [fn(game_states) for fn in self.head_prediction_actual_fns]
        predictions = [head(th.as_tensor(body_outs)) for head in self.heads[1:]]
        return sum([fn(predictions[idx], prediction_actuals[idx]) for idx,fn in enumerate(self.head_prediction_grade_fns)])

    def get_action_distribution(self, body_out):
        logits = self.heads[0](body_out)

        if isinstance(logits, th.Tensor):
            logits = (logits,)

        max_shape = max(self.shape)
        logits = th.stack(
            [
                l
                if l.shape[-1] == max_shape
                else F.pad(l, pad=(0, max_shape - l.shape[-1]), value=float("-inf"))
                for l in logits
            ],
            dim=1
        )

        return Categorical(logits=logits)


    def sample_action(
            self,
            distribution: Categorical,
            deterministic=None
    ):
        if deterministic is None:
            deterministic = self.deterministic
        if deterministic:
            action_indices = th.argmax(distribution.logits, dim=-1)
        else:
            action_indices = distribution.sample()

        return action_indices

    def log_prob(self, distribution: Categorical, selected_action):
        log_prob = distribution.log_prob(selected_action).sum(dim=-1)
        return log_prob

    def entropy(self, distribution: Categorical, selected_action):
        entropy = distribution.entropy().sum(dim=-1)
        return entropy

    def env_compatible(self, action):
        if isinstance(action, th.Tensor):
            action = action.numpy()
        return action