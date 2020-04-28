DEFAULTS = {
    'cuda': True,
    'batch_size': 64,
    'isc': False,
    'fid': False,
    'kid': False,
    'feature_extractor': 'inception-v3-compat',
    'feature_layer_isc': 'logits_unbiased',
    'feature_layer_fid': '2048',
    'feature_layer_kid': '2048',
    'feature_extractor_weights_path': None,
    'isc_splits': 10,
    'kid_subsets': 100,
    'kid_subset_size': 1000,
    'kid_degree': 3,
    'kid_gamma': None,
    'kid_coef0': 1,
    'samples_shuffle': True,
    'samples_find_deep': False,
    'samples_find_ext': 'png,jpg,jpeg',
    'samples_ext_lossy': 'jpg,jpeg',
    'datasets_root': None,
    'datasets_download': True,
    'cache_root': None,
    'cache': True,
    'cache_input1_name': None,
    'cache_input2_name': None,
    'rng_seed': 2020,
    'verbose': True,
}


def get_kwarg(name, kwargs):
    return kwargs.get(name, DEFAULTS[name])
