#!/usr/bin/env python
# -*- encoding: utf-8 -*-

import os.path as osp

import torch.distributed as dist

from colossalai.checkpointing import get_latest_checkpoint_path, get_checkpoint_path
from colossalai.registry import HOOKS
from colossalai.trainer.hooks import BaseHook
from colossalai.trainer import Trainer
from colossalai.utils import is_dp_rank_0


@HOOKS.register_module
class SaveCheckpointHook(BaseHook):
    """Saves the model by interval in training process.

    :param trainer: Trainer attached with current hook
    :param interval: Saving interval 
    :param checkpoint_dir: Directory of saving checkpoint 
    :param suffix: Saving suffix of the file
    :param priority: Priority in the printing, hooks with small priority will be printed in front
    :type trainer: Trainer
    :type interval: int, optional
    :type checkpoint_dir: int, optional
    :type suffix: str, optional
    :type priority: int, optional
    """

    def __init__(self,
                 trainer: Trainer,
                 interval: int = 1,
                 checkpoint_dir: str = None,
                 suffix: str = '',
                 priority: int = 0):
        super().__init__(trainer=trainer, priority=priority)
        assert isinstance(trainer, Trainer), \
            f'SaveCheckpointHook expects a Trainer, got {type(trainer)}'
        self.interval = interval
        self.checkpoint_dir = checkpoint_dir
        self.suffix = suffix

    def after_train_epoch(self):
        """Saves the model after a training epoch.
        """
        # save by interval
        if self.trainer.cur_epoch % self.interval == 0:
            # only gpus with data parallel rank equals to 0 write to the disk
            if is_dp_rank_0():
                self.trainer.save(path=self.checkpoint_dir, suffix=self.suffix)
                self.logger.info(
                    f'checkpoint for epoch {self.trainer.cur_epoch} is saved to {self.checkpoint_dir}')

            # wait until everyone is done
            if dist.is_initialized():
                dist.barrier()


@HOOKS.register_module
class LoadCheckpointHook(BaseHook):
    """Loads the model before training process.

    :param trainer: Trainer attached with current hook
    :param checkpoint_dir: Directory of saving checkpoint 
    :param epoch: Epoch number to be set
    :param finetune: Whether allows to load a part of the model
    :param strict: Whether loads a model that has the same shape of parameters 
    :param priority: Priority in the printing, hooks with small priority will be printed in front
    :type trainer: Trainer
    :type checkpoint_dir: str, optional
    :type epoch: str, optional
    :type finetune: bool, optional
    :type strict: bool, optional
    :type priority: int, optional
    """

    def __init__(self,
                 trainer: Trainer = None,
                 checkpoint_dir: str = None,
                 epoch: int = -1,
                 finetune: bool = False,
                 strict: bool = False,
                 priority: int = 10) -> None:
        assert isinstance(trainer, Trainer), \
            f'LoadLatestCheckpointHook excepts a Trainer, got {type(trainer)}'
        self.epoch = epoch
        self.checkpoint_dir = checkpoint_dir
        self.finetune = finetune
        self.strict = strict
        super().__init__(trainer=trainer, priority=priority)

    def before_train(self):
        """Loads parameters to the model before training.
        """
        if self.epoch == -1:
            path = get_latest_checkpoint_path(self.checkpoint_dir)
        else:
            path = get_checkpoint_path(self.checkpoint_dir, epoch=self.epoch)
        if osp.exists(path):
            self.trainer.load(
                path, finetune=self.finetune, strict=self.strict)
            self.logger.info(
                f'loaded checkpoint from {path}')
        else:
            raise FileNotFoundError(f'checkpoint is not found at {path}')

        # Some utilities want to load a checkpoint without distributed being initialized
        if dist.is_initialized():
            dist.barrier()