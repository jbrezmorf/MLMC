import os
import numpy as np
import shutil
from scipy import stats

from mlmc.synth_simulation import SynthSimulationWorkspace
from mlmc.sampler import Sampler
from mlmc.sample_storage import Memory
from mlmc.sample_storage_hdf import SampleStorageHDF
from mlmc.sampling_pool import ProcessPool, ThreadPool, OneProcessPool
from mlmc.moments import Legendre
from mlmc.quantity_estimate import QuantityEstimate
import mlmc.new_estimator as new_estimator


def test_sampling_pools():
    n_moments = 5

    distr = stats.norm(loc=1, scale=2)
    step_range = [0.01, 0.001, 0.0001]

    # Set work dir
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    work_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '_test_tmp')
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)
    shutil.copyfile('synth_sim_config.yaml', os.path.join(work_dir, 'synth_sim_config.yaml'))

    simulation_config = {"config_yaml": os.path.join(work_dir, 'synth_sim_config.yaml')}
    simulation_factory = SynthSimulationWorkspace(simulation_config)

    single_process_pool = OneProcessPool(work_dir=work_dir)
    multiprocess_pool = ProcessPool(4, work_dir=work_dir)
    thread_pool = ThreadPool(4, work_dir=work_dir)

    pools = [single_process_pool, multiprocess_pool, thread_pool]

    all_data = []
    for sampling_pool in pools:
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        os.makedirs(work_dir)
        print("os.getcwd() ", os.getcwd())
        shutil.copyfile('synth_sim_config.yaml', os.path.join(work_dir, 'synth_sim_config.yaml'))
        sample_storage = SampleStorageHDF(file_path=os.path.join(work_dir, "mlmc_{}.hdf5".format(len(step_range))))
        # Plan and compute samples
        sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                          step_range=step_range)

        true_domain = distr.ppf([0.0001, 0.9999])
        moments_fn = Legendre(n_moments, true_domain)

        sampler.set_initial_n_samples([10, 10, 10])
        # sampler.set_initial_n_samples([1000])
        sampler.schedule_samples()
        sampler.ask_sampling_pool_for_samples()

        q_estimator = QuantityEstimate(sample_storage=sample_storage, moments_fn=moments_fn, sim_steps=step_range)

        # target_var = 1e-3
        # sleep = 0
        # add_coef = 0.1
        #
        # # @TODO: test
        # # New estimation according to already finished samples
        # variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
        # n_estimated = new_estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
        #                                                                    n_levels=sampler.n_levels)
        # # Loop until number of estimated samples is greater than the number of scheduled samples
        # while not sampler.process_adding_samples(n_estimated, sleep, add_coef):
        #     # New estimation according to already finished samples
        #     variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
        #     n_estimated = new_estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
        #                                                                        n_levels=sampler.n_levels)

        all_data.append(sampler.sample_storage.sample_pairs())

        means, vars = q_estimator.estimate_moments(moments_fn)

        print("means ", means)
        print("vars ", vars)
        assert means[0] == 1
        #assert np.isclose(means[1], 0, atol=1e-2)
        assert vars[0] == 0
        sampler.schedule_samples()
        sampler.ask_sampling_pool_for_samples()

        storage = sampler.sample_storage

    assert np.array_equal(all_data[0], all_data[1])
    assert np.array_equal(all_data[1], all_data[2])


def oneprocess_test():
    np.random.seed(3)
    n_moments = 5

    distr = stats.norm(loc=1, scale=2)
    step_range = [0.01, 0.001, 0.0001]

    # Set work dir
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    work_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '_test_tmp')
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)
    shutil.copyfile('synth_sim_config.yaml', os.path.join(work_dir, 'synth_sim_config.yaml'))

    simulation_config = {"config_yaml": os.path.join(work_dir, 'synth_sim_config.yaml')}
    simulation_factory = SynthSimulationWorkspace(simulation_config)

    sample_storage = SampleStorageHDF(file_path=os.path.join(work_dir, "mlmc_{}.hdf5".format(len(step_range))))
    sampling_pool = OneProcessPool(work_dir=work_dir)

    # Plan and compute samples
    sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                      step_range=step_range)

    true_domain = distr.ppf([0.0001, 0.9999])
    moments_fn = Legendre(n_moments, true_domain)

    sampler.set_initial_n_samples()
    #sampler.set_initial_n_samples([1000])
    sampler.schedule_samples()
    sampler.ask_sampling_pool_for_samples()

    q_estimator = QuantityEstimate(sample_storage=sample_storage, moments_fn=moments_fn, sim_steps=step_range)

    target_var = 1e-3
    sleep = 0
    add_coef = 0.1

    # @TODO: test
    # New estimation according to already finished samples
    variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
    n_estimated = new_estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
                                                                       n_levels=sampler.n_levels)
    # Loop until number of estimated samples is greater than the number of scheduled samples
    while not sampler.process_adding_samples(n_estimated, sleep, add_coef):
        # New estimation according to already finished samples
        variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
        n_estimated = new_estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
                                                                           n_levels=sampler.n_levels)

    print("collected samples ", sampler._n_scheduled_samples)
    means, vars = q_estimator.estimate_moments(moments_fn)


    print("means ", means)
    print("vars ", vars)
    assert means[0] == 1
    assert np.isclose(means[1], 0, atol=1e-2)
    assert vars[0] == 0
    sampler.schedule_samples()
    sampler.ask_sampling_pool_for_samples()

    storage = sampler.sample_storage
    results = storage.sample_pairs()


