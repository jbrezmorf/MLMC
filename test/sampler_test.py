import os
import shutil
from scipy import stats

from test.new_synth_simulation import SimulationTest
from test.synth_simulation_with_workspace import SimulationTestUseWorkspace

from src.mlmc.sampler import Sampler
from src.mlmc.sample_storage import InMemory
from src.mlmc.sampling_pool import ProcessPool
from src.mlmc.sampling_pool_pbs import SamplingPoolPBS


def sampler_test():

    n_levels = 1
    failed_fraction = 0#0.2

    work_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '_test_tmp')
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)

    distr = stats.norm()
    step_range = (0.1, 0.006)

    # User configure and create simulation instance
    simulation_config = dict(distr=distr, complexity=2, nan_fraction=failed_fraction, sim_method='_sample_fn')
    #simulation_config = {"config_yaml": 'synth_sim_config.yaml'}
    simulation_factory = SimulationTest(simulation_config)

    #mlv = MLView(n_levels, simulation_factory, step_range)
    sample_storage = InMemory()
    sampling_pool = ProcessPool(4)

    # Plan and compute samples
    sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                      n_levels=n_levels, step_range=step_range)

    sampler.determine_level_n_samples()
    sampler.create_simulations()
    sampler.ask_simulations_for_samples()

    # After crash
    # sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, config=mlv)
    # sampler.load_from_storage()
    #
    # This should happen automatically
    # sampler.determine_level_n_samples()
    # sampler.create_simulations()


def sampler_test_with_sim_workspace():

    n_levels = 1
    failed_fraction = 0  # 0.2

    work_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '')


    distr = stats.norm()
    step_range = (0.1, 0.006)

    print("distr ", distr)

    # User configure and create simulation instance
    simulation_config = {"config_yaml": os.path.join(work_dir, 'synth_sim_config.yaml')}
    simulation_factory = SimulationTestUseWorkspace(simulation_config)

    # mlv = MLView(n_levels, simulation_factory, step_range)
    sample_storage = InMemory()
    sampling_pool = ProcessPool(4)

    # Plan and compute samples
    sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                      n_levels=n_levels, step_range=step_range, work_dir=work_dir)

    sampler.determine_level_n_samples()
    sampler.create_simulations()
    sampler.ask_simulations_for_samples()

    # After crash
    # sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, config=mlv)
    # sampler.load_from_storage()
    #
    # This should happen automatically
    # sampler.determine_level_n_samples()
    # sampler.create_simulations()


def sampler_test_pbs():
    n_levels = 1
    failed_fraction = 0  # 0.2

    work_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '')

    distr = stats.norm()
    step_range = (0.1, 0.006)

    print("distr ", distr)

    # User configure and create simulation instance
    simulation_config = {"config_yaml": 'synth_sim_config.yaml'}
    simulation_factory = SimulationTestUseWorkspace(simulation_config)

    # mlv = MLView(n_levels, simulation_factory, step_range)
    sample_storage = InMemory()
    sampling_pool = SamplingPoolPBS(job_weight=200000, job_count=0)

    # Plan and compute samples
    sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                      n_levels=n_levels, step_range=step_range, work_dir=work_dir)

    sampler.determine_level_n_samples()
    sampler.create_simulations()
    sampler.ask_simulations_for_samples()

    # After crash
    # sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, config=mlv)
    # sampler.load_from_storage()
    #
    # This should happen automatically
    # sampler.determine_level_n_samples()
    # sampler.create_simulations()

# mlmc_options = {'output_dir': work_dir,
#                 'keep_collected': True,
#                 'regen_failed': False}
#
#
#
# mc = mlmc.mlmc.MLMC(n_levels, simulation_factory, step_range, mlmc_options)
#
# mc.create_new_execution()
# mc.set_initial_n_samples(n_samples)
# mc.refill_samples()
# mc.wait_for_simulations()

#return mc



if __name__ == "__main__":
    #sampler_test()
    #sampler_test_with_sim_workspace()
    sampler_test_pbs()