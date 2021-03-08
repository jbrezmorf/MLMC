import os
import random
import matplotlib.pyplot as plt
from scipy.stats import ks_2samp
from mlmc.tool import plot
import mlmc.tool.simple_distribution
import mlmc.estimator
import mlmc.quantity_estimate as qe
from mlmc.sample_storage import Memory
from mlmc.quantity_spec import QuantitySpec, ChunkSpec
import numpy as np
from mlmc.sample_storage_hdf import SampleStorageHDF
from mlmc.moments import Legendre, Monomial
from mlmc.quantity import make_root_quantity
import mlmc.tool.simple_distribution


def plot_loss(train_loss, val_loss):
    plt.plot(train_loss, label='loss')
    plt.plot(val_loss, label='val_loss')
    #plt.ylim([0, 10])
    plt.yscale("log")
    plt.xlabel('Epoch')
    plt.ylabel('Error')
    plt.legend()
    plt.grid(True)
    plt.show()


def analyze_results(target, predictions):
    #statistics, pvalue = ks_2samp(target, predictions)

    print("Target mean: {}, var: {}, Q25: {}, Q50: {}, Q75: {}".format(np.mean(target),
                                                                       np.var(target),
                                                                       np.quantile(target, 0.25),
                                                                       np.quantile(target, 0.5),
                                                                       np.quantile(target, 0.75)))
    print("Predic mean: {}, var: {}, Q25: {}, Q50: {}, Q75: {}".format(np.mean(predictions),
                                                                       np.var(predictions),
                                                                       np.quantile(predictions, 0.25),
                                                                       np.quantile(predictions, 0.5),
                                                                       np.quantile(predictions, 0.75)))

    #print("KS statistics: {}, pvalue: {}".format(statistics, pvalue))
    # The closer KS statistic is to 0 the more likely it is that the two samples were drawn from the same distribution

    plt.hist(target,  alpha=0.5, label='target', density=True)
    plt.hist(predictions, alpha=0.5, label='predictions', density=True)
    plt.legend(loc='upper right')
    plt.show()


def estimate_density(values, title="Density"):
    sample_storage = Memory()
    n_levels = 1
    n_moments = 25
    distr_accuracy = 1e-7

    distr_plot = plot.Distribution(title=title,
                                   log_density=True)

    result_format = [QuantitySpec(name="flow", unit="m", shape=(1,), times=[0], locations=['0'])]

    sample_storage.save_global_data(result_format=result_format, level_parameters=np.ones(n_levels))

    successful_samples = {}
    failed_samples = {}
    n_ops = {}
    n_successful = len(values)
    for l_id in range(n_levels):
        sizes = []
        for quantity_spec in result_format:
            sizes.append(np.prod(quantity_spec.shape) * len(quantity_spec.times) * len(quantity_spec.locations))

        # Dict[level_id, List[Tuple[sample_id:str, Tuple[fine_result: ndarray, coarse_result: ndarray]]]]
        successful_samples[l_id] = []
        for sample_id in range(len(values)):
            successful_samples[l_id].append((str(sample_id), (values[sample_id], 0)))

        n_ops[l_id] = [random.random(), n_successful]

        sample_storage.save_scheduled_samples(l_id, samples=["S{:07d}".format(i) for i in range(n_successful)])

    sample_storage.save_samples(successful_samples, failed_samples)
    sample_storage.save_n_ops(list(n_ops.items()))

    quantity = make_root_quantity(storage=sample_storage, q_specs=result_format)
    length = quantity['flow']
    time = length[0]
    location = time['0']
    value_quantity = location[0]

    quantile = 0.001
    true_domain = mlmc.estimator.Estimate.estimate_domain(value_quantity, sample_storage, quantile=quantile)
    moments_fn = Legendre(n_moments, true_domain)

    estimator = mlmc.estimator.Estimate(quantity=value_quantity, sample_storage=sample_storage, moments_fn=moments_fn)

    reg_param = 0
    target_var = 1e-4
    distr_obj, info, result, moments_fn = estimator.construct_density(
        tol=distr_accuracy,
        reg_param=reg_param,
        orth_moments_tol=target_var)

    samples = value_quantity.samples(ChunkSpec(level_id=0, n_samples=sample_storage.get_n_collected()[0]))[..., 0]

    distr_plot.add_raw_samples(np.squeeze(samples))

    distr_plot.add_distribution(distr_obj, label="")

    # kl = mlmc.tool.simple_distribution.KL_divergence(self.cut_distr.pdf, distr_obj.density,
    #                                                  self.cut_distr.domain[0], self.cut_distr.domain[1])
    #kl_divergences.append(kl)

    distr_plot.show(file=None)


    return estimator.estimate_moments()


