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
    add_spikes, add_cluster)
from spikedetekt2.dataio.utils import convert_dtype
from spikedetekt2.dataio.spikecache import SpikeCache
from spikedetekt2.utils.six import (iteritems, string_types, iterkeys, 
    itervalues, next)
from spikedetekt2.utils.wrap import wrap

# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def _resolve_hdf5_path(files, path):
    """Resolve a HDF5 external link. Return the referred node (group or 
    dataset), or None if it does not exist.
    
    Arguments:
      * files: a dict {type: file_handle}.
      * path: a string like "{type}/path/to/node" where `type` is one of
        `kwx`, `raw.kwd`, etc.
      
    """  
    nodes = path.split('/')
    path_ext = '/' + '/'.join(nodes[1:])
    type = nodes[0]
    pattern = r'\{([a-zA-Z\._]+)\}'
    assert re.match(pattern, type)
    r = re.search(pattern, type)
    assert r
    type = r.group(1)
    # Resolve the link.
    file = files.get(type, None)
    if file:
        return file.getNode(path_ext)
    else:
        return None
    
def _get_child_id(child):
    id = child._v_name
    if id.isdigit():
        return int(id)
    else:
        return id

def _print_instance(obj, depth=0, name=''):
    # Handle the first element of the list/dict.
    if isinstance(obj, (list, dict)):
        if not obj:
            r = []
            return r
        if isinstance(obj, list):
            sobj = obj[0]
            key = '0'
        elif isinstance(obj, dict):
            key, sobj = next(iteritems(obj))
        if isinstance(sobj, (list, dict, int, long, string_types, np.ndarray, 
                      float)):
            r = []
        else:
            r = [(depth+1, str(key))] + _print_instance(sobj, depth+1)
    # Arrays do not have children.
    elif isinstance(obj, (np.ndarray, tb.EArray)):
        r = []
    # Handle class instances.
    elif hasattr(obj, '__dict__'):
        fields = {k: v 
            for k, v in iteritems(vars(obj)) 
                if not k.startswith('_')}
        r = list(chain(*[_print_instance(fields[n], depth=depth+1, name=str(n)) 
                for n in sorted(iterkeys(fields))]))
    else:
        r = []
    # Add the current object's display string.
    if name:
        if isinstance(obj, tb.EArray):
            s = name + ' [{dtype} {shape}]'.format(dtype=obj.dtype, 
                shape=obj.shape)
        else:
            s = name
        r = [(depth, s)] + r
    return r

class ArrayProxy(object):
    """Proxy to a view of an array."""
    def __init__(self, arr, col=None):
        self._arr = arr
        self._col = col
    
    @property
    def shape(self):
        return self._arr.shape[:-1]
    
    def __getitem__(self, item):
        if self._col is None:
            return self._arr[item]
        else:
            if isinstance(item, tuple):
                item += (self._col,)
                return self._arr[item]
            else:
                return self._arr[item, ..., self._col]
        
        
# -----------------------------------------------------------------------------
# Node wrappers
# -----------------------------------------------------------------------------
class Node(object):
    def __init__(self, files, node=None, root=None):
        self._files = files
        self._kwik = self._files.get('kwik', None)
        assert self._kwik is not None
        if node is None:
            node = self._kwik.root
        self._node = node
        self._root = root
        
    def _gen_children(self, container_name=None, child_class=None):
        """Return a dictionary {child_id: child_instance}."""
        # The container with the children is either the current node, or
        # a child of this node.
        if container_name is None:
            container = self._node
        else:
            container = self._node._f_getChild(container_name)
        return OrderedDict([
            (_get_child_id(child), child_class(self._files, child, root=self._root))
                for child in container
            ])
    
    def _get_child(self, child_name):
        """Return the child specified by its name.
        If this child has a `hdf5_path` special, then the path is resolved,
        and the referred child in another file is returned.
        """
        child = self._node._f_getChild(child_name)
        try:
            # There's a link that needs to be resolved: return it.
            path = child._f_getAttr('hdf5_path')
            return _resolve_hdf5_path(self._files, path)
        except AttributeError:
            # No HDF5 external link: just return the normal child.
            return child

