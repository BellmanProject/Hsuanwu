from gym.envs.registration import register
from collections import deque

import numpy as np
import gym

class FrameStack(gym.Wrapper):
    def __init__(self, env, k):
        gym.Wrapper.__init__(self, env)
        self._k = k
        self._frames = deque([], maxlen=k)
        shp = env.observation_space.shape
        self.observation_space = gym.spaces.Box(
            low=0,
            high=1,
            shape=((shp[0] * k,) + shp[1:]),
            dtype=env.observation_space.dtype
        )
        self._max_episode_steps = env._max_episode_steps

    def reset(self):
        obs = self.env.reset()
        for _ in range(self._k):
            self._frames.append(obs)
        return self._get_obs()

    def step(self, action):
        obs, reward, done, info = self.env.step(action)
        self._frames.append(obs)
        return self._get_obs(), reward, done, info

    def _get_obs(self):
        assert len(self._frames) == self._k
        return np.concatenate(list(self._frames), axis=0)

def make_dmc_env(
    env_id,
    resource_files,
    img_source,
    total_frames,
    seed=1,
    visualize_reward=True,
    from_pixels=False,
    height=84,
    width=84,
    camera_id=0,
    frame_stack=3,
    frame_skip=1,
    episode_length=1000,
    environment_kwargs=None
):
    domain_name, task_name = env_id.split('_')
    env_id = 'dmc_%s_%s_%s-v1' % (domain_name, task_name, seed)

    if from_pixels:
        assert not visualize_reward, 'cannot use visualize reward when learning from pixels'

    # shorten episode length
    max_episode_steps = (episode_length + frame_skip - 1) // frame_skip

    if not env_id in gym.envs.registry.env_specs:
        register(
            id=env_id,
            entry_point='hsuanwu.env.dmc.wrappers:DMCWrapper',
            kwargs={
                'domain_name': domain_name,
                'task_name': task_name,
                'resource_files': resource_files,
                'img_source': img_source,
                'total_frames': total_frames,
                'task_kwargs': {
                    'random': seed
                },
                'environment_kwargs': environment_kwargs,
                'visualize_reward': visualize_reward,
                'from_pixels': from_pixels,
                'height': height,
                'width': width,
                'camera_id': camera_id,
                'frame_skip': frame_skip,
            },
            max_episode_steps=max_episode_steps
        )
    return FrameStack(gym.make(env_id), k=frame_stack)