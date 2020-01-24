import numpy as np
import attr
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any, Union
from mlmc.level_simulation import LevelSimulation


@attr.s(auto_attribs=True)
class QuantitySpec:
    name: str
    unit: str
    shape: Tuple[int, int]
    times: List[float]
    locations: Union[List[str], List[Tuple[float, float, float]]]
    #dtype: Any = attr.ib()
    #used_attributes: List = ["name", "unit", "shape", "times", "locations"]

    # @dtype.default
    # def hdf_format(self):
    #     result_dtype = {'names': ('name', 'unit', 'shape', 'times', 'locations'),
    #                     'formats': ('S50',
    #                                 'S50',
    #                                 np.dtype((np.int32, (2,))),
    #                                 np.dtype((np.float, (len(self.times),))),
    #                                 np.dtype(('S50', (len(self.locations),)))
    #                                 )
    #                     }
    #
    #     return result_dtype


class Simulation(ABC):

    """
    Previous version:
        mc_level: create fine_simulation - it requires params: precision, level_id


                  make_sample_pair() - set_coarse_sim(): set fine_simulation from previous level as coarse_simulation
                                                         at current level
                                     - generate_random_sample(): make_fields and assign them to fine_sim.input_samples
                                                                 and coarse_sim.input_samples
                                     - call fine_simulation.simulation_sample() and coarse_simulation.simulation_sample()


    """

    def __init__(self, config):
        self._config = config

    @abstractmethod
    def level_instance(self, fine_level_params: List[float], coarse_level_params: List[float])-> LevelSimulation:
        """

        :param fine_level_params:
        :param coarse_level_params:
        :return:
        """

    @staticmethod
    def calculate(config_dict, sample_workspace=None):
        pass

    @staticmethod
    def result_format()-> List[QuantitySpec]:
        pass
