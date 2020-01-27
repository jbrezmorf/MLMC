import os
import time
import numpy as np
from typing import List
from sample_storage import SampleStorage
from sampling_pool import SamplingPool
from new_simulation import Simulation


class Sampler:

    def __init__(self, sample_storage: SampleStorage, sampling_pool: SamplingPool, sim_factory: Simulation,
                 step_range: List[int], work_dir=None):
        """

        :param sample_storage: store scheduled samples, results and result structure
        :param sampling_pool: calculate samples
        :param sim_factory: generate samples
        :param n_levels: number of MLMC levels
        :param step_range: simulation step range
        :param work_dir: working directory
        """
        self.sample_storage = sample_storage
        self._sampling_pool = sampling_pool

        self._samples = []

        self._n_levels = len(step_range)
        self._sim_factory = sim_factory
        self._step_range = step_range

        # Number of created samples
        self._n_created_samples = np.zeros(self._n_levels)
        # Number of target samples
        self._n_target_samples = np.zeros(self._n_levels)
        # Number of finished and collected samples
        self.n_collected_samples = 0

        self._level_sim_objects = []

        self._create_level_sim_objects()

        # Set workspaces
        #self._create_workspace_directories(work_dir)

        # Save simulation result specification
        #self.sample_storage.save_workspace(self._workspace)

    def _create_level_sim_objects(self):
        """
        Create LevelSimulation object for each level, use simulation factory
        :return: None
        """
        for level_id in range(self._n_levels):
            if level_id == 0:
                level_sim = self._sim_factory.level_instance([self._step_range[level_id]], [0])

            else:
                level_sim = self._sim_factory.level_instance([self._step_range[level_id]], [self._step_range[level_id-1]])

            level_sim.calculate = self._sim_factory.calculate
            level_sim.level_id = level_id
            self._level_sim_objects.append(level_sim)

    # def _create_workspace_directories(self, work_dir):
    #     """
    #     Sampler uses workspace object for communication with files system
    #     :param work_dir: abs path to working directory
    #     :return: None
    #     """
    #     try:
    #         self._workspace = WithoutWorkspace()
    #
    #         if work_dir:
    #             self._workspace = WholeWorkspace(work_dir, self._n_levels)
    #             try:
    #                 if self._sampling_pool.need_jobs:
    #                     self._workspace = PBSWorkspace(work_dir, self._n_levels)
    #                     self._sampling_pool.workspace = self._workspace
    #             except AttributeError:
    #                 print("PBS sampling pool must have need_jobs attribute")
    #
    #         # if self._sim_factory.need_workspace:
    #         #     self._workspace = SimulationWorkspace(work_dir)
    #     except AttributeError:
    #         print("Attribute error, need_workspace class attribute is obligatory")
    #
    #     print("workspace ", self._workspace)

    def sample_range(self, n0, nL):
        """
        Geometric sequence of L elements decreasing from n0 to nL.
        Useful to set number of samples explicitly.
        :param n0: int
        :param nL: int
        :return: np.array of length L = n_levels.
        """
        return np.round(np.exp2(np.linspace(np.log2(n0), np.log2(nL), self._n_levels))).astype(int)

    def set_initial_n_samples(self, n_samples=None):
        """
        Set target number of samples for each level
        :param n_samples: array of number of samples
        :return: None
        """
        if n_samples is None:
            n_samples = [100, 3]
        # Num of samples to ndarray
        n_samples = np.atleast_1d(n_samples)

        # Just maximal number of samples is set
        if len(n_samples) == 1:
            n_samples = np.array([n_samples[0], 3])

        # Create number of samples for all levels
        if len(n_samples) == 2:
            n0, nL = n_samples
            n_samples = self.sample_range(n0, nL)

        self._n_target_samples = n_samples

    def _get_sample_tag(self, level_id):
        """
        Create sample tag
        :param level_id: identifier of current level
        :return: str
        """
        return "L{:02d}_S{:07d}".format(level_id, int(self._n_created_samples[level_id]))

    def schedule_samples(self):
        """
        Create simulation samples, loop through "levels" and its samples (given the number of target samples):
            1) generate sample tag (same for fine and coarse simulation)
            2) get LevelSimulation instance by simulation factory
            3) schedule sample via sampling pool
            4) store scheduled samples in sample storage, separately for each level
        :return: None
        """
        self.ask_sampling_pool_for_samples()
        plan_samples = self._n_target_samples - self._n_created_samples

        for level_id, n_samples in enumerate(plan_samples):

            samples = []
            for _ in range(int(n_samples)):
                # Unique sample id
                sample_id = self._get_sample_tag(level_id)

                level_sim = self._level_sim_objects[level_id]

                #  @TODO: workspace to sampling pool
                # sample_dir = self._sampling_pool.change_to_sample_directory(sample_id, level_id)

                # Copy simulation files, ...
                # @TODO: it should be done by particular sampling pool
                # self._modify_level_sim_obj(level_sim, level_id, sample_dir)

                # Serialized SimulationLevel object
                # @TODO: remove and serialize level sim in hdf sampling pool
                # @TODO: Shouldn't we serialize level sim to hdf?
                # self._sampling_pool.serialize_level_sim(level_sim)

                # Schedule current sample
                self._sampling_pool.schedule_sample(sample_id, level_sim)
                # Increment number of created samples at current level
                self._n_created_samples[level_id] += 1

                samples.append(sample_id)

                # Store scheduled samples
                self.sample_storage.save_scheduled_samples(level_id, samples)

    # @TODO: move to sampling pool if needed
    # def _modify_level_sim_obj(self, level_sim, level_id, sample_dir):
    #     """
    #     Copy simulation common files to sample directory
    #     :param level_sim: LevelSimulation instance
    #     :param level_id: level identifier
    #     :param sample_dir: sample directory
    #     :return: LevelSimulation
    #     """
    #     # Copy simulation common files
    #     if level_sim.common_files:
    #         self._workspace.copy_sim_files(level_sim.common_files, sample_dir)
    #
    #         if level_sim.sample_workspace is not None:
    #             raise Exception("Sample workspace must be set in Sampler method")
    #         level_sim.sample_workspace = sample_dir
    #
    #
    #     return level_sim

    def ask_sampling_pool_for_samples(self, sleep=0, timeout=None):
        """
        Waiting for running simulations
        :param sleep: time for doing nothing
        :param timeout: maximum time for waiting on running simulations
        :return: int, number of running simulations
        """
        if timeout is None:
            timeout = 0
        elif timeout <= 0:
            return 1

        n_running = 1
        t0 = time.clock()
        while n_running > 0:
            finished_samples, n_running = self._sampling_pool.get_finished()

            # Store finished samples
            if len(finished_samples) > 0:
                self._store_finished_samples(finished_samples)

            time.sleep(sleep)
            if 0 < timeout < (time.clock() - t0):
                break

        return n_running

    def target_var_adding_samples(self, target_var, moments_fn, sleep=20, add_coef=0.1):
        """
        Set level target number of samples according to improving estimates.
        We assume set_initial_n_samples method was called before.
        :param target_var: float, whole mlmc target variance
        :param moments_fn: Object providing calculating moments
        :param sleep: Sample waiting time
        :param add_coef: Coefficient for adding samples
        :return: None
        """
        # @TODO: move elsewhere
        self._levels_results = self.sample_storage.sample_pairs()

        print("levels results ", self._levels_results)

        # New estimation according to already finished samples
        n_estimated = self.estimate_n_samples_for_target_variance(target_var, moments_fn)
        # Loop until number of estimated samples is greater than the number of scheduled samples
        while not self.process_adding_samples(n_estimated, sleep, add_coef):
            # New estimation according to already finished samples
            n_estimated = self.estimate_n_samples_for_target_variance(target_var, moments_fn)

    def estimate_n_samples_for_target_variance(self, target_variance, moments_fn=None, prescribe_vars=None):
        """
        Estimate optimal number of samples for individual levels that should provide a target variance of
        resulting moment estimate. Number of samples are directly set to levels.
        This also set given moment functions to be used for further estimates if not specified otherwise.
        TODO: separate target_variance per moment
        :param target_variance: Constrain to achieve this variance.
        :param moments_fn: moment evaluation functions
        :param prescribe_vars: vars[ L, M] for all levels L and moments M safe the (zeroth) constant moment with zero variance.
        :return: np.array with number of optimal samples for individual levels and moments, array (LxR)
        """
        _, n_samples_estimate_safe = self.n_sample_estimate_moments(target_variance, moments_fn, prescribe_vars)
        n_samples = np.max(n_samples_estimate_safe, axis=1).astype(int)

        return n_samples

    def process_adding_samples(self, n_estimated, pbs, sleep, add_coef=0.1):
        """
        Process adding samples
        :param n_estimated: Number of estimated samples on each level, list
        :param pbs: src.Pbs instance
        :param sleep: Sample waiting time
        :param add_coef: default value 0.1
        :return: bool, if True adding samples is complete
        """
        # Get default scheduled samples
        #n_scheduled = np.array(self.l_scheduled_samples())
        n_scheduled = self.l_scheduled_samples()
        print("n scheduled ", n_scheduled)

        # New scheduled sample will be 10 percent of difference
        # between current number of target samples and new estimated one
        # If 10 percent of estimated samples is greater than difference between estimated and scheduled samples,
        # set scheduled samples to estimated samples
        print("n estimated ", n_estimated)
        new_scheduled = np.where((n_estimated * add_coef) > (n_estimated - n_scheduled),
                                 n_estimated,
                                 n_scheduled + (n_estimated - n_scheduled) * add_coef)

        print("new scheduled ", new_scheduled)

        n_scheduled = np.ceil(np.where(n_estimated < n_scheduled,
                                       n_scheduled,
                                       new_scheduled))

        print("N scheduled ", n_scheduled)

        # Levels where estimated are greater than scheduled
        greater_items = np.where(np.greater(n_estimated, n_scheduled))[0]

        # Scheduled samples and wait until at least half of the samples are done
        self.set_scheduled_and_wait(n_scheduled, greater_items, pbs, sleep)

        print("n estimated ", n_estimated)
        print("n scheduled ", n_scheduled)

        return np.all(n_estimated[greater_items] == n_scheduled[greater_items])

    def n_sample_estimate_moments(self, target_variance, moments_fn=None, prescribe_vars=None):
        # if moments_fn is None:
        #     moments_fn = self.moments
        if prescribe_vars is None:
            vars = self.estimate_diff_vars_regression(moments_fn)
        else:
            vars = prescribe_vars

        # @TODO: set n ops estimate
        n_ops = np.array([lvl.task_size for lvl in self._level_sim_objects])

        sqrt_var_n = np.sqrt(vars.T * n_ops)  # moments in rows, levels in cols
        total = np.sum(sqrt_var_n, axis=1)  # sum over levels
        n_samples_estimate = np.round((sqrt_var_n / n_ops).T * total / target_variance).astype(int)  # moments in cols

        # Limit maximal number of samples per level
        n_samples_estimate_safe = np.maximum(np.minimum(n_samples_estimate, vars * self._n_levels / target_variance), 2)

        return n_samples_estimate, n_samples_estimate_safe

    def estimate_diff_vars_regression(self, moments_fn=None, raw_vars=None):
        """
        Estimate variances using linear regression model.
        Assumes increasing variance with moments, use only two moments with highest average variance.
        :param moments_fn: Moment evaluation function
        :return: array of variances, shape  L
        """
        # vars shape L x R
        if raw_vars is None:
            assert moments_fn is not None
            raw_vars, n_samples = self.estimate_diff_vars(moments_fn)
            print("raw vars ", raw_vars)
            print("n samples ", n_samples)
        sim_steps = self.sim_steps
        #vars = self._varinace_regression(raw_vars, sim_steps)
        vars = self._all_moments_variance_regression(raw_vars, sim_steps)
        return vars

    def estimate_diff_vars(self, moments_fn=None):
        """
        Estimate moments variance from samples
        :param moments_fn: Moment evaluation functions
        :return: (diff_variance, n_samples);
            diff_variance - shape LxR, variances of diffs of moments
            n_samples -  shape L, num samples for individual levels.

            Returns simple variance for level 0.
        """
        vars = []
        n_samples = []

        # @TODO: we are going to have all levels in one array
        for level_results in self._levels_results:
            v, n = self.estimate_diff_var(level_results, moments_fn)
            vars.append(v)
            n_samples.append(n)
        return np.array(vars), np.array(n_samples)

    ################################################
    # Level methods

    def estimate_diff_var(self, level_results, moments_fn):
        """
        Estimate moments variance
        :param moments_fn: Moments evaluation function
        :return: tuple (variance vector, length of moments)
        """

        mom_fine, mom_coarse = self.evaluate_moments(level_results, moments_fn)
        assert len(mom_fine) == len(mom_coarse)
        assert len(mom_fine) >= 2
        var_vec = np.var(mom_fine - mom_coarse, axis=0, ddof=1)
        ns = level_results.shape[1]
        assert ns == len(mom_fine)  # This was previous unconsistent implementation.
        return var_vec, ns

    def estimate_diff_mean(self, moments_fn):
        """
        Estimate moments mean
        :param moments_fn: Function for calculating moments
        :return: np.array, moments mean vector
        """
        mom_fine, mom_coarse = self.evaluate_moments(moments_fn)
        assert len(mom_fine) == len(mom_coarse)
        assert len(mom_fine) >= 1
        mean_vec = np.mean(mom_fine - mom_coarse, axis=0)
        return mean_vec

    def estimate_covariance(self, moments_fn, stable=False):
        """
        Estimate covariance matrix (non central).
        :param moments_fn: Moment functions object.
        :param stable: Use alternative formula with better numerical stability.
        :return: cov covariance matrix  with shape (n_moments, n_moments)
        """
        mom_fine, mom_coarse = self.evaluate_moments(moments_fn)
        assert len(mom_fine) == len(mom_coarse)
        assert len(mom_fine) >= 2
        assert self.n_samples == len(mom_fine)

        if stable:
            # Stable formula - however seems that we have no problem with numerical stability
            mom_diff = mom_fine - mom_coarse
            mom_sum = mom_fine + mom_coarse
            cov = 0.5 * (np.matmul(mom_diff.T, mom_sum) + np.matmul(mom_sum.T, mom_diff)) / self.n_samples
        else:
            # Direct formula
            cov_fine = np.matmul(mom_fine.T,   mom_fine)
            cov_coarse = np.matmul(mom_coarse.T, mom_coarse)
            cov = (cov_fine - cov_coarse) / self.n_samples

        return cov

    def evaluate_moments(self, moments_fn, force=False):
        """
        Evaluate level difference for all samples and given moments.
        :param moments_fn: Moment evaluation object.
        :param force: Reevaluate moments
        :return: (fine, coarse) both of shape (n_samples, n_moments)
        """
        # Current moment functions are different from last moment functions
        same_moments = moments_fn == self._last_moments_fn
        same_shapes = self.last_moments_eval is not None
        if force or not same_moments or not same_shapes:
            samples = self.sample_values

            # Moments from fine samples
            moments_fine = moments_fn(samples[:, 0])

            # For first level moments from coarse samples are zeroes
            if self.is_zero_level:
                moments_coarse = np.zeros((len(moments_fine), moments_fn.size))
            else:
                moments_coarse = moments_fn(samples[:, 1])
            # Set last moments function
            self._last_moments_fn = moments_fn
            # Moments from fine and coarse samples
            self.last_moments_eval = moments_fine, moments_coarse

            self._remove_outliers_moments()
            if self.sample_indices is not None:
                self.subsample(len(self.sample_indices))

        if self.sample_indices is None:
            return self.last_moments_eval
        else:
            m_fine, m_coarse = self.last_moments_eval
            return m_fine[self.sample_indices, :], m_coarse[self.sample_indices, :]

    def _remove_outliers_moments(self, ):
        """
        Remove moments from outliers from fine and course moments
        :return: None
        """
        # Fine and coarse moments mask
        ok_fine = np.all(np.isfinite(self.last_moments_eval[0]), axis=1)
        ok_coarse = np.all(np.isfinite(self.last_moments_eval[1]), axis=1)

        # Common mask for coarse and fine
        ok_fine_coarse = np.logical_and(ok_fine, ok_coarse)
        #self.ok_fine_coarse = ok_fine_coarse

        # New moments without outliers
        self.last_moments_eval = self.last_moments_eval[0][ok_fine_coarse, :], self.last_moments_eval[1][ok_fine_coarse, :]


    ###################################################

    def estimate_level_means(self, moments_fn):
        """
        Estimate means on individual levels.
        :param moments_fn: moments object of size R
        :return: shape (L, R)
        """
        means = []
        for level in self.mlmc.levels:
            means.append(level.estimate_diff_mean(moments_fn))
        return np.array(means)

    def set_scheduled_and_wait(self, n_scheduled, greater_items, pbs, sleep, fin_sample_coef=0.5):
        """
        Scheduled samples on each level and wait until at least half of the samples is done
        :param n_scheduled: ndarray, number of scheduled samples on each level
        :param greater_items: Items where n_estimated is greater than n_scheduled
        :param pbs: Pbs script generator object
        :param sleep: Time waiting for samples
        :param fin_sample_coef: The proportion of samples to finished for further estimate
        :return: None
        """
        # Set scheduled samples and run simulations
        self.set_level_target_n_samples(n_scheduled)
        self.schedule_samples()
        # Use PBS job scheduler
        if pbs is not None:
            pbs.execute()

        # Finished level samples
        n_finished = np.array([level.get_n_finished() for level in self.levels])
        # Wait until at least half of the scheduled samples are done on each level
        while np.any(n_finished[greater_items] < fin_sample_coef * n_scheduled[greater_items]):
            # Wait a while
            time.sleep(sleep)
            n_finished = np.array([level.get_n_finished() for level in self.levels])

    def set_level_target_n_samples(self, n_samples, fraction=1.0):
        """
        Set level number of target samples
        :param n_samples: list, each level target samples
        :param fraction: Use just fraction of total samples
        :return: None
        """
        for level, n in enumerate(n_samples):
            self.n_target_samples[level] += int(n * fraction)

    def l_scheduled_samples(self):
        """
        Get all levels target number of samples
        :return: list
        """
        return [level.target_n_samples for level in self.levels]

    def load_from_storage(self):
        raise NotImplementedError
        self._sample_storage.load_data()

    def _store_finished_samples(self, finished_samples):
        self.sample_storage.save_results(finished_samples)
