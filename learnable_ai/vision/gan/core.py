# AUTOGENERATED! DO NOT EDIT! File to edit: notebooks/vision.gan.core.ipynb (unless otherwise specified).

__all__ = ['logger', 'get_n_samplings', 'get_norm2d', 'get_activation', 'init_xavier_uniform', 'UpsampleConv2d',
           'UnsqueezeLatent', 'SqueezeLogit', 'DownsampleConv2d', 'ConvGenerator', 'ConvDiscriminator', 'get_generater',
           'get_discriminator', 'GAN']


# Cell
import torch
import logging
import functools
import torchvision
import pytorch_lightning as pl
from torch import nn
from dotenv import load_dotenv
from more_itertools import pairwise
from collections import OrderedDict
from ...layers import Identity
from ...data import get_dataset, get_dataloader
from .loss import get_adversarial_loss_fns
from .hparams import (
    # dataset
    DATASET,
    LATENT_DIM,
    DIM,
    CHANNELS,
    # architecture, loss
    GENERATOR_TYPE,
    DISCRIMINATOR_TYPE,
    ADVERSARIAL_LOSS_TYPE,
    NORM_TYPE,
    DIM_CHANNEL_MULTIPLIER,
    KERNEL_SIZE,
    # training
    BATCH_SIZE,
    LR,
    BETA1,
    BETA2,
)


_ = load_dotenv()
logger = logging.getLogger()
logger.setLevel("INFO")


# Cell
def get_n_samplings(dim):
    return int(torch.log2(torch.tensor(dim, dtype=torch.float32)).item()) - 2


# Cell
def get_norm2d(name):
    if name == "identity":
        return Identity
    elif name == "batch":
        return nn.BatchNorm2d
    elif name == "instance":
        return functools.partial(nn.InstanceNorm2d, affine=True)
    elif name == "layer":
        return lambda num_features: nn.GroupNorm(1, num_features)
    else:
        raise NotImplementedError


# Cell
def get_activation(name):
    if name == "relu":
        return nn.ReLU()
    elif name == "leaky_relu":
        return nn.LeakyReLU(0.2)
    elif name == "tanh":
        return nn.Tanh()
    else:
        raise NotImplementedError


# Cell
def init_xavier_uniform(layer):
    if hasattr(layer, "weight"):
        torch.nn.init.xavier_uniform_(layer.weight)
    if hasattr(layer, "bias"):
        if hasattr(layer.bias, "data"):
            layer.bias.data.fill_(0)


# Cell
class UpsampleConv2d(nn.Sequential):
    """基本上採樣： ConvTransponse2d -> Norm -> Activation"""

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size=KERNEL_SIZE,
                 stride=2,
                 padding=1,
                 norm_type="batch",
                 act="relu",
                 bias=True):

        # TODO: try unsample without convtranspose2d
        conv = nn.ConvTranspose2d(in_channels,
                                  out_channels,
                                  kernel_size,
                                  stride,
                                  padding,
                                  bias=bias)

        # FIXME: experimental
        spectral_norm = True
        conv = nn.utils.spectral_norm(conv)
        conv.apply(init_xavier_uniform)

        layers = [conv]

        if norm_type != "none":
#         if norm_type != "none" and not spectral_norm:  # FIXME: experimental
            layers.append(get_norm2d(norm_type)(out_channels))

        if act not in ["none", "linear"]:
            layers.append(get_activation(act))

        super().__init__(*layers)


# Cell
class UnsqueezeLatent(nn.Module):
    """將 latent vector unsqueeze"""
    def forward(self, x):
        return x[..., None, None]


# Cell
class SqueezeLogit(nn.Module):
    """Squeeze Discriminator logit"""
    def forward(self, x):
        return x.squeeze(-1).squeeze(-1)


# Cell
class DownsampleConv2d(nn.Sequential):
    """基本下採樣： Conv2d -> Norm -> Activation"""

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size=KERNEL_SIZE,
                 stride=2,
                 padding=1,
                 norm_type="batch",
                 act="leaky_relu",
                 bias=True,
                 spectral_norm=False):

        conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding, bias=bias)
        if spectral_norm:
            conv = nn.utils.spectral_norm(conv)
            conv.apply(init_xavier_uniform)

        layers = [conv]
        if norm_type != "none" and not spectral_norm:
            layers.append(get_norm2d(norm_type)(out_channels))

        layers.append(get_activation(act))
        super().__init__(*layers)


