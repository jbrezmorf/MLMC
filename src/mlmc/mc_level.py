import numpy as np
import numpy.ma as ma
from mlmc.sample import Sample


class Level:
    """
    Call Simulation methods
    There are information about random variable - average, dispersion, number of simulation, ...
    TODO:
    workflow:
    - queue simulations ( need simulation object for prepare input, need pbs as executor
    - check for finished simulations (need pbs
    - estimates for collected samples ... this can be in separate class as it is independent of simulation
    .. have to reconsider in context of Analysis
    """

    def __init__(self, sim_factory, previous_level, precision, logger, regen_failed=False):
        """
        :param sim_factory: Method that create instance of particular simulation class
        :param previous_level: Previous level object
        :param precision: Current level number / total number of all levels
        :param logger: Logger object
        :param regen_failed: bool, if True then regenerate failed simulations
        """
        # TODO: coarse_simulation can be different to previous_level_sim if they have same mean value
        # Method for creating simulations
        self._sim_factory = sim_factory
        # Level fine simulation precision
        self._precision = precision
        # Logger class instance
        self._logger = logger
        # Indicator of first level
        self.is_zero_level = (int(self._logger.level_idx) == 0)
        # Previous level instance
        self._previous_level = previous_level
        # Fine simulation instance
        self._fine_simulation = None
        # Coarse simulation instance
        self._coarse_simulation = None
        # Estimate of operations number
        self._n_ops_estimate = None
        # Running unfinished simulations that were generated in last whole mlmc run
        self.running_from_log = False
        # Target number of samples for the level
        self.target_n_samples = None
        # Last moments function
        self._last_moments_fn = None
        # Moments from coarse and fine samples
        self.last_moments_eval = None
        # Moments outliers mask
        self.mask = None
        # Currently running simulations
        self.running_simulations = []
        # Collected simulations, all results of simulations. Including Nans and None ...
        self.finished_simulations = []
        # Target number of samples.
        self.target_n_samples = 1
        # Collected samples (array may be partly filled)
        # Without any order, without Nans and inf. Only this is used for estimates.
        self._sample_values = np.empty((self.target_n_samples, 2))
        # Number of valid samples in _sample_values.
        self._n_valid_samples = 0
        # Possible subsample indices.
        self.sample_indices = None
        # Array of indices of nan samples (in fine or coarse sim)
        self.nan_samples = []
        # Cache evaluated moments.
        self._last_moments_fn = None
        self.fine_times = []
        self.coarse_times = []
        # Load simulations from log
        self.load_simulations(regen_failed)

    def reset(self):
        """
        Reset level variables for further use
        :return: None
        """
        self.running_simulations = []
        self.finished_simulations = []
        self.target_n_samples = 3
        self._sample_values = np.empty((self.target_n_samples, 2))
        self._n_valid_samples = 0
        self.sample_indices = None
        self.nan_samples = []
        self._last_moments_fn = None
        self.fine_times = []
        self.coarse_times = []

    @property
    def fine_simulation(self):
        """
        Fine simulation object
        :return: Simulation object
        """
        if self._fine_simulation is None:
            self._fine_simulation = self._sim_factory(self._precision, self._logger.level_idx)
        return self._fine_simulation

    @property
    def coarse_simulation(self):
        """
        Coarse simulation object
        :return: Simulations object
        """
        if self._previous_level is not None and self._coarse_simulation is None:
            self._coarse_simulation = self._previous_level.fine_simulation
        return self._coarse_simulation

    def load_simulations(self, regen_failed):
        """
        Load finished and running simulations from logs
        :return: None
        """
        finished = set()
        # Get logs content
        self._logger.reload_logs()

        for sim in self._logger.collected_log_content:
            i_level, i, _, _, value, times = sim
            # Don't add failed simulations, they will be generated again
            if not regen_failed:
                self.finished_simulations.append(sim)
                self._add_sample(i, value)
                finished.add((i_level, i))
                self.fine_times.append(times[0])
                self.coarse_times.append(times[1])
            elif value[0] != np.inf and value[1] != np.inf:
                self.finished_simulations.append(sim)
                self._add_sample(i, value)
                finished.add((i_level, i))
                self.fine_times.append(times[0])
                self.coarse_times.append(times[1])

        # Save simulations without those that failed
        if regen_failed:
            self._logger.rewrite_collected_log(self.finished_simulations)

        # Recover running
        for index, sim in enumerate(self._logger.running_log_content):
            if len(sim) != 5:
                # First line contains fine sim n ops estimate
                if index == 0:
                    self.n_ops_estimate = sim[0]
                    # Means that n_ops_estimate is already in log file
                    self._logger.n_ops_estimate = -1
                continue
            i_level, i, _, _, _ = sim

            if (i_level, i) not in finished:
                self.running_simulations.append(sim)

        if self.n_ops_estimate is None:
            self.set_coarse_sim()

        # Running simulations
        if len(self.running_simulations) > 0:
            self.collect_samples()

            if len(self.running_simulations) > 0:
                self.running_from_log = True

    def set_target_n_samples(self, n_samples):
        """
        Set target number of samples for the level.
        :param n_samples: Number of samples
        :return: None
        """
        self.target_n_samples = max(self.target_n_samples, n_samples)

    @property
    def sample_values(self):
        """
        Get valid level samples
        :return: array
        """
        return self._sample_values[:self._n_valid_samples]

    def _add_sample(self, idx, sample_pair):
        """
        Add samples pair to rest of samples
        :param id: sample id
        :param sample_pair: Fine and coarse result
        :return: None
        """

        fine, coarse = sample_pair

        # Samples are not finite
        if not np.isfinite(fine) or not np.isfinite(coarse):
            self.nan_samples.append(idx)
            return
        # Enlarge matrix of samples
        if self._n_valid_samples == self._sample_values.shape[0]:
            self.enlarge_samples(2 * self._n_valid_samples)

        # Add fine and coarse sample
        self._sample_values[self._n_valid_samples, :] = (fine, coarse)
        self._n_valid_samples += 1

    def enlarge_samples(self, size):
        """
        Enlarge matrix of samples
        :param size: New sample matrix size
        :return: None
        """
        # Enlarge sample matrix
        new_values = np.empty((size, 2))
        new_values[:self._n_valid_samples] = self._sample_values[:self._n_valid_samples]
        self._sample_values = new_values

    @property
    def n_total_samples(self):
        """
        Number of all level samples
        :return: int
        """
        return len(self.running_simulations) + len(self.finished_simulations)

    @property
    def n_samples(self):
        """
        Number of level sample
        :return: int, number of samples
        """
        # Number of samples used for estimates.
        if self.sample_indices is None:
            return self._n_valid_samples
        else:
            return len(self.sample_indices)

    def _get_sample_tag(self, char):
        """
        Create sample tag
        :param char: 'C' or 'F' depending on the type of simulation
        :return: str
        """
        return "L{:02d}_{}_S{:07d}".format(int(self._logger.level_idx), char, self.n_total_samples)

    @property
    def n_ops_estimate(self):
        """
        :return: number of fine sim operations
        """
        return self._n_ops_estimate

    @n_ops_estimate.setter
    def n_ops_estimate(self, n_ops):
        """
        Set n ops estimate
        :param n_ops: number of operations
        :return: None
        """
        if self._logger.n_ops_estimate is None or self._logger.n_ops_estimate > 0:
            self._n_ops_estimate = n_ops
            self._logger.n_ops_estimate = n_ops

    def set_coarse_sim(self):
        """
        Set coarse sim to fine simulation
        :return: None
        """
        if not self.fine_simulation.coarse_sim_set:
            self.fine_simulation.set_coarse_sim(self.coarse_simulation)
            self.n_ops_estimate = self.fine_simulation.n_ops_estimate()

    def _make_sample_pair(self):
        """
        Generate new random samples for fine and coarse simulation objects
        :return: list
        """
        import time as t
        start = t.time()
        self.set_coarse_sim()
        # All levels have fine simulation
        idx = self.n_total_samples
        self.fine_simulation.generate_random_sample()
        tag = self._get_sample_tag('F')
        fine_sample = self.fine_simulation.simulation_sample(tag, start)
        fine_sample.sample_id = idx

        start = t.time()
        if self.coarse_simulation is not None:
            tag = self._get_sample_tag('C')
            coarse_sample = self.coarse_simulation.simulation_sample(tag, start)
        else:
            # Zero level have no coarse simulation.
            coarse_sample = Sample()
            coarse_sample.result = 0.0
        coarse_sample.sample_id = idx

        return [fine_sample, coarse_sample]

    def _run_simulations(self):
        """
        Run already generated simulations again
        :return: None
        """
        for (_, fine_sim, coarse_sim) in self.running_simulations:
            self.set_coarse_sim()
            # All levels have fine simulation
            self.fine_simulation.generate_random_sample()

            if self.coarse_simulation is not None:
                self.coarse_simulation.simulation_sample(coarse_sim[0])

            self.fine_simulation.simulation_sample(fine_sim[0])

        self.collect_samples()

    def fill_samples(self):
        """
        Generate samples up to target number set through 'set_target_n_samples'.
        Simulations are planed for execution, but sample values are collected in
        :return: None
        """
        if self.running_from_log:
            self._run_simulations()

        orig_n_running = len(self.running_simulations)
        if self.target_n_samples > self.n_total_samples:
            self.enlarge_samples(self.target_n_samples)

            # Create pair of fine and coarse simulations and add them to list of all running simulations
            while self.n_total_samples < self.target_n_samples:
                self.running_simulations.append(self._make_sample_pair())
                self._logger.log_simulations(self.running_simulations[orig_n_running:])
                orig_n_running += 1

    def collect_samples(self):
        """
        Extract values for finished simulations.
        :return: Number of simulations to finish yet.
        """
        orig_n_finised = len(self.finished_simulations)
        new_running = []

        # Loop through pair of running simulations
        for (fine_sample, coarse_sample) in self.running_simulations:
            fine_sample = self.fine_simulation.extract_result(fine_sample)
            fine_done = fine_sample.result is not None

            if not self.is_zero_level:
                coarse_sample = self.coarse_simulation.extract_result(coarse_sample)
            coarse_done = coarse_sample.result is not None

            if fine_done and coarse_done:
                if fine_sample.result is np.inf or coarse_sample.result is np.inf:
                    coarse_sample.result = coarse_sample.result = np.inf

                self.fine_times.append(fine_sample.time)
                self.coarse_times.append(coarse_sample.time)

                # collect values
                self.finished_simulations.append([fine_sample, coarse_sample])
                self._add_sample(fine_sample.sample_id, (fine_sample.result, coarse_sample.result))
            else:
                new_running.append([fine_sample, coarse_sample])

        self.running_simulations = new_running

        # log new collected simulation pairs
        new_finished = self.finished_simulations[orig_n_finised:]

        self._logger.log_simulations(new_finished, collected=True)
        return len(self.running_simulations)

    def subsample(self, size):
        """
        sub-selection from simulations results
        :param size: number of subsamples
        :return: None
        """
        if size is None:
            self.sample_indices = None
        else:
            assert 0 < size < self._n_valid_samples, "0 < {} < {}".format(size, self._n_valid_samples)
            self.sample_indices = np.random.choice(np.arange(self._n_valid_samples, dtype=int), size=size)

    def evaluate_moments(self, moments_fn, force=False):
        """
        Evaluating moments from moments function
        :param moments_fn: Moment evaluation functions
        :param force: Reevaluate moments
        :return: tuple
        """
        # Current moment functions are different from last moment functions
        if force or moments_fn != self._last_moments_fn:
            samples = self.sample_values
            # Moments from fine samples
            moments_fine = moments_fn(samples[:, 0])

            # For first level moments from coarse samples are zeroes
            if self.is_zero_level:
                moments_coarse = np.zeros_like(np.eye(len(moments_fine), moments_fn.size))
            else:
                moments_coarse = moments_fn(samples[:, 1])
            # Set last moments function
            self._last_moments_fn = moments_fn
            # Moments from fine and coarse samples
            self.last_moments_eval = moments_fine, moments_coarse

            self._remove_outliers_moments()

        if self.sample_indices is None:
            return self.last_moments_eval
        else:
            m_fine, m_coarse = self.last_moments_eval
            return m_fine[self.sample_indices, :], m_coarse[self.sample_indices, :]

    def _remove_outliers_moments(self):
        """
        Remove moments from outliers from fine and course moments
        :return: None
        """
        # Fine and coarse moments mask
        mask_fine = ma.masked_invalid(self.last_moments_eval[0]).mask
        mask_coarse = ma.masked_invalid(self.last_moments_eval[1]).mask

        # Common mask for coarse and fine
        mask_fine_coarse = np.logical_or(mask_fine, mask_coarse)[:, -1]

        self.mask = mask_fine_coarse

        # New moments without outliers
        self.last_moments_eval = self.last_moments_eval[0][~mask_fine_coarse], self.last_moments_eval[1][
            ~mask_fine_coarse]

        # Remove outliers also from sample values
        self._sample_values = self._sample_values[:self._n_valid_samples][~mask_fine_coarse]

        # Set new number of valid samples
        self._n_valid_samples = len(self._sample_values)

    def estimate_diff_var(self, moments_fn):
        """
        Estimate moments variance
        :param moments_fn: Moments evaluation function
        :return: tuple (variance vector, length of moments)
        """

        assert self.n_samples > 1
        mom_fine, mom_coarse = self.evaluate_moments(moments_fn, force=True)
        var_vec = np.var(mom_fine - mom_coarse, axis=0, ddof=1)
        return var_vec, len(mom_fine)

    def estimate_diff_mean(self, moments_fn):
        """
        Estimate moments mean
        :param moments_fn: Function for calculating moments
        :return: np.array, moments mean vector
        """
        mom_fine, mom_coarse = self.evaluate_moments(moments_fn, force=True)
        mean_vec = np.mean(mom_fine - mom_coarse, axis=0)
        return mean_vec

    def sample_range(self):
        """
        Determine limits for outliers
        :return: tuple
        """
        fine_sample = self.sample_values[:, 0]
        quantile_1, quantile_3 = np.percentile(fine_sample, [25, 75])

        iqr = quantile_3 - quantile_1
        min_sample = np.min(fine_sample)

        left = max(min_sample, quantile_1 - 1.5 * iqr)
        if min_sample > 0.0:  # guess that we have positive distribution
            left = min_sample
        right = min(np.max(fine_sample), quantile_3 + 1.5 * iqr)

        return left, right

    def get_n_finished(self):
        """
        Number of finished simulations
        :return: int
        """
        self.collect_samples()
        return len(self.finished_simulations)

    def sample_time(self):
        """
        Get average sample time
        :return: float
        """
        times = np.array(self.fine_times) + np.array(self.coarse_times)
        # Remove error times - temporary solution
        times = times[(times < 1e5)]

        return np.mean(times)