class NodeWrapper(object):
    """Like a PyTables node, but supports in addition: `node.attr`."""
    def __init__(self, node):
        self._node = node
        
    def __getitem__(self, key):
        return self._node[key]
        
    def __getattr__(self, key):
        # Do not override if key is an attribute of this class.
        if key.startswith('_'):
            try:
                return self.__dict__[key]
            # Accept nodewrapper._method if _method is a method of the PyTables
            # Node object.
            except KeyError:
                return getattr(self._node, key)
        try:
            # Return the wrapped node if the child is a group.
            attr = getattr(self._node, key)
            if isinstance(attr, tb.Group):
                return NodeWrapper(attr)
            else:
                return attr
        # Return the attribute.
        except:
            try:
                return self._node._f_getAttr(key)
            except AttributeError:
                warn(("{key} needs to be an attribute of "
                     "{node}").format(key=key, node=self._node._v_name))
                return None
            
    def __setattr__(self, key, value):
        if key.startswith('_'):
            self.__dict__[key] = value
            return
        # Ensure the key is an existing attribute to the current node.
        try:
            self._node._f_getAttr(key)
        except AttributeError:
            raise "{key} needs to be an attribute of {node}".format(
                key=key, node=self._node._v_name)
        # Set the attribute.
        self._node._f_setAttr(key, value)
            
    def __dir__(self):
        return sorted(dir(self._node) + self._node._v_attrs._v_attrnames)
        
    def __repr__(self):
        return self._node.__repr__()

class DictVectorizer(object):
    """This object serves as a vectorized proxy for a dictionary of objects 
    that have individual fields of interest. For example: d={k: obj.attr1}.
    The object dv = DictVectorizer(d, 'attr1.subattr') can be used as:
    
        dv[3]
        dv[[1,2,5]]
        dv[2:4]
    
    """
    def __init__(self, dict, path):
        self._dict = dict
        self._path = path.split('.')
        
    def keys(self):
        return self._dict.keys()
        
    def values(self):
        return self._dict.values()
        
    def _get_path(self, key):
        """Resolve the path recursively for a given key of the dictionary."""
        val = self._dict[key]
        for p in self._path:
            val = getattr(val, p)
        return val
        
    def _set_path(self, key, value):
        """Resolve the path recursively for a given key of the dictionary,
        and set a value."""
        val = self._dict[key]
        for p in self._path[:-1]:
            val = getattr(val, p)
        setattr(val, key, value)
        
    def __getitem__(self, item):
        if isinstance(item, slice):
            item = slice_to_indices(item, lenindices=len(self._dict), 
                                    keys=sorted(self._dict.keys()))
        if hasattr(item, '__len__'):
            return np.array([self._get_path(k) for k in item])
        else:
            return self._get_path(item)
            
    def __setitem__(self, item, value):
        if key.startswith('_'):
            self.__dict__[key] = value
            return
        if isinstance(item, slice):
            item = slice_to_indices(item, lenindices=len(self._dict))
        if hasattr(item, '__len__'):
            if not hasattr(value, '__len__'):
                value = [value] * len(item)
            for k, val in zip(item, value):
                self._set_path(k, value)
        else:
            return self._set_path(item, value)
        

# -----------------------------------------------------------------------------
# Experiment class and sub-classes.
# -----------------------------------------------------------------------------
class Experiment(Node):
    """An Experiment instance holds all information related to an
    experiment. One can access any information using a logical structure
    that is somewhat independent from the physical representation on disk.
    """
    def __init__(self, name=None, dir=None, files=None, mode='r', prm={}):
        """`name` must correspond to the basename of the files."""
        self.name = name
        self._dir = dir
        self._mode = mode
        self._files = files
        self._prm = prm
        if self._files is None:
            self._files = open_files(self.name, dir=self._dir, mode=self._mode)
        def _get_filename(file):
            if file is None:
                return None
            else:
                return os.path.realpath(file.filename)
        self._filenames = {type: _get_filename(file)
            for type, file in iteritems(self._files)}
        super(Experiment, self).__init__(self._files)
        self._root = self._node
        
        self.application_data = NodeWrapper(self._root.application_data)
        self.user_data = NodeWrapper(self._root.user_data)
        
        self.channel_groups = self._gen_children('channel_groups', ChannelGroup)
        self.recordings = self._gen_children('recordings', Recording)
        self.event_types = self._gen_children('event_types', EventType)

        # Initialize the spike cache of the first channel group.
        self.channel_groups.itervalues().next().spikes.init_cache()
        
    def gen_filename(self, extension):
        if extension.startswith('.'):
            extension = extension[1:]
        return os.path.splitext(self._filenames['kwik'])[0] + '.' + extension
        
    def __enter__(self):
        return self
    
    def close(self):
        if self._files is not None:
            close_files(self._files)
    
    def __repr__(self):
        n = "<Experiment '{name}'>".format(name=self.name)
        l = _print_instance(self, name=n)
        # print l
        return '\n'.join('    '*d + s for d, s in l)
    
    def __exit__ (self, type, value, tb):
        self.close()
        
