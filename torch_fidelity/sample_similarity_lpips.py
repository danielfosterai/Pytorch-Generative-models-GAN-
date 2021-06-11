# Adaptation of the following sources:
#   https://github.com/richzhang/PerceptualSimilarity/blob/master/lpips/pretrained_networks.py
#   https://github.com/richzhang/PerceptualSimilarity/blob/master/lpips/lpips.py
#   Distributed under BSD 2-Clause: https://github.com/richzhang/PerceptualSimilarity/blob/master/LICENSE
import sys
from contextlib import redirect_stdout

import torch
import torch.nn as nn
import torchvision
from torch.hub import load_state_dict_from_url

from torch_fidelity.helpers import vassert
from torch_fidelity.sample_similarity_base import SampleSimilarityBase

# VGG16 pretrained weights from torchvision models hub
#   Distributed under BSD 3-Clause: https://github.com/pytorch/vision/blob/master/LICENSE
#   Original weights distributed under CC-BY: https://www.robots.ox.ac.uk/~vgg/research/very_deep/
URL_VGG16_BASE = 'https://download.pytorch.org/models/vgg16-397923af.pth'

# VGG16 LPIPS original weights re-uploaded from the following location:
#   https://github.com/richzhang/PerceptualSimilarity/blob/master/lpips/weights/v0.1/vgg.pth
#   Distributed under BSD 2-Clause: https://github.com/richzhang/PerceptualSimilarity/blob/master/LICENSE
URL_VGG16_LPIPS = 'https://github.com/toshas/torch-fidelity/releases/download/v0.2.0/weights-vgg16-lpips.pth'


class VGG16features(torch.nn.Module):
    def __init__(self):
        super().__init__()
        vgg_pretrained_features = torchvision.models.vgg16(pretrained=False)
        with redirect_stdout(sys.stderr):
            vgg_pretrained_features.load_state_dict(load_state_dict_from_url(URL_VGG16_BASE))
        vgg_pretrained_features = vgg_pretrained_features.features
        self.slice1 = torch.nn.Sequential()
        self.slice2 = torch.nn.Sequential()
        self.slice3 = torch.nn.Sequential()
        self.slice4 = torch.nn.Sequential()
        self.slice5 = torch.nn.Sequential()
        self.N_slices = 5
        for x in range(4):
            self.slice1.add_module(str(x), vgg_pretrained_features[x])
        for x in range(4, 9):
            self.slice2.add_module(str(x), vgg_pretrained_features[x])
        for x in range(9, 16):
            self.slice3.add_module(str(x), vgg_pretrained_features[x])
        for x in range(16, 23):
            self.slice4.add_module(str(x), vgg_pretrained_features[x])
        for x in range(23, 30):
            self.slice5.add_module(str(x), vgg_pretrained_features[x])
        self.eval()
        for param in self.parameters():
            param.requires_grad = False

    def forward(self, X):
        h = self.slice1(X)
        h_relu1_2 = h
        h = self.slice2(h)
        h_relu2_2 = h
        h = self.slice3(h)
        h_relu3_3 = h
        h = self.slice4(h)
        h_relu4_3 = h
        h = self.slice5(h)
        h_relu5_3 = h
        return h_relu1_2, h_relu2_2, h_relu3_3, h_relu4_3, h_relu5_3


def spatial_average(in_tensor):
    return in_tensor.mean([2, 3]).squeeze(1)


def normalize_tensor(in_features, eps=1e-10):
    norm_factor = torch.sqrt(torch.sum(in_features ** 2, dim=1, keepdim=True))
    return in_features / (norm_factor + eps)


class NetLinLayer(nn.Module):
    def __init__(self, chn_in, chn_out=1, use_dropout=False):
        super(NetLinLayer, self).__init__()
        layers = [nn.Dropout(), ] if use_dropout else []
        layers += [nn.Conv2d(chn_in, chn_out, 1, stride=1, padding=0, bias=False), ]
        self.model = nn.Sequential(*layers)


class SampleSimilarityLPIPS(SampleSimilarityBase):
    SUPPORTED_DTYPES = {
        'uint8': torch.uint8,
        'float32': torch.float32,
    }

    def __init__(
            self,
            name,
            sample_similarity_resize=None,
            sample_similarity_dtype=None,
            **kwargs
    ):
        super(SampleSimilarityLPIPS, self).__init__(name)
        self.sample_similarity_resize = sample_similarity_resize
        self.sample_similarity_dtype = sample_similarity_dtype
        self.chns = [64, 128, 256, 512, 512]
        self.L = len(self.chns)
        self.lin0 = NetLinLayer(self.chns[0], use_dropout=True)
        self.lin1 = NetLinLayer(self.chns[1], use_dropout=True)
        self.lin2 = NetLinLayer(self.chns[2], use_dropout=True)
        self.lin3 = NetLinLayer(self.chns[3], use_dropout=True)
        self.lin4 = NetLinLayer(self.chns[4], use_dropout=True)
        self.lins = [self.lin0, self.lin1, self.lin2, self.lin3, self.lin4]
        with redirect_stdout(sys.stderr):
            state_dict = load_state_dict_from_url(URL_VGG16_LPIPS, map_location='cpu', progress=True)
        self.load_state_dict(state_dict)
        self.net = VGG16features()
        self.eval()
        for param in self.parameters():
            param.requires_grad = False

    @staticmethod
    def normalize(x):
        # torchvision values in range [0,1] mean = [0.485, 0.456, 0.406] and std = [0.229, 0.224, 0.225]
        mean_rescaled = (1 + torch.tensor([-.030, -.088, -.188], device=x.device)[None, :, None, None]) * 255 / 2
        inv_std_rescaled = 2 / (torch.tensor([.458, .448, .450], device=x.device)[None, :, None, None] * 255)
        x = (x.float() - mean_rescaled) * inv_std_rescaled
        return x

    @staticmethod
    def resize(x, size):
        if x.shape[-1] > size and x.shape[-2] > size:
            x = torch.nn.functional.interpolate(x, (size, size), mode='area')
        else:
            x = torch.nn.functional.interpolate(x, (size, size), mode='bilinear', align_corners=False)
        return x

    def forward(self, in0, in1):
        vassert(torch.is_tensor(in0) and torch.is_tensor(in1), 'Inputs must be torch tensors')
        vassert(in0.dim() == 4 and in0.shape[1] == 3, 'Input 0 is not Bx3xHxW')
        vassert(in1.dim() == 4 and in1.shape[1] == 3, 'Input 1 is not Bx3xHxW')
        if self.sample_similarity_dtype is not None:
            dtype = self.SUPPORTED_DTYPES.get(self.sample_similarity_dtype, None)
            vassert(dtype is not None and in0.dtype == dtype and in1.dtype == dtype,
                    f'Unexpected input dtype ({in0.dtype})')
        in0_input = self.normalize(in0)
        in1_input = self.normalize(in1)

        if self.sample_similarity_resize is not None:
            in0_input = self.resize(in0_input, self.sample_similarity_resize)
            in1_input = self.resize(in1_input, self.sample_similarity_resize)

        outs0 = self.net.forward(in0_input)
        outs1 = self.net.forward(in1_input)

        feats0, feats1, diffs = {}, {}, {}

        for kk in range(self.L):
            feats0[kk], feats1[kk] = normalize_tensor(outs0[kk]), normalize_tensor(outs1[kk])
            diffs[kk] = (feats0[kk] - feats1[kk]) ** 2

        res = [spatial_average(self.lins[kk].model(diffs[kk])) for kk in range(self.L)]
        val = sum(res)
        return val