def create_quantity(target, predictions):
    sample_storage = Memory()
    n_levels = 2

    result_format = [QuantitySpec(name="conductivity", unit="m", shape=(1, 1), times=[1], locations=['0'])]

    sample_storage.save_global_data(result_format=result_format, level_parameters=np.ones(n_levels))

    successful_samples = {}
    failed_samples = {}
    n_ops = {}
    n_successful = len(target)
    for l_id in range(n_levels):
        sizes = []
        for quantity_spec in result_format:
            sizes.append(np.prod(quantity_spec.shape) * len(quantity_spec.times) * len(quantity_spec.locations))

        successful_samples[l_id] = []
        for sample_id in range(n_successful):
            if l_id == 0:
                fine_result = predictions[sample_id]
                coarse_result = (np.zeros((np.sum(sizes),)))
            else:
                fine_result = target[sample_id]
                coarse_result = predictions[sample_id]

            successful_samples[l_id].append((str(sample_id), (fine_result, coarse_result)))

        n_ops[l_id] = [random.random(), n_successful]
        sample_storage.save_scheduled_samples(l_id, samples=["S{:07d}".format(i) for i in range(n_successful)])

    sample_storage.save_samples(successful_samples, failed_samples)
    sample_storage.save_n_ops(list(n_ops.items()))

    quantity = make_root_quantity(storage=sample_storage, q_specs=result_format)
    length = quantity['flow']
    time = length[0]
    location = time['0']
    value_quantity = location[0]

    return value_quantity, sample_storage


def diff_moments(target, predictions):
    n_moments = 25
    quantity, target_sample_storage = create_quantity(target, predictions)

    quantile = 0.001
    true_domain = mlmc.estimator.Estimate.estimate_domain(quantity, target_sample_storage, quantile=quantile)

    moments_fn = Legendre(n_moments, true_domain)

    quantity_moments = qe.moments(quantity, moments_fn)


    moments_mean = qe.estimate_mean(quantity_moments)

    print("moments l means ", moments_mean.l_means)
    print("moments l vars ", moments_mean.l_vars)

    print("np.max values mean l vars ", np.max(moments_mean.l_vars, axis=1))

    print("moments mean ", moments_mean.mean)
    print("moments var ", moments_mean.var)


def create_quantity_mlmc(data, level_parameters=None):
    sample_storage = Memory()
    n_levels = len(data)

    result_format = [QuantitySpec(name="conductivity", unit="m", shape=(1, 1), times=[1], locations=['0'])]

    if level_parameters is None:
        level_parameters = np.ones(n_levels)

    sample_storage.save_global_data(result_format=result_format, level_parameters=level_parameters)

    successful_samples = {}
    failed_samples = {}
    n_ops = {}
    n_successful = 15
    sizes = []
    for l_id in range(n_levels):
        n_successful = data[l_id].shape[1]
        sizes = []
        for quantity_spec in result_format:
            sizes.append(np.prod(quantity_spec.shape) * len(quantity_spec.times) * len(quantity_spec.locations))

        # Dict[level_id, List[Tuple[sample_id:str, Tuple[fine_result: ndarray, coarse_result: ndarray]]]]
        successful_samples[l_id] = []
        for sample_id in range(n_successful):

            fine_result = data[l_id][:, sample_id, 0]
            if l_id == 0:
                coarse_result = (np.zeros((np.sum(sizes),)))
            else:
                coarse_result = data[l_id][:, sample_id, 1]
            successful_samples[l_id].append((str(sample_id), (fine_result, coarse_result)))

        n_ops[l_id] = [random.random(), n_successful]

        sample_storage.save_scheduled_samples(l_id, samples=["S{:07d}".format(i) for i in range(n_successful)])

    sample_storage.save_samples(successful_samples, failed_samples)
    sample_storage.save_n_ops(list(n_ops.items()))

    return sample_storage


