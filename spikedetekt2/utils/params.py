"""Handle user-specified and default parameters."""
# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
import os
import pprint

from spikedetekt2.utils import python_to_pydict, to_lower, get_pydict
from six import string_types, iteritems


# -----------------------------------------------------------------------------
# Python script <==> dictionaries conversion
# -----------------------------------------------------------------------------
def get_params(filename=None, **kwargs):
    """Return all the parameters, retrieved following this order of priority:
    
    * parameters specified as keyword arguments in this function,
    * parameters specified in the .PRM file given in `filename`,
    * default parameters.
    
    """
    return get_pydict(filename=filename, 
                      pydict_default=load_default_params(kwargs),
                      **kwargs)


# -----------------------------------------------------------------------------
# Default parameters
# -----------------------------------------------------------------------------
def load_default_params(namespace=None):
    """Load default parameters, in a given namespace (empty by default)."""
    if namespace is None:
        namespace = {}
        
    # The default parameters are read in a namespace that must contain
    # sample_rate.
    namespace = {'sample_rate': namespace.get('sample_rate', 0)}
    
    folder = os.path.dirname(os.path.realpath(__file__))
    params_default_path = os.path.join(folder, 'params_default.py')
    with open(params_default_path, 'r') as f:
        params_default_python = f.read()
    params_default = python_to_pydict(params_default_python, namespace)
    return to_lower(params_default)


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def display_params(prm):
    return pprint.pformat(prm)