# Cell
class ConvGenerator(nn.Sequential):
    """將特定維度的潛在向量上採樣到指定圖片大小的生成器"""

    def __init__(self,
                 latent_dim=LATENT_DIM,
                 out_dim=DIM,
                 out_channels=CHANNELS,
                 kernel_size=KERNEL_SIZE,
                 max_channels=None,
                 norm_type=NORM_TYPE,
                 act="relu",
                 dim_channel_multiplier=DIM_CHANNEL_MULTIPLIER):
        self.latent_dim = latent_dim
        self.out_dim = out_dim
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.dim_channel_multiplier = dim_channel_multiplier
        self.norm_type = norm_type
        self.act = act
        self.max_channels = max_channels if max_channels else self.out_dim * self.dim_channel_multiplier

        # decide appropriate number of upsampling process based on expected output image shape
        self.n_upsamples = get_n_samplings(self.out_dim)

        # projected to spatial extent convolutional repr. with feature maps
        # x.shape == (batch_size, latent_dim)
        layers = [
            UnsqueezeLatent(),
            UpsampleConv2d(in_channels=self.latent_dim,
                           out_channels=self.max_channels,
                           kernel_size=self.kernel_size,
                           stride=1,  # no need to stride in first layer
                           padding=0,  # no padding in first layer
                           norm_type=self.norm_type,
                           act=self.act)]

        # upsamples
        # x.shape == (batch_size, max_channels, kernel_size, kernel_size)
        chs = [self.max_channels // (2 ** i) for i in range(self.n_upsamples)]
        chs.append(self.out_channels)

        layers.extend([
            UpsampleConv2d(in_channels=in_ch,
                           out_channels=out_ch,
                           kernel_size=self.kernel_size,
                           stride=2,
                           norm_type=self.norm_type if i != self.n_upsamples else "none",
                           act=self.act if i != self.n_upsamples else "tanh",
                           bias=False if i != self.n_upsamples else True)
         for i, (in_ch, out_ch) in enumerate(pairwise(chs), 1)])
        # out.shape == (batch_size, out_channels, out_dim, out_dim)

        # final act: tanh
        # using a bounded activation allowed the model to learn more quickly to
        # saturate and cover the color space of the training distribution.

        super().__init__(*layers)


# Cell
class ConvDiscriminator(nn.Sequential):
    """將特定大小圖片下採樣的辨識器"""

    def __init__(self,
                 in_channels=CHANNELS,
                 in_dim=DIM,
                 norm_type=NORM_TYPE,
                 kernel_size=KERNEL_SIZE,
                 max_channels=None,
                 dim_channel_multiplier=DIM_CHANNEL_MULTIPLIER,
                 spectral_norm=False):
        self.in_channels = in_channels
        self.in_dim = in_dim
        self.norm_type = norm_type
        self.kernel_size = kernel_size
        self.n_downsamples = get_n_samplings(self.in_dim)
        self.dim_channel_multiplier = dim_channel_multiplier
        self.spectral_norm = spectral_norm
        self.max_channels = max_channels if max_channels else self.in_dim * self.dim_channel_multiplier

        # downsample
        chs = [self.in_channels]
        chs += sorted([self.max_channels // (2 ** i) for i in range(self.n_downsamples)])

        # x.shape == (batch_size, in_channels, in_dim, in_dim)
        layers = [
            DownsampleConv2d(in_ch,
                             out_ch,
                             self.kernel_size,
                             stride=2,
                             norm_type=self.norm_type if i != 1 else "none",
                             bias=False if i != 1 else True,
                             spectral_norm=self.spectral_norm)
            for i, (in_ch, out_ch) in enumerate(pairwise(chs), 1)]

        # compute logits
        # x.shape == (batch_size, max_channels, kernel_size, kernel_size)
        final_conv = nn.Conv2d(chs[-1], 1, kernel_size=self.kernel_size)
        if self.spectral_norm:
            final_conv = nn.utils.spectral_norm(final_conv)
            final_conv.apply(init_xavier_uniform)

        layers.extend([
            final_conv,
            SqueezeLogit()
        ])
        # out.shape == (batch_size, 1)

        super().__init__(*layers)


# Cell
def get_generater(_type):
    if _type == "conv":
        return ConvGenerator
    else:
        raise NotImplementedError

def get_discriminator(_type):
    if _type == "conv":
        return ConvDiscriminator
    else:
        raise NotImplementedError


# Cell
class GAN(pl.LightningModule):
    """對抗生成網路"""

    def __init__(self, hparams):
        super(GAN, self).__init__()
        self.hparams = hparams

        # adversarial losses
        self.g_loss_fn, self.d_loss_fn = \
            get_adversarial_loss_fns(self.hparams.adversarial_loss_type)

        # infer image size by dataset



        # initialize networks
        g = get_generater(self.hparams.generator_type)
        self.generator = g(latent_dim=self.hparams.latent_dim,
                           out_dim=self.hparams.dim,
                           out_channels=self.hparams.channels,
                           kernel_size=self.hparams.kernel_size,
                           norm_type=self.hparams.norm_type)

        d = get_discriminator(self.hparams.discriminator_type)
        self.discriminator = d(in_channels=self.hparams.channels,
                               in_dim=self.hparams.dim,
                               norm_type=self.hparams.norm_type,
                               kernel_size=self.hparams.kernel_size,
                               spectral_norm=self.hparams.discriminator_spectral_norm)

        # cache for generated images
        self.generated_images = None
        self.last_real_images = None

    def prepare_data(self):
        self.train_dataset = get_dataset(dataset_name=self.hparams.dataset,
                                         split="train",
                                         size=(self.hparams.dim, self.hparams.dim),
                                         return_label=False)

        self.valid_dataset = get_dataset(dataset_name=self.hparams.dataset,
                                         split="valid",
                                         size=(self.hparams.dim, self.hparams.dim),
                                         return_label=False)

    def train_dataloader(self):
        return get_dataloader(self.train_dataset, batch_size=self.hparams.batch_size)

    def configure_optimizers(self):
        self.g_optim = torch.optim.Adam(self.generator.parameters(),
                                        lr=self.hparams.lr,
                                        betas=(self.hparams.beta1, self.hparams.beta2))
        self.d_optim = torch.optim.Adam(self.discriminator.parameters(),
                                        lr=self.hparams.lr,
                                        betas=(self.hparams.beta1, self.hparams.beta2))
        return [self.d_optim, self.g_optim], []

    def get_latent_vectors(self, n, on_gpu=True):
        z = torch.randn(n, self.hparams.latent_dim)
        if on_gpu:
            z = z.cuda(self.last_real_images.device.index)
        return z

    def training_step(self, batch, batch_idx, optimizer_idx):
        self.last_real_images = real_images = batch
        z = self.get_latent_vectors(n=self.hparams.batch_size, on_gpu=self.on_gpu)

        # discriminator's turn
        if optimizer_idx == 0:
            fake_images = self.generator(z).detach()
            real_logits = self.discriminator(real_images)
            fake_logits = self.discriminator(fake_images)

            d_real_loss, d_fake_loss = self.d_loss_fn(real_logits, fake_logits,
                                                      on_gpu=self.on_gpu)
            d_loss = d_real_loss + d_fake_loss

            # TODO: gradient penality

            tqdm_dict = {'d_loss': d_loss}
            output = OrderedDict({
                'loss': d_loss,
                'progress_bar': tqdm_dict,
                'log': tqdm_dict
            })
            return output

        # generator's turn
        if optimizer_idx == 1:
            # clip discriminator's weight if required
            clip_value = self.hparams.discriminator_weight_clip_value
            if clip_value:
                for p in self.discriminator.parameters():
                    p.data.clamp_(-clip_value, clip_value)

            # genererator forward
            fake_images = self.generateed_images = self.generator(z)
            fake_logits = self.discriminator(fake_images)
            g_loss = self.g_loss_fn(fake_logits)

            tqdm_dict = {'g_loss': g_loss}
            output = OrderedDict({
                'loss': g_loss,
                'progress_bar': tqdm_dict,
                'log': tqdm_dict
            })
            return output

    def forward(self, z):
        return self.generator(z)

#     def on_train_start(self):
#         # https://github.com/PyTorchLightning/pytorch-lightning/blob/af621f8590b2f2ba046b508da2619cfd4995d876/pytorch_lightning/core/hooks.py#L45-L49
#         # https://pytorch.org/docs/stable/tensorboard.html#torch.utils.tensorboard.writer.SummaryWriter.add_hparams
#         hparam_dict = {}
#         metric_dict = {}
#         self.logger.experiment.add_hparams({'lr': 0.1*i, 'bsize': i},{})

    def on_epoch_end(self):
        z = self.get_latent_vectors(n=64, on_gpu=self.on_gpu)
        sample_images = self.generator(z).clamp(0.0, 1.0)
        grid = torchvision.utils.make_grid(sample_images)
        self.logger.experiment.add_image('sample_images', grid, self.current_epoch)