def estimate_moments(sample_storage, true_domain=None):
    n_moments = 25
    result_format = sample_storage.load_result_format()
    root_quantity = make_root_quantity(sample_storage, result_format)

    conductivity = root_quantity['conductivity']
    time = conductivity[1]  # times: [1]
    location = time['0']  # locations: ['0']
    q_value = location[0, 0]

    if true_domain is None:
        quantile = 0.001
        true_domain = mlmc.estimator.Estimate.estimate_domain(q_value, sample_storage, quantile=quantile)
    print("true domain ", true_domain)
    moments_fn = Legendre(n_moments, true_domain)

    estimator = mlmc.estimator.Estimate(quantity=q_value, sample_storage=sample_storage, moments_fn=moments_fn)
    #means, vars = estimator.estimate_moments(moments_fn)

    moments_mean = qe.estimate_mean(qe.moments(q_value, moments_fn))
    return moments_mean, estimator, true_domain, q_value


def ref_storage(mlmc_file):
    sample_storage = SampleStorageHDF(file_path=mlmc_file)
    return sample_storage


def get_largest_domain(storages):
    true_domains = []
    for storage in storages:
        result_format = storage.load_result_format()
        root_quantity = make_root_quantity(storage, result_format)

        conductivity = root_quantity['conductivity']
        time = conductivity[1]  # times: [1]
        location = time['0']  # locations: ['0']
        q_value = location[0, 0]

        # @TODO: How to estimate true_domain?
        quantile = 0.001
        domain = mlmc.estimator.Estimate.estimate_domain(q_value, storage, quantile=quantile)
        print("domain ", domain)

        true_domains.append([domain[0], domain[1]])

    true_domains = np.array(true_domains)

    print("true domains ", true_domains)
    true_domain = [np.min(true_domains[:, 0]), np.max(true_domains[:, 1])]
    #true_domain = [np.max(true_domains[:, 0]), np.min(true_domains[:, 1])]
    #true_domain = [np.mean(true_domains[:, 0]), np.mean(true_domains[:, 1])]
    print("true domain ", true_domain)

    #true_domain = true_domain[-1]

    return true_domain


def compare_moments(original_q_estimator, predict_q_estimator, ref_estimator):
    original_q_estimator.estimate_moments()
    orig_moments_mean = original_q_estimator.moments_mean

    predict_q_estimator.estimate_moments()
    predict_moments_mean = predict_q_estimator.moments_mean

    ref_estimator.estimate_moments()
    ref_moments_mean = ref_estimator.moments_mean

    print("ref moments mean ", ref_moments_mean.mean)
    print("orig moments mean ", orig_moments_mean.mean)
    print("predict moments mean ", predict_moments_mean.mean)

    print("ref orig mean SSE ", np.sum((ref_moments_mean.mean - orig_moments_mean.mean)**2))
    print("ref predict mean SSE ", np.sum((ref_moments_mean.mean - predict_moments_mean.mean) ** 2))

    print("ref orig mean SE ", np.sum(np.abs((ref_moments_mean.mean - orig_moments_mean.mean))))
    print("ref predict mean SE ", np.sum(np.abs((ref_moments_mean.mean - predict_moments_mean.mean))))

    print("ref moments var ", ref_moments_mean.var)
    print("orig moments var ", orig_moments_mean.var)
    print("predict moments var ", predict_moments_mean.var)

    print("ref orig var SSE ", np.sum((ref_moments_mean.var - orig_moments_mean.var) ** 2))
    print("ref predict var SSE ", np.sum((ref_moments_mean.var - predict_moments_mean.var) ** 2))

    print("ref orig var SE ", np.sum(np.abs((ref_moments_mean.var - orig_moments_mean.var))))
    print("ref predict var SE ", np.sum(np.abs((ref_moments_mean.var - predict_moments_mean.var))))


