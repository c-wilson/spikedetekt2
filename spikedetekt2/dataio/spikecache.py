"""Object-oriented interface to an experiment's data."""

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
import os
import re
from itertools import chain
from collections import OrderedDict

import numpy as np
import pandas as pd
import tables as tb

from selection import select, slice_to_indices
from spikedetekt2.dataio.kwik import (get_filenames, open_files, close_files,
    add_spikes)
from spikedetekt2.dataio.utils import convert_dtype
from spikedetekt2.utils.six import (iteritems, string_types, iterkeys, 
    itervalues, next)
from spikedetekt2.utils.wrap import wrap

def _select(arr, indices):
    fm = np.empty((len(indices),) + arr.shape[1:], 
                              dtype=arr.dtype)
    for j, i in enumerate(indices):
        # fm[j:j+1,...] = arr[i:i+1,...]
        fm[j,...] = arr[i,...]
    return indices, fm

class SpikeCache(object):
    def __init__(self, spike_clusters=None, cache_fraction=1.,
                 # nspikes=None,
                 features_masks=None,
                 waveforms_raw=None,
                 waveforms_filtered=None):
        self.spike_clusters = spike_clusters[:]
        self.nspikes = len(self.spike_clusters)
        # self.cluster_sizes = np.bincount(spike_clusters)
        self.cache_fraction = cache_fraction
        self.features_masks = features_masks
        self.waveforms_raw = waveforms_raw
        self.waveforms_filtered = waveforms_filtered
        
        self.features_masks_cached = None
        self.cache_indices = None
        
        assert self.nspikes == len(self.spike_clusters)
        assert self.nspikes == self.features_masks.shape[0]
        if self.waveforms_raw is not None:
            assert self.nspikes == self.waveforms_raw.shape[0]
        assert self.nspikes == self.waveforms_filtered.shape[0]
        
        assert cache_fraction > 0
        
    def cache_features_masks(self, offset=0):
        k = np.clip(int(1. / self.cache_fraction), 1, self.nspikes)
        # Load and save subset in feature_masks.
        self.features_masks_cached = self.features_masks[offset::k,...]
        self.cache_indices = np.arange(self.nspikes)[offset::k,...]
        self.cache_size = len(self.cache_indices)
    
    def load_features_masks(self, fraction=None, clusters=None):
        """Load a subset of features & masks. 
        
        Arguments:
          * fraction: fraction of spikes to load from the cache.
          * clusters: if not None, load all features & masks of all spikes in 
            the selected clusters.
            
        """
        assert fraction is not None or clusters is not None
        
        # Cache susbet of features masks and save them in an array.
        if self.features_masks_cached is None:
            self.cache_features_masks()
        
        if clusters is None:
            offset = 0
            k = np.clip(int(1. / fraction), 1, self.cache_size)
            
            # Load and save subset from cache_feature_masks.
            loaded_features_masks = self.features_masks_cached[offset::k,...]
            loaded_indices = self.cache_indices[offset::k]
            return loaded_indices, loaded_features_masks
        else:
            # Find the indices of all spikes in the requested clusters
            indices = np.nonzero(np.in1d(self.spike_clusters, clusters))[0]
            arr = (self.features_masks_cached 
                   if self.cache_fraction == 1. else self.features_masks)
            return _select(arr, indices)
           
    def load_waveforms(self, clusters=None, count=10, filtered=True):
        """Load some waveforms from the requested clusters.
        
        Arguments:
          * clusters: list of clusters
          * count: max number of waveforms per cluster
          * filtered=True: whether to load filtered or raw waveforms
        
        """
        assert count > 0
        nclusters = len(clusters)
        indices = []
        for cluster in clusters:
            # Number of spikes to load for this cluster: count
            # but we want this number to be < cluster size, and > 10 if possible
            ind = np.nonzero(self.spike_clusters == cluster)[0]
            cluster_size = len(ind)
            if cluster_size == 0:
                continue
            nspikes = np.clip(count, min(cluster_size, 10),
                                     max(cluster_size, count))
            indices.append(ind[::len(ind)//nspikes])
        # indices now contains some spike indices from the requested clusters
        if len(indices) > 0:
            indices = np.hstack(indices)
        w = self.waveforms_filtered if filtered else self.waveforms_raw
        return _select(w, indices)
        
        
        
        