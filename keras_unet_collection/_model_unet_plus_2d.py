
from __future__ import absolute_import

from keras_unet_collection.layer_utils import *
from keras_unet_collection.activations import GELU, Snake

from tensorflow.keras.layers import Input, Conv2D
from tensorflow.keras.layers import BatchNormalization, Activation, concatenate, multiply
from tensorflow.keras.layers import ReLU, LeakyReLU, PReLU, ELU
from tensorflow.keras.models import Model

def unet_plus_2d_backbone(input_tensor, filter_num, stack_num_down=2, stack_num_up=2,
                          activation='ReLU', batch_norm=False, pool=True, unpool=True, 
                          deep_supervision=False, name='xnet'):
    '''
    The backbone of U-net++
    
    unet_plus_2d_backbone(input_tensor, filter_num, stack_num_down=2, stack_num_up=2,
                          activation='ReLU', batch_norm=False, pool=True, unpool=True, 
                          deep_supervision=False, name='xnet')
    
    ----------
    Zhou, Z., Siddiquee, M.M.R., Tajbakhsh, N. and Liang, J., 2018. Unet++: A nested u-net architecture 
    for medical image segmentation. In Deep Learning in Medical Image Analysis and Multimodal Learning 
    for Clinical Decision Support (pp. 3-11). Springer, Cham.
    
    Input
    ----------
        input_tensor: the input tensor of the backbone, e.g., keras.layers.Inpyt((None, None, 3))
        filter_num: an iterable that defines the number of filters for each \
                      down- and upsampling level. E.g., [64, 128, 256, 512]
                      the depth is expected as `len(filter_num)`
        stack_num_down: number of convolutional layers per downsampling level/block. 
        stack_num_up: number of convolutional layers (after concatenation) per upsampling level/block.
        activation: one of the `tensorflow.keras.layers` or `keras_unet_collection.activations` interfaces, e.g., ReLU
        batch_norm: True for batch normalization.
        pool: True for maxpooling, False for strided convolutional layers.
        unpool: True for unpooling (i.e., reflective padding), False for transpose convolutional layers.
        deep_supervision: True for a model that supports deep supervision. Details see Zhou et al. (2018).
        name: prefix of the created keras layers.
        
    Output
    ----------
        If deep_supervision = False; Then the output is a tensor.
        If deep_supervision = True; Then the output is a list of tensors 
            with the first tensor obtained from the first downsampling level (for checking the input/output shapes only),
            the second to the `depth-1`-th tensors obtained from each intermediate upsampling levels (deep supervision tensors),
            and the last tensor obtained from the end of the backbone.
    
    '''
    
    depth_ = len(filter_num)
    
    X = input_tensor
    
    # allocate nested lists for collecting output tensors 
    X_nest_skip = [[] for _ in range(depth_)] 
    
    # downsampling blocks (same as in 'unet_2d')
    X = CONV_stack(X, filter_num[0], stack_num=stack_num_down, activation=activation, 
                   batch_norm=batch_norm, name='{}_down0'.format(name))
    X_nest_skip[0].append(X)
    for i, f in enumerate(filter_num[1:]):
        X = UNET_left(X, f, stack_num=stack_num_down, activation=activation, 
                      pool=pool, batch_norm=batch_norm, name='{}_down{}'.format(name, i+1))        
        X_nest_skip[0].append(X)
    
    for nest_lev in range(1, depth_):
        
        # subset filter numbers to the current upsampling level
        filter_num_sub = filter_num[:(depth_-nest_lev)]
        
        # loop over individual upsamling levels
        for i, f in enumerate(filter_num_sub[::-1]):
            
            # collecting previous downsampling outputs
            previous_skip = []
            for previous_lev in range(nest_lev):
                previous_skip.append(X_nest_skip[previous_lev][i])
                
            # upsamping block that concatenates all available (same feature map size) down-/upsampling outputs
            X_nest_skip[nest_lev].append(
                UNET_right(X_nest_skip[nest_lev-1][i+1], previous_skip, filter_num[i], 
                           stack_num=stack_num_up, activation=activation, name='xnet_{}{}'.format(nest_lev, i)))
            
    # output
    if deep_supervision:
        
        X_list = []
        
        for i in range(depth_):
            X_list.append(X_nest_skip[i][0])
        
        return X_list
        
    else:
        return X_nest_skip[-1][0]

