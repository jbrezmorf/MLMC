import os
import sys
import numpy as np
import gstools
import time
from mlmc.sampler import Sampler
from mlmc.sample_storage_hdf import SampleStorageHDF
from mlmc.sampling_pool import OneProcessPool, ProcessPool, ThreadPool
from mlmc.sampling_pool_pbs import SamplingPoolPBS
from mlmc.tool.flow_mc import FlowSim
from mlmc.moments import Legendre, Monomial
from mlmc.tool.process_base import ProcessBase
from mlmc.random import correlated_field as cf
#from mlmc.quantity_estimate import QuantityEstimate
from mlmc.quantity import make_root_quantity
from mlmc.quantity_estimate import estimate_mean, moment, moments, covariance
from mlmc import estimator
import mlmc.tool.simple_distribution


class ProcessSimple:

    def __init__(self):
        args = ProcessBase.get_arguments(sys.argv[1:])

        self.work_dir = os.path.abspath(args.work_dir)
        self.append = False
        # Add samples to existing ones
        self.clean = args.clean
        # Remove HDF5 file, start from scratch
        self.debug = args.debug
        # 'Debug' mode is on - keep sample directories
        self.use_pbs = True
        # Use PBS sampling pool
        self.n_levels = 5
        self.n_moments = 25
        # Number of MLMC levels

        step_range = [1, 0.0055]
        # step   - elements
        # 0.1    - 262
        # 0.08   - 478
        # 0.06   - 816
        # 0.055  - 996
        # 0.005  - 106056
        # 0.004  - 165404
        # 0.0035 - 217208

        # step_range [simulation step at the coarsest level, simulation step at the finest level]

        # Determine level parameters at each level (In this case, simulation step at each level) are set automatically
        self.level_parameters = ProcessSimple.determine_level_parameters(self.n_levels, step_range)

        # Determine number of samples at each level
        self.n_samples = ProcessSimple.determine_n_samples(self.n_levels)

        if args.command == 'run':
            self.run()
        elif args.command == "process":
            self.process()
        else:
            self.append = True  # Use 'collect' command (see base_process.Process) to add samples
            self.clean = False
            self.run(renew=True) if args.command == 'renew' else self.run()

    def process(self):
        """
        Use collected data
        :return: None
        """
        assert os.path.isdir(self.work_dir)
        mlmc_estimators = {}
        n_levels = [0, 1, 2, 3, 5] # 0 - ref MC 100k samples
        #n_levels = [5]
        #n_levels = [0, 3, 5]
        #n_levels = [1, 2]
        n_levels = [0]
        #for nl in [ 1,3,5,7,9]:

        true_domain = self.get_largest_domain(n_levels)

        #n_levels = [1]
        step_range = [1, 0.0055]

        for nl in n_levels:  # high resolution fields
            #print("LEVELS ", nl)
            estimator = self.create_estimator(nl, true_domain=true_domain)
            mlmc_estimators[nl] = estimator

            # level_parameters = ProcessSimple.determine_level_parameters(nl, step_range)
            # print("level parameters ", level_parameters)
            #print("nl: {}, N collected: {}".format(nl, estimator._sample_storage.get_n_collected()))

            # if nl > 0:
            #     str_n_col = ""
            #     n_col = estimator._sample_storage.get_n_collected()
            #     #print("stimator._sample_storage.get_n_ops() ", estimator._sample_storage.get_n_ops())
            #     #print("cost ", np.sum(estimator._sample_storage.get_n_ops() * np.array(n_col)))
            #     for i in range(5):
            #         if i >= len(n_col):
            #             str_n_col += " & "
            #         elif i == len(n_col)-1:
            #             str_n_col += str(n_col[i])
            #         else:
            #             str_n_col += str(n_col[i]) + " & "
            #     print("str n col ", str_n_col)


        #self.analyze_times(mlmc_estimators)
        self.plot_moments(mlmc_estimators)
        #self.get_costs(mlmc_estimators)
        self.plot_distr(mlmc_estimators, domain=true_domain)
        #self.plot_distr_log(mlmc_estimators, domain=true_domain)


    def get_costs(self, mlmc_estimators):
        for nl, estimator in mlmc_estimators.items():
            if nl > 0:
                print("nl: {}".format(nl))
                str_n_col = ""

                # sample_storage = SampleStorageHDF(
                #     file_path=os.path.join(self.work_dir, "n_ops/L{}/mlmc_{}.hdf5".format(nl, nl)))
                n_ops = estimator._sample_storage.get_n_ops()

                print("n ops ", n_ops)
                if isinstance(n_ops[0], np.ndarray):
                    new_n_ops = []
                    for nop in n_ops:
                        nop = np.squeeze(nop)
                        if len(nop) > 0:
                            # print("nop ", nop)
                            new_n_ops.append(nop[..., 0] / nop[..., 1])
                    n_ops = new_n_ops

                print("n ops ", n_ops)
                n_collected = estimator._sample_storage.get_n_collected()
                print("n collected ", n_collected)

                costs = n_collected * np.array(n_ops)


                n_col = costs
                #print("stimator._sample_storage.get_n_ops() ", estimator._sample_storage.get_n_ops())
                #print("cost ", np.sum(estimator._sample_storage.get_n_ops() * np.array(n_col)))
                for i in range(5):
                    if i >= len(n_col):
                        str_n_col += " & "
                    elif i == len(n_col)-1:
                        str_n_col += "{:0.0f}".format(n_col[i])
                    else:
                        str_n_col += "{:0.0f} & ".format(n_col[i])

                str_n_col += " & {:0.0f}".format(np.sum(costs))

                print("str n col ", str_n_col)

                # print("level costs ", costs)
                # print("total cost ", np.sum(costs))
                print("##################################")


    def plot_moments(self, mlmc_estimators):
        moments_plot = mlmc.tool.plot.MomentsPlots(
            title="Legendre {} moments".format(self.n_moments))

        # moments_plot = mlmc.tool.plot.PlotMoments(
        #     title="Monomial {} moments".format(self.n_moments), log_mean_y=False)

        for nl, estimator in mlmc_estimators.items():
            moments_mean = estimate_mean(moments(estimator._quantity, estimator._moments_fn))
            est_moments = moments_mean.mean
            est_vars = moments_mean.var

            n_collected = [str(n_c) for n_c in estimator._sample_storage.get_n_collected()]
            moments_plot.add_moments((moments_mean.mean, moments_mean.var), label="#L{} N:".format(nl) + ", ".join(n_collected))


            print("moments level means ", moments_mean.l_means)
            print("moments level vars ", moments_mean.l_vars)

            print("moments level max vars ", np.max(moments_mean.l_vars, axis=1))

            print("est moments ", est_moments)
            print("est_vars ", est_vars)
            print("np.max(est_vars) ", np.max(est_vars))
        #exit()

        moments_plot.show(None)
        moments_plot.show(file=os.path.join(self.work_dir, "{}_moments".format(self.n_moments)))
        moments_plot.reset()

    def plot_distr(self, mlmc_estimators, tol=1e-7, domain=None):

        # distr_plot = mlmc.tool.plot.ArticleDistribution(
        #     title="{} levels, {} moments".format(self.n_levels, self.n_moments))

        distr_plot = mlmc.tool.plot.ArticlePDF(
            title="{} levels, {} moments".format(self.n_levels, self.n_moments))

        ref_distr_obj = None

        for nl, estimator in mlmc_estimators.items():
            if nl == 0:
                if domain is None:
                    domain = estimator._moments_fn.domain

                ref_distr_obj = self.construct_density(estimator, tol=tol)
                distr_plot.add_distribution(ref_distr_obj, label="ref" + ", M={}".format(len(ref_distr_obj.multipliers)),
                                            color="black", linestyle=":")
            else:
                distr_obj = self.construct_density(estimator, tol=tol)

                if ref_distr_obj is not None:
                    kl_div = mlmc.tool.simple_distribution.KL_divergence(ref_distr_obj.density, distr_obj.density, *domain)
                    distr_plot.add_distribution(distr_obj, label="L={}, ".format(nl) +
                                                                 r'$D$' +
                                                                 "={:0.1e}".format(kl_div) + ", M={}".format(len(distr_obj.multipliers)))
                else:
                    distr_plot.add_distribution(distr_obj, label="L={} ".format(nl))

            if nl == 0:# and len(mlmc_estimators) == 1:
                samples = estimator.get_level_samples(level_id=0)[..., 0]
                distr_plot.add_raw_samples(np.squeeze(samples))

        distr_plot.show(None)
        distr_plot.show(file=os.path.join(self.work_dir, "pdf_cdf_{}_moments_hist".format(self.n_moments)))
        distr_plot.reset()

    def plot_distr_log(self, mlmc_estimators, tol=1e-7, domain=None):

        # distr_plot = mlmc.tool.plot.ArticleDistribution(
        #     title="{} levels, {} moments".format(self.n_levels, self.n_moments))

        distr_plot = mlmc.tool.plot.ArticlePDF(
            title="{} levels, {} moments".format(self.n_levels, self.n_moments))

        ref_distr_obj = None

        for nl, estimator in mlmc_estimators.items():
            if nl == 0:
                if domain is None:
                    domain = estimator._moments_fn.domain

                ref_distr_obj = self.construct_density(estimator, tol=tol)
                distr_plot.add_distribution_log(ref_distr_obj, label="MC", color="black", linestyle=":")
            else:
                distr_obj = self.construct_density(estimator, tol=tol)

                print("domain ", domain)

                # domain = [0.01, domain[1]]
                if ref_distr_obj is not None:
                    kl_div = mlmc.tool.simple_distribution.KL_divergence_log(ref_distr_obj.density_exp, distr_obj.density_exp, *domain)
                    distr_plot.add_distribution_log(distr_obj, label="L={}, ".format(nl) +
                                                                 r'$D$' + "={:0.1e}".format(kl_div) +
                                                                     ", M={}".format(len(distr_obj.multipliers)))
                else:
                    distr_plot.add_distribution(distr_obj, label="L={} ".format(nl))

            if nl == 0:# and len(mlmc_estimators) == 1:
                samples = estimator.get_level_samples(level_id=0)[..., 0]
                #distr_plot.add_raw_samples(np.squeeze(samples))
                distr_plot.add_raw_samples_log(np.squeeze(samples))

        distr_plot.show(None)
        distr_plot.show(file=os.path.join(self.work_dir, "pdf_cdf_{}_moments_hist".format(self.n_moments)))
        distr_plot.reset()

    def get_largest_domain(self, n_levels):
        true_domains = []
        for nl in n_levels:
            hdf_n = nl
            if nl == 0:
                hdf_n = 1
            sample_storage = SampleStorageHDF(file_path=os.path.join(self.work_dir, "L{}/mlmc_{}.hdf5".format(nl, hdf_n)))
            sample_storage.chunk_size = 1e8
            result_format = sample_storage.load_result_format()
            root_quantity = make_root_quantity(sample_storage, result_format)

            conductivity = root_quantity['conductivity']
            time = conductivity[1]  # times: [1]
            location = time['0']  # locations: ['0']
            q_value = location[0, 0]

            # length = root_quantity['length']
            # time = length[1]
            # location = time['10']
            # q_value = location[0]

            # @TODO: How to estimate true_domain?
            quantile = 0.001
            domain = mlmc.estimator.Estimate.estimate_domain(q_value, sample_storage, quantile=quantile)
            #print("domain ", domain)

            true_domains.append([domain[0], domain[1]])

            # print("sample_storage.get_n_ops() ", sample_storage.get_n_ops())
            # print("level parsm ", sample_storage.get_level_parameters())
            #
            # print("n ops ", np.array(sample_storage.get_n_ops())[:, 0] /np.array(sample_storage.get_n_ops())[:, 1])
            # print("n collected ", sample_storage.get_n_collected())
            # total_time = np.array(sample_storage.get_n_ops())[:, 0] /np.array(sample_storage.get_n_ops())[:, 1]\
            #              * np.array(sample_storage.get_n_collected())
            # print("nl: {}, time: {}".format(nl, np.sum(total_time)))

            # if domain[0] < true_domain[0]:
            #     true_domain[0] = domain[0]
            #
            # if domain[1] > true_domain[1]:
            #     true_domain[1] = domain[1]

        true_domains = np.array(true_domains)

        print("true domains ", true_domains)

        true_domain = [np.min(true_domains[:, 0]), np.max(true_domains[:, 1])]
        #true_domain = [np.max(true_domains[:, 0]), np.min(true_domains[:, 1])]
        #true_domain = [np.mean(true_domains[:, 0]), np.mean(true_domains[:, 1])]
        print("true domain ", true_domain)
        return true_domain

    def create_estimator(self, nl, true_domain=None):
        hdf_n = nl
        if nl == 0:
            hdf_n = 1
        sample_storage = SampleStorageHDF(file_path=os.path.join(self.work_dir, "L{}/mlmc_{}.hdf5".format(nl, hdf_n)))
        sample_storage.chunk_size = 1e8
        result_format = sample_storage.load_result_format()
        root_quantity = make_root_quantity(sample_storage, result_format)

        conductivity = root_quantity['conductivity']
        time = conductivity[1]  # times: [1]
        location = time['0']  # locations: ['0']
        q_value = location[0, 0]

        # length = root_quantity['length']
        # time = length[1]
        # location = time['10']
        # q_value = location[0]

        # @TODO: How to estimate true_domain?
        quantile = 0.001
        if true_domain is None:
            true_domain = mlmc.estimator.Estimate.estimate_domain(q_value, sample_storage, quantile=quantile)

        #moments_fn = Monomial(self.n_moments, true_domain)
        moments_fn = Legendre(self.n_moments, true_domain)

        return mlmc.estimator.Estimate(quantity=q_value, sample_storage=sample_storage, moments_fn=moments_fn)

    # def process(self):
    #     estimator = self.create_estimator(self.n_levels)
    #     means, vars = estimator.estimate_moments(estimator._moments_fn)
    #
    #     moments_quantity = moments(estimator.quantity, moments_fn=estimator._moments_fn, mom_at_bottom=True)
    #     moments_mean = estimate_mean(moments_quantity)
    #     assert moments_mean.mean[0] == 1
    #
    #     # true_domain = [-10, 10]  # keep all values on the original domain
    #     # central_moments = Monomial(self.n_moments, true_domain, ref_domain=true_domain, mean=means())
    #     # central_moments_quantity = moments(root_quantity, moments_fn=central_moments, mom_at_bottom=True)
    #     # central_moments_mean = estimate_mean(central_moments_quantity)
    #
    #     #estimator.sub_subselect(sample_vector=[10000])
    #
    #     #self.process_target_var(estimator)
    #
    #     # distr_plot = mlmc.tool.plot.Distribution(title="{} levels, {} moments".format(self.n_levels, self.n_moments))
    #
    #     self.plot_distr({self.n_levels: estimator}, tol=1e-8)
    #
    #     self.data_plots(estimator)

    def data_plots(self, estimator):
        estimator.fine_coarse_violinplot()

    def process_target_var(self, estimator):
        n0, nL = 100, 3
        n_samples = np.round(np.exp2(np.linspace(np.log2(n0), np.log2(nL), self.n_levels))).astype(int)

        n_estimated = estimator.bs_target_var_n_estimated(target_var=1e-5, sample_vec=n_samples)  # number of estimated sampels for given target variance
        estimator.plot_variances(sample_vec=n_estimated)
        estimator.plot_bs_var_log(sample_vec=n_estimated)

    def construct_density(self, estimator, tol=1e-7, reg_param=0.0):
        """
        Construct approximation of the density using given moment functions.
        :param estimator: mlmc.estimator.Estimate instance, it contains quantity for which the density is reconstructed
        :param tol: Tolerance of the fitting problem, with account for variances in moments.
                    Default value 1.95 corresponds to the two tail confidence 0.95.
        :param reg_param: regularization parameter
        :return: None
        """
        distr_obj, result, _, _ = estimator.construct_density(tol=tol, reg_param=reg_param)
        return distr_obj

    def run(self, renew=False):
        """
        Run MLMC
        :param renew: If True then rerun failed samples with same sample id
        :return: None
        """
        # Create working directory if necessary
        os.makedirs(self.work_dir, mode=0o775, exist_ok=True)

        if self.clean:
            # Remove HFD5 file
            if os.path.exists(os.path.join(self.work_dir, "mlmc_{}.hdf5".format(self.n_levels))):
                os.remove(os.path.join(self.work_dir, "mlmc_{}.hdf5".format(self.n_levels)))

        # Create sampler (mlmc.Sampler instance) - crucial class which actually schedule samples
        sampler = self.setup_config(clean=True)
        # Schedule samples
        self.generate_jobs(sampler, n_samples=None, renew=renew, target_var=1e-5)
        #self.generate_jobs(sampler, n_samples=[500, 500], renew=renew, target_var=1e-5)
        self.all_collect(sampler)  # Check if all samples are finished
        self.calculate_moments(sampler)  # Simple moment check

    def setup_config(self, clean):
        """
        Simulation dependent configuration
        :param clean: bool, If True remove existing files
        :return: mlmc.sampler instance
        """
        # Set pbs config, flow123d, gmsh, ..., random fields are set in simulation class
        self.set_environment_variables()

        # Create Pbs sampling pool
        sampling_pool = self.create_sampling_pool()

        simulation_config = {
            'work_dir': self.work_dir,
            'env': dict(flow123d=self.flow123d, gmsh=self.gmsh, gmsh_version=1),  # The Environment.
            'yaml_file': os.path.join(self.work_dir, '01_conductivity.yaml'),
            'geo_file': os.path.join(self.work_dir, 'square_1x1.geo'),
            'fields_params': dict(model='exp', sigma=4, corr_length=0.1),
            'field_template': "!FieldElementwise {mesh_data_file: \"$INPUT_DIR$/%s\", field_name: %s}"
        }

        # Create simulation factory
        simulation_factory = FlowSim(config=simulation_config, clean=clean)

        # Create HDF sample storage
        sample_storage = SampleStorageHDF(
            file_path=os.path.join(self.work_dir, "mlmc_{}.hdf5".format(self.n_levels)),
            #append=self.append
        )

        # Create sampler, it manages sample scheduling and so on
        sampler = Sampler(sample_storage=sample_storage, sampling_pool=sampling_pool, sim_factory=simulation_factory,
                          level_parameters=self.level_parameters)

        return sampler

    def set_environment_variables(self):
        """
        Set pbs config, flow123d, gmsh
        :return: None
        """
        root_dir = os.path.abspath(self.work_dir)
        while root_dir != '/':
            root_dir, tail = os.path.split(root_dir)

        if tail == 'storage' or tail == 'auto':
            # Metacentrum
            self.sample_sleep = 30
            self.init_sample_timeout = 600
            self.sample_timeout = 0
            self.flow123d = 'flow123d'  # "/storage/praha1/home/jan_brezina/local/flow123d_2.2.0/flow123d"
            self.gmsh = "/storage/liberec3-tul/home/martin_spetlik/astra/gmsh/bin/gmsh"
        else:
            # Local
            self.sample_sleep = 1
            self.init_sample_timeout = 60
            self.sample_timeout = 60
            self.flow123d = "/home/jb/workspace/flow123d/bin/fterm flow123d dbg"
            self.gmsh = "/home/martin/gmsh/bin/gmsh"

    def create_sampling_pool(self):
        """
        Initialize sampling pool, object which
        :return: None
        """
        if not self.use_pbs:
            return OneProcessPool(work_dir=self.work_dir, debug=self.debug)  # Everything runs in one process

        # Create PBS sampling pool
        sampling_pool = SamplingPoolPBS(work_dir=self.work_dir, debug=self.debug)

        pbs_config = dict(
            n_cores=1,
            n_nodes=1,
            select_flags=['cgroups=cpuacct'],
            mem='4Gb',
            queue='charon',
            pbs_name='flow123d',
            walltime='1:00:00',
            optional_pbs_requests=[],  # e.g. ['#PBS -m ae', ...]
            home_dir='/storage/liberec3-tul/home/martin_spetlik/',
            python='python3',
            env_setting=['cd $MLMC_WORKDIR',
                         'module load python36-modules-gcc',
                         'source env/bin/activate',
                         'pip3 install /storage/liberec3-tul/home/martin_spetlik/MLMC_new_design',
                         'module use /storage/praha1/home/jan-hybs/modules',
                         'module load python36-modules-gcc',
                         'module load flow123d',
                         'module list']
        )

        sampling_pool.pbs_common_setting(flow_3=True, **pbs_config)

        return sampling_pool

    def generate_jobs(self, sampler, n_samples=None, renew=False, target_var=None):
        """
        Generate level samples
        :param n_samples: None or list, number of samples for each level
        :param renew: rerun failed samples with same random seed (= same sample id)
        :return: None
        """
        if renew:
            sampler.ask_sampling_pool_for_samples()
            sampler.renew_failed_samples()
            sampler.ask_sampling_pool_for_samples(sleep=self.sample_sleep, timeout=self.sample_timeout)
        else:
            if n_samples is not None:
                sampler.set_initial_n_samples(n_samples)
            else:
                sampler.set_initial_n_samples()
            sampler.schedule_samples()
            sampler.ask_sampling_pool_for_samples(sleep=self.sample_sleep, timeout=self.sample_timeout)

            if target_var is not None:
                start_time = time.time()
                self.all_collect(sampler)

                moments_fn = self.set_moments(sampler._sample_storage)

                q_estimator = QuantityEstimate(sample_storage=sampler._sample_storage, moments_fn=moments_fn,
                                               sim_steps=self.level_parameters)

                target_var = 1e-5
                sleep = 0
                add_coef = 0.1

                # @TODO: test
                # New estimation according to already finished samples
                variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
                n_estimated = estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
                                                                                   n_levels=sampler.n_levels)

                # Loop until number of estimated samples is greater than the number of scheduled samples
                while not sampler.process_adding_samples(n_estimated, sleep, add_coef):
                    with open(os.path.join(self.work_dir, "sampling_info.txt"), "a") as writer:
                        n_target_str = ",".join([str(n_target) for n_target in sampler._n_target_samples])
                        n_scheduled_str = ",".join([str(n_scheduled) for n_scheduled in sampler._n_scheduled_samples])
                        n_estimated_str = ",".join([str(n_est) for n_est in n_estimated])
                        variances_str = ",".join([str(vars) for vars in variances])
                        n_ops_str = ",".join([str(n_o) for n_o in n_ops])

                        writer.write("{}; {}; {}; {}; {}; {}\n".format(n_target_str, n_scheduled_str,
                                                                   n_estimated_str, variances_str,
                                                                   n_ops_str, str(time.time() - start_time)))

                    # New estimation according to already finished samples
                    variances, n_ops = q_estimator.estimate_diff_vars_regression(sampler._n_scheduled_samples)
                    n_estimated = estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
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
            running += sampler.ask_sampling_pool_for_samples(sleep=self.sample_sleep, timeout=0.1)
            print("N running: ", running)

    @staticmethod
    def determine_level_parameters(n_levels, step_range):
        """
        Determine level parameters,
        In this case, a step of fine simulation at each level
        :param n_levels: number of MLMC levels
        :param step_range: simulation step range
        :return: List
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

    @staticmethod
    def determine_n_samples(n_levels, n_samples=None):
        """
        Set target number of samples for each level
        :param n_levels: number of levels
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
            n_samples = np.round(np.exp2(np.linspace(np.log2(n0), np.log2(nL), n_levels))).astype(int)

        return n_samples


if __name__ == "__main__":
    ProcessSimple()

    # import cProfile
    # import pstats
    # pr = cProfile.Profile()
    # pr.enable()
    #
    # my_result = ProcessSimple()
    #
    # pr.disable()
    # ps = pstats.Stats(pr).sort_stats('cumtime')
    # ps.print_stats()
