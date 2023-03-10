from torch.utils.data.sampler import BatchSampler, SubsetRandomSampler

import torch

from hsuanwu.common.typing import *

class VanillaRolloutBuffer:
    """Vanilla rollout buffer for on-policy algorithms.
    
    Args:
        device: Device (cpu, cuda, ...) on which the code should be run.
        obs_shape: The data shape of observations.
        action_shape: The data shape of actions.
        action_type: The type of actions, 'cont' or 'dis'.
        num_steps: The sample steps of per rollout.
        num_envs: The number of parallel environments.
        gamma: discount factor.
        gae_lambda: Weighting coefficient for generalized advantage estimation (GAE).

    Returns:
        Vanilla rollout buffer.
    """
    def __init__(self,
                 device: torch.device,
                 obs_shape: Tuple,
                 action_shape: Tuple,
                 action_type: str,
                 num_steps: int,
                 num_envs: int,
                 gamma: float = 0.99,
                 gae_lambda: float = 0.95) -> None:
        self._obs_shape = obs_shape
        self._action_shape = action_shape
        self._device = torch.device(device)
        self._num_steps = num_steps
        self._num_envs = num_envs
        self._gamma = gamma
        self._gae_lambda = gae_lambda

        self._storage = dict()
        # transition part
        self._storage['obs'] = torch.empty(size=(num_steps, num_envs, *obs_shape), 
                                           dtype=torch.float32, 
                                           device=self._device)
        if action_type == 'dis':
            self._action_dim = 1
            self._storage['actions']  = torch.empty(size=(num_steps, num_envs, 1), 
                                                    dtype=torch.float32, 
                                                    device=self._device)
        if action_type == 'cont':
            self._action_dim = action_shape[0]
            self._storage['actions'] = torch.empty(size=(num_steps, num_envs, self._action_dim), 
                                                   dtype=torch.float32, 
                                                   device=self._device)
        self._storage['rewards'] = torch.empty(size=(num_steps, num_envs, 1), dtype=torch.float32, device=self._device)
        self._storage['dones'] = torch.empty(size=(num_steps + 1, num_envs, 1), dtype=torch.float32, device=self._device)
        # first next_done
        self._storage['dones'][0].copy_(torch.zeros(num_envs, 1).to(self._device))
        # extra part
        self._storage['log_probs'] = torch.empty(size=(num_steps, num_envs, 1), dtype=torch.float32, device=self._device)
        self._storage['values'] = torch.empty(size=(num_steps, num_envs, 1), dtype=torch.float32, device=self._device)
        self._storage['returns'] = torch.empty(size=(num_steps, num_envs, 1), dtype=torch.float32, device=self._device)
        self._storage['advantages'] = torch.empty(size=(num_steps, num_envs, 1), dtype=torch.float32, device=self._device)

        self._global_step = 0
    
    def get(self, key):
        """Get stored experiences.

        Args:
            key: Keyword of the storage dictionary, e.g., "obs".
        
        Returns:
            Value of the storage dictionary.
        """
        return self._storage[key]
    

    def add(self, obs: Any, actions: Any, rewards: Any, dones: Any, log_probs: Any, values: Any) -> None:
        """Add sampled transitions into storage.
        
        Args:
            obs: Observations.
            actions: Actions.
            rewards: Rewards.
            dones: Dones.
            log_probs: Log of the probability evaluated at `actions`.
            values: Estimated values.

        Returns:
            None.
        """
        self._storage['obs'][self._global_step].copy_(obs)
        self._storage['actions'][self._global_step].copy_(actions)
        self._storage['rewards'][self._global_step].copy_(rewards)
        self._storage['dones'][self._global_step + 1].copy_(dones)
        self._storage['log_probs'][self._global_step].copy_(log_probs)
        self._storage['values'][self._global_step].copy_(values)

        self._global_step = (self._global_step + 1) % self._num_steps
        

    def reset(self) -> None:
        """Reset the terminal state of each env.

        """
        self._storage['dones'][0].copy_(self._storage['dones'][-1])
        

    def compute_returns_and_advantages(self, last_values: Tensor) -> None:
        """Perform generalized advantage estimation (GAE).
        
        Args:
            last_values: Estimated values of the last step.
            gamma: Discount factor.
            gae_lamdba: Coefficient of GAE.
        
        Returns:
            None.
        """
        gae = 0
        for step in reversed(range(self._num_steps)):
            if step == self._num_steps - 1:
                next_non_terminal = 1.0 - self._storage['dones'][-1]
                next_values = last_values
            else:
                next_non_terminal = 1.0 - self._storage['dones'][step + 1]
                next_values = self._storage['values'][step + 1]
            delta = self._storage['rewards'][step] + self._gamma * next_values * next_non_terminal - self._storage['values'][step]
            gae = delta + self._gamma * self._gae_lambda * next_non_terminal * gae
            self._storage['advantages'][step] = gae
        
        self._storage['returns'] = self._storage['advantages'] + self._storage['values']


    def generator(self, num_mini_batch: int = None) -> Batch:
        """Sample data from storage.
        
        Args:
            num_mini_batch: Number of mini-batches

        Returns:
            Batch data.
        """
        batch_size = self._num_envs * self._num_steps

        assert batch_size >= num_mini_batch, (
            "PPO requires the number of processes ({}) "
            "* number of steps ({}) = {} "
            "to be greater than or equal to the number of PPO mini batches ({})."
            "".format(self._num_envs, self._num_steps, batch_size, num_mini_batch))
        mini_batch_size = batch_size // num_mini_batch

        sampler = BatchSampler(
            SubsetRandomSampler(range(batch_size)),
            mini_batch_size,
            drop_last=True)
        
        for indices in sampler:
            batch_obs = self._storage['obs'].view(-1, *self._obs_shape)[indices]
            batch_actions = self._storage['actions'].view(-1, self._action_dim)[indices]
            batch_values = self._storage['values'].view(-1, 1)[indices]
            batch_returns = self._storage['returns'].view(-1, 1)[indices]
            batch_dones = self._storage['dones'][:-1].view(-1, 1)[indices]
            batch_old_log_probs = self._storage['log_probs'].view(-1, 1)[indices]
            adv_targ = self._storage['advantages'].view(-1, 1)[indices]

            yield batch_obs, batch_actions, batch_values, batch_returns, batch_dones, batch_old_log_probs, adv_targ