def compare_densities(estimator_1, estimator_2, ref_estimator, label_1="", label_2=""):

    distr_plot = plot.ArticleDistribution(title="densities", log_density=True)
    tol = 1e-10
    reg_param = 0

    distr_obj_1, result, _, _ = estimator_1.construct_density(tol=tol, reg_param=reg_param)
    #distr_plot.add_distribution(distr_obj_1, label=label_1, color="blue")

    distr_obj_2, result, _, _ = estimator_2.construct_density(tol=tol, reg_param=reg_param)
    #distr_plot.add_distribution(distr_obj_2, label=label_2, color="red", line_style="--")

    ref_distr_obj, result, _, _ = ref_estimator.construct_density(tol=tol, reg_param=reg_param)
    #distr_plot.add_distribution(ref_distr_obj, label="MC reference", color="black", line_style=":")

    kl_div_ref_mlmc = mlmc.tool.simple_distribution.KL_divergence(ref_distr_obj.density, distr_obj_1.density, ref_distr_obj.domain[0], ref_distr_obj.domain[1])

    print("KL div ref|mlmc: {}".format(kl_div_ref_mlmc))

    # domain = [np.min([ref_distr_obj.domain[0], distr_obj_2.domain[0]]),
    #           np.max([ref_distr_obj.domain[1], distr_obj_2.domain[1]])]
    kl_div_ref_gnn = mlmc.tool.simple_distribution.KL_divergence(ref_distr_obj.density, distr_obj_2.density, ref_distr_obj.domain[0],
                                                         ref_distr_obj.domain[1])

    print("KL div ref|mlmc prediction: {}".format(kl_div_ref_gnn))

    distr_plot.add_distribution(distr_obj_1, label=label_1 + ", KL(ref|orig):{:0.4g}".format(kl_div_ref_mlmc), color="blue")
    distr_plot.add_distribution(distr_obj_2, label=label_2 + ", KL(ref|gnn):{:0.4g}".format(kl_div_ref_gnn), color="red", line_style="--")
    distr_plot.add_distribution(ref_distr_obj, label="MC reference", color="black", line_style=":")

    distr_plot.show(file=None)


def get_quantity_estimator(sample_storage, true_domain=None):
    n_moments = 25
    result_format = sample_storage.load_result_format()
    root_quantity = make_root_quantity(sample_storage, result_format)
    conductivity = root_quantity['conductivity']
    time = conductivity[1]  # times: [1]
    location = time['0']  # locations: ['0']
    quantity = location[0, 0]

    if true_domain is None:
        quantile = 0.001
        true_domain = mlmc.estimator.Estimate.estimate_domain(quantity, sample_storage, quantile=quantile)

    moments_fn = Legendre(n_moments, true_domain)

    return mlmc.estimator.Estimate(quantity=quantity, sample_storage=sample_storage, moments_fn=moments_fn)


