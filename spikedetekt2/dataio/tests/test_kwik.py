"""HDF5 tools tests."""

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
import os
import tempfile

import numpy as np
import tables as tb
from nose import with_setup

from spikedetekt2.utils.six import itervalues
from spikedetekt2.dataio.kwik import *


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
DIRPATH = tempfile.mkdtemp()

def setup_create():
    prm = {'nfeatures': 3, 'nwavesamples': 10}
    prb = {'channel_groups': [
        {
            'channels': [4, 6, 8],
            'graph': [[4, 6], [8, 4]],
            'geometry': {4: [0.4, 0.6], 6: [0.6, 0.8], 8: [0.8, 0.0]},
        }
    ]}
    
    create_files('myexperiment', dir=DIRPATH, prm=prm, prb=prb)

def teardown_create():
    files = get_filenames('myexperiment', dir=DIRPATH)
    [os.remove(path) for path in itervalues(files)]

    
# -----------------------------------------------------------------------------
# Filename tests
# -----------------------------------------------------------------------------
def test_get_filenames():
    filenames = get_filenames('myexperiment')
    assert os.path.basename(filenames['kwik']) == 'myexperiment.kwik'
    assert os.path.basename(filenames['kwx']) == 'myexperiment.kwx'
    assert os.path.basename(filenames['raw.kwd']) == 'myexperiment.raw.kwd'
    assert os.path.basename(filenames['low.kwd']) == 'myexperiment.low.kwd'
    assert os.path.basename(filenames['high.kwd']) == 'myexperiment.high.kwd'
    
def test_basename_1():
    bn = 'myexperiment'
    filenames = get_filenames(bn)
    kwik = filenames['kwik']
    kwx = filenames['kwx']
    kwdraw = filenames['raw.kwd']
    
    assert get_basename(kwik) == bn
    assert get_basename(kwx) == bn
    assert get_basename(kwdraw) == bn
    
def test_basename_2():
    kwik = '/my/path/experiment.kwik'
    kwx = '/my/path/experiment.kwx'
    kwdhigh = '/my/path/experiment.high.kwd'
    
    assert get_basename(kwik) == 'experiment'
    assert get_basename(kwx) == 'experiment'
    assert get_basename(kwdhigh) == 'experiment'
    
    
# -----------------------------------------------------------------------------
# HDF5 creation functions tests
# -----------------------------------------------------------------------------
def test_create_kwik():
    path = os.path.join(DIRPATH, 'myexperiment.kwik')
    
    prm = {
        'nwavesamples': 20,
        'nfeatures': 3*32,
    }
    prb = {'channel_groups': [
        {
            'channels': [4, 6, 8],
            'graph': [[4, 6], [8, 4]],
            'geometry': {4: [0.4, 0.6], 6: [0.6, 0.8], 8: [0.8, 0.0]},
        }
    ]}
    
    create_kwik(path, prm=prm, prb=prb)
    
    f = tb.openFile(path, 'r')
    channel = f.root.channel_groups.__getattr__('0').channels.__getattr__('4')
    assert channel._v_attrs.name == 'channel_4'
    
    f.close()
    os.remove(path)
    
def test_create_kwx():
    path = os.path.join(DIRPATH, 'myexperiment.kwx')
    
    # Create the KWX file.
    nwavesamples = 20
    nchannels = 32
    nchannels2 = 24
    nfeatures = 3*nchannels
    prm = {
        'nwavesamples': 20,
        'nfeatures': 3*nchannels,
    }
    prb = {'channel_groups': [
        {
            'channels': np.arange(nchannels),
        },
        {
            'channels': nchannels + np.arange(nchannels2),
            'nfeatures': 3*nchannels2
        },
        {
            'channels': nchannels + nchannels2 + np.arange(nchannels),
            'nfeatures': 2*nchannels
        },
    ]}
    
    create_kwx(path, prb=prb, prm=prm)
    
    # Open the KWX file.
    f = tb.openFile(path, 'r')
    
    # Group 1
    fm1 = f.root.channel_groups.__getattr__('1').features_masks
    wr1 = f.root.channel_groups.__getattr__('1').waveforms_raw
    wf1 = f.root.channel_groups.__getattr__('1').waveforms_filtered
    assert fm1.shape[1:] == (3*nchannels2, 2)
    assert wr1.shape[1:] == (nwavesamples, nchannels2)
    assert wf1.shape[1:] == (nwavesamples, nchannels2)

    # Group 2
    fm2 = f.root.channel_groups.__getattr__('2').features_masks
    wr2 = f.root.channel_groups.__getattr__('2').waveforms_raw
    wf2 = f.root.channel_groups.__getattr__('2').waveforms_filtered
    assert fm2.shape[1:] == (2*nchannels, 2)
    assert wr2.shape[1:] == (nwavesamples, nchannels)
    assert wf2.shape[1:] == (nwavesamples, nchannels)
    
    f.close()
    
    # Delete the file.
    os.remove(path)
    
