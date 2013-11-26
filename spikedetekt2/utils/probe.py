"""Handle user-specified and default parameters."""
# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
import os
import itertools

import numpy as np

from spikedetekt2.utils import get_pydict
from spikedetekt2.utils.six import iterkeys, iteritems


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def _get_geometry_arr(geometry):
    k = sorted(iterkeys(geometry))
    return np.array([geometry[_] for _ in k])
    
def _get_adjacency_list(graph):
    """Convert a list of edges into an adjacency list."""
    adj = {}
    for i, j in graph:
        if i in adj:
            ni = adj[i]
        else:
            ni = adj[i] = set()
        if j in adj:
            nj = adj[j]
        else:
            nj = adj[j] = set()
        ni.add(j)
        nj.add(i)
    return adj
    
def _assert_channel_graphs(channels=None, graph=None):
    """Assert all channels in the graph belong to the channel list."""
    channels_in_graph = set(itertools.chain(*graph))
    assert channels_in_graph <= set(channels)
    

# -----------------------------------------------------------------------------
# Probe class
# -----------------------------------------------------------------------------
class Probe(object):
    def __init__(self, prb, name=None):
        """prb is a dictionary."""
        self.name = name
        channel_groups = prb.get('channel_groups', [])
        self.channel_groups = [ProbeChannelGroup(i, c) 
            for i, c in enumerate(channel_groups)]
        # Get the full adjacency graph, which is just the concatenation
        # of all graphs in all channel groups.
        graphs = [cg.graph for cg in self.channel_groups]
        self.graph = list(itertools.chain(*graphs))
        self.adjacency_list = _get_adjacency_list(self.graph)
        
    def __repr__(self):
        name = "'{0:s}' ".format(self.name) if self.name else ''
        return '<Probe {name}with {0:d} channel groups>'.format(
            len(self.channel_groups),
            name=name)
        
class ProbeChannelGroup(object):
    def __init__(self, i, channel_group):
        self.index = i
        self.channels = channel_group['channels']
        self.graph = [tuple(pair) for pair in channel_group.get('graph', [])]
        self.geometry = channel_group.get('geometry', {})
        self.geometry_arr = _get_geometry_arr(self.geometry)
        _assert_channel_graphs(graph=self.graph, channels=self.channels)
        
    def __repr__(self):
        return '<Probe channel group {0:d} with {1:d} channels>'.format(
            self.index,
            len(self.channels)
        )
