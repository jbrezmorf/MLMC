"""
Estimate time per simulation for individual levels
"""
import os
import sys
import numpy as np
import glob
import json

src_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(src_path, '..', 'src'))

from flow_pbs import FlowPbs


work_dir = sys.argv[1]

#file_dir = os.path.dirname(os.path.realpath(__file__))
#input_dir = os.path.join(file_dir, '01_cond_field')
#output_dir = os.path.join(work_dir, 'output_9_100')
#scripts_dir = os.path.join(output_dir, 'scripts')

pbs = FlowPbs(work_dir=work_dir)
print(pbs.estimate_level_times())