def test_create_kwd():
    path = os.path.join(DIRPATH, 'myexperiment.raw.kwd')
    
    # Create the KWD file.
    nchannels_tot = 32*3
    prm = {'nchannels': nchannels_tot}
    
    create_kwd(path, type='raw', prm=prm,)
    
    # Open the KWX file.
    f = tb.openFile(path, 'r')
    
    assert f.root.recordings
    
    f.close()
    
    # Delete the file.
    os.remove(path)
    
def test_create_empty():
    files = create_files('myexperiment', dir=DIRPATH)
    [os.remove(path) for path in itervalues(files)]
    
    
# -----------------------------------------------------------------------------
# Item creation functions tests
# -----------------------------------------------------------------------------
@with_setup(setup_create, teardown_create)
def test_add_recording():
    files = open_files('myexperiment', dir=DIRPATH, mode='a')
    
    sample_rate = 20000.
    start_time = 10.
    start_sample = 200000.
    bit_depth = 16
    band_high = 100.
    band_low = 500.
    nchannels = 32
    nsamples = 0
    
    add_recording(files, 
                  sample_rate=sample_rate,
                  start_time=start_time, 
                  start_sample=start_sample,
                  bit_depth=bit_depth,
                  band_high=band_high,
                  band_low=band_low,
                  nchannels=nchannels,
                  nsamples=nsamples,
                  )
    
    rec = files['kwik'].root.recordings.__getattr__('0')
    assert rec._v_attrs.sample_rate == sample_rate
    assert rec._v_attrs.start_time == start_time
    assert rec._v_attrs.start_sample == start_sample
    assert rec._v_attrs.bit_depth == bit_depth
    assert rec._v_attrs.band_high == band_high
    assert rec._v_attrs.band_low == band_low
    
    close_files(files)
    
@with_setup(setup_create, teardown_create)
def test_add_event_type():
    files = open_files('myexperiment', dir=DIRPATH, mode='a')
    add_event_type(files, 'myevents')
    events = files['kwik'].root.event_types.myevents.events
    
    assert isinstance(events.time_samples, tb.EArray)
    assert isinstance(events.recording, tb.EArray)
    events.user_data
    
    close_files(files)

@with_setup(setup_create, teardown_create)
def test_add_cluster_group():
    files = open_files('myexperiment', dir=DIRPATH, mode='a')
    add_cluster_group(files, channel_group_id='0', id='noise', name='Noise')
    noise = files['kwik'].root.channel_groups.__getattr__('0').cluster_groups.noise
    
    assert noise._v_attrs.name == 'Noise'
    noise.application_data.klustaviewa._v_attrs.color
    noise.user_data
    
    close_files(files)

@with_setup(setup_create, teardown_create)
def test_add_cluster():
    files = open_files('myexperiment', dir=DIRPATH, mode='a')
    add_cluster(files, channel_group_id='0',)
    cluster = files['kwik'].root.channel_groups.__getattr__('0').clusters.__getattr__('0')
    
    cluster._v_attrs.cluster_group
    cluster._v_attrs.mean_waveform_raw
    cluster._v_attrs.mean_waveform_filtered
    
    cluster.quality_measures
    cluster.application_data.klustaviewa._v_attrs.color
    cluster.user_data
    
    close_files(files)