def process_mlmc(mlmc_file, sampling_info_path, ref_mlmc_file, targets, predictions, train_targets, val_targets, l_0_targets=None, l_0_predictions=None,
                 l1_sample_time=None, l0_sample_time=None):
    n_levels = 5
    #mlmc_file = "/home/martin/Documents/metamodels/data/cl_0_3_s_4/L5/mlmc_5.hdf5"
    # mlmc_file = "/home/martin/Documents/metamodels/data/1000_ele/cl_0_1_s_1/L5/mlmc_5.hdf5"
    # sampling_info_path = "/home/martin/Documents/metamodels/data/1000_ele/cl_0_1_s_1/sampling_info"

    level_zero = False

    sample_storage = SampleStorageHDF(file_path=mlmc_file)
    original_moments, estimator, original_true_domain, _ = estimate_moments(sample_storage)

    # Test storage creation
    data = []
    for l_id in range(n_levels):
        level_samples = estimator.get_level_samples(level_id=l_id)
        data.append(level_samples)
    sample_storage_2 = create_quantity_mlmc(data)
    moments_2, estimator_2, _, _ = estimate_moments(sample_storage_2)
    assert np.allclose(original_moments.mean, moments_2.mean)
    assert np.allclose(original_moments.var, moments_2.var)

    print("moments_2.l_vars max ", np.max(moments_2.l_vars, axis=1))

    n_ops, field_times, flow_times = get_sample_times(sampling_info_path)

    n_collected_times = n_ops * np.array(sample_storage_2.get_n_collected())
    # print("n collected times ", n_collected_times)
    # print("total time ", np.sum(n_collected_times))
    # print("n ops ", n_ops)
    # print("field_times ", field_times)
    # print("flow_times ", flow_times)
    # exit()

    n_ops_predict = [l0_sample_time + field_times[0], n_ops[0] + l1_sample_time, *n_ops[1:]]

    print("n ops ", n_ops)
    print("n ops predict ", n_ops_predict)

    # # Use train and test data without validation data
    # data = []
    # for l_id in range(n_levels):
    #     level_samples = estimator.get_level_samples(level_id=l_id)
    #     if l_id == 0:
    #         level_samples = np.concatenate((train_targets.reshape(1, len(train_targets), 1),
    #                                         targets.reshape(1, len(targets), 1)), axis=1)
    #     data.append(level_samples)
    # sample_storage_nn = create_quantity_mlmc(data)
    # moments_nn, estimator_nn, _, _ = estimate_moments(sample_storage_nn, true_domain=original_true_domain)

    if level_zero is True:
        n_lev = n_levels
        n_ops_predict = [l0_sample_time + field_times[0], *n_ops[1:]]
        level_params = sample_storage.get_level_parameters()
    else:
        n_lev = n_levels + 1
        level_params = [sample_storage.get_level_parameters()[0], *sample_storage.get_level_parameters()]

    # Use predicted data as zero level results and level one coarse results

    if l_0_targets is not None and l_0_predictions is not None:
        data = []
        for l_id in range(n_lev):
            if l_id == 0:
                level_samples = l_0_predictions.reshape(1, len(l_0_predictions), 1)
                #level_samples = level_samples[:, :100000, :]
            else:
                if level_zero is True:
                    level_id = l_id
                    level_samples = estimator.get_level_samples(level_id=level_id)
                else:
                    level_id = l_id - 1
                    level_samples = estimator.get_level_samples(level_id=level_id)
                    if l_id == 1:
                        coarse_level_samples = predictions.reshape(1, len(predictions), 1)
                        fine_level_samples = targets.reshape(1, len(targets), 1)
                        level_samples = np.concatenate((fine_level_samples, coarse_level_samples), axis=2)



            data.append(level_samples)

        # n0 = 100
        # nL = 10
        # num_levels = n_levels + 1
        # initial_n_samples = np.round(np.exp2(np.linspace(np.log2(n0), np.log2(nL), num_levels))).astype(int)
        # if len(initial_n_samples) == len(data):
        #     for i in range(len(data)):
        #         print(data[i].shape)
        #         data[i] = data[i][:, :initial_n_samples[i], :]
        #         print("data[i].shape ", data[i].shape)

        #level_params = [sample_storage.get_level_parameters()[0], *sample_storage.get_level_parameters()]
        sample_storage_predict = create_quantity_mlmc(data, level_parameters=level_params)

        moments_predict, estimator_predict, _, quantity = estimate_moments(sample_storage_predict, true_domain=original_true_domain)
        target_var = 1e-5

        #n_level_samples = initial_n_samples #sample_storage_predict.get_n_collected()
        n_level_samples = sample_storage_predict.get_n_collected()
        # custom_n_ops = [sample_storage.get_n_ops()[0], *sample_storage.get_n_ops()]
        # print("custom n ops ", custom_n_ops)

        print("n level samples ", n_level_samples)

        # @TODO: test
        # New estimation according to already finished samples
        variances, n_ops = estimator_predict.estimate_diff_vars_regression(n_level_samples)
        #print("variances ", variances)
        print("level max var ", np.max(variances, axis=1))
        print("n ops ", n_ops)
        n_ops = n_ops_predict
        n_estimated = mlmc.estimator.estimate_n_samples_for_target_variance(target_var, variances, n_ops,
                                                                            n_levels=len(n_level_samples))
        print("n estimated ", n_estimated)
        print("original collected ", sample_storage_2.get_n_collected())

        est_times = n_ops_predict * np.array(n_estimated)

        print("est times ", est_times)
        print("original n collected times ", n_collected_times)
        print("total est times ", np.sum(est_times))
        print("original total collected times ", np.sum(n_collected_times))


        ref_sample_storage = ref_storage(ref_mlmc_file)
        domain = get_largest_domain([sample_storage, sample_storage_predict, ref_sample_storage])
        #domain = [0.001, 5]

        original_q_estimator = get_quantity_estimator(sample_storage, true_domain=domain)
        predict_q_estimator = get_quantity_estimator(sample_storage_predict, true_domain=domain)
        ref_estimator = get_quantity_estimator(ref_sample_storage, true_domain=domain)

        # print("means nn ", moments_nn.mean)
        # print("means_predict ", moments_predict.mean)
        #
        # print("means nn - means predict ", moments_nn.mean - moments_predict.mean)
        # print("abs means nn - means predict ", np.abs(moments_nn.mean - moments_predict.mean))
        #
        # print("vars nn ", moments_nn.var)
        # print("vars predict ", moments_predict.var)
        #
        # print("moments_nn.l_means ", moments_nn.l_means[0])
        # print("moments_predict.l_means ", moments_predict.l_means[0])
        #
        # print("moments nn n samples ", moments_nn.n_samples)
        # print("moments nn n removed samples ", moments_predict.n_rm_samples)
        # print("moments predict n samples ", moments_predict.n_samples)
        # print("moments predict n removed samples ", moments_predict.n_rm_samples)
        #
        # for l_id, (l_mom, l_mom_pred) in enumerate(zip(moments_nn.l_means, moments_predict.l_means)):
        #     print("L id: {}, mom diff: {}".format(l_id, l_mom - l_mom_pred))

        compare_moments(original_q_estimator, predict_q_estimator, ref_estimator)

        compare_densities(original_q_estimator, predict_q_estimator, ref_estimator, label_1="orig N: {}".format(moments_2.n_samples),
                          label_2="gnn N: {}".format(moments_predict.n_samples))