class ChannelGroup(Node):
    def __init__(self, files, node=None, root=None):
        super(ChannelGroup, self).__init__(files, node, root=root)
        
        self.name = self._node._v_attrs.name
        self.adjacency_graph = self._node._v_attrs.adjacency_graph
        self.application_data = NodeWrapper(self._node.application_data)
        self.user_data = NodeWrapper(self._node.user_data)
        
        self.channels = self._gen_children('channels', Channel)
        self.clusters = ClustersNode(self._files, self._node.clusters, root=self._root)
        self.cluster_groups = ClusterGroupsNode(self._files, self._node.cluster_groups, root=self._root)
        
        self.spikes = Spikes(self._files, self._node.spikes, root=self._root)
        
class Spikes(Node):
    def __init__(self, files, node=None, root=None):
        super(Spikes, self).__init__(files, node, root=root)
        
        self.time_samples = self._node.time_samples
        self.time_fractional = self._node.time_fractional
        self.recording = self._node.recording
        self.clusters = Clusters(self._files, self._node.clusters, root=self._root)
        
        # Get large datasets, that may be in external files.
        self.features_masks = self._get_child('features_masks')
        self.waveforms_raw = self._get_child('waveforms_raw')
        self.waveforms_filtered = self._get_child('waveforms_filtered')
        
        self.nsamples, self.nchannels = self.waveforms_raw.shape[1:]
        self.features = ArrayProxy(self.features_masks, col=0)
        self.nfeatures = self.features.shape[1]
        self.masks = ArrayProxy(self.features_masks, col=1)
       
    def add(self, **kwargs):
        """Add a spike. Only `time_samples` is mandatory."""
        add_spikes(self._files, **kwargs)
    
    def init_cache(self):
        """Initialize the cache for the features & masks."""
        self._spikecache = SpikeCache(
            # TODO: handle multiple clusterings in the spike cache here
            spike_clusters=self.clusters.main[:], 
            features_masks=self.features_masks,
            waveforms_raw=self.waveforms_raw,
            waveforms_filtered=self.waveforms_filtered,
            # TODO: put this value in the parameters
            cache_fraction=1.,)
    
    def load_features_masks(self, *args, **kwargs):
        return self._spikecache.load_features_masks(*args, **kwargs)
    
    def load_waveforms(self, *args, **kwargs):
        return self._spikecache.load_waveforms(*args, **kwargs)
    
    def __getitem__(self, item):
        raise NotImplementedError("""It is not possible to select entire spikes 
            yet.""")
            
    def __len__(self):
        return self.time_samples.shape[0]
        
class Clusters(Node):
    """The parent of main, original, etc. Contains multiple clusterings."""
    def __init__(self, files, node=None, root=None):
        super(Clusters, self).__init__(files, node, root=root)        
        # Each child of the Clusters group is assigned here.
        for node in self._node._f_iterNodes():
            setattr(self, node._v_name, node)
        
class Clustering(Node):
    """An actual clustering, with the cluster numbers for all spikes."""
    def __init__(self, files, node=None, root=None, child_class=None):
        super(Clustering, self).__init__(files, node, root=root)
        self._child_class = child_class
        self._update()
        
    def _update(self):
        self._dict = self._gen_children(child_class=self._child_class)
        self.color = DictVectorizer(self._dict, 'application_data.klustaviewa.color')

    def __getitem__(self, item):
        return self._dict[item]
        
    def __iter__(self):
        return self._dict.__iter__()

    def __len__(self):
        return len(self._dict)

    def __contains__(self, v):
        return v in self._dict

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def iteritems(self):
        return self._dict.iteritems()
        
