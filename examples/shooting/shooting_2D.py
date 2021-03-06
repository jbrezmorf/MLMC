import numpy as np
from mlmc.estimator import Estimate, estimate_n_samples_for_target_variance
from mlmc.sampler import Sampler
from mlmc.sample_storage import Memory
from mlmc.sampling_pool import OneProcessPool
from examples.shooting.simulation_shooting_2D import ShootingSimulation2D
from mlmc.quantity.quantity import make_root_quantity
from mlmc.quantity.quantity_estimate import moments, estimate_mean
from mlmc.moments import Legendre
from mlmc.plot.plots import Distribution


# Simple example with OneProcessPool, MultiProcessPool, also show usage of different storages - Memory(), HDFStorage()


class ProcessShooting2D:

    def __init__(self):
        n_levels = 5
        # Number of MLMC levels
        step_range = [0.05, 0.005]
        # step_range [simulation step at the coarsest level, simulation step at the finest level]
        level_parameters = ProcessShooting2D.determine_level_parameters(n_levels, step_range)
        # Determine each level parameters (in this case, simulation step at each level), level_parameters should be
        # simulation dependent
        self._sample_sleep = 0  # 30
        # Time to do nothing just to make sure the simulations aren't constantly checked, useful mainly for PBS run
        self._sample_timeout = 60
        # Maximum waiting time for running simulations
        self._adding_samples_coef = 0.1
        self._n_moments = 20
        # number of generalized statistical moments used for MLMC number of samples estimation
        self._quantile = 0.001
        # Setting parameters that are utilized when scheduling samples
        ###
        # MLMC run
        ###
        sampler = self.create_sampler(level_parameters=level_parameters)
        # Create sampler (mlmc.Sampler instance) - crucial class that controls MLMC run
        self.generate_samples(sampler, n_samples=None, target_var=1e-3)
        # Generate MLMC samples, there are two ways:
        # 1) set exact number of samples at each level,
        #    e.g. for 5 levels - self.generate_samples(sampler, n_samples=[1000, 500, 250, 100, 50])
        # 2) set target variance of MLMC estimates,
        #    e.g. self.generate_samples(sampler, n_samples=None, target_var=1e-6)
        self.all_collect(sampler)
        # Check if all samples are finished
        ###
        # Postprocessing
        ###
        self.process_results(sampler, n_levels)
        # Postprocessing, MLMC is finished at this point

    def create_estimator(self, quantity, sample_storage):
        estimated_domain = Estimate.estimate_domain(quantity, sample_storage, quantile=self._quantile)
        moments_fn = Legendre(self._n_moments, estimated_domain)
        # Create estimator for your quantity
        return Estimate(quantity=quantity, sample_storage=sample_storage,
                                              moments_fn=moments_fn)

    def process_results(self, sampler, n_levels):
        sample_storage = sampler.sample_storage
        # Load result format from sample storage
        result_format = sample_storage.load_result_format()
        # Create quantity instance representing your real quantity of interest
        root_quantity = make_root_quantity(sample_storage, result_format)

        # You can access item of quantity according to result format
        target = root_quantity['target']
        time = target[10]  # times: [1]
        position = time['0']  # locations: ['0']
        x_quantity_value = position[0]
        y_quantity_value = position[1]

        # Create estimator for quantities
        x_estimator = self.create_estimator(x_quantity_value, sample_storage)
        y_estimator = self.create_estimator(y_quantity_value, sample_storage)

        root_quantity_estimated_domain = Estimate.estimate_domain(root_quantity, sample_storage,
                                                                  quantile=self._quantile)
        root_quantity_moments_fn = Legendre(self._n_moments, root_quantity_estimated_domain)

        # There is another possible approach to calculating all moments at once and then choose quantity
        moments_quantity = moments(root_quantity, moments_fn=root_quantity_moments_fn, mom_at_bottom=True)
        moments_mean = estimate_mean(moments_quantity)
        target_mean = moments_mean['target']
        time_mean = target_mean[10]  # times: [1]
        location_mean = time_mean['0']  # locations: ['0']
        value_mean = location_mean[0]  # result shape: (1,)

        self.approx_distribution(x_estimator, n_levels, tol=1e-8)
        self.approx_distribution(y_estimator, n_levels, tol=1e-8)

    def approx_distribution(self, estimator, n_levels, tol=1.95):
        """
        Probability density function approximation
        :param estimator: mlmc.estimator.Estimate instance, it contains quantity for which the density is approximated
        :param n_levels: int, number of MLMC levels
        :param tol: Tolerance of the fitting problem, with account for variances in moments.
        :return: None
        """
        distr_obj, result, _, _ = estimator.construct_density(tol=tol)
        distr_plot = Distribution(title="distributions", error_plot=None)
        distr_plot.add_distribution(distr_obj)

        if n_levels == 1:
            samples = estimator.get_level_samples(level_id=0)[..., 0]
            distr_plot.add_raw_samples(np.squeeze(samples))
        distr_plot.show(None)
        distr_plot.reset()

    def create_sampler(self, level_parameters):
        """
        Simulation dependent configuration
        :return: mlmc.sampler instance
        """
        # Create Pbs sampling pool
        sampling_pool = OneProcessPool()

        simulation_config = {
            "start_position": np.array([0, 0]),
            "start_velocity": np.array([10, 0]),
            "area_borders":  np.array([-100, 200, -300, 400]),
            "max_time": 10,
            "complexity": 2,  # used for initial estimate of number of operations per sample
            'fields_params': dict(model='gauss', dim=1, sigma=1, corr_length=0.1),
        }

        # Create simulation factory
        simulation_factory = ShootingSimulation2D(config=simulation_config)
        # Create HDF sample storage
        sample_storage = Memory()
        # Create sampler, it manages sample scheduling and so on
        sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                          level_parameters=level_parameters)

        return sampler

    def generate_samples(self, sampler, n_samples=None, target_var=None):
        """
        Generate MLMC samples
        :param sampler: mlmc.sampler.Sampler instance
        :param n_samples: None or list, number of samples at each level
        :param target_var: target variance of MLMC estimates
        :return: None
        """
        # The number of samples is set by user
        if n_samples is not None:
            sampler.set_initial_n_samples(n_samples)
        # The number of initial samples is determined automatically
        else:
            sampler.set_initial_n_samples()
        # Samples are scheduled and the program is waiting for all of them to be completed.
        sampler.schedule_samples()
        sampler.ask_sampling_pool_for_samples(sleep=self._sample_sleep, timeout=self._sample_timeout)
        self.all_collect(sampler)

        # MLMC estimates target variance is set
        if target_var is not None:
            # The mlmc.quantity.quantity.Quantity instance is created
            # parameters 'storage' and 'q_specs' are obtained from sample_storage,
            # originally 'q_specs' is set in the simulation class
            root_quantity = make_root_quantity(storage=sampler.sample_storage,
                                               q_specs=sampler.sample_storage.load_result_format())

            # Moment functions object is created
            # The MLMC algorithm determines number of samples according to the moments variance,
            # Type of moment functions (Legendre by default) might affect the total number of MLMC samples
            moments_fn = self.set_moments(root_quantity, sampler.sample_storage, n_moments=self._n_moments)
            estimate_obj = Estimate(root_quantity, sample_storage=sampler.sample_storage,
                                    moments_fn=moments_fn)

            # Initial estimation of the number of samples at each level
            variances, n_ops = estimate_obj.estimate_diff_vars_regression(sampler.n_finished_samples)
            # Firstly, the variance of moments and execution time of samples at each level are calculated from already finished samples
            n_estimated = estimate_n_samples_for_target_variance(target_var, variances, n_ops,
                                                                 n_levels=sampler.n_levels)

            #####
            # MLMC sampling algorithm - gradually schedules samples and refines the total number of samples
            #####
            # Loop until number of estimated samples is greater than the number of scheduled samples
            while not sampler.process_adding_samples(n_estimated, self._sample_sleep, self._adding_samples_coef,
                                                     timeout=self._sample_timeout):
                # New estimation according to already finished samples
                variances, n_ops = estimate_obj.estimate_diff_vars_regression(sampler._n_scheduled_samples)
                n_estimated = estimate_n_samples_for_target_variance(target_var, variances, n_ops,
                                                                     n_levels=sampler.n_levels)

    def all_collect(self, sampler):
        """
        Collect samples
        :param sampler: mlmc.Sampler object
        :return: None
        """
        running = 1
        while running > 0:
            running = 0
            running += sampler.ask_sampling_pool_for_samples()
            print("N running: ", running)

    def set_moments(self, quantity, sample_storage, n_moments=25):
        true_domain = Estimate.estimate_domain(quantity, sample_storage, quantile=self._quantile)
        return Legendre(n_moments, true_domain)

    @staticmethod
    def determine_level_parameters(n_levels, step_range):
        """
        Determine level parameters,
        In this case, a step of fine simulation at each level
        :param n_levels: number of MLMC levels
        :param step_range: simulation step range
        :return: List of lists
        """
        assert step_range[0] > step_range[1]
        level_parameters = []
        for i_level in range(n_levels):
            if n_levels == 1:
                level_param = 1
            else:
                level_param = i_level / (n_levels - 1)
            level_parameters.append([step_range[0] ** (1 - level_param) * step_range[1] ** level_param])
        return level_parameters


if __name__ == "__main__":
    ProcessShooting2D()