def unet_plus_2d(input_size, filter_num, n_labels,
                 stack_num_down=2, stack_num_up=2,
                 activation='ReLU', output_activation='Softmax', 
                 batch_norm=False, pool=True, unpool=True, deep_supervision=False, name='xnet'):
    '''
    U-net++
    
    unet_plus_2d(input_size, filter_num, n_labels,
                 stack_num_down=2, stack_num_up=2,
                 activation='ReLU', output_activation='Softmax', 
                 batch_norm=False, pool=True, unpool=True, deep_supervision=False, name='xnet')
    
    ----------
    Zhou, Z., Siddiquee, M.M.R., Tajbakhsh, N. and Liang, J., 2018. Unet++: A nested u-net architecture 
    for medical image segmentation. In Deep Learning in Medical Image Analysis and Multimodal Learning 
    for Clinical Decision Support (pp. 3-11). Springer, Cham.
    
    Input
    ----------
        input_size: a tuple that defines the shape of input, e.g., (None, None, 3)
        filter_num: an iterable that defines the number of filters for each
                    down- and upsampling level. E.g., [64, 128, 256, 512]
                    the depth is expected as `len(filter_num)`
        n_labels: number of output labels.
        stack_num_down: number of convolutional layers per downsampling level/block. 
        stack_num_up: number of convolutional layers (after concatenation) per upsampling level/block.
        activation: one of the `tensorflow.keras.layers` or `keras_unet_collection.activations` interfaces, e.g., ReLU
        output_activation: one of the `tensorflow.keras.layers` or `keras_unet_collection.activations` interfaces or 'Sigmoid'.
                           Default option is Softmax
                           if None is received, then linear activation is applied.
        batch_norm: True for batch normalization.
        pool: True for maxpooling, False for strided convolutional layers.
        unpool: True for unpooling (i.e., reflective padding), False for transpose convolutional layers.
        deep_supervision: True for a model that supports deep supervision. Details see Zhou et al. (2018).
        name: prefix of the created keras layers.
        
    Output
    ----------
        model: a keras model 
    
    '''
    
    depth_ = len(filter_num)
    
    IN = Input(input_size)
    
    # backbone
    X = unet_plus_2d_backbone(IN, filter_num, stack_num_down=stack_num_down, stack_num_up=stack_num_up,
                              activation=activation, batch_norm=batch_norm, pool=pool, unpool=unpool, 
                              deep_supervision=deep_supervision, name=name)
    
    # output
    if deep_supervision:
        
        # backbone returns a list of tensors
        X_list = X
        OUT_list = []
        
        print('----------\ndeep_supervision = True\nnames of output tensors are listed as follows (the last one is the final output):')
        
        # depth_ > 2 is expected (a least two downsampling blocks)
        for i in range(1, depth_-1):
            
            print('\t{}_output_sup{}'.format(name, i))
            OUT_list.append(CONV_output(X_list[i], n_labels, kernel_size=1, activation=output_activation, 
                                        name='{}_output_sup{}'.format(name, i)))
        
        print('\t{}_output_final'.format(name))
        OUT_list.append(CONV_output(X_list[-1], n_labels, kernel_size=1, activation=output_activation, name='{}_output'.format(name)))
        
    else:
        OUT = CONV_output(X, n_labels, kernel_size=1, activation=output_activation, name='{}_output'.format(name))
        OUT_list = [OUT,]
        
    # model
    model = Model(inputs=[IN,], outputs=OUT_list, name='{}_model'.format(name))
    
    return model
