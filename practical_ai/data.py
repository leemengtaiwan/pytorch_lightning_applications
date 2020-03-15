# AUTOGENERATED! DO NOT EDIT! File to edit: notebooks/data.ipynb (unless otherwise specified).

__all__ = ['logger', 'get_data_root', 'build_dataset', 'build_data_loader']


# Cell
import os
import torch
import logging
from easydict import EasyDict as edict
from torchvision import datasets, transforms
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger()
logger.setLevel("INFO")


# Cell
def get_data_root(data_root=None):
    data_root = data_root if data_root else os.getenv("DATA_ROOT", ".")
    if not os.path.exists(data_root):
        os.makedirs(data_root)
    return data_root


# Cell
def build_dataset(dataset, split="full", size=None, transform=None, return_label=True,
                  **kwargs):

    dataset = dataset.lower()
    if dataset == "mnist":
        size = size if size else (28, 28)
        logging.info(f"MNIST will be resized to {size}.")

        transform = transforms.Compose([
            transforms.Resize(size=size),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5], std=[0.5])
        ]) if not transform else transform

        ds_params = dict(root=get_data_root(), transform=transform, download=True)
        if split == "train":
            ds_params['train'] = True
        elif split == "test":
            ds_params['train'] = False
        dataset = datasets.MNIST(**ds_params)

        if not return_label:
            dataset = ImageOnlyDataset(dataset)
        setattr(dataset, "shape", (*size, 1))
    else:
        raise NotImplementedError

    return dataset


# Cell
def build_data_loader(dataset, batch_size, shuffle=True, num_workers=4, collate_fn=None,
                       drop_last=True, pin_memory=False, **kwargs):

    data_loader = DataLoader(dataset, batch_size=batch_size, shuffle=shuffle,
                             num_workers=num_workers, collate_fn=collate_fn,
                             drop_last=drop_last, pin_memory=pin_memory)
    return data_loader