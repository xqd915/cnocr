# coding: utf-8
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""From DenseNet in Gluon.
  from gluoncv.model_zoo.densenet import DenseNet
"""
import logging
from mxnet.gluon.block import HybridBlock
from mxnet.gluon import nn
from mxnet.gluon.contrib.nn import HybridConcurrent, Identity


logger = logging.getLogger(__name__)


def cal_num_params(net):
    import numpy as np
    params = [p for p in net.collect_params().values()]
    for p in params:
        logger.info(p)
    total = sum([np.prod(p.shape) for p in params])
    logger.info('total params: %d' % total)
    return total


# Helpers
def _make_dense_block(num_layers, bn_size, growth_rate, dropout, stage_index):
    out = nn.HybridSequential(prefix='stage%d_' % stage_index)
    with out.name_scope():
        for _ in range(num_layers):
            out.add(_make_dense_layer(growth_rate, bn_size, dropout))
    return out


def _make_dense_layer(growth_rate, bn_size, dropout):
    """Convolutional(1x1) --> Convolutional(3x3)"""
    new_features = nn.HybridSequential(prefix='')
    new_features.add(nn.BatchNorm())
    new_features.add(nn.Activation('relu'))
    new_features.add(nn.Conv2D(bn_size * growth_rate, kernel_size=1, use_bias=False))
    new_features.add(nn.BatchNorm())
    new_features.add(nn.Activation('relu'))
    new_features.add(nn.Conv2D(growth_rate, kernel_size=3, padding=1, use_bias=False))
    if dropout:
        new_features.add(nn.Dropout(dropout))

    out = _make_residual(new_features)
    return out


def _make_residual(cell_net):
    out = HybridConcurrent(axis=1, prefix='')
    # 把原始的channels加进来，所以最终 out_channel = in_channel + net.out_channel
    out.add(Identity())
    out.add(cell_net)
    return out


def _make_transition(num_output_features, strides=2):
    out = nn.HybridSequential(prefix='')
    out.add(nn.BatchNorm())
    out.add(nn.Activation('relu'))
    out.add(nn.Conv2D(num_output_features, kernel_size=1, use_bias=False))
    out.add(nn.MaxPool2D(pool_size=2, strides=strides))
    return out


class DenseNet(HybridBlock):
    r"""Densenet-BC model from the
    `"Densely Connected Convolutional Networks" <https://arxiv.org/pdf/1608.06993.pdf>`_ paper.

    Parameters
    ----------
    num_init_features : int
        Number of filters to learn in the first convolution layer.
    growth_rate : int
        Number of filters to add each layer (`k` in the paper).
    block_config : list of int
        List of integers for numbers of layers in each pooling block.
    bn_size : int, default 4
        Multiplicative factor for number of bottle neck layers.
        (i.e. bn_size * k features in the bottleneck layer)
    dropout : float, default 0
        Rate of dropout after each dense layer.
    classes : int, default 1000
        Number of classification classes.
    """
    def __init__(self, layer_channels, **kwargs):
        assert len(layer_channels) == 4
        super(DenseNet, self).__init__(**kwargs)
        with self.name_scope():
            # Stage 0
            self.features = nn.HybridSequential(prefix='')
            self.features.add(_make_first_stage_net((layer_channels[0], layer_channels[1])))
            self.features.add(_make_transition(layer_channels[1]))
            # self.features.add(nn.Conv2D(num_init_features, kernel_size=3,
            #                             strides=1, padding=1, use_bias=False))
            # self.features.add(nn.BatchNorm())
            # self.features.add(nn.Activation('relu'))
            # self.features.add(nn.MaxPool2D(pool_size=2, strides=2))
            # Add dense blocks

            # Stage 1
            self.features.add(_make_inter_stage_net(1, num_layers=2, growth_rate=layer_channels[0]))
            self.features.add(_make_transition(layer_channels[2]))

            # Stage 2
            self.features.add(_make_inter_stage_net(2, num_layers=2, growth_rate=layer_channels[1]))
            self.features.add(_make_transition(layer_channels[3], strides=(2, 1)))
            # self.features.add(nn.MaxPool2D(pool_size=2, strides=(2, 1)))
            # self.features.add(_make_transition(512))

            # Stage 3
            self.features.add(_make_final_stage_net(3, out_channels=layer_channels[3]))

            # num_features = num_init_features
            # for i, num_layers in enumerate(block_config):
            #     self.features.add(_make_dense_block(num_layers, bn_size, growth_rate, dropout, i+1))
            #     num_features = num_features + num_layers * growth_rate
            #     if i != len(block_config) - 1:
            #         self.features.add(_make_transition(num_features // 2))
            #         num_features = num_features // 2
            # self.features.add(nn.BatchNorm())
            # self.features.add(nn.Activation('relu'))
            # self.features.add(nn.AvgPool2D(pool_size=7))
            # self.features.add(nn.Flatten())

            # self.output = nn.Dense(classes)

    def hybrid_forward(self, F, x):
        x = self.features(x)
        # x = self.output(x)
        return x


def _make_first_stage_net(out_channels):
    features = nn.HybridSequential(prefix='stage%d_' % 0)
    with features.name_scope():
        features.add(nn.Conv2D(out_channels[0], kernel_size=3,
                               strides=1, padding=1, use_bias=False))
        features.add(nn.BatchNorm())
        features.add(nn.Activation('relu'))
        features.add(nn.Conv2D(out_channels[1], kernel_size=3,
                               strides=1, padding=1, use_bias=False))
        # features.add(nn.BatchNorm())
        # features.add(nn.Activation('relu'))
    return _make_residual(features)


def _make_inter_stage_net(stage_index, num_layers=2, growth_rate=128):
    return _make_dense_block(num_layers, bn_size=2, growth_rate=growth_rate, dropout=0.0, stage_index=stage_index)


def _make_final_stage_net(stage_index, out_channels):
    features = nn.HybridSequential(prefix='stage%d_' % stage_index)
    with features.name_scope():
        features.add(nn.BatchNorm())
        features.add(nn.Activation('relu'))
        features.add(nn.Conv2D(out_channels // 4, kernel_size=1, use_bias=False))
        features.add(nn.BatchNorm())
        features.add(nn.Activation('relu'))
        features.add(nn.Conv2D(out_channels, kernel_size=(4, 1), use_bias=False))
        features.add(nn.BatchNorm())
        features.add(nn.Activation('relu'))
    return features