def multiprocess_test():
    np.random.seed(3)
    n_moments = 5
    distr = stats.norm(loc=1, scale=2)
    step_range = [0.01, 0.001]#, 0.001, 0.0001]

    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    work_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '_test_tmp')
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)
    shutil.copyfile('synth_sim_config.yaml', os.path.join(work_dir, 'synth_sim_config.yaml'))

    simulation_config = {"config_yaml": os.path.join(work_dir, 'synth_sim_config.yaml')}
    simulation_factory = SynthSimulationWorkspace(simulation_config)

    sample_storage = Memory()
    sampling_pool = ProcessPool(4, work_dir=work_dir)

    # Plan and compute samples
    sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                      step_range=step_range)

    true_domain = distr.ppf([0.0001, 0.9999])
    moments_fn = Legendre(n_moments, true_domain)

    sampler.set_initial_n_samples()
    #sampler.set_initial_n_samples([1000])
    sampler.schedule_samples()
    sampler.ask_sampling_pool_for_samples()

    q_estimator = QuantityEstimate(sample_storage=sample_storage, moments_fn=moments_fn, sim_steps=step_range)

    target_var = 1e-4
    sleep = 0
    add_coef = 0.1

    # # @TODO: test
    # # New estimation according to already finished samples
    # variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
    # n_estimated = new_estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
    #                                                                    n_levels=sampler.n_levels)
    # # Loop until number of estimated samples is greater than the number of scheduled samples
    # while not sampler.process_adding_samples(n_estimated, sleep, add_coef):
    #     # New estimation according to already finished samples
    #     variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
    #     n_estimated = new_estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
    #                                                                        n_levels=sampler.n_levels)

    print("collected samples ", sampler._n_scheduled_samples)
    means, vars = q_estimator.estimate_moments(moments_fn)

    print("means ", means)
    print("vars ", vars)
    assert means[0] == 1
    assert np.isclose(means[1], 0, atol=1e-2)
    assert vars[0] == 0
    sampler.schedule_samples()
    sampler.ask_sampling_pool_for_samples()

    storage = sampler.sample_storage
    results = storage.sample_pairs()


def thread_test():
    np.random.seed(3)
    n_moments = 5
    distr = stats.norm(loc=1, scale=2)

    step_range = [0.01, 0.001, 0.0001]

    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    work_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '_test_tmp')
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)
    shutil.copyfile('synth_sim_config.yaml', os.path.join(work_dir, 'synth_sim_config.yaml'))

    simulation_config = {"config_yaml": os.path.join(work_dir, 'synth_sim_config.yaml')}
    simulation_factory = SynthSimulationWorkspace(simulation_config)

    sample_storage = Memory()
    sampling_pool = ThreadPool(4, work_dir=work_dir)

    # Plan and compute samples
    sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                      step_range=step_range)

    true_domain = distr.ppf([0.0001, 0.9999])
    moments_fn = Legendre(n_moments, true_domain)

    sampler.set_initial_n_samples()
    # sampler.set_initial_n_samples([1000])
    sampler.schedule_samples()
    sampler.ask_sampling_pool_for_samples()

    sampler.target_var_adding_samples(1e-4, moments_fn, sleep=20)
    print("collected samples ", sampler._n_created_samples)

    means, vars = sampler.estimate_moments(moments_fn)

    print("means ", means)
    print("vars ", vars)
    assert means[0] == 1
    assert np.isclose(means[1], 0, atol=1e-2)
    assert vars[0] == 0
    sampler.schedule_samples()
    sampler.ask_sampling_pool_for_samples()

    storage = sampler.sample_storage
    results = storage.sample_pairs()


if __name__ == "__main__":
    test_sampling_pools()
    #multiprocess_test()
    #oneprocess_test()
    #thread_test()