def analyze_mlmc_data():
    n_levels = 5
    # mlmc_file = "/home/martin/Documents/metamodels/data/cl_0_3_s_4/L5/mlmc_5.hdf5"
    mlmc_file = "/home/martin/Documents/metamodels/data/cl_0_1_s_1/L5/mlmc_5.hdf5"

    sample_storage = SampleStorageHDF(file_path=mlmc_file)
    original_moments, estimator, original_true_domain = estimate_moments(sample_storage)

    # Test storage creation
    data = []
    for l_id in range(n_levels):
        level_samples = estimator.get_level_samples(level_id=l_id)


        l_fine = np.squeeze(level_samples[..., 0])

        print("mean l_fine ", np.mean(l_fine))
        plt.hist(l_fine, alpha=0.5, label='{}'.format(l_id), density=True)
        data.append(level_samples)

    plt.legend(loc='upper right')
    plt.show()
    sample_storage_2 = create_quantity_mlmc(data)
    moments_2, estimator_2, _ = estimate_moments(sample_storage_2)
    assert np.allclose(original_moments.mean, moments_2.mean)
    assert np.allclose(original_moments.var, moments_2.var)


def get_sample_times(sampling_info_path):
    n_levels = [5]
    for nl in n_levels:
        # sampling_info_path = "/home/martin/Documents/MLMC_article/data/sampling_info"
        #sampling_info_path = "/home/martin/Documents/metamodels/data/1000_ele/sampling_info"

        variances = []
        n_ops = []
        times = []

        times_scheduled_samples = []
        running_times = []
        flow_running_times = []

        for i in range(0, 100):
            sampling_info_path_iter = os.path.join(sampling_info_path, str(i))
            if os.path.isdir(sampling_info_path_iter):
                variances.append(np.load(os.path.join(sampling_info_path_iter, "variances.npy")))
                n_ops.append(np.load(os.path.join(sampling_info_path_iter, "n_ops.npy")))
                times.append(np.load(os.path.join(sampling_info_path_iter, "time.npy")))

                running_times.append(np.load(os.path.join(sampling_info_path_iter, "running_times.npy")))
                flow_running_times.append(np.load(os.path.join(sampling_info_path_iter, "flow_running_times.npy")))
                if os.path.exists(os.path.join(sampling_info_path_iter, "scheduled_samples_time.npy")):
                    times_scheduled_samples.append(
                        np.load(os.path.join(sampling_info_path_iter, "scheduled_samples_time.npy")))
            else:
                break

        def time_for_sample_func(data):
            new_n_ops = []
            for nop in data:
                nop = np.squeeze(nop)
                if len(nop) > 0:
                    new_n_ops.append(nop[:, 0]/nop[:, 1])
            return new_n_ops

        n_ops = time_for_sample_func(n_ops)
        running_times = time_for_sample_func(running_times)
        flow_running_times = time_for_sample_func(flow_running_times)

        field_times = np.mean(np.array(running_times) - np.array(flow_running_times) - np.array(flow_running_times),
                              axis=0)

        flow_times = np.mean(np.array(flow_running_times), axis=0)
        n_ops = np.mean(n_ops, axis=0)

        return n_ops, field_times, flow_times


if __name__ == "__main__":
    analyze_mlmc_data()