class ClustersClustering(Clustering):
    """An actual clustering, with color and group."""
    def __init__(self, *args, **kwargs):
        super(ClustersClustering, self).__init__(*args, **kwargs)
        self.group = DictVectorizer(self._dict, 'cluster_group')
        
    def add_cluster(self, id=None, color=None, **kwargs):
        channel_group_id = self._node._v_parent._v_parent._v_name
        clustering = self._node._v_name
        add_cluster(self._files, channel_group_id=channel_group_id, 
                    color=color,
                    id=str(id), clustering=clustering, **kwargs)
        self._update()
        
class ClusterGroupsClustering(Clustering):
    pass
        
class ClustersNode(Node):
    """The parent of clustering types: main, original..."""
    def __init__(self, files, node=None, root=None):
        super(ClustersNode, self).__init__(files, node, root=root)
        # Each child of the group is assigned here.
        for node in self._node._f_iterNodes():
            setattr(self, node._v_name, ClustersClustering(self._files, node, 
                child_class=Cluster, root=self._root))
        
class ClusterGroupsNode(Node):
    def __init__(self, files, node=None, root=None):
        super(ClusterGroupsNode, self).__init__(files, node, root=root)        
        # Each child of the group is assigned here.
        for node in self._node._f_iterNodes():
            setattr(self, node._v_name, ClusterGroupsClustering(self._files, node, child_class=ClusterGroup))
        
class Channel(Node):
    def __init__(self, files, node=None, root=None):
        super(Channel, self).__init__(files, node, root=root)
        
        self.name = self._node._v_attrs.name
        self.kwd_index = self._node._v_attrs.kwd_index
        self.ignored = self._node._v_attrs.ignored
        self.position = self._node._v_attrs.position
        self.voltage_gain = self._node._v_attrs.voltage_gain
        self.display_threshold = self._node._v_attrs.display_threshold
        
        self.application_data = NodeWrapper(self._node.application_data)
        self.user_data = NodeWrapper(self._node.user_data)
    
class Cluster(Node):
    def __init__(self, files, node=None, root=None):
        super(Cluster, self).__init__(files, node, root=root)
        
        self.cluster_group = self._node._v_attrs.cluster_group
        self.mean_waveform_raw = self._node._v_attrs.mean_waveform_raw
        self.mean_waveform_filtered = self._node._v_attrs.mean_waveform_filtered
        
        self.application_data = NodeWrapper(self._node.application_data)
        self.color = self.application_data.klustaviewa.color
        self.user_data = NodeWrapper(self._node.user_data)
        self.quality_measures = NodeWrapper(self._node.quality_measures)

class ClusterGroup(Node):
    def __init__(self, files, node=None, root=None):
        super(ClusterGroup, self).__init__(files, node, root=root)
        self.name = self._node._v_attrs.name
        
        self.application_data = NodeWrapper(self._node.application_data)
        self.user_data = NodeWrapper(self._node.user_data)
    
class Recording(Node):
    def __init__(self, files, node=None, root=None):
        super(Recording, self).__init__(files, node, root=root)
        
        self.name = self._node._v_attrs.name
        self.start_time = self._node._v_attrs.start_time
        self.start_sample = self._node._v_attrs.start_sample
        self.sample_rate = self._node._v_attrs.sample_rate
        self.bit_depth = self._node._v_attrs.bit_depth
        self.band_high = self._node._v_attrs.band_high
        self.band_low = self._node._v_attrs.band_low
        
        self.raw = self._get_child('raw')
        self.high = self._get_child('high')
        self.low = self._get_child('low')
        
        self.user_data = NodeWrapper(self._node.user_data)
    
class EventType(Node):
    def __init__(self, files, node=None, root=None):
        super(EventType, self).__init__(files, node, root=root)
    
        self.events = Events(self._files, self._node.events)
        
        self.application_data = NodeWrapper(self._node.application_data)
        self.user_data = NodeWrapper(self._node.user_data)
    
class Events(Node):
    def __init__(self, files, node=None, root=None):
        super(Events, self).__init__(files, node, root=root)
        
        self.time_samples = self._node.time_samples
        self.recording = self._node.recording
        
        self.user_data = NodeWrapper(self._node.user_data)
